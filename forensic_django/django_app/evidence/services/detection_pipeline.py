import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).resolve().parents[1] / "weights"

FORENSIC_CLASSES = {
    "gun",
    "knife",
    "grenade",
    "blood_stain",
    "fingerprint",
    "footprint",
}
NORMALIZED_LABELS = set(FORENSIC_CLASSES)

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
    "pistol": "gun",
    "revolver": "gun",
    "hand gun": "gun",
    "handgun": "gun",
    "rifle": "gun",
    "knife": "knife",
    "blade": "knife",
    "dagger": "knife",
    "grenade": "grenade",
    "hand grenade": "grenade",
    "finger print": "fingerprint",
    "possible blood-like region": "blood_stain",
    "possible blood like region": "blood_stain",
    "possible_blood_like_region": "blood_stain",
    "possible fingerprint-like ridge region": "fingerprint",
    "possible fingerprint like ridge region": "fingerprint",
    "possible_fingerprint_like_ridge_region": "fingerprint",
    "footprint": "footprint",
    "foot print": "footprint",
    "shoe print": "footprint",
    "shoeprint": "footprint",
    "footwear impression": "footprint",
}

DISPLAY_LABELS = {
    "blood_stain": "Blood Stain",
    "fingerprint": "Fingerprint",
    "footprint": "Footprint",
    "grenade": "Grenade",
    "gun": "Gun",
    "knife": "Knife",
}

WEAPON_LABELS = {"gun", "knife", "grenade"}
TRACE_LABELS = {"blood_stain", "fingerprint", "footprint"}
CANDIDATE_LABELS = set()
MODEL_DETECTED_LABELS = (NORMALIZED_LABELS - CANDIDATE_LABELS)
ALLOWED_OUTPUT_LABELS = MODEL_DETECTED_LABELS | CANDIDATE_LABELS

LABEL_COLORS = {
    "blood_stain": "#dc2626",
    "fingerprint": "#3b82f6",
    "footprint": "#06b6d4",
    "grenade": "#f97316",
    "gun": "#ef4444",
    "knife": "#ef4444",
}

DEFAULT_THRESHOLDS = {
    "blood_stain": 0.35,
    "fingerprint": 0.40,
    "footprint": 0.40,
    "grenade": 0.35,
    "gun": 0.35,
    "knife": 0.30,
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
    "forensic_trace_v1": {
        "env": "FORENSIC_TRACE_WEIGHTS",
        "default": "",
        "intended_classes": TRACE_LABELS,
    },
    "forensic_footprint_v1": {
        "env": "FORENSIC_FOOTPRINT_WEIGHTS",
        "default": "",
        "intended_classes": {"footprint"},
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
    if label == "fingerprint":
        return "medium"
    if label == "footprint":
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


def _bbox_aspect(bbox):
    x1, y1, x2, y2 = bbox
    return max((x2 - x1) / max(y2 - y1, 1), (y2 - y1) / max(x2 - x1, 1))


def _looks_blade_like(image_path, bbox):
    """Heuristic guard for YOLO gun/knife confusion on long blade-shaped objects."""
    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(image_path))
        if img is None:
            return False
        x1, y1, x2, y2 = bbox
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return False
        h, w = crop.shape[:2]
        if min(h, w) < 20:
            return False

        gray = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
        edges = cv2.Canny(gray, 45, 130)
        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold=max(20, min(w, h) // 5),
            minLineLength=max(24, int(max(w, h) * 0.38)),
            maxLineGap=max(8, min(w, h) // 12),
        )
        if lines is None:
            return False

        long_lines = 0
        diagonal_lines = 0
        for line in lines[:, 0, :]:
            lx1, ly1, lx2, ly2 = line
            length = float(np.hypot(lx2 - lx1, ly2 - ly1))
            if length < max(w, h) * 0.38:
                continue
            long_lines += 1
            angle = abs(np.degrees(np.arctan2(ly2 - ly1, lx2 - lx1)))
            angle = min(angle, 180 - angle)
            if 15 <= angle <= 75:
                diagonal_lines += 1

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        blade_pixels = (sat < 75) & (val > 105)
        blade_ratio = float(np.count_nonzero(blade_pixels)) / max(crop.shape[0] * crop.shape[1], 1)

        return (
            _bbox_aspect(bbox) >= 1.7
            and long_lines >= 2
            and diagonal_lines >= 1
            and blade_ratio >= 0.08
        )
    except Exception:
        logger.exception("Knife/gun shape correction failed")
        return False


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
                    notes = "Confirmed model detection with pixel bounding box."
                    if label == "gun" and _looks_blade_like(image_path, bbox):
                        label = "knife"
                        notes = "Model output corrected from gun to knife by blade-shape analysis."
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
                            notes=notes,
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
    b, g, r = cv2.split(img)
    red1 = cv2.inRange(hsv, np.array([0, 45, 20]), np.array([12, 255, 190]))
    red2 = cv2.inRange(hsv, np.array([168, 45, 20]), np.array([180, 255, 190]))
    red_dominance = (
        (r.astype(np.int16) - g.astype(np.int16) > 28)
        & (r.astype(np.int16) - b.astype(np.int16) > 28)
        & (r > 45)
        & (g < 95)
        & (b < 95)
    ).astype(np.uint8) * 255
    mask = red1 | red2 | red_dominance
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blood_boxes = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:18]:
        area = cv2.contourArea(contour)
        if area < max(80, 0.00004 * w * h):
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw * bh > 0.18 * w * h:
            continue
        bbox = clamp_bbox([x, y, x + bw, y + bh], w, h)
        if bbox:
            blood_boxes.append((area, bbox))
    if blood_boxes:
        primary = blood_boxes[0][1]
        pcx = (primary[0] + primary[2]) / 2
        pcy = (primary[1] + primary[3]) / 2
        max_merge_distance = max(w, h) * 0.18
        top_boxes = []
        for _area, box in blood_boxes[:8]:
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            if ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5 <= max_merge_distance:
                top_boxes.append(box)
        if not top_boxes:
            top_boxes = [primary]
        x1 = min(box[0] for box in top_boxes)
        y1 = min(box[1] for box in top_boxes)
        x2 = max(box[2] for box in top_boxes)
        y2 = max(box[3] for box in top_boxes)
        bbox = clamp_bbox([x1, y1, x2, y2], w, h)
        if bbox and (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) > 0.12 * w * h:
            bbox = primary
        if bbox:
            detections.append(
                Detection(
                    label="blood_stain",
                    confidence=0.46 if len(top_boxes) > 1 else 0.42,
                    bbox=bbox,
                    source="local_cv",
                    model_name="opencv_blood_candidate",
                    model_version="not_a_trained_detector",
                    verification_status="candidate_unverified",
                    location=bbox_location(bbox, w, h),
                    notes="Unverified dark-red stain candidate; analyst must confirm blood evidence.",
                ).as_dict()
            )

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
                label="fingerprint",
                confidence=0.38,
                bbox=bbox,
                source="local_cv",
                model_name="opencv_ridge_candidate",
                model_version="not_a_trained_detector",
                verification_status="candidate_unverified",
                location=bbox_location(bbox, w, h),
                notes="Unverified visual candidate; analyst must confirm fingerprint evidence.",
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
    detections = [
        det for det in dedupe_detections(yolo_detections + cv_detections)
        if det.get("label") in ALLOWED_OUTPUT_LABELS
    ]
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
        "footprint_count": count_label(detections, {"footprint"}),
        "grenade_count": count_label(detections, {"grenade"}),
        "class_counts": {label: count_label(detections, {label}) for label in sorted(FORENSIC_CLASSES)},
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
        "model_health": get_model_health(load_classes=True),
        "analysis_duration_ms": int((time.perf_counter() - started) * 1000),
    }
