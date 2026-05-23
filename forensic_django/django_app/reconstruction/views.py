# reconstruction/views.py

import json
import math
from pathlib import Path
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .scene_builder import reconstruct_scene
from .models import SceneReconstruction


def scene_payload(scene):
    ply_path = Path(settings.MEDIA_ROOT) / str(scene.ply_file) if scene.ply_file else None
    ply_exists = bool(ply_path and ply_path.exists())
    ply_size = ply_path.stat().st_size if ply_exists else 0

    return {
        'id': scene.id,
        'scene_id': scene.id,
        'case_id': scene.case_id,
        'evidence_id': scene.evidence_id,
        'ply_url': f"/media/{scene.ply_file}" if scene.ply_file else None,
        'total_points': scene.total_points,
        'num_points': scene.total_points,
        'num_clusters': scene.num_clusters,
        'success': scene.success,
        'error_message': scene.error_message,
        'created_at': scene.created_at.isoformat(),
        'ply_exists': ply_exists,
        'ply_size_bytes': ply_size,
        'ply_size_mb': round(ply_size / (1024 * 1024), 2) if ply_size else 0,
    }


def _safe_float(value, digits=5):
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return round(value, digits)


def _sample_indices(total, max_points):
    if total <= max_points:
        return None
    step = math.ceil(total / max_points)
    return slice(0, total, step)


def point_cloud_data(request, scene_id):
    """
    Return validated, render-ready point cloud data for the browser viewer.
    This avoids opaque client-side PLY parsing failures and gives the UI
    enough metadata to explain what was reconstructed.
    """
    scene = get_object_or_404(SceneReconstruction, pk=scene_id)
    if not scene.success:
        return JsonResponse({
            'error': scene.error_message or 'This reconstruction did not complete successfully.',
            **scene_payload(scene),
        }, status=400)
    if not scene.ply_file:
        return JsonResponse({'error': 'No point-cloud file is attached to this reconstruction.'}, status=404)

    ply_path = Path(settings.MEDIA_ROOT) / str(scene.ply_file)
    if not ply_path.exists():
        return JsonResponse({
            'error': f'Point-cloud file is missing on disk: {scene.ply_file}',
            **scene_payload(scene),
        }, status=404)

    try:
        max_points = int(request.GET.get('max_points', 90000))
    except (TypeError, ValueError):
        max_points = 90000
    max_points = max(1000, min(max_points, 200000))

    try:
        import numpy as np
        import open3d as o3d

        pcd = o3d.io.read_point_cloud(str(ply_path))
        points_np = np.asarray(pcd.points, dtype=np.float32)
        colors_np = np.asarray(pcd.colors, dtype=np.float32)
    except Exception as exc:
        return JsonResponse({
            'error': f'Could not read point-cloud file: {exc}',
            **scene_payload(scene),
        }, status=500)

    total_points = int(points_np.shape[0])
    if total_points == 0:
        return JsonResponse({
            'error': 'The point-cloud file loaded, but it contains zero points.',
            **scene_payload(scene),
        }, status=422)

    sample = _sample_indices(total_points, max_points)
    render_points = points_np[sample] if sample is not None else points_np
    has_colors = colors_np.shape[0] == total_points
    render_colors = colors_np[sample] if sample is not None and has_colors else colors_np if has_colors else None

    mins = points_np.min(axis=0)
    maxs = points_np.max(axis=0)
    center = (mins + maxs) / 2
    size = maxs - mins

    payload = scene_payload(scene)
    payload.update({
        'rendered_points': int(render_points.shape[0]),
        'sampled': sample is not None,
        'sample_step': sample.step if sample is not None else 1,
        'has_colors': bool(has_colors),
        'bounds': {
            'min': [_safe_float(v) for v in mins],
            'max': [_safe_float(v) for v in maxs],
            'center': [_safe_float(v) for v in center],
            'size': [_safe_float(v) for v in size],
        },
        'points': [[_safe_float(x), _safe_float(y), _safe_float(z)] for x, y, z in render_points],
    })
    if render_colors is not None:
        payload['colors'] = [[_safe_float(r, 4), _safe_float(g, 4), _safe_float(b, 4)] for r, g, b in render_colors]

    return JsonResponse(payload)


@csrf_exempt
def reconstruct_from_evidence(request, evidence_id):
    """
    Trigger 3D reconstruction from an already-analyzed evidence image.
    POST /reconstruction/from-evidence/<id>/
    """
    from evidence.models import Evidence

    evidence = get_object_or_404(Evidence, pk=evidence_id)
    image_path = Path(settings.MEDIA_ROOT) / str(evidence.image)

    detections = evidence.get_detections()

    try:
        result = reconstruct_scene(
            image_path  = image_path,
            detections  = detections,
            output_dir  = Path(settings.MEDIA_ROOT) / 'point_clouds',
            density     = 2,
        )
        scene = SceneReconstruction.objects.create(
            case=evidence.case,
            evidence=evidence,
            scene_name=f"Scene from evidence #{evidence.id}",
            ply_file=f"point_clouds/{result['ply_name']}",
            total_points=result['num_points'],
            num_clusters=len(detections),
            success=True,
        )
        data = scene_payload(scene)
        data['detections'] = detections
        return JsonResponse(data)
    except Exception as exc:
        scene = SceneReconstruction.objects.create(
            case=evidence.case,
            evidence=evidence,
            scene_name=f"Failed scene from evidence #{evidence.id}",
            success=False,
            error_message=str(exc),
        )
        return JsonResponse({'error': str(exc), **scene_payload(scene)}, status=500)


@csrf_exempt  
def reconstruct_direct(request):
    """
    Upload image directly and get 3D reconstruction.
    POST /reconstruction/direct/
    """
    if request.method == 'POST' and request.content_type and 'application/json' in request.content_type:
        try:
            body = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        evidence_id = body.get('evidence_id')
        if evidence_id:
            return reconstruct_from_evidence(request, evidence_id)
        return JsonResponse({'error': 'evidence_id is required'}, status=400)

    if request.method != 'POST' or 'image' not in request.FILES:
        return render(request, 'index.html')

    img_file  = request.FILES['image']
    upload_dir = Path(settings.MEDIA_ROOT) / 'temp_reconstruction'
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / img_file.name
    with open(save_path, 'wb+') as f:
        for chunk in img_file.chunks():
            f.write(chunk)

    try:
        result = reconstruct_scene(
            image_path = save_path,
            detections = None,
            output_dir = Path(settings.MEDIA_ROOT) / 'point_clouds',
            density    = 2,
        )
        return JsonResponse({
            'ply_url':      f"/media/point_clouds/{result['ply_name']}",
            'num_points':   result['num_points'],
            'total_points': result['num_points'],
            'num_clusters': 0,
        })
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def reconstruction_list(request):
    case_id = request.GET.get('case_id')
    scenes = SceneReconstruction.objects.filter(success=True)
    if case_id:
        scenes = scenes.filter(case_id=case_id)
    return JsonResponse([scene_payload(scene) for scene in scenes], safe=False)


def scene_viewer(request, scene_id=None):
    """Render the Three.js 3D viewer."""
    context = {'scene_id': scene_id}
    if scene_id:
        scene = get_object_or_404(SceneReconstruction, pk=scene_id)
        context['scene'] = scene
        context['ply_url'] = f"/media/{scene.ply_file}"
    return render(request, 'index.html', context)
