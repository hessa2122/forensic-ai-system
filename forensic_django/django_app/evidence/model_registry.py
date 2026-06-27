import logging
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
WEAPON_CLASSES = {"gun", "pistol", "handgun", "rifle", "knife", "grenade"}
CONFIRMED_FORENSIC_CLASSES = WEAPON_CLASSES | {"blood", "shell_casing"}
CLASS_ALIASES = {
    "blood stain": "blood",
    "blood stains": "blood",
    "shell casing": "shell_casing",
    "shell casings": "shell_casing",
    "bullet casing": "shell_casing",
    "firearm": "gun",
    "revolver": "pistol",
}
DISPLAY_LABELS = {
    "blood": "Blood Stain",
    "shell_casing": "Shell Casing",
    "gun": "Gun",
    "knife": "Knife",
    "pistol": "Pistol",
    "handgun": "Handgun",
    "rifle": "Rifle",
    "grenade": "Grenade",
    "possible_blood_like_region": "Possible blood-like region",
    "possible_fingerprint_like_ridge_region": "Possible fingerprint-like ridge region",
}
LABEL_COLORS = {
    "blood": "#dc2626",
    "shell_casing": "#f97316",
    "gun": "#ef4444",
    "knife": "#ef4444",
    "pistol": "#ef4444",
    "handgun": "#ef4444",
    "rifle": "#ef4444",
    "grenade": "#ef4444",
    "possible_blood_like_region": "#f59e0b",
    "possible_fingerprint_like_ridge_region": "#3b82f6",
}
CLASS_THRESHOLDS = {
    "blood": 0.35,
    "shell_casing": 0.30,
    "knife": 0.30,
    "gun": 0.35,
    "pistol": 0.35,
    "handgun": 0.35,
    "rifle": 0.35,
    "grenade": 0.35,
}

MODEL_REGISTRY = {
    "forensic_weapons_v1": {
        "path": WEIGHTS_DIR / "forensic_best.pt",
        "enabled": True,
        "allowed_classes": {"grenade", "gun", "knife", "pistol", "handgun", "rifle"},
    },
    "forensic_v2": {
        "path": WEIGHTS_DIR / "forensic_best_v2.pt",
        "enabled": True,
        "allowed_classes": {"gun", "knife", "grenade", "pistol", "rifle", "blood", "shell_casing"},
    },
    "coco_yolov8m": {
        "path": WEIGHTS_DIR / "yolov8m.pt",
        "enabled": False,
        "allowed_classes": {"knife"},
    },
}

_MODEL_CACHE = {}


@dataclass(frozen=True)
class Detection:
    label: str
    display_label: str
    confidence: float
    bbox: list | None
    source: str
    model_name: str
    model_version: str
    verification_status: str
    forensic_significance: str
    description: str
    color: str
    location: str = "detected region"
    notes: str = ""

    def as_dict(self):
        return {
            "label": self.label,
            "display_label": self.display_label,
            "confidence": round(float(self.confidence), 3),
            "bbox": self.bbox,
            "source": self.source,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "verification_status": self.verification_status,
            "forensic_significance": self.forensic_significance,
            "description": self.description,
            "color": self.color,
            "location": self.location,
            "notes": self.notes,
        }


def normalize_label(label):
    normalized = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = CLASS_ALIASES.get(normalized.replace("_", " "), normalized)
    return normalized


def display_label(label):
    return DISPLAY_LABELS.get(label, label.replace("_", " ").title())


def significance_for(label, verification_status="model_detected"):
    if verification_status != "model_detected":
        return "medium"
    if label in WEAPON_CLASSES or label == "blood":
        return "high"
    if label == "shell_casing":
        return "medium"
    return "low"


def color_for(label):
    return LABEL_COLORS.get(label, "#6b7280")


def clamp_bbox(bbox, width, height):
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    x1 = max(0, min(width - 1, int(round(x1))))
    y1 = max(0, min(height - 1, int(round(y1))))
    x2 = max(0, min(width - 1, int(round(x2))))
    y2 = max(0, min(height - 1, int(round(y2))))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def bbox_location(bbox, width, height):
    if not bbox:
        return "not localized"
    x1, y1, x2, y2 = bbox
    cx = ((x1 + x2) / 2) / max(width, 1)
    cy = ((y1 + y2) / 2) / max(height, 1)
    vertical = "top" if cy < 0.33 else "bottom" if cy > 0.66 else "center"
    horizontal = "left" if cx < 0.33 else "right" if cx > 0.66 else "center"
    return f"{vertical}-{horizontal}" if vertical != "center" else horizontal


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0


def dedupe_detections(detections, iou_threshold=0.55):
    ordered = sorted(detections, key=lambda item: item.get("confidence", 0), reverse=True)
    kept = []
    for det in ordered:
        duplicate = False
        for old in kept:
            if det.get("label") != old.get("label"):
                continue
            if det.get("bbox") and old.get("bbox") and iou(det["bbox"], old["bbox"]) >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(det)
    return kept


def get_enabled_model_metadata():
    metadata = []
    for name, config in MODEL_REGISTRY.items():
        path = Path(config["path"])
        item = {
            "model_name": name,
            "model_version": path.name,
            "path_exists": path.exists(),
            "enabled": bool(config.get("enabled")),
            "configured_classes": sorted(config.get("allowed_classes", set())),
            "loaded_classes": [],
        }
        if path.exists():
            try:
                model = load_model(name)
                item["loaded_classes"] = [normalize_label(v) for v in model.names.values()]
            except Exception as exc:
                item["load_error"] = str(exc)
        metadata.append(item)
    return metadata


def load_model(model_name):
    config = MODEL_REGISTRY[model_name]
    path = Path(config["path"])
    if not path.exists():
        raise FileNotFoundError(path.name)
    key = str(path.resolve())
    if key not in _MODEL_CACHE:
        from ultralytics import YOLO

        started = time.perf_counter()
        model = YOLO(key)
        classes = {normalize_label(v) for v in model.names.values()}
        unsupported = set(config.get("allowed_classes", set())) - classes
        if unsupported:
            logger.warning(
                "Model registry mismatch model=%s version=%s missing_classes=%s loaded_classes=%s",
                model_name,
                path.name,
                sorted(unsupported),
                sorted(classes),
            )
        logger.info(
            "Loaded YOLO model name=%s version=%s classes=%s load_ms=%s",
            model_name,
            path.name,
            sorted(classes),
            int((time.perf_counter() - started) * 1000),
        )
        _MODEL_CACHE[key] = model
    return _MODEL_CACHE[key]


def run_registered_yolo_models(image_path):
    from PIL import Image

    with Image.open(image_path) as img:
        width, height = img.size

    detections = []
    source_models = []
    seen_classes = set()
    for model_name, config in MODEL_REGISTRY.items():
        if not config.get("enabled"):
            continue
        path = Path(config["path"])
        if not path.exists():
            logger.warning("YOLO model missing name=%s version=%s", model_name, path.name)
            continue
        model = load_model(model_name)
        model_classes = {normalize_label(v) for v in model.names.values()}
        runnable = (set(config.get("allowed_classes", set())) & model_classes) - seen_classes
        if not runnable:
            continue
        source_models.append({"model_name": model_name, "model_version": path.name, "classes": sorted(runnable)})
        results = model(str(image_path), conf=min(CLASS_THRESHOLDS.values()), imgsz=768, verbose=False)
        for result in results:
            for box in result.boxes:
                raw_label = result.names[int(box.cls[0])]
                label = normalize_label(raw_label)
                if label not in runnable or label not in CONFIRMED_FORENSIC_CLASSES:
                    continue
                confidence = float(box.conf[0])
                if confidence < CLASS_THRESHOLDS.get(label, 0.35):
                    continue
                bbox = clamp_bbox(box.xyxy[0].tolist(), width, height)
                if not bbox:
                    continue
                detections.append(
                    Detection(
                        label=label,
                        display_label=display_label(label),
                        confidence=confidence,
                        bbox=bbox,
                        source="local_yolo",
                        model_name=model_name,
                        model_version=path.name,
                        verification_status="model_detected",
                        forensic_significance=significance_for(label),
                        description=f"Local YOLO model detected {display_label(label)}.",
                        color=color_for(label),
                        location=bbox_location(bbox, width, height),
                        notes="Confirmed model detection with pixel bounding box.",
                    ).as_dict()
                )
        seen_classes |= runnable
    return dedupe_detections(detections), source_models


def confirmed_count(detections):
    return sum(1 for det in detections if det.get("verification_status") == "model_detected")


def candidate_count(detections):
    return sum(1 for det in detections if det.get("verification_status") == "candidate_unverified")


def weapons_found(detections):
    return any(
        det.get("verification_status") == "model_detected" and det.get("label") in WEAPON_CLASSES
        for det in detections
    )
