import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).resolve().parents[1] / "weights"

NORMALIZED_LABELS = {
    "blood_stain",
    "fingerprint",
    "gun",
    "pistol",
    "handgun",
    "rifle",
    "knife",
    "grenade",
    "shell_casing",
    "possible_blood_like_region",
    "possible_fingerprint_like_ridge_region",
}

LABEL_ALIASES = {
    "blood": "blood_stain",
    "bloodstain": "blood_stain",
    "blood stain": "blood_stain",
    "blood stains": "blood_stain",
    "fingerprint": "fingerprint",
    "fingerprint mark": "fingerprint",
    "latent fingerprint": "fingerprint",
    "gun": "gun",
    "firearm": "gun",
    "pistol": "pistol",
    "revolver": "pistol",
    "hand gun": "handgun",
    "handgun": "handgun",
    "rifle": "rifle",
    "knife": "knife",
    "grenade": "grenade",
    "bullet casing": "shell_casing",
    "cartridge casing": "shell_casing",
    "shell casing": "shell_casing",
    "shell_casing": "shell_casing",
    "possible blood-like region": "possible_blood_like_region",
    "possible_blood_like_region": "possible_blood_like_region",
    "possible fingerprint-like ridge region": "possible_fingerprint_like_ridge_region",
    "possible_fingerprint_like_ridge_region": "possible_fingerprint_like_ridge_region",
}

DISPLAY_LABELS = {
    "blood_stain": "Blood Stain",
    "fingerprint": "Fingerprint",
    "gun": "Gun",
    "pistol": "Pistol",
    "handgun": "Handgun",
    "rifle": "Rifle",
    "knife": "Knife",
    "grenade": "Grenade",
    "shell_casing": "Shell Casing",
    "possible_blood_like_region": "Possible Blood-like Region",
    "possible_fingerprint_like_ridge_region": "Possible Fingerprint-like Ridge Region",
}

WEAPON_LABELS = {"gun", "pistol", "handgun", "rifle", "knife", "grenade"}
CANDIDATE_LABELS = {"possible_blood_like_region", "possible_fingerprint_like_ridge_region"}
MODEL_DETECTED_LABELS = (NORMALIZED_LABELS - CANDIDATE_LABELS)

LABEL_COLORS = {
    "blood_stain": "#dc2626",
    "fingerprint": "#3b82f6",
    "shell_casing": "#f97316",
    "possible_blood_like_region": "#f59e0b",
    "possible_fingerprint_like_ridge_region": "#60a5fa",
    "gun": "#ef4444",
    "pistol": "#ef4444",
    "handgun": "#ef4444",
    "rifle": "#ef4444",
    "knife": "#ef4444",
    "grenade": "#ef4444",
}

DEFAULT_THRESHOLDS = {
    "blood_stain": 0.35,
    "fingerprint": 0.40,
    "shell_casing": 0.30,
    "gun": 0.35,
    "pistol": 0.35,
    "handgun": 0.35,
    "rifle": 0.35,
    "knife": 0.30,
    "grenade": 0.35,
}

MODEL_SPECS = {
    "forensic_weapons_v1": {
        "env": "FORENSIC_WEAPON_WEIGHTS",
        "default": WEIGHTS_DIR / "forensic_best.pt",
        "intended_classes": WEAPON_LABELS,
    },
    "forensic_blood_v1": {
        "env": "FORENSIC_BLOOD_WEIGHTS",
        "default": "",
        "intended_classes": {"blood_stain"},
    },
    "forensic_fingerprint_v1": {
        "env": "FORENSIC_FINGERPRINT_WEIGHTS",
        "default": "",
        "intended_classes": {"fingerprint"},
    },
    "forensic_combined_v1": {
        "env": "FORENSIC_COMBINED_WEIGHTS",
        "default": WEIGHTS_DIR / "forensic_best_v2.pt",
        "intended_classes": MODEL_DETECTED_LABELS,
    },
}

_MODEL_CACHE = {}


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: list
    source: str
    model_name: str
    model_version: str
    verification_status: str
    location: str
    notes: str = ""

    def as_dict(self):
        label = normalize_label(self.label)
        return {
            "label": label,
            "display_label": display_label(label),
            "confidence": round(float(self.confidence), 3),
            "bbox": self.bbox,
            "source": self.source,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "verification_status": self.verification_status,
            "forensic_significance": significance_for(label, self.verification_status),
            "description": description_for(label, self.verification_status, self.model_name),
            "location": self.location,
            "color": color_for(label),
            "notes": self.notes,
        }


def normalize_label(label):
    key = str(label or "").strip().lower().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    return LABEL_ALIASES.get(key)


def display_label(label):
    label = normalize_label(label) or str(label or "evidence")
    return DISPLAY_LABELS.get(label, label.replace("_", " ").title())


def color_for(label):
    return LABEL_COLORS.get(normalize_label(label) or label, "#6b7280")


def significance_for(label, verification_status="model_detected"):
    label = normalize_label(label) or label
    if verification_status != "model_detected":
        return "medium"
    if label in WEAPON_LABELS or label == "blood_stain":
        return "high"
    if label in {"fingerprint", "shell_casing"}:
        return "medium"
    return "low"


def description_for(label, verification_status, model_name):
    if verification_status == "candidate_unverified":
        return f"{display_label(label)} found by visual heuristic. Analyst verification required."
    return f"{display_label(label)} detected by trained local model."


def threshold_for(label):
    label = normalize_label(label) or label
    configured = getattr(settings, "FORENSIC_CLASS_THRESHOLDS", {})
    if isinstance(configured, dict) and label in configured:
        return float(configured[label])
    env_name = f"FORENSIC_CONF_{str(label).upper()}"
    if os.getenv(env_name):
        return float(os.getenv(env_name))
    return DEFAULT_THRESHOLDS.get(label, 0.35)


def nms_iou_threshold():
    return float(getattr(settings, "FORENSIC_NMS_IOU_THRESHOLD", os.getenv("FORENSIC_NMS_IOU_THRESHOLD", 0.55)))


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


def dedupe_detections(detections, iou_threshold=None):
    iou_threshold = nms_iou_threshold() if iou_threshold is None else iou_threshold
    ordered = sorted(
        detections,
        key=lambda item: (
            item.get("verification_status") != "model_detected",
            -float(item.get("confidence", 0)),
            str(item.get("label", "")),
        ),
    )
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


def model_path_for(spec):
    configured = os.getenv(spec["env"], "").strip() or str(getattr(settings, spec["env"], "") or "").strip()
    value = configured or spec.get("default") or ""
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    return path


def load_model(path):
    key = str(path.resolve())
    if key not in _MODEL_CACHE:
        from ultralytics import YOLO

        _MODEL_CACHE[key] = YOLO(key)
    return _MODEL_CACHE[key]


def model_classes(model):
    names = getattr(model, "names", {}) or {}
    values = names.values() if isinstance(names, dict) else names
    return {normalize_label(name) for name in values if normalize_label(name)}


def get_model_health(load_classes=True):
    health = []
    for model_name, spec in MODEL_SPECS.items():
        path = model_path_for(spec)
        item = {
            "model_name": model_name,
            "model_version": path.name if path else "",
            "path": str(path) if path else "",
            "path_exists": bool(path and path.exists()),
            "enabled": bool(path and path.exists()),
            "configured_classes": sorted(spec["intended_classes"]),
            "loaded_classes": [],
            "missing_classes": sorted(spec["intended_classes"]),
            "confidence_thresholds": {label: threshold_for(label) for label in sorted(spec["intended_classes"])},
            "ready": False,
            "suitable_for_confirmed_detection": False,
        }
        if path and path.exists() and load_classes:
            try:
                classes = model_classes(load_model(path))
                runnable = classes & spec["intended_classes"]
                item["loaded_classes"] = sorted(classes)
                item["missing_classes"] = sorted(spec["intended_classes"] - classes)
                item["ready"] = bool(runnable)
                item["suitable_for_confirmed_detection"] = bool(runnable)
            except Exception as exc:
                item["load_error"] = str(exc)
                logger.exception("Unable to inspect model %s at %s", model_name, path)
        return_item = item
        health.append(return_item)
    return health


def _run_yolo_models(image_path):
    from PIL import Image

    with Image.open(image_path) as img:
        width, height = img.size

    detections = []
    source_models = []
    seen_classes = set()
    for model_name, spec in MODEL_SPECS.items():
        path = model_path_for(spec)
        if not path or not path.exists():
            logger.info("Forensic model unavailable name=%s path=%s", model_name, path)
            continue
        try:
            model = load_model(path)
            classes = model_classes(model)
            runnable = (classes & spec["intended_classes"] & MODEL_DETECTED_LABELS) - seen_classes
            if not runnable:
                logger.warning("Forensic model has no runnable configured classes name=%s classes=%s", model_name, sorted(classes))
                continue
            source_models.append(
                {"model_name": model_name, "model_version": path.name, "classes": sorted(runnable)}
            )
            min_conf = min(threshold_for(label) for label in runnable)
            results = model(str(image_path), conf=min_conf, imgsz=getattr(settings, "FORENSIC_YOLO_IMAGE_SIZE", 768), verbose=False)
            for result in results:
                for box in result.boxes:
                    raw_label = result.names[int(box.cls[0])]
                    label = normalize_label(raw_label)
                    if label not in runnable:
                        continue
                    confidence = float(box.conf[0])
                    if confidence < threshold_for(label):
                        continue
                    bbox = clamp_bbox(box.xyxy[0].tolist(), width, height)
                    if not bbox:
                        continue
                    detections.append(
                        Detection(
                            label=label,
                            confidence=confidence,
                            bbox=bbox,
                            source="local_yolo",
                            model_name=model_name,
                            model_version=path.name,
                            verification_status="model_detected",
                            location=bbox_location(bbox, width, height),
                            notes="Confirmed model detection with pixel bounding box.",
                        ).as_dict()
                    )
            seen_classes |= runnable
        except Exception:
            logger.exception("YOLO inference failed model=%s path=%s", model_name, path)
    return detections, source_models


def run_cv_candidates(image_path):
    if not getattr(settings, "ENABLE_CV_CANDIDATES", False):
        return []
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    h, w = img.shape[:2]
    detections = []
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red1 = cv2.inRange(hsv, np.array([0, 45, 35]), np.array([12, 255, 230]))
    red2 = cv2.inRange(hsv, np.array([165, 45, 35]), np.array([180, 255, 230]))
    mask = cv2.morphologyEx(red1 | red2, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours[:10]:
        area = cv2.contourArea(contour)
        if area < max(250, 0.00025 * w * h):
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        bbox = clamp_bbox([x, y, x + bw, y + bh], w, h)
        if bbox:
            detections.append(
                Detection(
                    label="possible_blood_like_region",
                    confidence=0.42,
                    bbox=bbox,
                    source="local_cv",
                    model_name="opencv_color_candidate",
                    model_version="not_a_trained_detector",
                    verification_status="candidate_unverified",
                    location=bbox_location(bbox, w, h),
                    notes="Unverified candidate only; not counted as confirmed blood evidence.",
                ).as_dict()
            )
            break

    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    edges = cv2.Canny(gray, 60, 140)
    tile = max(96, min(180, min(w, h) // 4))
    stride = max(1, tile // 2)
    best = None
    for y in range(0, max(1, h - tile), stride):
        for x in range(0, max(1, w - tile), stride):
            roi = edges[y:y + tile, x:x + tile]
            density = float(np.count_nonzero(roi)) / roi.size
            if not 0.075 <= density <= 0.24:
                continue
            lines = cv2.HoughLinesP(roi, 1, np.pi / 180, threshold=18, minLineLength=12, maxLineGap=6)
            line_count = 0 if lines is None else len(lines)
            score = density * min(line_count, 60)
            if line_count >= 18 and (best is None or score > best[0]):
                best = (score, [x, y, min(w - 1, x + tile), min(h - 1, y + tile)])
    if best:
        bbox = best[1]
        detections.append(
            Detection(
                label="possible_fingerprint_like_ridge_region",
                confidence=0.38,
                bbox=bbox,
                source="local_cv",
                model_name="opencv_ridge_candidate",
                model_version="not_a_trained_detector",
                verification_status="candidate_unverified",
                location=bbox_location(bbox, w, h),
                notes="Unverified candidate only; not counted as confirmed fingerprint evidence.",
            ).as_dict()
        )
    return detections


def confirmed_count(detections):
    return sum(1 for det in detections if det.get("verification_status") == "model_detected")


def candidate_count(detections):
    return sum(1 for det in detections if det.get("verification_status") == "candidate_unverified")


def count_label(detections, labels, confirmed_only=True):
    label_set = set(labels)
    return sum(
        1
        for det in detections
        if det.get("label") in label_set
        and (not confirmed_only or det.get("verification_status") == "model_detected")
    )


def weapons_found(detections):
    return count_label(detections, WEAPON_LABELS) > 0


def analyze_image(image_path):
    started = time.perf_counter()
    yolo_detections, source_models = _run_yolo_models(image_path)
    cv_detections = run_cv_candidates(image_path)
    detections = dedupe_detections(yolo_detections + cv_detections)
    detections.sort(
        key=lambda det: (
            det.get("verification_status") != "model_detected",
            det.get("label", ""),
            -float(det.get("confidence", 0)),
        )
    )
    counts = {
        "confirmed_count": confirmed_count(detections),
        "candidate_count": candidate_count(detections),
        "total_detection_count": len(detections),
        "weapon_count": count_label(detections, WEAPON_LABELS),
        "blood_count": count_label(detections, {"blood_stain"}),
        "fingerprint_count": count_label(detections, {"fingerprint"}),
    }
    sources_used = []
    if yolo_detections:
        sources_used.append("local_yolo")
    if cv_detections:
        sources_used.append("local_cv")
    return {
        "detections": detections,
        "scene_summary": (
            f"{counts['confirmed_count']} confirmed detection(s) and "
            f"{counts['candidate_count']} unverified candidate(s) found."
        ),
        "evidence_count": counts["confirmed_count"],
        **counts,
        "weapons_found": counts["weapon_count"] > 0,
        "scene_type": "unknown",
        "sources_used": sources_used,
        "source_models": source_models,
        "model_health": get_model_health(load_classes=False),
        "analysis_duration_ms": int((time.perf_counter() - started) * 1000),
    }
