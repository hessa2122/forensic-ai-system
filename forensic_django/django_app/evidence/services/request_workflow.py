from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import log_action
from accounts.permissions import can_access_evidence, can_review_analysis_requests, is_system_admin
from accounts.services import notify_admins, notify_user
from evidence.models import AnalysisRequest


ACTIVE_STATUSES = {"pending", "approved", "processing"}
CLOSED_CASE_STATUSES = {"closed", "archived"}
ALLOWED_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled"},
    "approved": {"processing"},
    "processing": {"completed", "failed"},
}


def _transition(req, new_status):
    if req.status == new_status:
        return False
    if new_status not in ALLOWED_TRANSITIONS.get(req.status, set()):
        raise ValidationError(f"Invalid request transition: {req.status} -> {new_status}")
    req.status = new_status
    return True


def _locked_request(request_id):
    return AnalysisRequest.objects.select_for_update().select_related("evidence", "requested_by").get(pk=request_id)


def case_allows_activity(case):
    return bool(case and case.status not in CLOSED_CASE_STATUSES)


def case_allows_processing(evidence):
    case = getattr(evidence, "case", None)
    return case_allows_activity(case)


def _ensure_case_open(evidence):
    if not case_allows_processing(evidence):
        raise ValidationError("This case is closed. New analysis and reconstruction processing are disabled.")


@transaction.atomic
def submit_request(evidence, requested_by, request_type="detection", request=None):
    if request_type not in {"detection", "reconstruction"}:
        raise ValidationError("Unsupported request type.")
    if not can_access_evidence(requested_by, evidence):
        raise PermissionDenied("You cannot request analysis for this evidence.")
    _ensure_case_open(evidence)
    if AnalysisRequest.objects.select_for_update().filter(
        evidence=evidence,
        request_type=request_type,
        status__in=ACTIVE_STATUSES,
    ).exists():
        raise IntegrityError("An active request already exists for this evidence and request type.")
    req = AnalysisRequest.objects.create(
        evidence=evidence,
        requested_by=requested_by,
        request_type=request_type,
        status="pending",
    )
    log_action(requested_by, "request_submitted", target=f"AnalysisRequest #{req.id}", request=request)
    transaction.on_commit(lambda: notify_admins(
        f"{requested_by.get_username()} submitted a {request_type} request for {evidence.original_filename}.",
        "analysis" if request_type == "detection" else "reconstruction",
        req,
        title=f"User submitted {request_type} request",
        priority="high",
    ))
    return req


@transaction.atomic
def approve_request(request_id, reviewer, request=None):
    req = _locked_request(request_id)
    if not can_review_analysis_requests(reviewer):
        raise PermissionDenied("Admin access required.")
    if req.requested_by_id == reviewer.id:
        raise PermissionDenied("Requesters cannot approve their own requests.")
    changed = _transition(req, "approved")
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.rejection_reason = ""
    req.error_message = ""
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "error_message"])
    if changed:
        log_action(reviewer, "request_approved", target=f"AnalysisRequest #{req.id}", request=request)
        transaction.on_commit(lambda: notify_user(
            req.requested_by,
            f"Admin approved your {req.request_type} request for {req.evidence.original_filename}.",
            "analysis" if req.request_type == "detection" else "reconstruction",
            req,
            title=f"{req.request_type.title()} request approved",
        ))
    return req


@transaction.atomic
def reject_request(request_id, reviewer, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A rejection reason is required.")
    req = _locked_request(request_id)
    if not can_review_analysis_requests(reviewer):
        raise PermissionDenied("Admin access required.")
    if req.requested_by_id == reviewer.id:
        raise PermissionDenied("Requesters cannot reject their own requests.")
    _transition(req, "rejected")
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.rejection_reason = reason
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])
    log_action(reviewer, "request_rejected", target=f"AnalysisRequest #{req.id}", details=reason, request=request)
    transaction.on_commit(lambda: notify_user(
        req.requested_by,
        f"Admin rejected your {req.request_type} request for {req.evidence.original_filename}: {reason}",
        "analysis" if req.request_type == "detection" else "reconstruction",
        req,
        title=f"{req.request_type.title()} request rejected",
        priority="high",
    ))
    return req


@transaction.atomic
def cancel_request(request_id, actor, request=None):
    req = _locked_request(request_id)
    if req.requested_by_id != actor.id and not can_review_analysis_requests(actor):
        raise PermissionDenied("You cannot cancel this request.")
    _transition(req, "cancelled")
    req.completed_at = timezone.now()
    req.save(update_fields=["status", "completed_at"])
    log_action(actor, "request_rejected", target=f"AnalysisRequest #{req.id}", details="cancelled", request=request)
    return req


@transaction.atomic
def start_request(request_id, actor=None, request=None):
    req = _locked_request(request_id)
    if req.status == "processing":
        return req
    _ensure_case_open(req.evidence)
    _transition(req, "processing")
    req.processing_started_at = timezone.now()
    req.error_message = ""
    req.save(update_fields=["status", "processing_started_at", "error_message"])
    log_action(actor or req.reviewed_by, "analysis_run", target=f"AnalysisRequest #{req.id}", request=request)
    return req


@transaction.atomic
def complete_request(request_id, actor=None, request=None):
    req = _locked_request(request_id)
    if req.status == "completed":
        return req
    _transition(req, "completed")
    req.completed_at = timezone.now()
    req.error_message = ""
    req.save(update_fields=["status", "completed_at", "error_message"])
    log_action(actor or req.reviewed_by, "analysis_run", target=f"AnalysisRequest #{req.id}", details="completed", request=request)
    transaction.on_commit(lambda: notify_user(
        req.requested_by,
        f"{req.request_type.title()} completed for {req.evidence.original_filename}.",
        "analysis" if req.request_type == "detection" else "reconstruction",
        req,
        title=f"{req.request_type.title()} completed",
    ))
    if actor and not is_system_admin(actor):
        transaction.on_commit(lambda: notify_admins(
            f"{actor.get_username()} completed {req.request_type} processing for {req.evidence.original_filename}.",
            "analysis" if req.request_type == "detection" else "reconstruction",
            req,
            title=f"User completed {req.request_type}",
        ))
    return req


@transaction.atomic
def fail_request(request_id, error_message, actor=None, request=None):
    req = _locked_request(request_id)
    if req.status == "failed":
        return req
    _transition(req, "failed")
    req.completed_at = timezone.now()
    req.error_message = str(error_message)
    req.save(update_fields=["status", "completed_at", "error_message"])
    log_action(actor or req.reviewed_by, "analysis_run", target=f"AnalysisRequest #{req.id}", details=f"failed: {error_message}", request=request)
    transaction.on_commit(lambda: notify_user(
        req.requested_by,
        f"{req.request_type.title()} failed for {req.evidence.original_filename}: {error_message}",
        "analysis" if req.request_type == "detection" else "reconstruction",
        req,
        title=f"{req.request_type.title()} failed",
        priority="high",
    ))
    return req
