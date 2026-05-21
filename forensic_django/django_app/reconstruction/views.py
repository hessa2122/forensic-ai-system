# reconstruction/views.py

import json
from pathlib import Path
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .scene_builder import reconstruct_scene
from .models import SceneReconstruction


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

    result = reconstruct_scene(
        image_path  = image_path,
        detections  = detections,
        output_dir  = Path(settings.MEDIA_ROOT) / 'point_clouds',
        density     = 1,   # full density for crime scene
    )

    # Save to database
    scene = SceneReconstruction.objects.create(
        evidence   = evidence,
        ply_file   = f"point_clouds/{result['ply_name']}",
        num_points = result['num_points'],
    )

    return JsonResponse({
        'scene_id':   scene.id,
        'ply_url':    f"/media/point_clouds/{result['ply_name']}",
        'num_points': result['num_points'],
        'detections': detections,
    })


@csrf_exempt  
def reconstruct_direct(request):
    """
    Upload image directly and get 3D reconstruction.
    POST /reconstruction/direct/
    """
    if request.method != 'POST' or 'image' not in request.FILES:
        return render(request, 'reconstruction/upload.html')

    img_file  = request.FILES['image']
    upload_dir = Path(settings.MEDIA_ROOT) / 'temp_reconstruction'
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / img_file.name
    with open(save_path, 'wb+') as f:
        for chunk in img_file.chunks():
            f.write(chunk)

    result = reconstruct_scene(
        image_path = save_path,
        detections = None,
        output_dir = Path(settings.MEDIA_ROOT) / 'point_clouds',
        density    = 2,
    )

    return JsonResponse({
        'ply_url':    f"/media/point_clouds/{result['ply_name']}",
        'num_points': result['num_points'],
    })


def scene_viewer(request, scene_id=None):
    """Render the Three.js 3D viewer."""
    context = {'scene_id': scene_id}
    if scene_id:
        scene = get_object_or_404(SceneReconstruction, pk=scene_id)
        context['scene'] = scene
        context['ply_url'] = f"/media/{scene.ply_file}"
    return render(request, 'reconstruction/viewer.html', context)