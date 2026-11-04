"""Synthetic abdomen and optional aligned NIfTI/TotalSegmentator input."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import numpy as np
from scipy.ndimage import gaussian_filter


PALETTE = {
    "liver": "#eaa4aa", "spleen": "#a6a1e9", "stomach": "#e9b48e",
    "kidney_left": "#d98b9e", "kidney_right": "#f0a57f",
    "aorta": "#f16d80", "inferior_vena_cava": "#7e9de5", "spine": "#dcd7c6",
}


@dataclass
class ScanDataset:
    image: np.ndarray
    affine: np.ndarray
    kind: str
    label: str
    masks: dict[str, np.ndarray] = field(default_factory=dict)
    mask_files: dict[str, Path] = field(default_factory=dict)
    source_path: Path | None = None
    _loaded: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    @property
    def spacing(self) -> tuple[float, float, float]:
        # Length of each voxel axis in physical space (handles rotated acquisitions).
        return tuple(float(x) for x in np.linalg.norm(self.affine[:3, :3], axis=0))

    @property
    def structures(self) -> list[str]:
        return sorted(set(self.masks) | set(self.mask_files))

    def mask(self, name: str) -> np.ndarray:
        if name in self.masks:
            return self.masks[name]
        if name not in self.mask_files:
            raise KeyError(f"Unknown structure: {name}")
        if name not in self._loaded:
            import nibabel as nib
            nii = nib.as_closest_canonical(nib.load(str(self.mask_files[name])))
            # No silent resampling: images and masks must share voxel geometry.
            if tuple(nii.shape[:3]) != self.image.shape or not np.allclose(
                nii.affine, self.affine, rtol=1e-4, atol=0.025
            ):
                raise ValueError(
                    f"Mask {name} does not match CT shape/affine. Align/resample "
                    "the image and mask with an established imaging tool first."
                )
            self._loaded[name] = np.asanyarray(nii.dataobj) > 0
        return self._loaded[name]


def make_synthetic_demo() -> ScanDataset:
    """Deterministic, anatomically illustrative (not anatomically validated) CT-like volume."""
    n = (116, 112, 102)
    spacing = (1.45, 1.45, 1.65)
    xx, yy, zz = np.ogrid[:n[0], :n[1], :n[2]]

    def ellipsoid(x, y, z, a, b, c):
        return ((xx-x)/a)**2 + ((yy-y)/b)**2 + ((zz-z)/c)**2 <= 1

    body = ellipsoid(58, 54, 50, 50, 44, 49)
    image = np.full(n, -920.0, dtype=np.float32)
    image[body] = 20.0
    # Synthetic tissue regions, designed for visible grayscale anatomical context.
    masks = {
        "liver": ellipsoid(77, 68, 61, 23, 20, 25),
        "spleen": ellipsoid(29, 66, 63, 10, 14, 19),
        "stomach": ellipsoid(43, 76, 67, 13, 11, 15),
        "kidney_left": ellipsoid(37, 44, 39, 10, 9, 15),
        "kidney_right": ellipsoid(78, 44, 39, 10, 9, 15),
        "aorta": (((xx-56.5)/4.4)**2 + ((yy-53)/4.3)**2 <= 1) & (zz >= 13) & (zz <= 91),
        "inferior_vena_cava": (((xx-64)/4.8)**2 + ((yy-53)/5.1)**2 <= 1) & (zz >= 13) & (zz <= 88),
        "spine": ellipsoid(57, 29, 51, 13, 12, 45),
    }
    values = {
        "liver": 68, "spleen": 53, "stomach": 0,
        "kidney_left": 43, "kidney_right": 43,
        "aorta": 155, "inferior_vena_cava": 130, "spine": 230,
    }
    for name, mask in masks.items():
        image[mask] = values[name]
    rng = np.random.default_rng(17)
    noise = gaussian_filter(rng.standard_normal(n).astype(np.float32), 0.6)
    image += noise * 18
    image[~body] = -920 + noise[~body] * 4
    affine = np.diag([*spacing, 1.0]).astype(float)
    affine[:3, 3] = [-84.1, -81.2, -84.15]
    return ScanDataset(
        image=image, affine=affine, kind="synthetic", label="Synthetic abdomen (not patient imaging)",
        masks={key: val.astype(bool) for key, val in masks.items()},
    )


def load_nifti_folder(folder: str | Path) -> ScanDataset:
    """Read a TotalSegmentator-style subject folder: ct.nii.gz, segmentations/*.nii.gz."""
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("Install nibabel (pip install -r requirements.txt) for NIfTI support") from exc
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Dataset folder does not exist: {folder}")
    ct_path = next((p for p in (folder / "ct.nii.gz", folder / "ct.nii") if p.exists()), None)
    if ct_path is None:
        raise FileNotFoundError("Expected ct.nii.gz (or ct.nii) in ANATOMY_DATASET_DIR")
    segmentations = folder / "segmentations"
    files = sorted([*segmentations.glob("*.nii.gz"), *segmentations.glob("*.nii")])
    if not files:
        raise FileNotFoundError("Expected NIfTI structure masks in segmentations/")
    mask_files = {p.name.removesuffix(".nii.gz").removesuffix(".nii"): p for p in files}
    nii = nib.as_closest_canonical(nib.load(str(ct_path)))
    if len(nii.shape) != 3:
        raise ValueError("Only 3D CT volumes are supported")
    if np.prod(nii.shape, dtype=np.int64) > 200_000_000:
        raise ValueError("This CT is too large for the demonstration server (>200 million voxels)")
    arr = np.asarray(nii.get_fdata(dtype=np.float32))
    return ScanDataset(
        image=arr, affine=np.asarray(nii.affine, dtype=float),
        kind="nifti", label="User-provided local NIfTI scan",
        mask_files=mask_files, source_path=folder,
    )


def load_configured_dataset() -> ScanDataset:
    path = os.environ.get("ANATOMY_DATASET_DIR", "").strip()
    return load_nifti_folder(path) if path else make_synthetic_demo()
