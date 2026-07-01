from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, JsonResponse


def is_system_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def is_approved_user(user):
    if not user or not user.is_authenticated:
        return False
    if is_system_admin(user):
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.is_approved)


def is_investigator(user):
    profile = getattr(user, "profile", None)
    return bool(is_approved_user(user) and profile and profile.role == "investigator")


def is_analyst(user):
    profile = getattr(user, "profile", None)
    return bool(is_approved_user(user) and profile and profile.role == "analyst")


def can_access_case(user, case):
    if is_system_admin(user):
        return True
    if not is_approved_user(user) or case is None:
        return False
    return case.assigned_to_id == user.id


def can_access_evidence(user, evidence):
    if is_system_admin(user):
        return True
    if not is_approved_user(user) or evidence is None:
        return False
    return evidence.case_id and can_access_case(user, evidence.case)


def can_manage_cases(user):
    return is_system_admin(user)


def can_review_analysis_requests(user):
    return is_system_admin(user)


def can_view_audit_logs(user):
    return is_system_admin(user)


def can_manage_services(user):
    return is_system_admin(user)


def can_manage_backups(user):
    return is_system_admin(user)


def case_access_q(user):
    if is_system_admin(user):
        return Q()
    if not is_approved_user(user):
        return Q(pk__isnull=True)
    return Q(assigned_to=user)


def evidence_access_q(user):
    if is_system_admin(user):
        return Q()
    if not is_approved_user(user):
        return Q(pk__isnull=True)
    return Q(case__assigned_to=user)


def admin_required_json(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not is_system_admin(request.user):
            return JsonResponse({"error": "Admin access required"}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def raise_404_unless(condition):
    if not condition:
        raise Http404()


def raise_403_unless(condition):
    if not condition:
        raise PermissionDenied()
