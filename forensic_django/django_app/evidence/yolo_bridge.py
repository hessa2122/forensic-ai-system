"""
evidence/yolo_bridge.py

Connects Django to YOLOv8 forensic weapon detection model.
Classes confirmed from forensic_best.pt:
  0: Grenade, 1: Gun, 2: Knife, 3: Pistol, 4: handgun, 5: rifle
"""

from pathlib import Path
from django.conf import settings

WEIGHTS_DIR    = Path(__file__).resolve().parent / 'weights'
FORENSIC_MODEL = WEIGHTS_DIR / 'forensic_best.pt'
BASE_MODEL     = WEIGHTS_DIR / 'yolov8m.pt'

# ── Exact class names from the trained model ──────────────────────────────────
FORENSIC_CLASSES = {
    0: 'Grenade',
    1: 'Gun',
    2: 'Knife',
    3: 'Pistol',
    4: 'handgun',
    5: 'rifle',
}

# ── Risk level per weapon type ────────────────────────────────────────────────
RISK_LEVELS = {
    'Grenade': 'critical',   # explosive — highest danger
    'Gun':     'high',
    'rifle':   'high',
    'Pistol':  'high',
    'handgun': 'high',
    'Knife':   'moderate',
}

# ── Risk colours for frontend UI ─────────────────────────────────────────────
RISK_COLORS = {
    'critical': '#8b5cf6',   # purple
    'high':     '#ef4444',   # red
    'moderate': '#f59e0b',   # amber
    'low':      '#22c55e',   # green
    'none':     '#6b7280',   # grey
}

_model = None   # singleton — loaded once when Django starts


def get_model():
    """Load model once and reuse for every detection request."""
    global _model
    if _model is None:
        from ultralytics import YOLO
        weights = FORENSIC_MODEL if FORENSIC_MODEL.exists() else BASE_MODEL
        print(f"[yolo_bridge] Loading model: {weights.name}")
        _model = YOLO(str(weights))
    return _model


def detect_evidence(image_path: str, confidence: float = 0.25) -> dict:
    """
    Run YOLOv8 detection on a crime scene image.

    Args:
        image_path  — full path to uploaded image
        confidence  — minimum confidence 0.0 to 1.0
                      original script used 0.75 — we use 0.45
                      to catch more evidence at lower confidence

    Returns:
        detections      — list of every detected object
        annotated_path  — image with bounding boxes drawn on it
        total_objects   — total count of detections
        summary         — count per weapon type
        overall_risk    — highest risk level in the scene
        risk_color      — hex colour for the overall risk
    """
    model   = get_model()
    results = model(image_path, conf=confidence)[0]

    detections = []
    summary    = {}

    for box in results.boxes:
        cls_id     = int(box.cls[0])
        cls_name   = results.names.get(cls_id, f'unknown_{cls_id}')
        conf_score = float(box.conf[0])
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]

        risk = RISK_LEVELS.get(cls_name, 'moderate')

        detection = {
            'class_id':   cls_id,
            'class_name': cls_name,
            'confidence': round(conf_score, 3),
            'confidence_pct': round(conf_score * 100, 1),
            'bbox': {
                'x1': round(x1),
                'y1': round(y1),
                'x2': round(x2),
                'y2': round(y2),
            },
            'risk_level': risk,
            'risk_color': RISK_COLORS.get(risk, '#6b7280'),
        }
        detections.append(detection)
        summary[cls_name] = summary.get(cls_name, 0) + 1

    # ── Save annotated image with bounding boxes ──────────────────────────────
    annotated_dir = Path(settings.MEDIA_ROOT) / 'results' / 'annotated'
    annotated_dir.mkdir(parents=True, exist_ok=True)
    annotated_name = Path(image_path).stem + '_detected.jpg'
    annotated_path = str(annotated_dir / annotated_name)
    results.save(filename=annotated_path)

    # ── Calculate overall scene risk ──────────────────────────────────────────
    priority = {'critical': 4, 'high': 3, 'moderate': 2, 'low': 1, 'none': 0}
    if detections:
        highest      = max(detections, key=lambda d: priority.get(d['risk_level'], 0))
        overall_risk = highest['risk_level']
    else:
        overall_risk = 'none'

    return {
        'detections':     detections,
        'annotated_path': annotated_path,
        'total_objects':  len(detections),
        'summary':        summary,
        'overall_risk':   overall_risk,
        'risk_color':     RISK_COLORS.get(overall_risk, '#6b7280'),
        'weapons_found':  len(detections) > 0,
    }


def get_model_info() -> dict:
    """Returns metadata about the loaded model — used by Django admin."""
    model = get_model()
    return {
        'model_file':    FORENSIC_MODEL.name if FORENSIC_MODEL.exists() else BASE_MODEL.name,
        'num_classes':   len(model.names),
        'class_names':   list(model.names.values()),
        'forensic_model': FORENSIC_MODEL.exists(),
    }