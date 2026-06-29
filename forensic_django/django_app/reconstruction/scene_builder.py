"""
reconstruction/scene_builder.py
--------------------------------
Converts an evidence image into a solid 3D mesh using:
  1. Depth Anything V2  (neural monocular depth)
  2. Correct pinhole camera intrinsics (FOV-derived)
  3. Open3D Poisson Surface Reconstruction → solid mesh
  4. Vertex-colour transfer from the source image
  5. GLB export  (primary)  +  PLY export  (fallback)
  6. DBSCAN clustering on the point cloud for evidence annotation

Install:
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    pip install transformers timm huggingface-hub
    pip install open3d trimesh scipy opencv-contrib-python Pillow numpy
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import cv2
from PIL import Image

log = logging.getLogger(__name__)

# ─── optional heavy imports ───────────────────────────────────────────────────

def _import_open3d():
    try:
        import open3d as o3d
        return o3d
    except Exception as exc:
        log.warning("Open3D unavailable (%s); using solid surface fallback.", exc)
        return None

def _import_trimesh():
    try:
        import trimesh
        return trimesh
    except ImportError:
        return None

def _import_torch():
    try:
        import torch
        return torch
    except ImportError:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  DEPTH ESTIMATION
# ═════════════════════════════════════════════════════════════════════════════

class DepthEstimator:
    """Depth Anything V2 via HuggingFace, with geometry-prior fallback."""

    _instance: Optional["DepthEstimator"] = None

    def __init__(self):
        self.pipe = None
        self._try_load()

    @classmethod
    def get(cls) -> "DepthEstimator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _try_load(self):
        if os.environ.get("ENABLE_NEURAL_DEPTH", "0") != "1":
            log.info("Neural depth disabled; using local geometry-prior depth.")
            self.pipe = None
            return
        try:
            from transformers import pipeline as hf_pipeline
            torch = _import_torch()
            device = "cuda" if (torch and torch.cuda.is_available()) else "cpu"
            log.info("Loading Depth-Anything-V2-Small on %s …", device)
            self.pipe = hf_pipeline(
                task="depth-estimation",
                model="depth-anything/Depth-Anything-V2-Small-hf",
                device=device,
            )
            log.info("Depth Anything V2 loaded.")
        except Exception as exc:
            log.warning("DepthAnything unavailable (%s) — using geometry prior.", exc)
            self.pipe = None

    def estimate(self, img_rgb: np.ndarray) -> np.ndarray:
        """Return depth map in [0,1] float32, same H×W as input."""
        if self.pipe is not None:
            try:
                pil = Image.fromarray(img_rgb)
                result = self.pipe(pil)
                depth = np.array(result["depth"], dtype=np.float32)
                # normalise to [0,1]
                lo, hi = depth.min(), depth.max()
                if hi > lo:
                    depth = (depth - lo) / (hi - lo)
                else:
                    depth = np.ones_like(depth) * 0.5
                return depth
            except Exception as exc:
                log.warning("DepthAnything inference failed (%s) — fallback.", exc)

        return self._geometry_prior(img_rgb)

    @staticmethod
    def _geometry_prior(img_rgb: np.ndarray) -> np.ndarray:
        """Fast geometry-based depth: dark=far, bright=near + vertical gradient."""
        h, w = img_rgb.shape[:2]
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        # sharpness proxy
        lap = cv2.Laplacian(gray, cv2.CV_32F)
        sharp = np.abs(lap)
        sharp = (sharp - sharp.min()) / (sharp.max() + 1e-6)
        # vertical gradient (objects near floor are closer)
        yg = np.linspace(0.3, 1.0, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32)
        depth = 0.5 * sharp + 0.3 * gray + 0.2 * yg
        lo, hi = depth.min(), depth.max()
        return (depth - lo) / (hi - lo + 1e-6)


# ═════════════════════════════════════════════════════════════════════════════
#  SCENE BUILDER
# ═════════════════════════════════════════════════════════════════════════════

# camera field of view (degrees)
FOV_DEG = 60.0
# downsample image before point-cloud construction (speed vs quality)
MAX_DIM = int(os.environ.get("RECON_MAX_DIM", "1024"))
# Poisson depth parameter – higher = more detail, slower
POISSON_DEPTH = int(os.environ.get("RECON_POISSON_DEPTH", "10"))
VOXEL_SIZE = float(os.environ.get("RECON_VOXEL_SIZE", "0.025"))
MESH_SMOOTH_ITERATIONS = int(os.environ.get("RECON_MESH_SMOOTH_ITERATIONS", "2"))
# minimum cluster size for DBSCAN
MIN_CLUSTER_PTS = 50


def _load_image(path: str) -> np.ndarray:
    """Load image as RGB numpy array, resize so longest side ≤ MAX_DIM."""
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    if max(h, w) > MAX_DIM:
        scale = MAX_DIM / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _build_point_cloud(img: np.ndarray, depth: np.ndarray, o3d):
    """
    Back-project image pixels into 3D using pinhole model.
    Returns an Open3D PointCloud with colours.
    """
    h, w = img.shape[:2]
    fov  = np.deg2rad(FOV_DEG)
    fx   = w / (2.0 * np.tan(fov / 2.0))
    fy   = fx
    cx, cy = w / 2.0, h / 2.0

    # --- depth in metres: map [0,1] → [0.5, 10] m (closer to camera = larger depth value)
    z = 0.5 + depth * 9.5          # shape H×W, z > 0

    # pixel grid
    u = np.arange(w, dtype=np.float32)
    v = np.arange(h, dtype=np.float32)
    uu, vv = np.meshgrid(u, v)     # H×W

    X = (uu - cx) / fx * z
    Y = (vv - cy) / fy * z         # Y points down
    Z =  z                          # Z points into scene

    pts   = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    cols  = img.reshape(-1, 3).astype(np.float64) / 255.0

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.colors = o3d.utility.Vector3dVector(cols)
    return pcd


def _poisson_mesh(pcd, o3d):
    """
    Estimate normals → Poisson Surface Reconstruction → trimmed mesh.
    Returns (mesh, ok:bool).
    """
    try:
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.3, max_nn=30)
        )
        pcd.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=POISSON_DEPTH, width=0, scale=1.1, linear_fit=False
        )
        # trim low-density vertices (artifacts on the boundary)
        dens = np.asarray(densities)
        thresh = np.percentile(dens, 10)
        verts_to_remove = dens < thresh
        mesh.remove_vertices_by_mask(verts_to_remove)
        if MESH_SMOOTH_ITERATIONS > 0:
            mesh = mesh.filter_smooth_taubin(number_of_iterations=MESH_SMOOTH_ITERATIONS)
        mesh.compute_vertex_normals()
        return mesh, True
    except Exception as exc:
        log.warning("Poisson failed (%s) — falling back to voxel mesh.", exc)
        return None, False


def _voxel_mesh(pcd, o3d, trimesh_mod):
    """
    Fallback: voxelise point cloud → solid box mesh per voxel.
    Returns Open3D TriangleMesh.
    """
    pts  = np.asarray(pcd.points)
    cols = np.asarray(pcd.colors)

    # adaptive voxel size
    extent = pts.max(axis=0) - pts.min(axis=0)
    vsize  = float(max(extent)) / 80.0

    vg = o3d.geometry.VoxelGrid.create_from_point_cloud(pcd, voxel_size=vsize)
    voxels = vg.get_voxels()

    if not voxels:
        # degenerate — just return a flat coloured mesh
        mesh = o3d.geometry.TriangleMesh.create_sphere(radius=0.5)
        mesh.paint_uniform_color([0.6, 0.6, 0.6])
        mesh.compute_vertex_normals()
        return mesh

    # build one box per voxel using trimesh then merge
    if trimesh_mod is not None:
        boxes = []
        for vox in voxels:
            centre = vg.get_voxel_center_coordinate(vox.grid_index)
            col    = vox.color[:3]
            b = trimesh_mod.creation.box(extents=[vsize]*3)
            b.apply_translation(centre)
            b.visual.vertex_colors = np.tile(
                (np.array(col) * 255).astype(np.uint8), (len(b.vertices), 1)
            )
            boxes.append(b)
        merged = trimesh_mod.util.concatenate(boxes)
        # convert trimesh → open3d
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices  = o3d.utility.Vector3dVector(merged.vertices)
        mesh.triangles = o3d.utility.Vector3iVector(merged.faces)
        if hasattr(merged.visual, 'vertex_colors') and merged.visual.vertex_colors is not None:
            vc = merged.visual.vertex_colors[:, :3].astype(np.float64) / 255.0
            mesh.vertex_colors = o3d.utility.Vector3dVector(vc)
        mesh.compute_vertex_normals()
        return mesh
    else:
        # trimesh not available — plain coloured box mesh via open3d
        mesh = o3d.geometry.TriangleMesh()
        all_v, all_t, all_c = [], [], []
        base_box = o3d.geometry.TriangleMesh.create_box(vsize, vsize, vsize)
        bv = np.asarray(base_box.vertices)
        bt = np.asarray(base_box.triangles)
        for vox in voxels:
            centre = vg.get_voxel_center_coordinate(vox.grid_index)
            offset = len(all_v)
            verts  = bv + (centre - np.array([vsize/2]*3))
            col    = list(vox.color[:3])
            all_v.extend(verts.tolist())
            all_t.extend((bt + offset).tolist())
            all_c.extend([col] * len(verts))
        mesh.vertices      = o3d.utility.Vector3dVector(np.array(all_v))
        mesh.triangles     = o3d.utility.Vector3iVector(np.array(all_t))
        mesh.vertex_colors = o3d.utility.Vector3dVector(np.array(all_c))
        mesh.compute_vertex_normals()
        return mesh


def _transfer_vertex_colours(mesh, pcd, o3d):
    """Paint mesh vertices with nearest-neighbour colour from the point cloud."""
    try:
        pcd_tree = o3d.geometry.KDTreeFlann(pcd)
        pc       = np.asarray(pcd.colors)
        verts    = np.asarray(mesh.vertices)
        colours  = np.zeros_like(verts)
        for i, v in enumerate(verts):
            _, idx, _ = pcd_tree.search_knn_vector_3d(v, 1)
            colours[i] = pc[idx[0]]
        mesh.vertex_colors = o3d.utility.Vector3dVector(colours)
    except Exception as exc:
        log.warning("Colour transfer failed: %s", exc)
    return mesh


def _dbscan_clusters(pcd, o3d) -> list[dict]:
    """Run DBSCAN and return list of cluster metadata dicts."""
    try:
        pts   = np.asarray(pcd.points)
        cols  = np.asarray(pcd.colors)
        labels = np.array(pcd.cluster_dbscan(eps=0.3, min_points=MIN_CLUSTER_PTS, print_progress=False))
        clusters = []
        for lbl in sorted(set(labels)):
            if lbl < 0:
                continue
            mask   = labels == lbl
            c_pts  = pts[mask]
            c_cols = cols[mask]
            centroid = c_pts.mean(axis=0).tolist()
            colour   = (c_cols.mean(axis=0) * 255).astype(int).tolist()
            aabb_min = c_pts.min(axis=0).tolist()
            aabb_max = c_pts.max(axis=0).tolist()
            clusters.append({
                "id":       lbl,
                "centroid": centroid,
                "colour":   colour,
                "aabb_min": aabb_min,
                "aabb_max": aabb_max,
                "count":    int(mask.sum()),
            })
        return clusters
    except Exception as exc:
        log.warning("DBSCAN clustering failed: %s", exc)
        return []


def _save_depth_map(depth: np.ndarray, out_path: str):
    """Save a false-colour depth map as PNG."""
    d8 = (depth * 255).astype(np.uint8)
    coloured = cv2.applyColorMap(d8, cv2.COLORMAP_TURBO)
    cv2.imwrite(out_path, coloured)


def _write_ascii_ply(vertices: np.ndarray, faces: np.ndarray, rgb: np.ndarray, out_path: str) -> bool:
    """Write a coloured triangle mesh as ASCII PLY without optional mesh libraries."""
    try:
        vertices = np.asarray(vertices, dtype=np.float32)
        faces = np.asarray(faces, dtype=np.int64)
        rgb = np.asarray(rgb, dtype=np.uint8)
        with open(out_path, "w", encoding="ascii", newline="\n") as fh:
            fh.write("ply\n")
            fh.write("format ascii 1.0\n")
            fh.write(f"element vertex {len(vertices)}\n")
            fh.write("property float x\n")
            fh.write("property float y\n")
            fh.write("property float z\n")
            fh.write("property uchar red\n")
            fh.write("property uchar green\n")
            fh.write("property uchar blue\n")
            fh.write(f"element face {len(faces)}\n")
            fh.write("property list uchar int vertex_indices\n")
            fh.write("end_header\n")
            for vertex, colour in zip(vertices, rgb):
                fh.write(
                    f"{vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f} "
                    f"{int(colour[0])} {int(colour[1])} {int(colour[2])}\n"
                )
            for face in faces:
                fh.write(f"3 {int(face[0])} {int(face[1])} {int(face[2])}\n")
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except Exception as exc:
        log.warning("Plain PLY export failed: %s", exc)
        return False


def _mesh_to_glb(mesh, o3d, out_path: str) -> bool:
    """Write mesh as GLB. Returns True on success."""
    trimesh_mod = _import_trimesh()
    if trimesh_mod is None:
        log.warning("trimesh not installed — cannot export GLB.")
        return False
    try:
        verts  = np.asarray(mesh.vertices)
        tris   = np.asarray(mesh.triangles)
        cols   = np.asarray(mesh.vertex_colors) if mesh.has_vertex_colors() else None

        tm = trimesh_mod.Trimesh(vertices=verts, faces=tris, process=False)
        if cols is not None:
            rgba = np.ones((len(verts), 4), dtype=np.uint8) * 255
            rgba[:, :3] = (cols * 255).astype(np.uint8)
            tm.visual = trimesh_mod.visual.ColorVisuals(vertex_colors=rgba, mesh=tm)

        tm.export(out_path)
        log.info("GLB written: %s  (%.1f KB)", out_path, Path(out_path).stat().st_size / 1024)
        return True
    except Exception as exc:
        log.warning("GLB export failed (%s).", exc)
        traceback.print_exc()
        return False


def _mesh_to_ply(mesh, o3d, out_path: str) -> bool:
    """Write mesh as PLY. Returns True on success."""
    try:
        o3d.io.write_triangle_mesh(out_path, mesh)
        log.info("PLY written: %s  (%.1f KB)", out_path, Path(out_path).stat().st_size / 1024)
        return True
    except Exception as exc:
        log.warning("PLY export failed (%s).", exc)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def _build_trimesh_surface_scene(image_path: str, glb_out: str, ply_out: str, depth_out: str) -> dict:
    """Fallback solid mesh path that avoids Open3D entirely."""
    trimesh_mod = _import_trimesh()

    img = _load_image(image_path)
    surface_dim = int(os.environ.get("RECON_SURFACE_DIM", "720"))
    depth_scale = float(os.environ.get("RECON_DEPTH_SCALE", "1.5"))
    h, w = img.shape[:2]
    if max(h, w) > surface_dim:
        scale = surface_dim / max(h, w)
        img = cv2.resize(img, (max(2, int(w * scale)), max(2, int(h * scale))), interpolation=cv2.INTER_AREA)

    depth = DepthEstimator.get().estimate(img)
    try:
        _save_depth_map(depth, depth_out)
    except Exception as exc:
        log.warning("Could not save fallback depth map: %s", exc)

    h, w = img.shape[:2]
    x = np.linspace(-4.8, 4.8, w, dtype=np.float32)
    y = np.linspace(3.2, -3.2, h, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    zz = (depth.astype(np.float32) - 0.5) * depth_scale
    vertices = np.column_stack([xx.reshape(-1), yy.reshape(-1), zz.reshape(-1)])

    grid = np.arange(h * w, dtype=np.int64).reshape(h, w)
    faces_a = np.column_stack([
        grid[:-1, :-1].reshape(-1),
        grid[1:, :-1].reshape(-1),
        grid[:-1, 1:].reshape(-1),
    ])
    faces_b = np.column_stack([
        grid[:-1, 1:].reshape(-1),
        grid[1:, :-1].reshape(-1),
        grid[1:, 1:].reshape(-1),
    ])
    faces = np.vstack([faces_a, faces_b])

    rgba = np.ones((len(vertices), 4), dtype=np.uint8) * 255
    rgba[:, :3] = img.reshape(-1, 3)
    glb_ok = False
    if trimesh_mod is not None:
        mesh = trimesh_mod.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual = trimesh_mod.visual.ColorVisuals(vertex_colors=rgba, mesh=mesh)
        try:
            mesh.export(glb_out)
            glb_ok = Path(glb_out).exists()
        except Exception as exc:
            log.warning("Fallback GLB export failed: %s", exc)

        ply_ok = False
        try:
            mesh.export(ply_out)
            ply_ok = True
        except Exception as exc:
            log.warning("Fallback PLY export failed: %s", exc)
    else:
        log.warning("trimesh not installed; exporting PLY-only reconstruction.")
        ply_ok = _write_ascii_ply(vertices, faces, rgba[:, :3], ply_out)

    clusters = [{
        "id": 0,
        "centroid": vertices.mean(axis=0).tolist(),
        "colour": rgba[:, :3].mean(axis=0).astype(int).tolist(),
        "aabb_min": vertices.min(axis=0).tolist(),
        "aabb_max": vertices.max(axis=0).tolist(),
        "count": int(len(vertices)),
    }]

    return {
        "total_points": int(len(vertices)),
        "num_clusters": len(clusters),
        "clusters": clusters,
        "glb_ok": glb_ok,
        "ply_ok": ply_ok,
    }


def build_scene(
    image_path: str,
    glb_out: str,
    ply_out: str,
    depth_out: str,
) -> dict:
    """
    Full pipeline: image → depth → point cloud → mesh → GLB/PLY.

    Returns a metadata dict:
        {
            "total_points": int,
            "num_clusters": int,
            "clusters":     list[dict],
            "glb_ok":       bool,
            "ply_ok":       bool,
        }
    """
    if os.environ.get("ENABLE_OPEN3D_RECONSTRUCTION", "0") != "1":
        return _build_trimesh_surface_scene(image_path, glb_out, ply_out, depth_out)

    o3d = _import_open3d()
    if o3d is None:
        return _build_trimesh_surface_scene(image_path, glb_out, ply_out, depth_out)

    trimesh_mod = _import_trimesh()

    # 1. Load & resize image
    img = _load_image(image_path)
    h, w = img.shape[:2]
    log.info("Image loaded: %dx%d", w, h)

    # 2. Estimate depth
    depth = DepthEstimator.get().estimate(img)
    log.info("Depth estimated: min=%.3f max=%.3f", depth.min(), depth.max())

    # 3. Save depth map
    try:
        _save_depth_map(depth, depth_out)
    except Exception as exc:
        log.warning("Could not save depth map: %s", exc)

    # 4. Build point cloud
    pcd = _build_point_cloud(img, depth, o3d)
    log.info("Point cloud: %d points", len(pcd.points))

    # 5. Downsample for speed
    pcd = pcd.voxel_down_sample(voxel_size=VOXEL_SIZE)
    log.info("After voxel downsample: %d points", len(pcd.points))

    # 6. Remove outliers
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=30, std_ratio=2.2)
    log.info("After outlier removal: %d points", len(pcd.points))

    # 7. DBSCAN clusters (before meshing, on point cloud)
    clusters = _dbscan_clusters(pcd, o3d)
    log.info("Clusters found: %d", len(clusters))

    # 8. Surface reconstruction
    mesh, poisson_ok = _poisson_mesh(pcd, o3d)
    if not poisson_ok or mesh is None or len(np.asarray(mesh.triangles)) < 100:
        log.info("Using voxel mesh fallback.")
        mesh = _voxel_mesh(pcd, o3d, trimesh_mod)
    else:
        # Transfer colours from point cloud to Poisson mesh
        mesh = _transfer_vertex_colours(mesh, pcd, o3d)

    log.info("Mesh: %d vertices, %d triangles",
             len(np.asarray(mesh.vertices)),
             len(np.asarray(mesh.triangles)))

    # 9. Export
    glb_ok = _mesh_to_glb(mesh, o3d, glb_out)
    ply_ok = _mesh_to_ply(mesh, o3d, ply_out)

    return {
        "total_points": len(np.asarray(pcd.points)),
        "num_clusters": len(clusters),
        "clusters":     clusters,
        "glb_ok":       glb_ok,
        "ply_ok":       ply_ok,
    }
