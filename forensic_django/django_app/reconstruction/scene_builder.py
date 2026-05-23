# reconstruction/scene_builder.py

import cv2
import json
import torch
import numpy as np
import open3d as o3d
from pathlib import Path
from PIL import Image

# ── Depth Model Setup ─────────────────────────────────────────────────────────
WEIGHTS_DIR = Path(__file__).parent / 'weights'
_depth_model = None

def load_depth_model(encoder='vits'):
    """
    Load Depth Anything V2 model.
    encoder options: 'vits' (fast, ~94MB), 'vitb' (better), 'vitl' (best, ~1.3GB)
    """
    global _depth_model
    if _depth_model is not None:
        return _depth_model

    import sys
    sys.path.append(str(Path(__file__).parent.parent))

    try:
        from depth_anything_v2.dpt import DepthAnythingV2

        model_configs = {
            'vits': {'encoder': 'vits', 'features': 64,  'out_channels': [48, 96, 192, 384]},
            'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
            'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256,512,1024,1024]},
        }

        model = DepthAnythingV2(**model_configs[encoder])
        weight_path = WEIGHTS_DIR / f'depth_anything_v2_{encoder}.pth'
        if not weight_path.exists():
            print(f"Warning: depth model weights not found at {weight_path}, using image-based fallback")
            _depth_model = None
            return _depth_model
        model.load_state_dict(torch.load(weight_path, map_location='cpu'))
        model.eval()
        _depth_model = model
        return _depth_model
    except ImportError:
        print("Warning: depth_anything_v2 not found, using image-based fallback")
        _depth_model = None
        return _depth_model


def load_midas_fallback():
    """Fallback depth model using MiDaS (built into torch hub)."""
    model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small")
    model.eval()
    return model


def estimate_depth_fallback(img_rgb):
    """Fast local depth approximation so reconstruction works without model downloads."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    h, w = gray.shape
    vertical_prior = np.linspace(0.25, 1.0, h, dtype=np.float32)[:, None]
    edges = cv2.Laplacian(gray, cv2.CV_32F)
    texture = cv2.GaussianBlur(np.abs(edges), (0, 0), 3)
    depth = 0.65 * vertical_prior + 0.25 * (1.0 - gray) + 0.10 * texture
    depth = cv2.GaussianBlur(depth, (0, 0), 2)
    return (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)


def estimate_depth(model, image_path):
    """
    Estimate depth map from image.
    Returns numpy array (H x W) normalized 0-1.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    h, w = img.shape[:2]

    if model is None:
        depth = estimate_depth_fallback(img_rgb)
    else:
        try:
        # Depth Anything V2
            depth = model.infer_image(img_rgb)
        except AttributeError:
            depth = estimate_depth_fallback(img_rgb)

    # Normalize to 0-1
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
    depth = cv2.resize(depth.astype(np.float32), (w, h))

    return depth, img_rgb


def build_point_cloud(image_rgb, depth_map, detections=None, density=2):
    """
    Build colored 3D point cloud from image + depth.
    
    Args:
        image_rgb:   H x W x 3 numpy array
        depth_map:   H x W numpy array (0-1)
        detections:  list of detection dicts from evidence analysis
        density:     1=full, 2=half, 4=quarter (higher = faster)
    
    Returns:
        open3d.geometry.PointCloud
    """
    h, w = depth_map.shape

    # Generate pixel grid
    ys, xs = np.meshgrid(
        np.arange(0, h, density),
        np.arange(0, w, density),
        indexing='ij'
    )
    xs_flat = xs.flatten()
    ys_flat = ys.flatten()

    # Get depth values
    z = depth_map[ys_flat, xs_flat].astype(np.float64)

    # Simple pinhole camera model
    fx = fy = w * 0.8  # estimated focal length
    cx, cy = w / 2, h / 2

    # Back-project to 3D
    X = (xs_flat - cx) * z / fx
    Y = (ys_flat - cy) * z / fy
    Z = z

    points = np.stack([X, Y, Z], axis=1)

    # Get colors from image
    colors = image_rgb[ys_flat, xs_flat].astype(np.float64) / 255.0

    # ── Highlight detected evidence in point cloud ────────────────────────
    EVIDENCE_COLORS = {
        'gun':          [1.0, 0.0, 0.0],   # bright red
        'pistol':       [1.0, 0.1, 0.1],
        'rifle':        [1.0, 0.2, 0.0],
        'knife':        [1.0, 0.5, 0.0],   # orange
        'grenade':      [0.8, 0.0, 0.0],
        'blood':        [0.7, 0.0, 0.0],   # dark red
        'fingerprint':  [0.0, 1.0, 1.0],   # cyan
        'shell_casing': [1.0, 1.0, 0.0],   # yellow
        'rope':         [0.6, 0.4, 0.2],   # brown
        'drugs':        [0.0, 1.0, 0.0],   # green
        'footprint':    [1.0, 0.0, 1.0],   # magenta
        'broken_glass': [0.8, 0.8, 0.8],   # light gray
    }

    if detections:
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls = det['class']
            highlight_color = EVIDENCE_COLORS.get(cls, [1.0, 1.0, 0.0])

            # Find points inside this bounding box
            mask = (
                (xs_flat >= x1) & (xs_flat <= x2) &
                (ys_flat >= y1) & (ys_flat <= y2)
            )
            colors[mask] = highlight_color

    # Remove invalid points (zero depth)
    valid = Z > 0.01
    points = points[valid]
    colors = colors[valid]

    # Create Open3D point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors)

    # Denoise
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)

    return pcd


def save_point_cloud(pcd, output_path):
    """Save point cloud as PLY file."""
    o3d.io.write_point_cloud(str(output_path), pcd)
    print(f"Saved point cloud: {output_path} ({len(pcd.points)} points)")
    return output_path


def reconstruct_scene(image_path, detections=None, output_dir=None, density=2):
    """
    Full pipeline: image → depth → point cloud → PLY file.
    
    Args:
        image_path:  path to crime scene image
        detections:  list of detections from evidence analysis
        output_dir:  where to save PLY file
        density:     point cloud density (1=dense, 2=normal, 4=sparse)
    
    Returns:
        dict with ply_path and stats
    """
    image_path = Path(image_path)

    if output_dir is None:
        output_dir = image_path.parent / 'point_clouds'
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"Loading depth model...")
    model = load_depth_model(encoder='vits')

    print(f"Estimating depth for: {image_path.name}")
    depth_map, image_rgb = estimate_depth(model, image_path)

    print(f"Building point cloud (density={density})...")
    pcd = build_point_cloud(image_rgb, depth_map, detections=detections, density=density)

    ply_name   = image_path.stem + '_scene.ply'
    ply_path   = Path(output_dir) / ply_name
    save_point_cloud(pcd, ply_path)

    return {
        'ply_path':    str(ply_path),
        'ply_name':    ply_name,
        'num_points':  len(pcd.points),
        'image_size':  list(image_rgb.shape[:2]),
    }
