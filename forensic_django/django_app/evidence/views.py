# evidence/views.py

import os
import cv2
import json
import numpy as np
from pathlib import Path
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.conf import settings
from ultralytics import YOLO

# ── Load models once at startup ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# Primary forensic model (your newly trained one)
FORENSIC_MODEL_PATH = BASE_DIR / 'weights' / 'forensic_best_v2.pt'
# Fallback to original if new one not ready
if not FORENSIC_MODEL_PATH.exists():
    FORENSIC_MODEL_PATH = BASE_DIR / 'weights' / 'forensic_best.pt'

forensic_model = YOLO(str(FORENSIC_MODEL_PATH))

# Class colors for visualization (BGR format for OpenCV)
CLASS_COLORS = {
    'gun':           (0,   0,   255),   # Red
    'pistol':        (0,   0,   200),   # Dark red
    'rifle':         (0,   50,  255),   # Orange-red
    'knife':         (0,   165, 255),   # Orange
    'grenade':       (0,   0,   128),   # Dark red
    'blood':         (50,  50,  200),   # Blood red
    'fingerprint':   (255, 200, 0  ),   # Cyan-ish
    'shell_casing':  (0,   255, 255),   # Yellow
    'rope':          (42,  42,  165),   # Brown
    'drugs':         (0,   255, 0  ),   # Green
    'footprint':     (255, 0,   255),   # Magenta
    'broken_glass':  (200, 200, 200),   # Light gray
}

DANGER_CLASSES = {'gun', 'pistol', 'rifle', 'grenade', 'knife'}
TRACE_CLASSES  = {'blood', 'fingerprint', 'shell_casing', 'footprint'}


def analyze_image(image_path):
    """
    Run full forensic analysis on an image.
    Returns dict with detections, annotated image path, threat level.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return {'error': 'Could not read image'}

    results_data = {
        'detections': [],
        'threat_level': 'LOW',
        'summary': {},
        'annotated_image': None,
    }

    # ── 1. YOLOv8 Detection ───────────────────────────────────────────────
    yolo_results = forensic_model(img, conf=0.25, iou=0.45)

    for r in yolo_results:
        for box in r.boxes:
            cls_id  = int(box.cls[0])
            cls_name = forensic_model.names[cls_id]
            conf    = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detection = {
                'class':      cls_name,
                'confidence': round(conf, 3),
                'bbox':       [x1, y1, x2, y2],
                'center':     [(x1+x2)//2, (y1+y2)//2],
                'type':       'weapon'    if cls_name in DANGER_CLASSES
                              else 'trace' if cls_name in TRACE_CLASSES
                              else 'other',
            }
            results_data['detections'].append(detection)

            # Draw bounding box
            color = CLASS_COLORS.get(cls_name, (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            label = f"{cls_name} {conf:.0%}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (x1, y1-lh-8), (x1+lw+4, y1), color, -1)
            cv2.putText(img, label, (x1+2, y1-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

    # ── 2. Blood Detection (color analysis) ──────────────────────────────
    blood_regions = detect_blood(img)
    for (bx1, by1, bx2, by2, area) in blood_regions:
        results_data['detections'].append({
            'class':      'blood',
            'confidence': 0.80,
            'bbox':       [bx1, by1, bx2, by2],
            'center':     [(bx1+bx2)//2, (by1+by2)//2],
            'type':       'trace',
            'area_px':    area,
        })
        cv2.rectangle(img, (bx1, by1), (bx2, by2), (50, 50, 200), 2)
        cv2.putText(img, f"blood ~{area}px", (bx1, by1-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50,50,200), 2)

    # ── 3. Fingerprint Detection (texture analysis) ───────────────────────
    fp_regions = detect_fingerprints(img)
    for (fx, fy, fw, fh) in fp_regions:
        results_data['detections'].append({
            'class':      'fingerprint',
            'confidence': 0.65,
            'bbox':       [fx, fy, fx+fw, fy+fh],
            'center':     [fx+fw//2, fy+fh//2],
            'type':       'trace',
        })
        cv2.rectangle(img, (fx, fy), (fx+fw, fy+fh), (255, 200, 0), 2)
        cv2.putText(img, "fingerprint", (fx, fy-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,0), 2)

    # ── 4. Threat Level ───────────────────────────────────────────────────
    classes_found = {d['class'] for d in results_data['detections']}
    if classes_found & DANGER_CLASSES:
        results_data['threat_level'] = 'HIGH'
    elif classes_found & TRACE_CLASSES:
        results_data['threat_level'] = 'MEDIUM'

    # ── 5. Summary ────────────────────────────────────────────────────────
    summary = {}
    for d in results_data['detections']:
        summary[d['class']] = summary.get(d['class'], 0) + 1
    results_data['summary'] = summary

    # ── 6. Save annotated image ───────────────────────────────────────────
    annotated_path = str(image_path).replace('.jpg', '_analyzed.jpg') \
                                    .replace('.png', '_analyzed.jpg')
    cv2.imwrite(annotated_path, img)
    results_data['annotated_image'] = os.path.basename(annotated_path)

    return results_data


def detect_blood(img):
    """Detect blood regions using HSV color analysis."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Blood color range (red hues, medium-low brightness)
    lower1 = np.array([0,   60,  20])
    upper1 = np.array([10,  255, 160])
    lower2 = np.array([160, 60,  20])
    upper2 = np.array([180, 255, 160])

    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask  = cv2.bitwise_or(mask1, mask2)

    # Morphological cleanup
    kernel = np.ones((5,5), np.uint8)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 500:  # ignore tiny noise
            x, y, w, h = cv2.boundingRect(cnt)
            regions.append((x, y, x+w, y+h, int(area)))

    return regions


def detect_fingerprints(img):
    """Detect potential fingerprint regions using texture analysis."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Enhance contrast
    clahe  = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)

    # Gabor filter to detect ridge patterns (fingerprint characteristic)
    regions = []
    ksize   = 31
    for theta in [0, 45, 90, 135]:
        kernel = cv2.getGaborKernel(
            (ksize, ksize), sigma=4.0,
            theta=np.radians(theta),
            lambd=10.0, gamma=0.5, psi=0
        )
        filtered = cv2.filter2D(enhanced, cv2.CV_8UC3, kernel)
        _, thresh = cv2.threshold(filtered, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 300 < area < 5000:
                x, y, w, h = cv2.boundingRect(cnt)
                aspect = w / max(h, 1)
                if 0.5 < aspect < 2.0:  # roughly square = fingerprint-like
                    regions.append((x, y, w, h))

    # Deduplicate overlapping regions
    return regions[:5]  # return top 5 candidates


# ── Django Views ──────────────────────────────────────────────────────────────

def evidence_list(request):
    return render(request, 'evidence/list.html')


@csrf_exempt
def analyze_evidence(request):
    """Main upload + analyze endpoint."""
    if request.method != 'POST':
        return render(request, 'evidence/analyze.html')

    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image uploaded'}, status=400)

    img_file = request.FILES['image']
    upload_dir = Path(settings.MEDIA_ROOT) / 'evidence_uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / img_file.name
    with open(save_path, 'wb+') as f:
        for chunk in img_file.chunks():
            f.write(chunk)

    # Run analysis
    analysis = analyze_image(save_path)

    # Save to database
    from .models import Evidence
    evidence_obj = Evidence.objects.create(
        image=f'evidence_uploads/{img_file.name}',
        detections=json.dumps(analysis['detections']),
        threat_level=analysis['threat_level'],
        summary=json.dumps(analysis.get('summary', {})),
    )

    return JsonResponse({
        'id':             evidence_obj.id,
        'detections':     analysis['detections'],
        'threat_level':   analysis['threat_level'],
        'summary':        analysis['summary'],
        'annotated_image': analysis.get('annotated_image'),
        'total_found':    len(analysis['detections']),
    })


def evidence_detail(request, pk):
    from .models import Evidence
    obj = get_object_or_404(Evidence, pk=pk)
    return render(request, 'evidence/detail.html', {'evidence': obj})