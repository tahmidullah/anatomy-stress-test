"""Physical-distance boundary perturbations, volumetry and reproducible 3D meshes."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes


OFFSETS_MM = [round(-3.0 + i * 0.5, 1) for i in range(13)]


@dataclass
class StressExperiment:
    """Cropped Euclidean distance transforms to keep memory manageable.

    All calculations use the full-resolution binary mask, not display geometry.
    The local ROI includes a margin beyond the maximum supported offset.
    """
    original_count: int
    full_shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    start: tuple[int, int, int]
    stop: tuple[int, int, int]
    original: np.ndarray
    inside_distance: np.ndarray
    outside_distance: np.ndarray
    touches_fov: bool

    @classmethod
    def from_mask(cls, mask: np.ndarray, spacing, max_offset_mm: float = 3.0):
        mask = np.asarray(mask, dtype=bool)
        if mask.ndim != 3 or not mask.any():
            raise ValueError("Mask must be a non-empty 3D binary volume")
        spacing = tuple(float(x) for x in spacing)
        if any(not np.isfinite(x) or x <= 0 for x in spacing):
            raise ValueError("Voxel spacing must contain finite positive values")
        positions = np.where(mask)
        mins = [int(np.min(x)) for x in positions]
        maxs = [int(np.max(x)) + 1 for x in positions]
        start = tuple(max(0, m - int(np.ceil(max_offset_mm / s)) - 3) for m, s in zip(mins, spacing))
        stop = tuple(min(n, m + int(np.ceil(max_offset_mm / s)) + 3) for n, m, s in zip(mask.shape, maxs, spacing))
        roi = mask[tuple(slice(a, b) for a, b in zip(start, stop))].copy()
        touching = any(lo == 0 or hi == n for lo, hi, n in zip(mins, maxs, mask.shape))
        return cls(
            original_count=int(mask.sum()), full_shape=tuple(mask.shape), spacing=spacing,
            start=start, stop=stop, original=roi,
            inside_distance=ndi.distance_transform_edt(roi, sampling=spacing).astype(np.float32),
            outside_distance=ndi.distance_transform_edt(~roi, sampling=spacing).astype(np.float32),
            touches_fov=touching,
        )

    @property
    def voxel_volume_ml(self) -> float:
        return float(np.prod(self.spacing) / 1000)

    def offset_mask(self, offset_mm: float) -> np.ndarray:
        offset = float(offset_mm)
        if not np.isfinite(offset) or abs(offset) > 3.0001:
            raise ValueError("Supported boundary offsets are -3 to +3 mm")
        if abs(offset) < 1e-9:
            return self.original.copy()
        if offset > 0:
            # Existing mask + any background voxel whose center is within the offset.
            return self.original | (self.outside_distance <= offset + 1e-5)
        # Erosion: distance is measured from an interior center to nearest exterior center.
        return self.original & (self.inside_distance > -offset + 1e-5)

    def metrics(self, offset_mm: float) -> dict:
        count = int(self.offset_mask(offset_mm).sum())
        baseline = self.original_count * self.voxel_volume_ml
        current = count * self.voxel_volume_ml
        return {
            "offset_mm": float(offset_mm),
            "baseline_ml": round(baseline, 3),
            "current_ml": round(current, 3),
            "delta_ml": round(current - baseline, 3),
            "delta_pct": round(100 * (current / baseline - 1), 2),
            "voxels": count,
            "voxel_volume_mm3": round(self.voxel_volume_ml * 1000, 5),
            "touches_fov": self.touches_fov,
        }

    def curve(self) -> list[dict]:
        return [self.metrics(o) for o in OFFSETS_MM]

    def local_plane(self, axis: str, index: int, offset_mm: float) -> tuple[np.ndarray, tuple[int, int]]:
        """Return cropped 2D edited mask and placement in the full display plane.

        Plane arrays use (columns index, rows index) prior to display orientation flips.
        """
        axis_number = {"axial": 2, "coronal": 1, "sagittal": 0}[axis]
        if index < self.start[axis_number] or index >= self.stop[axis_number]:
            return np.zeros((0, 0), dtype=bool), (0, 0)
        roi = self.offset_mask(offset_mm)
        loc = index - self.start[axis_number]
        if axis == "axial":
            return roi[:, :, loc], (self.start[0], self.start[1])
        if axis == "coronal":
            return roi[:, loc, :], (self.start[0], self.start[2])
        return roi[loc, :, :], (self.start[1], self.start[2])


def mask_centroid(mask: np.ndarray) -> list[int]:
    counts = np.where(mask)
    if not len(counts[0]):
        raise ValueError("Cannot center on an empty mask")
    return [int(np.rint(np.mean(axis))) for axis in counts]


def mesh_geometry(local_mask: np.ndarray, start, affine, step_size: int = 2) -> dict:
    """Extract a display mesh with RAS physical coordinates and offset-aware origin.

    Mesh simplification does not affect computed volume metrics.
    """
    if not np.asarray(local_mask).any():
        return {"x": [], "y": [], "z": [], "i": [], "j": [], "k": []}
    mask = np.pad(np.asarray(local_mask, dtype=np.uint8), 1)
    verts, faces, _, _ = marching_cubes(mask, level=0.5, step_size=step_size, allow_degenerate=False)
    ijk = verts + np.asarray(start, dtype=float)[None, :] - 1
    world = ijk @ np.asarray(affine, dtype=float)[:3, :3].T + np.asarray(affine)[:3, 3]
    return {
        "x": np.round(world[:, 0], 3).tolist(),
        "y": np.round(world[:, 1], 3).tolist(),
        "z": np.round(world[:, 2], 3).tolist(),
        "i": faces[:, 0].tolist(), "j": faces[:, 1].tolist(), "k": faces[:, 2].tolist(),
    }
