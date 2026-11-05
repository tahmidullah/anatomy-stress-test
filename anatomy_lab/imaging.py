"""RGBA CT slice rendering with original vs perturbed mask boundaries."""
from __future__ import annotations
from io import BytesIO
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from .geometry import StressExperiment


def display_plane(array: np.ndarray, axis: str, index: int) -> np.ndarray:
    """Radiological viewing convention for canonical RAS+ voxel arrays.

    Axial: patient R at image left, A at top.
    Coronal: patient R at image left, S at top.
    Sagittal: A at image left, S at top.
    """
    if axis == "axial":
        cut = array[:, :, index]
    elif axis == "coronal":
        cut = array[:, index, :]
    elif axis == "sagittal":
        cut = array[index, :, :]
    else:
        raise ValueError(f"Unknown plane: {axis}")
    return np.flip(cut.T, axis=(0, 1))


def slice_png(image: np.ndarray, base_mask: np.ndarray, experiment: StressExperiment,
              axis: str, index: int, offset_mm: float, crosshair: tuple[int, int, int],
              window_low: float = -150, window_high: float = 250, overlay: bool = True, show_crosshair: bool = True) -> bytes:
    """Make one color PNG. Boundary overlays are visualization-only."""
    plane = display_plane(image, axis, index)
    gray = np.clip((plane - window_low) * 255 / (window_high - window_low), 0, 255).astype(np.uint8)
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    original = display_plane(base_mask, axis, index)
    altered_patch, (start_u, start_v) = experiment.local_plane(axis, index, offset_mm)
    altered = np.zeros(original.shape, dtype=bool)
    if altered_patch.size:
        # Use the same original 2D axis order and flips as display_plane.
        raw = np.zeros(plane.shape[::-1], dtype=bool)  # (first input axis, second input axis)
        raw[start_u:start_u + altered_patch.shape[0], start_v:start_v + altered_patch.shape[1]] = altered_patch
        altered = np.flip(raw.T, axis=(0, 1))

    if overlay:
        if altered.any():
            rgb[altered] = (rgb[altered].astype(np.float32) * .82 +
                            np.array([99, 122, 255]) * .18).astype(np.uint8)
        base_border = original & ~binary_erosion(original)
        edited_border = altered & ~binary_erosion(altered)
        rgb[base_border] = [224, 198, 255]
        rgb[edited_border] = [141, 163, 255]

    i, j, k = crosshair
    if axis == "axial":
        x, y = image.shape[0] - 1 - i, image.shape[1] - 1 - j
    elif axis == "coronal":
        x, y = image.shape[0] - 1 - i, image.shape[2] - 1 - k
    else:
        x, y = image.shape[1] - 1 - j, image.shape[2] - 1 - k
    if show_crosshair and 0 <= x < rgb.shape[1] and 0 <= y < rgb.shape[0]:
        # Subtle crosshair with 3-pixel center opening so anatomy remains visible.
        color = np.array([255, 255, 255], dtype=np.uint8)
        for xx in range(rgb.shape[1]):
            if abs(xx - x) > 2:
                rgb[y, xx] = (rgb[y, xx].astype(float) * .45 + color * .55).astype(np.uint8)
        for yy in range(rgb.shape[0]):
            if abs(yy - y) > 2:
                rgb[yy, x] = (rgb[yy, x].astype(float) * .45 + color * .55).astype(np.uint8)
    output = BytesIO()
    Image.fromarray(rgb).save(output, "PNG", optimize=True)
    return output.getvalue()
