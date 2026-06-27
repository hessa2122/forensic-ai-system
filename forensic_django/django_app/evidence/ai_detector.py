"""
evidence/ai_detector.py — NO BILLING VERSION
Detection pipeline:
  - YOLO        → weapons (gun, knife, pistol, rifle, grenade) — free, local, instant
  - Gemini 2.0  → everything else (blood, fingerprint, suspicious, body, shell casing)
                  Free tier: 1500 requests/day, no billing, no credit card
Google Vision removed entirely — not needed.
"""
from .roboflow_detector import run_roboflow_detection
import os
import json
import logging
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings

from .model_registry import (
    candidate_count,
    confirmed_count,
    dedupe_detections,
    display_label,
    run_registered_yolo_models,
    weapons_found,
)

logger = logging.getLogger(__name__)
_YOLO_MODEL_CACHE = {}

# ──────────────────────────────────────────────
# LABEL COLOURS
# ──────────────────────────────────────────────
LABEL_COLORS = {
    "gun":               "#ef4444",
    "knife":             "#ef4444",
    "pistol":            "#ef4444",
    "rifle":             "#ef4444",
    "grenade":           "#ef4444",
    "handgun":           "#ef4444",
    "weapon":            "#ef4444",
    "blood stain":       "#dc2626",
    "blood":             "#dc2626",
    "fingerprint":       "#3b82f6",
    "suspicious object": "#f59e0b",
    "suspicious":        "#f59e0b",
    "body":              "#8b5cf6",
    "shell casing":      "#f97316",
    "evidence":          "#10b981",
    "default":           "#6b7280",
}

WEAPON_CLASSES = {"gun", "knife", "pistol", "rifle", "grenade", "handgun", "weapon"}
FORENSIC_LABEL_KEYWORDS = {
    "gun", "knife", "pistol", "rifle", "grenade", "handgun", "weapon",
    "blood", "fingerprint", "shell casing", "shoe print", "footprint",
    "tool mark", "body", "suspicious object", "evidence",
}

CLASS_THRESHOLDS = {
    "blood": 0.22,
    "blood stain": 0.22,
    "blood stains": 0.22,
    "knife": 0.24,
    "shell casing": 0.24,
    "shell_casing": 0.24,
    "fingerprint": 0.30,
    "gun": 0.35,
    "pistol": 0.35,
    "rifle": 0.35,
    "grenade": 0.35,
    "handgun": 0.35,
}

FORENSIC_SIGNIFICANCE = {
    "gun": "high", "knife": "high", "pistol": "high",
    "rifle": "high", "grenade": "high", "handgun": "high",
    "weapon": "high", "blood stain": "high", "blood": "high",
    "body": "high", "fingerprint": "medium",
    "suspicious object": "medium", "shell casing": "medium",
}


def get_label_color(label: str) -> str:
    for key, color in LABEL_COLORS.items():
        if key in label.lower():
            return color
    return LABEL_COLORS["default"]


def get_significance(label: str) -> str:
    for key, sig in FORENSIC_SIGNIFICANCE.items():
        if key in label.lower():
            return sig
    return "low"


def normalize_label(label: str) -> str:
    label = str(label or "evidence").lower().strip().replace("_", " ")
    aliases = {
        "bloodstains": "blood stain",
        "bloodstain": "blood stain",
        "blood stains": "blood stain",
        "shell casings": "shell casing",
        "bullet casing": "shell casing",
        "bullet casings": "shell casing",
        "cartridge casing": "shell casing",
        "shell casing": "shell casing",
        "handgun": "pistol",
        "firearm": "gun",
        "revolver": "pistol",
        "gun weapon": "gun",
        "weapon gun": "gun",
        "possible fingerprint": "fingerprint",
        "footwear impression": "shoe print",
        "shoeprint": "shoe print",
    }
    return aliases.get(label, label)


def threshold_for(label: str) -> float:
    label = normalize_label(label)
    return CLASS_THRESHOLDS.get(label, 0.35)


def is_forensic_label(label: str) -> bool:
    label = normalize_label(label)
    return any(key in label for key in FORENSIC_LABEL_KEYWORDS)


def _default_yolo_weights():
    app_dir = Path(__file__).resolve().parents[1]
    evidence_weights = Path(__file__).parent / "weights"
    configured = os.environ.get("YOLO_WEIGHTS_PATH", "").strip()

    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend([
        evidence_weights / "forensic_best_v2.pt",
        evidence_weights / "forensic_best.pt",
        app_dir / "runs" / "detect" / "forensic_v3_smart-2" / "weights" / "best.pt",
        app_dir / "runs" / "detect" / "forensic_v3_accurate" / "weights" / "best.pt",
        app_dir / "runs" / "detect" / "forensic_v2_fast-2" / "weights" / "best.pt",
        app_dir / "runs" / "detect" / "forensic_v2_fast" / "weights" / "best.pt",
        evidence_weights / "yolov8m.pt",
    ])

    seen = set()
    found = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = app_dir / path
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            found.append(path)

    if not found:
        logger.warning("No YOLO weights found. Checked %s", [str(p) for p in candidates])
    return found


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0


# ──────────────────────────────────────────────
# 1. YOLO — weapons only (free, local)
# ──────────────────────────────────────────────
def run_yolo_detection(image_path: str, weights_path: str = None) -> list:
    try:
        from ultralytics import YOLO

        if weights_path is None:
            weights_path = Path(__file__).parent / "weights" / "forensic_best_v2.pt"

        if not Path(weights_path).exists():
            logger.warning("YOLO weights not found at %s", weights_path)
            return []

        weights_key = str(Path(weights_path).resolve())
        model = _YOLO_MODEL_CACHE.get(weights_key)
        if model is None:
            model = YOLO(weights_key)
            _YOLO_MODEL_CACHE[weights_key] = model

        results = model(image_path, conf=0.20, imgsz=768, verbose=False)
        detections = []
        source_name = "yolo_forensic_v2" if "v2" in Path(weights_path).stem else "yolo_weapons"

        for r in results:
            for box in r.boxes:
                label      = normalize_label(r.names[int(box.cls[0])])
                confidence = float(box.conf[0])
                if not is_forensic_label(label):
                    continue
                if confidence < threshold_for(label):
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "label":                 label,
                    "confidence":            round(confidence, 3),
                    "bbox":                  [int(x1), int(y1), int(x2), int(y2)],
                    "source":                source_name,
                    "forensic_significance": get_significance(label),
                    "color":                 get_label_color(label),
                    "description":           f"YOLOv8 detected {label} ({confidence:.0%} confidence)",
                    "location":              _bbox_to_location([x1, y1, x2, y2], image_path),
                    "notes":                 "Weapon classifier — bounding box available for 2D overlay",
                })

        return detections

    except Exception as e:
        logger.error("YOLO detection failed: %s", e)
        return []


def _bbox_to_location(bbox, image_path) -> str:
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return "unknown"
        h, w  = img.shape[:2]
        cx    = (bbox[0] + bbox[2]) / 2 / w
        cy    = (bbox[1] + bbox[3]) / 2 / h
        vert  = "top"  if cy < 0.33 else ("bottom" if cy > 0.66 else "center")
        horiz = "left" if cx < 0.33 else ("right"  if cx > 0.66 else "center")
        return f"{vert}-{horiz}" if vert != "center" else horiz
    except Exception:
        return "unknown"


def run_cv_forensic_detection(image_path: str) -> list:
    detections = []
    img = cv2.imread(str(image_path))
    if img is None:
        return detections

    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Blood-like red/brown stain candidates. This is intentionally conservative
    # and used as a fallback label helper, not a replacement for model evidence.
    red1 = cv2.inRange(hsv, np.array([0, 45, 35]), np.array([12, 255, 230]))
    red2 = cv2.inRange(hsv, np.array([165, 45, 35]), np.array([180, 255, 230]))
    blood_mask = cv2.morphologyEx(red1 | red2, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(blood_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < max(250, 0.00025 * w * h):
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < 12 or bh < 12:
            continue
        bbox = [x, y, x + bw, y + bh]
        detections.append({
            "label": "possible_blood_like_region",
            "display_label": "Possible blood-like region",
            "confidence": 0.42,
            "bbox": bbox,
            "source": "local_cv",
            "model_name": "opencv_color_candidate",
            "model_version": "not_a_trained_detector",
            "verification_status": "candidate_unverified",
            "description": "Color/shape analysis found a blood-like region. Analyst verification required.",
            "location": _bbox_to_location(bbox, image_path),
            "forensic_significance": "medium",
            "color": get_label_color("blood"),
            "notes": "Unverified candidate only; not counted as confirmed blood evidence.",
        })
        if len(detections) >= 3:
            break

    # Fingerprint-like ridge candidates: dense, thin edge patterns in a compact tile.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    edges = cv2.Canny(gray, 60, 140)
    tile = max(96, min(180, min(w, h) // 4))
    stride = tile // 2
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
        detections.append({
            "label": "possible_fingerprint_like_ridge_region",
            "display_label": "Possible fingerprint-like ridge region",
            "confidence": 0.38,
            "bbox": bbox,
            "source": "local_cv",
            "model_name": "opencv_ridge_candidate",
            "model_version": "not_a_trained_detector",
            "verification_status": "candidate_unverified",
            "description": "Ridge-pattern analysis found a possible fingerprint-like region",
            "location": _bbox_to_location(bbox, image_path),
            "forensic_significance": "medium",
            "color": get_label_color("fingerprint"),
            "notes": "Analyst verification required. This is not a trained fingerprint detection.",
        })

    return detections


# ──────────────────────────────────────────────
# 2. GEMINI 2.0 FLASH — all forensic categories
#    Free: 1500 req/day, no billing needed
# ──────────────────────────────────────────────
GEMINI_PROMPT = """You are a senior forensic AI analyst assisting law enforcement.
Analyze this crime scene image carefully and return ONLY a valid JSON object.
No markdown fences, no explanation text — just the raw JSON.

Required format:
{
  "detections": [
    {
      "label": "blood stain|fingerprint|weapon|suspicious object|body|shell casing|shoe print|tool mark|other evidence",
      "confidence": <float 0.0-1.0>,
      "description": "<precise forensic description of exactly what you see>",
      "location": "<top-left|top-center|top-right|center-left|center|center-right|bottom-left|bottom-center|bottom-right>",
      "forensic_significance": "<high|medium|low>",
      "notes": "<collection method, pattern type, or forensic relevance>"
    }
  ],
  "scene_summary": "<2-3 sentences describing the overall forensic scene>",
  "evidence_count": <integer>,
  "scene_type": "<indoor|outdoor|vehicle|unknown>"
}

Look carefully for:
- Blood stains or spatter patterns (shape, distribution, colour)
- Latent or visible fingerprints
- Shoe or footwear impressions
- Shell casings or bullet holes
- Disturbed surfaces, drag marks, signs of struggle
- Suspicious or out-of-place objects
- Body or body parts
- Tool marks or forced entry signs

If the image shows no forensic evidence at all, return an empty detections array.
Do NOT invent detections — only report what is visually present."""


def run_gemini_detection(image_path: str, api_key: str = None) -> dict:
    empty = {
        "detections":     [],
        "scene_summary":  "Gemini analysis not available.",
        "evidence_count": 0,
        "scene_type":     "unknown",
    }

    try:
        from google import genai
        from google.genai import types

        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — skipping Gemini")
            return empty

        client = genai.Client(api_key=api_key)

        ext      = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png",  ".webp": "image/webp", ".bmp": "image/bmp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                GEMINI_PROMPT,
            ],
        )

        text = response.text.strip()

        # Strip any accidental markdown fences
        if "```" in text:
            parts = text.split("```")
            text  = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        result = json.loads(text)

        for det in result.get("detections", []):
            det["source"] = "gemini_vision"
            det["model_name"] = "gemini"
            det["model_version"] = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
            det["verification_status"] = "candidate_unverified"
            det["display_label"] = display_label(normalize_label(det.get("label", "")))
            det["color"]  = get_label_color(det.get("label", ""))
            det["bbox"]   = None   # Gemini gives location string, not pixel coords

        return result

    except json.JSONDecodeError as e:
        logger.error("Gemini returned invalid JSON: %s", e)
        return empty
    except Exception as e:
        message = str(e)
        if "RESOURCE_EXHAUSTED" in message or "429" in message:
            logger.warning("Gemini detection skipped: quota/rate limit exhausted.")
        else:
            logger.error("Gemini detection failed: %s", e)
        return empty


# ──────────────────────────────────────────────
# 3. FUSION — merge YOLO + Gemini
# ──────────────────────────────────────────────
def fuse_detections(yolo_results: list, gemini_results: dict) -> list:
    unified = []

    # YOLO weapons first (have pixel bboxes — highest value)
    for det in yolo_results:
        unified.append({
            "label":                 det["label"],
            "confidence":            det["confidence"],
            "bbox":                  det["bbox"],
            "source":                "yolo",
            "description":           det.get("description", ""),
            "location":              det.get("location", "unknown"),
            "forensic_significance": det.get("forensic_significance", "high"),
            "color":                 det.get("color", "#ef4444"),
            "notes":                 det.get("notes", ""),
        })

    yolo_labels = {u["label"] for u in unified}

    # Gemini handles everything else
    for det in gemini_results.get("detections", []):
        label = det.get("label", "evidence").lower()

        # Don't double-report weapons YOLO already caught
        if label in WEAPON_CLASSES and label in yolo_labels:
            continue

        unified.append({
            "label":                 label,
            "confidence":            det.get("confidence", 0.85),
            "bbox":                  None,
            "source":                "gemini_vision",
            "description":           det.get("description", ""),
            "location":              det.get("location", "unknown"),
            "forensic_significance": det.get("forensic_significance", get_significance(label)),
            "color":                 det.get("color", get_label_color(label)),
            "notes":                 det.get("notes", ""),
        })

    # Sort: high significance first, then by confidence
    sig_order = {"high": 0, "medium": 1, "low": 2}
    unified.sort(key=lambda x: (
        sig_order.get(x.get("forensic_significance", "low"), 2),
        -x.get("confidence", 0),
    ))

    return unified


# ──────────────────────────────────────────────
# 4. MAIN ENTRY POINT
# ──────────────────────────────────────────────
def analyze_image(image_path: str, yolo_weights: str = None) -> dict:
    image_path = str(image_path)
    sources_used = []
    source_models = []

    yolo_results, source_models = run_registered_yolo_models(image_path)
    if yolo_results:
        sources_used.append("local_yolo")

    roboflow_results = run_roboflow_detection(image_path)
    for det in roboflow_results:
        det.setdefault("model_name", "roboflow")
        det.setdefault("model_version", str(det.get("source", "roboflow")).split(":", 1)[-1])
        det.setdefault("verification_status", "candidate_unverified")
        det.setdefault("display_label", display_label(normalize_label(det.get("label", ""))))
        det["bbox"] = det.get("bbox") if det.get("bbox") else None
    if roboflow_results:
        sources_used.append("roboflow_api")

    # 3. Merge results
    fused = []

    for det in yolo_results:
        fused.append(det)

    for det in roboflow_results:
        fused.append(det)

    cv_results = []
    if getattr(settings, "ENABLE_CV_CANDIDATES", False):
        cv_results = run_cv_forensic_detection(image_path)
    if cv_results:
        sources_used.append("local_cv")
        fused.extend(cv_results)

    # 4. Optional Gemini semantic backup for evidence types that do not have
    # reliable local bounding-box classes yet, especially fingerprints and tool
    # marks. Keep it opt-in so offline/local runs do not stall on network calls.
    if getattr(settings, "ENABLE_GEMINI_BACKUP", False):
        gemini_results = run_gemini_detection(image_path)
        gemini_detections = gemini_results.get("detections", [])
        backup_labels = ("fingerprint", "shoe print", "footprint", "tool mark", "suspicious object")
        useful_gemini = [
            det for det in gemini_detections
            if any(key in normalize_label(det.get("label", "")) for key in backup_labels)
        ]
        if useful_gemini:
            sources_used.append("gemini_vision")
            fused.extend(useful_gemini)

    # 5. Optional heavy local fallback. Disabled by default because YOLO-World
    # loads CLIP text embeddings and can be slow or memory-heavy on CPU laptops.
    if not fused and getattr(settings, "ENABLE_YOLO_WORLD_FALLBACK", False):
        from .free_forensic_detector import run_free_forensic_detection
        free_results = run_free_forensic_detection(image_path)
        if free_results:
            sources_used.append("yolo_world_free")
            fused.extend(free_results)

    fused = dedupe_detections(fused)

    # 6. Sort high risk first
    sig_order = {"high": 0, "medium": 1, "low": 2}
    fused.sort(
        key=lambda x: (
            sig_order.get(x.get("forensic_significance", "low"), 2),
            -x.get("confidence", 0)
        )
    )

    return {
        "detections": fused,
        "scene_summary": (
            f"{confirmed_count(fused)} confirmed detection(s) and "
            f"{candidate_count(fused)} unverified candidate(s) found."
        ),
        "evidence_count": confirmed_count(fused),
        "confirmed_count": confirmed_count(fused),
        "candidate_count": candidate_count(fused),
        "weapons_found": weapons_found(fused),
        "scene_type": "unknown",
        "sources_used": sources_used,
        "source_models": source_models,
    }
