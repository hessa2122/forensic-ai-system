from pathlib import Path
import logging

logger = logging.getLogger(__name__)

FORENSIC_CLASSES = [
    "gun",
    "pistol",
    "knife",
    "rifle",
    "grenade",
    "weapon",
    "blood stain",
    "blood splatter",
    "fingerprint",
    "footprint",
    "shoe print",
    "shell casing",
    "bullet hole",
    "dead body",
    "suspicious object",
    "broken glass",
    "rope",
    "bag",
]

LABEL_COLORS = {
    "gun": "#ef4444",
    "pistol": "#ef4444",
    "knife": "#ef4444",
    "rifle": "#ef4444",
    "grenade": "#ef4444",
    "weapon": "#ef4444",
    "blood": "#dc2626",
    "fingerprint": "#3b82f6",
    "footprint": "#3b82f6",
    "shoe print": "#3b82f6",
    "shell casing": "#f97316",
    "bullet hole": "#f97316",
    "dead body": "#8b5cf6",
    "suspicious object": "#f59e0b",
    "broken glass": "#f59e0b",
    "rope": "#f59e0b",
    "bag": "#f59e0b",
    "default": "#6b7280",
}


def get_label_color(label):
    label = label.lower()
    for key, color in LABEL_COLORS.items():
        if key in label:
            return color
    return LABEL_COLORS["default"]


def get_significance(label):
    label = label.lower()

    high_items = [
        "gun", "pistol", "knife", "rifle", "grenade",
        "weapon", "blood", "dead body"
    ]

    medium_items = [
        "fingerprint", "footprint", "shoe print",
        "shell casing", "bullet hole", "suspicious",
        "broken glass", "rope", "bag"
    ]

    for item in high_items:
        if item in label:
            return "high"

    for item in medium_items:
        if item in label:
            return "medium"

    return "low"


def run_free_forensic_detection(image_path, confidence_threshold=0.20):
    """
    Free local open-vocabulary detection using YOLO-World.
    No Gemini key.
    No Roboflow key.
    No billing.
    """

    detections = []

    try:
        from ultralytics import YOLO

        # First time it may download the model automatically.
        model = YOLO("yolov8s-worldv2.pt")
        # Tell YOLO-World what forensic evidence to look for
        model.set_classes(FORENSIC_CLASSES)

        results = model.predict(
            source=str(image_path),
            conf=confidence_threshold,
            imgsz=320,
            verbose=False
)

        for result in results:
            names = result.names

            for box in result.boxes:
                cls_id = int(box.cls[0])
                label = names.get(cls_id, "evidence").lower()
                confidence = float(box.conf[0])

                x1, y1, x2, y2 = box.xyxy[0].tolist()

                detections.append({
                    "label": label,
                    "confidence": round(confidence, 3),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "source": "yolo_world_free",
                    "description": f"Free YOLO-World detected {label} with {confidence:.0%} confidence",
                    "location": "detected region",
                    "forensic_significance": get_significance(label),
                    "color": get_label_color(label),
                    "notes": "Free local open-vocabulary forensic detection. Human verification required.",
                })

    except Exception as e:
        import traceback
        print("Free forensic detector real error:")
        traceback.print_exc()
        logger.error("Free forensic detector failed: %s", e)
    return detections