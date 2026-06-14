import os
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def redact_api_key(message):
    return re.sub(r"(api_key=)[^&\s]+", r"\1[redacted]", str(message))


LABEL_COLORS = {
    "gun": "#ef4444",
    "knife": "#ef4444",
    "pistol": "#ef4444",
    "blood": "#dc2626",
    "blood stain": "#dc2626",
    "blood stains": "#dc2626",
    "footprint": "#3b82f6",
    "fingerprint": "#3b82f6",
    "suspicious object": "#f59e0b",
    "default": "#6b7280",
}


FORENSIC_SIGNIFICANCE = {
    "gun": "high",
    "knife": "high",
    "pistol": "high",
    "blood": "high",
    "blood stain": "high",
    "blood stains": "high",
    "footprint": "medium",
    "fingerprint": "medium",
    "suspicious object": "medium",
}


def get_label_color(label):
    label = label.lower()
    for key, color in LABEL_COLORS.items():
        if key in label:
            return color
    return LABEL_COLORS["default"]


def get_significance(label):
    label = label.lower()
    for key, value in FORENSIC_SIGNIFICANCE.items():
        if key in label:
            return value
    return "low"


def normalize_roboflow_prediction(pred, model_id):
    """
    Roboflow usually returns:
    x, y, width, height, confidence, class
    where x and y are center points.
    """

    label = pred.get("class", pred.get("label", "evidence")).lower()
    confidence = float(pred.get("confidence", 0))

    x = float(pred.get("x", 0))
    y = float(pred.get("y", 0))
    w = float(pred.get("width", 0))
    h = float(pred.get("height", 0))

    x1 = int(x - w / 2)
    y1 = int(y - h / 2)
    x2 = int(x + w / 2)
    y2 = int(y + h / 2)

    return {
        "label": label,
        "confidence": round(confidence, 3),
        "bbox": [x1, y1, x2, y2],
        "source": f"roboflow:{model_id}",
        "description": f"Roboflow detected {label} with {confidence:.0%} confidence",
        "location": "detected region",
        "forensic_significance": get_significance(label),
        "color": get_label_color(label),
        "notes": "Detected using Roboflow hosted forensic/evidence model",
    }


def run_roboflow_detection(image_path):
    if os.environ.get("ENABLE_ROBOFLOW_DETECTION", "0") != "1":
        logger.info("Roboflow detection disabled. Set ENABLE_ROBOFLOW_DETECTION=1 to enable it.")
        return []

    api_key = os.environ.get("ROBOFLOW_API_KEY", "")

    if not api_key:
        logger.warning("ROBOFLOW_API_KEY not set. Skipping Roboflow detection.")
        return []

    try:
        from inference_sdk import InferenceHTTPClient
    except Exception as e:
        logger.error("inference-sdk not installed: %s", e)
        return []

    # You can change these model ids later from Roboflow Universe.
    model_ids = [
        "evidence-detection-l2tem/1",  # gun, knife, blood, footprint
        "bloodstain-z2fox/1",         # blood stains
    ]

    def infer_model(model_id):
        client = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key=api_key
        )
        result = client.infer(image_path, model_id=model_id)
        detections = []
        for pred in result.get("predictions", []):
            det = normalize_roboflow_prediction(pred, model_id)
            if det["confidence"] >= 0.35:
                detections.append(det)
        return detections

    all_detections = []

    with ThreadPoolExecutor(max_workers=len(model_ids)) as executor:
        futures = {executor.submit(infer_model, model_id): model_id for model_id in model_ids}
        for future in as_completed(futures):
            model_id = futures[future]
            try:
                all_detections.extend(future.result())
            except Exception as e:
                logger.error("Roboflow detection failed for %s: %s", model_id, redact_api_key(e))

    return all_detections
