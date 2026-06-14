"""
reconstruction/depth_estimator.py
----------------------------------
Monocular depth using Depth Anything V2 (HuggingFace pipeline).
Falls back to a multi-cue geometry prior when the model is unavailable.
"""

from __future__ import annotations
import os
import numpy as np
from pathlib import Path
from PIL import Image

_PIPELINE = None
MODEL_ID  = "depth-anything/Depth-Anything-V2-Small-hf"
# Larger options:
#   "depth-anything/Depth-Anything-V2-Base-hf"   ~400 MB
#   "depth-anything/Depth-Anything-V2-Large-hf"  ~1.3 GB


def _get_pipeline():
    global _PIPELINE
    if os.environ.get("ENABLE_NEURAL_DEPTH", "0") != "1":
        return None
    if _PIPELINE is not None:
        return _PIPELINE
    try:
        import torch
        from transformers import pipeline as hf_pipeline
        device = 0 if torch.cuda.is_available() else -1
        _PIPELINE = hf_pipeline(
            task="depth-estimation",
            model=MODEL_ID,
            device=device,
        )
        print(f"[Depth] Loaded {MODEL_ID} on {'GPU' if device == 0 else 'CPU'}")
        return _PIPELINE
    except Exception as exc:
        print(f"[Depth] Model unavailable: {exc}. Using geometry-prior fallback.")
        return None


def estimate_depth(image: Image.Image) -> np.ndarray:
    """
    Returns float32 (H, W) in [0, 1].
    1 = closest to camera (disparity / inverse-depth convention).
    """
    pipe = _get_pipeline()
    return _neural_depth(image, pipe) if pipe is not None else _prior_depth(image)


def estimate_depth_from_path(path: str | Path) -> np.ndarray:
    return estimate_depth(Image.open(path).convert("RGB"))


# ── Neural ────────────────────────────────────────────────────────────────────

def _neural_depth(image: Image.Image, pipe) -> np.ndarray:
    result = pipe(image)
    depth  = np.array(result["depth"], dtype=np.float32)
    lo, hi = depth.min(), depth.max()
    if hi - lo < 1e-6:
        return np.full_like(depth, 0.5)
    return ((depth - lo) / (hi - lo)).astype(np.float32)


# ── Geometry-prior fallback ───────────────────────────────────────────────────

def _prior_depth(image: Image.Image) -> np.ndarray:
    import cv2

    rgb  = np.array(image.convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]

    # 1. Vertical prior (bottom = close)
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)
    v_prior = np.tile(y[:, None], (1, w))

    # 2. Darkness cue
    gray  = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    dark  = 1.0 - gray / 255.0

    # 3. High-frequency (texture) cue
    lap  = np.abs(cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F))
    tex  = lap / (lap.max() + 1e-6)

    # 4. Saturation cue  (colourful objects tend to be foreground)
    hsv  = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat  = hsv[:, :, 1] / 255.0

    depth = 0.45 * v_prior + 0.25 * dark + 0.15 * tex + 0.15 * sat
    depth = cv2.GaussianBlur(depth, (21, 21), 0)
    lo, hi = depth.min(), depth.max()
    if hi - lo < 1e-6:
        return np.full_like(depth, 0.5)
    return ((depth - lo) / (hi - lo)).astype(np.float32)
