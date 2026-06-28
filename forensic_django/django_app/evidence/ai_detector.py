"""Compatibility wrapper for evidence detection.

The canonical implementation lives in evidence.services.detection_pipeline.
"""

from .services.detection_pipeline import analyze_image, run_cv_candidates


def run_yolo_detection(image_path: str, weights_path: str = None) -> list:
    from .services.detection_pipeline import _run_yolo_models

    detections, _source_models = _run_yolo_models(image_path)
    if weights_path:
        return [det for det in detections if det.get("model_version") == str(weights_path).split("\\")[-1]]
    return detections


def run_cv_forensic_detection(image_path: str) -> list:
    return run_cv_candidates(image_path)
