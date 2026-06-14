"""
evidence/views.py
Adds approval guard and audit logging to all evidence operations.
"""
import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .ai_detector import analyze_image
from .models import DetectionResult, Evidence
from accounts.models import log_action

logger = logging.getLogger(__name__)
ANALYSIS_COPY_SUFFIXES = {'.jfif', '.jpe'}


def _case_for_user(case_id, user):
    from cases.models import Case
    if user.is_staff:
        return get_object_or_404(Case, id=case_id)
    return get_object_or_404(
        Case,
        Q(created_by=user) | Q(assigned_to=user) | Q(created_by__isnull=True),
        id=case_id,
    )


def _dashboard_detection(det):
    label = str(det.get('label', 'evidence')).strip().lower() or 'evidence'
    display_label = label.replace('_', ' ').title()
    confidence = float(det.get('confidence') or 0)
    significance = det.get('forensic_significance', 'low').lower()
    risk_map = {'high': 'high', 'medium': 'moderate', 'low': 'low'}
    bbox = det.get('bbox') if isinstance(det.get('bbox'), list) else [0, 0, 0, 0]
    if len(bbox) != 4:
        bbox = [0, 0, 0, 0]
    return {
        'label':         label,
        'class_name':    label,
        'display_label': display_label,
        'source':        det.get('source', 'unknown'),
        'description':   det.get('description', ''),
        'location':      det.get('location', ''),
        'confidence':    round(confidence, 3),
        'confidence_pct': round(confidence * 100, 1),
        'bbox':          {'x1': bbox[0], 'y1': bbox[1], 'x2': bbox[2], 'y2': bbox[3]},
        'risk_level':    risk_map.get(significance, 'low'),
        'risk_color':    det.get('color', '#6b7280'),
    }


def _analysis_path(evidence):
    image_path = Path(evidence.file.path)
    out_dir = Path(settings.MEDIA_ROOT) / 'results' / 'analysis'
    out_dir.mkdir(parents=True, exist_ok=True)
    jpg_path = out_dir / f'evidence_{evidence.id}_analysis.jpg'

    if jpg_path.exists() and jpg_path.stat().st_mtime >= image_path.stat().st_mtime:
        return str(jpg_path)

    from PIL import Image, ImageOps
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in {'RGBA', 'LA'}:
            background = Image.new('RGB', img.size, 'white')
            background.paste(img, mask=img.getchannel('A'))
            img = background
        else:
            img = img.convert('RGB')
        img.save(jpg_path, 'JPEG', quality=95, optimize=True)
    return str(jpg_path)


def _display_label(label):
    return str(label or 'Evidence').replace('_', ' ').title()


def _location_bbox(location, width, height):
    location = str(location or 'center').lower()
    x_map = {'left': 0.20, 'center': 0.50, 'right': 0.80}
    y_map = {'top': 0.20, 'center': 0.50, 'bottom': 0.80}
    cx = x_map['center']
    cy = y_map['center']
    for key, value in x_map.items():
        if key in location: cx = value
    for key, value in y_map.items():
        if key in location: cy = value
    box_w = width * 0.26
    box_h = height * 0.22
    x1 = max(0, int(cx * width - box_w / 2))
    y1 = max(0, int(cy * height - box_h / 2))
    x2 = min(width - 1, int(cx * width + box_w / 2))
    y2 = min(height - 1, int(cy * height + box_h / 2))
    return [x1, y1, x2, y2]


def _detection_bbox(det, width, height):
    bbox = det.get('bbox')
    if isinstance(bbox, list) and len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))
        x2 = max(0, min(width - 1, x2))
        y2 = max(0, min(height - 1, y2))
        if x2 > x1 and y2 > y1:
            return [x1, y1, x2, y2]
    return _location_bbox(det.get('location'), width, height)


def _make_annotated_image(evidence, analysis_path, detections):
    from PIL import Image, ImageDraw, ImageFont
    out_dir = Path(settings.MEDIA_ROOT) / 'results' / 'annotated'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'evidence_{evidence.id}_annotated.jpg'

    with Image.open(analysis_path) as img:
        img = img.convert('RGB')
        draw = ImageDraw.Draw(img)
        width, height = img.size
        try:
            font = ImageFont.truetype('arial.ttf', max(14, int(width * 0.018)))
        except Exception:
            font = ImageFont.load_default()
        for det in detections:
            color = det.get('color', '#ef4444')
            bbox  = _detection_bbox(det, width, height)
            label = _display_label(det.get('label'))
            conf  = det.get('confidence')
            text  = f"{label} {int(float(conf)*100)}%" if conf is not None else label
            x1, y1, x2, y2 = bbox
            for offset in range(3):
                draw.rectangle([x1 - offset, y1 - offset, x2 + offset, y2 + offset], outline=color)
            text_box = draw.textbbox((0, 0), text, font=font)
            text_w = text_box[2] - text_box[0]
            text_h = text_box[3] - text_box[1]
            label_y = max(0, y1 - text_h - 8)
            draw.rectangle([x1, label_y, x1 + text_w + 10, label_y + text_h + 8], fill=color)
            draw.text((x1 + 5, label_y + 4), text, fill='white', font=font)
        img.save(out_path, 'JPEG', quality=92)

    return f"{settings.MEDIA_URL}results/annotated/{out_path.name}"


def _overall_risk(detections):
    priority = {'critical': 4, 'high': 3, 'moderate': 2, 'low': 1, 'none': 0}
    if not detections:
        return 'none'
    return max((d['risk_level'] for d in detections), key=lambda r: priority.get(r, 0))


def _risk_color(risk):
    return {
        'critical': '#8b5cf6',
        'high':     '#ef4444',
        'moderate': '#f59e0b',
        'low':      '#22c55e',
        'none':     '#6b7280',
    }.get(risk, '#6b7280')


def _save_analysis(evidence):
    analysis_path = _analysis_path(evidence)
    analysis = analyze_image(analysis_path)
    try:
        analysis['annotated_url'] = _make_annotated_image(
            evidence, analysis_path, analysis.get('detections', []),
        )
    except Exception:
        logger.exception('Annotated image generation failed for evidence_id=%s', evidence.id)
        analysis['annotated_url'] = evidence.file.url
    DetectionResult.objects.update_or_create(
        evidence=evidence,
        defaults={
            'detections_json': json.dumps(analysis.get('detections', [])),
            'scene_summary':   analysis.get('scene_summary', ''),
            'evidence_count':  analysis.get('evidence_count', 0),
            'scene_type':      analysis.get('scene_type', 'unknown'),
            'sources_used':    ','.join(analysis.get('sources_used', [])),
        },
    )
    evidence.status = 'analyzed'
    evidence.save(update_fields=['status'])
    return analysis


def _is_approved(user):
    """Return True if user is staff or has an approved profile."""
    if user.is_staff:
        return True
    try:
        return user.profile.is_approved
    except Exception:
        return False


@login_required
def upload_evidence(request, case_id):
    if not _is_approved(request.user):
        return render(request, 'accounts/pending_approval.html')
    case = _case_for_user(case_id, request.user)
    if request.method == 'POST':
        files = request.FILES.getlist('evidence_files')
        for file in files:
            evidence = Evidence.objects.create(
                case=case,
                uploaded_by=request.user,
                file=file,
                original_filename=file.name,
                file_size=file.size,
                notes=request.POST.get('notes', ''),
            )
            _save_analysis(evidence)
            log_action(request.user, 'evidence_upload',
                       target=f'Case #{case.case_number} / {file.name}')
        return redirect('evidence_list', case_id=case_id)
    return render(request, 'evidence/upload.html', {'case': case})


@csrf_exempt
@require_http_methods(['POST'])
def api_upload_evidence(request):
    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'Authentication required. Please log in again and retry.',
            'code':  'authentication_required',
        }, status=401)

    if not _is_approved(request.user):
        return JsonResponse({'error': 'Account pending admin approval.'}, status=403)

    case_id = request.POST.get('case_id')
    image   = request.FILES.get('image') or request.FILES.get('evidence_files')
    if not case_id:
        return JsonResponse({'error': 'case_id is required'}, status=400)
    if not image:
        return JsonResponse({'error': 'image file is required'}, status=400)

    try:
        case = _case_for_user(case_id, request.user)
    except (Http404, ValueError):
        return JsonResponse({'error': 'Selected case is not available for upload.'}, status=404)

    evidence = Evidence.objects.create(
        case=case,
        uploaded_by=request.user,
        file=image,
        original_filename=image.name,
        file_size=image.size,
        notes=request.POST.get('notes', ''),
    )

    try:
        analysis = _save_analysis(evidence)
    except Exception as exc:
        logger.exception('Evidence detection failed for evidence_id=%s', evidence.id)
        return JsonResponse({
            'error':       'Detection failed on the server.',
            'detail':      str(exc),
            'evidence_id': evidence.id,
        }, status=500)

    log_action(request.user, 'evidence_upload',
               target=f'Case #{case.case_number} / {image.name}')

    dashboard_detections = [_dashboard_detection(d) for d in analysis.get('detections', [])]
    risk = _overall_risk(dashboard_detections)
    return JsonResponse({
        'id':              evidence.id,
        'evidence_id':     evidence.id,
        'filename':        evidence.original_filename,
        'image_url':       evidence.file.url,
        'annotated_url':   analysis.get('annotated_url', evidence.file.url),
        'detections':      dashboard_detections,
        'raw_detections':  analysis.get('detections', []),
        'total_objects':   len(dashboard_detections),
        'weapons_found':   any(d['risk_level'] in {'high', 'critical'} for d in dashboard_detections),
        'overall_risk':    risk,
        'risk_color':      _risk_color(risk),
        'scene_summary':   analysis.get('scene_summary', ''),
        'sources_used':    analysis.get('sources_used', []),
    })


@login_required
def evidence_list(request, case_id):
    if not _is_approved(request.user):
        return render(request, 'accounts/pending_approval.html')
    case = _case_for_user(case_id, request.user)
    evidence_items = Evidence.objects.filter(case=case).order_by('-analyzed_at')
    for ev in evidence_items:
        try:
            dr = ev.detectionresult
            ev.detections    = json.loads(dr.detections_json)
            ev.scene_summary = dr.scene_summary
            ev.evidence_count = dr.evidence_count
        except DetectionResult.DoesNotExist:
            ev.detections    = []
            ev.scene_summary = ''
            ev.evidence_count = 0
    return render(request, 'evidence/list.html', {'case': case, 'evidence_items': evidence_items})


@login_required
def evidence_detail(request, evidence_id):
    if not _is_approved(request.user):
        return render(request, 'accounts/pending_approval.html')
    if request.user.is_staff:
        evidence = get_object_or_404(Evidence, id=evidence_id)
    else:
        evidence = get_object_or_404(
            Evidence, id=evidence_id,
            case__in=__import__('cases.models', fromlist=['Case']).Case.objects.filter(
                Q(created_by=request.user) | Q(assigned_to=request.user)
            )
        )
    try:
        dr = evidence.detectionresult
        detections   = json.loads(dr.detections_json)
        scene_summary = dr.scene_summary
        sources_used  = [s for s in dr.sources_used.split(',') if s]
    except DetectionResult.DoesNotExist:
        detections   = []
        scene_summary = ''
        sources_used  = []
    return render(request, 'evidence/detail.html', {
        'evidence':       evidence,
        'detections':     detections,
        'detections_json': json.dumps(detections),
        'scene_summary':  scene_summary,
        'sources_used':   sources_used,
    })


@login_required
@require_http_methods(['POST'])
def reanalyze_evidence(request, evidence_id):
    if not _is_approved(request.user):
        return JsonResponse({'error': 'Account pending approval'}, status=403)
    if request.user.is_staff:
        evidence = get_object_or_404(Evidence, id=evidence_id)
    else:
        evidence = get_object_or_404(Evidence, id=evidence_id, case__created_by=request.user)
    analysis = _save_analysis(evidence)
    log_action(request.user, 'analysis_run',
               target=f'Evidence #{evidence_id}')
    return JsonResponse({
        'status':         'ok',
        'detections':     analysis.get('detections', []),
        'scene_summary':  analysis.get('scene_summary', ''),
        'evidence_count': analysis.get('evidence_count', 0),
        'sources_used':   analysis.get('sources_used', []),
    })


@login_required
@require_http_methods(['POST'])
def delete_evidence(request, evidence_id):
    if not _is_approved(request.user):
        return JsonResponse({'error': 'Account pending approval'}, status=403)
    if request.user.is_staff:
        evidence = get_object_or_404(Evidence, id=evidence_id)
    else:
        evidence = get_object_or_404(Evidence, id=evidence_id, case__created_by=request.user)
    case_id = evidence.case.id
    fn = evidence.original_filename
    if evidence.file and os.path.exists(evidence.file.path):
        os.remove(evidence.file.path)
    evidence.delete()
    log_action(request.user, 'evidence_delete', target=fn)
    return redirect('evidence_list', case_id=case_id)
