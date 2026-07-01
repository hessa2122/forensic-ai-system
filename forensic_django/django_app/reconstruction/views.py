"""
reconstruction/views.py
------------------------
Django views for the 3D scene reconstruction pipeline.

Endpoints
---------
POST /reconstruction/reconstruct/
    Trigger reconstruction for an Evidence object.

GET /reconstruction/reconstructions/
    List all SceneReconstruction records (JSON).

GET /reconstruction/reconstruction-data/<scene_id>/
    Return scene metadata + signed URLs for GLB/PLY/depth.

GET /reconstruction/<evidence_id>/
    Render the 3D viewer HTML page.

GET /reconstruction/<evidence_id>/data/
    Return the latest reconstruction data for an evidence item.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.permissions import can_access_evidence, can_review_analysis_requests, is_approved_user, is_system_admin
from accounts.services import notify_user
from evidence.models import AnalysisRequest, Evidence
from evidence.services import request_workflow
from .models import SceneReconstruction
from .scene_builder import build_scene

log = logging.getLogger(__name__)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _media_url(field) -> str | None:
    """Return absolute URL for a FileField / ImageField, or None if empty."""
    if not field:
        return None
    try:
        return field.url
    except Exception:
        return None


def _media_path(field) -> str | None:
    """Return absolute filesystem path for a FileField, or None if empty."""
    if not field:
        return None
    try:
        return field.path
    except Exception:
        return None


def _sibling_ply_url(field) -> str | None:
    path = _media_path(field)
    if not path:
        return None
    ply_path = Path(path).with_suffix(".ply")
    if not ply_path.exists():
        return None
    try:
        rel = ply_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    except ValueError:
        return None
    return settings.MEDIA_URL + rel


def _out_paths(scene_id: int) -> dict[str, str]:
    """Return filesystem paths for all scene output files."""
    base = Path(settings.MEDIA_ROOT) / "scenes"
    pc   = base / "pointclouds"
    dm   = base / "depthmaps"
    pc.mkdir(parents=True, exist_ok=True)
    dm.mkdir(parents=True, exist_ok=True)
    return {
        "glb":   str(pc / f"scene_{scene_id}.glb"),
        "ply":   str(pc / f"scene_{scene_id}.ply"),
        "depth": str(dm / f"depth_{scene_id}.png"),
    }


def _is_approved(user) -> bool:
    return is_approved_user(user)


def _permitted_evidence_queryset(user):
    qs = Evidence.objects.select_related("case", "uploaded_by")
    if is_system_admin(user):
        return qs
    return qs.filter(Q(case__assigned_to=user))


def _get_permitted_evidence(user, evidence_id: int):
    return get_object_or_404(_permitted_evidence_queryset(user), pk=evidence_id)


# ─── reconstruct ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def reconstruct_api(request):
    """
    POST body (JSON): { "request_id": <int> }
    Runs an approved reconstruction request. A direct evidence id is not sufficient.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError as exc:
        return JsonResponse({"error": f"Bad request: {exc}"}, status=400)

    if not _is_approved(request.user):
        return JsonResponse({"error": "Account pending admin approval.", "code": "account_unapproved"}, status=403)

    request_id = body.get("request_id") or body.get("analysis_request_id")
    evidence_id = body.get("evidence_id")
    request_qs = AnalysisRequest.objects.select_related("evidence", "evidence__case", "requested_by").filter(
        request_type="reconstruction",
    )
    if request_id:
        try:
            analysis_request = get_object_or_404(request_qs, pk=int(request_id))
        except (TypeError, ValueError):
            return JsonResponse({"error": "request_id must be a number."}, status=400)
    elif evidence_id:
        try:
            evidence = _get_permitted_evidence(request.user, int(evidence_id))
        except (TypeError, ValueError):
            return JsonResponse({"error": "evidence_id must be a number."}, status=400)
        analysis_request = request_qs.filter(
            evidence=evidence,
            status="approved",
        ).order_by("-requested_at").first()
        if not analysis_request:
            return JsonResponse({
                "error": "No approved reconstruction request found. Submit a 3D reconstruction request and wait for admin approval.",
                "code": "approved_request_required",
            }, status=403)
    else:
        return JsonResponse({"error": "request_id or evidence_id is required."}, status=400)

    if not is_system_admin(request.user) and analysis_request.requested_by_id != request.user.id:
        return JsonResponse({"error": "Only the requester or an admin can run this approved reconstruction request."}, status=403)
    if analysis_request.status not in {"approved", "processing"}:
        return JsonResponse({"error": "Reconstruction request must be approved before processing."}, status=403)
    evidence = analysis_request.evidence

    if not evidence.file:
        return JsonResponse({"error": "Evidence has no file attached."}, status=400)

    image_path = _media_path(evidence.file)
    if not image_path or not Path(image_path).exists():
        request_workflow.fail_request(analysis_request.id, "Evidence file is unavailable.", actor=request.user)
        return JsonResponse({"error": "Evidence file is unavailable.", "code": "evidence_file_missing"}, status=400)

    if evidence.case_id is None:
        return JsonResponse({"error": "Evidence must belong to a case before 3D reconstruction."}, status=400)

    # Re-use or create SceneReconstruction record
    try:
        analysis_request = request_workflow.start_request(analysis_request.id, actor=request.user, request=request)
    except Exception as exc:
        return JsonResponse({"error": str(exc), "code": "reconstruction_blocked"}, status=403)

    scene, _ = SceneReconstruction.objects.get_or_create(
        evidence=evidence,
        defaults={"case": evidence.case, "scene_name": evidence.original_filename or "", "analysis_request": analysis_request},
    )
    scene.analysis_request = analysis_request
    scene.success = False
    scene.error_message = ""
    scene.started_at = timezone.now()
    scene.save()

    paths = _out_paths(scene.pk)
    for output_path in paths.values():
        try:
            Path(output_path).unlink(missing_ok=True)
        except Exception:
            log.warning("Could not remove previous reconstruction output: %s", output_path)

    try:
        meta = build_scene(
            image_path = image_path,
            glb_out    = paths["glb"],
            ply_out    = paths["ply"],
            depth_out  = paths["depth"],
        )
    except Exception as exc:
        log.exception("build_scene failed for evidence %d", evidence.id)
        scene.error_message = str(exc)
        scene.completed_at = timezone.now()
        scene.save(update_fields=["error_message", "completed_at"])
        request_workflow.fail_request(analysis_request.id, str(exc), actor=request.user, request=request)
        return JsonResponse({
            "error": "Reconstruction failed on the server.",
            "code": "reconstruction_failed",
            "scene_id": scene.pk,
        }, status=500)

    # persist relative paths (relative to MEDIA_ROOT)
    media_root = Path(settings.MEDIA_ROOT)

    def _rel(p: str) -> str:
        return str(Path(p).relative_to(media_root))

    mesh_type = None
    if meta.get("glb_ok") and Path(paths["glb"]).exists():
        scene.glb_file = _rel(paths["glb"])
        mesh_type = "glb"
    if meta.get("ply_ok") and Path(paths["ply"]).exists():
        scene.ply_file = _rel(paths["ply"])
        mesh_type = mesh_type or "ply"
    if not mesh_type:
        scene.error_message = "Reconstruction finished but did not produce a GLB or PLY mesh."
        scene.success = False
        scene.save(update_fields=["error_message", "success"])
        request_workflow.fail_request(analysis_request.id, scene.error_message, actor=request.user, request=request)
        return JsonResponse({"error": scene.error_message, "scene_id": scene.pk}, status=500)

    if Path(paths["depth"]).exists():
        scene.depth_map = _rel(paths["depth"])

    scene.total_points  = meta["total_points"]
    scene.vertex_count  = int(meta.get("vertex_count", 0) or 0)
    scene.triangle_count = int(meta.get("triangle_count", 0) or 0)
    scene.num_clusters  = meta["num_clusters"]
    scene.clusters_json = meta["clusters"]
    scene.mesh_type     = mesh_type
    scene.model_name    = meta.get("model_name", "Depth Anything V2/Open3D")
    scene.model_version = meta.get("model_version", "")
    scene.parameters_json = meta.get("parameters", {})
    scene.success       = True
    scene.completed_at  = timezone.now()
    scene.save()
    request_workflow.complete_request(analysis_request.id, actor=request.user, request=request)

    mesh_url = _media_url(scene.glb_file) or _media_url(scene.ply_file)
    ply_url = _media_url(scene.ply_file)
    depth_url = _media_url(scene.depth_map)

    return JsonResponse({
        "scene_id":     scene.pk,
        "total_points": scene.total_points,
        "num_clusters": scene.num_clusters,
        "clusters":     scene.clusters_json,
        "mesh_url":     mesh_url,
        "mesh_type":    mesh_type,
        "ply_url":      ply_url,
        "depth_url":    depth_url,
        "glb_ok":       meta.get("glb_ok", False),
        "ply_ok":       meta.get("ply_ok", False),
        "success":      True,
    })


# ─── list ─────────────────────────────────────────────────────────────────────

@login_required
def reconstructions_api(request):
    """Return JSON list of all scene records (latest first)."""
    if not _is_approved(request.user):
        return JsonResponse({"error": "Account pending admin approval.", "code": "account_unapproved"}, status=403)
    scenes = SceneReconstruction.objects.select_related("evidence", "case")
    if not request.user.is_staff:
        scenes = scenes.filter(Q(case__assigned_to=request.user))
    case_id = request.GET.get("case_id")
    if case_id:
        scenes = scenes.filter(case_id=case_id)
    scenes = scenes.order_by("-created_at")[:50]
    data = []
    for s in scenes:
        mesh_url = _media_url(s.glb_file) or _media_url(s.ply_file)
        mesh_type = s.mesh_type or ("ply" if mesh_url and mesh_url.lower().endswith(".ply") else "glb")
        mesh_size_mb = 0
        mesh_path = _media_path(s.ply_file)
        if mesh_path and Path(mesh_path).exists():
            mesh_size_mb = round(Path(mesh_path).stat().st_size / 1_048_576, 2)
        data.append({
            "id":           s.pk,
            "case_id":      s.case_id,
            "evidence_id":  s.evidence_id,
            "scene_name":   s.scene_name,
            "total_points": s.total_points,
            "num_clusters": s.num_clusters,
            "success":      s.success,
            "created_at":   s.created_at.isoformat(),
            "mesh_url":     mesh_url,
            "mesh_type":    mesh_type,
            "ply_url":      mesh_url,
            "ply_size_mb":  mesh_size_mb,
        })
    return JsonResponse({"reconstructions": data})


# ─── scene data ───────────────────────────────────────────────────────────────

@login_required
def reconstruction_scene_data_api(request, scene_id: int):
    """Return metadata + file URLs for a specific scene."""
    if not _is_approved(request.user):
        return JsonResponse({"error": "Account pending admin approval.", "code": "account_unapproved"}, status=403)
    scenes = SceneReconstruction.objects.select_related("case", "evidence")
    if not request.user.is_staff:
        scenes = scenes.filter(Q(case__assigned_to=request.user))
    scene = get_object_or_404(scenes, pk=scene_id)

    mesh_url  = _media_url(scene.glb_file) or _media_url(scene.ply_file)
    depth_url = _media_url(scene.depth_map)
    ply_url = _media_url(scene.ply_file)

    # Detect whether stored file is GLB or PLY
    mesh_type = scene.mesh_type or "glb"

    return JsonResponse({
        "id":           scene.pk,
        "scene_name":   scene.scene_name,
        "total_points": scene.total_points,
        "num_clusters": scene.num_clusters,
        "vertex_count": scene.vertex_count,
        "triangle_count": scene.triangle_count,
        "clusters":     scene.clusters_json,
        "mesh_url":     mesh_url,
        "mesh_type":    mesh_type,
        "depth_url":    depth_url,
        "ply_url":      ply_url,
        "success":      scene.success,
        "error":        scene.error_message,
    })


# ─── viewer page ──────────────────────────────────────────────────────────────

@login_required
def reconstruction_view(request, evidence_id: int):
    """Render the 3D viewer template for a given evidence item."""
    if not _is_approved(request.user):
        return JsonResponse({"error": "Account pending admin approval.", "code": "account_unapproved"}, status=403)
    evidence = _get_permitted_evidence(request.user, evidence_id)
    scene = SceneReconstruction.objects.filter(
        evidence=evidence,
        success=True,
        ply_file__gt="",
    ).order_by("-created_at").first()
    active_request = evidence.analysis_requests.filter(
        request_type="reconstruction",
        status__in=["pending", "approved", "processing"],
    ).order_by("-requested_at").first()
    case_allows_processing = request_workflow.case_allows_processing(evidence)

    mesh_url  = None
    mesh_type = "glb"
    ply_url   = None
    depth_url = None
    clusters  = []

    if scene and scene.success:
        mesh_url  = _media_url(scene.glb_file) or _media_url(scene.ply_file)
        ply_url   = _media_url(scene.ply_file)
        depth_url = _media_url(scene.depth_map)
        clusters  = scene.clusters_json or []
        mesh_type = scene.mesh_type or ("ply" if mesh_url and mesh_url.lower().endswith(".ply") else "glb")

    return render(request, "reconstruction/viewer.html", {
        "evidence":   evidence,
        "scene":      scene,
        "active_request": active_request,
        "can_run_reconstruction": bool(
            case_allows_processing
            and
            active_request
            and active_request.status == "approved"
            and (is_system_admin(request.user) or active_request.requested_by_id == request.user.id)
        ),
        "can_submit_reconstruction_request": bool(case_allows_processing and not active_request),
        "case_allows_processing": case_allows_processing,
        "mesh_url":   mesh_url,
        "mesh_type":  mesh_type,
        "ply_url":    ply_url,
        "depth_url":  depth_url,
        "clusters":   clusters,
        "scene_id":   scene.pk if scene else None,
    })


# ─── evidence data shortcut ───────────────────────────────────────────────────

@login_required
def reconstruction_data_api(request, evidence_id: int):
    """Return the latest reconstruction data for a given evidence item."""
    if not _is_approved(request.user):
        return JsonResponse({"error": "Account pending admin approval.", "code": "account_unapproved"}, status=403)
    evidence = _get_permitted_evidence(request.user, evidence_id)
    scene = SceneReconstruction.objects.filter(
        evidence=evidence,
        success=True,
        ply_file__gt="",
    ).order_by("-created_at").first()

    if not scene:
        return JsonResponse({"error": "No reconstruction found."}, status=404)

    return reconstruction_scene_data_api(request, scene.pk)
