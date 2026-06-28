"""Compatibility exports for the canonical detection pipeline.

New code should import from evidence.services.detection_pipeline directly.
This module remains so older views/tests/admin code do not grow a second
active detection implementation.
"""

from .services.detection_pipeline import (  # noqa: F401
    CANDIDATE_LABELS,
    DEFAULT_THRESHOLDS as CLASS_THRESHOLDS,
    DISPLAY_LABELS,
    MODEL_DETECTED_LABELS as CONFIRMED_FORENSIC_CLASSES,
    MODEL_SPECS,
    WEAPON_LABELS as WEAPON_CLASSES,
    bbox_location,
    candidate_count,
    clamp_bbox,
    color_for,
    confirmed_count,
    count_label,
    dedupe_detections,
    display_label,
    get_model_health as get_enabled_model_metadata,
    iou,
    normalize_label,
    significance_for,
    threshold_for,
    weapons_found,
)


MODEL_REGISTRY = {
    name: {
        "path": config.get("default"),
        "enabled": True,
        "allowed_classes": set(config.get("intended_classes", set())),
        "env": config.get("env"),
    }
    for name, config in MODEL_SPECS.items()
}


def run_registered_yolo_models(image_path):
    from .services.detection_pipeline import _run_yolo_models

    return _run_yolo_models(image_path)
