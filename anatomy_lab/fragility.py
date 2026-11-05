"""Descriptive segmentation sensitivity, measured on the original voxel grid."""
import numpy as np
from .geometry import StressExperiment, mesh_geometry

METHOD = 'Regional fraction of baseline voxels removed by inward Euclidean voxel-center offset'


def regional_map(exp, affine, distance=2.0, cell_mm=10.0):
    if not np.isfinite(distance) or distance <= 0 or distance > 3:
        raise ValueError('Distance must be greater than zero and at most 3 mm.')
    # Grid anchored to full-volume voxel index zero, with physical axis lengths.
    indices = np.asarray(np.where(exp.original)).T
    full_indices = indices + np.asarray(exp.start)
    cells = np.floor(full_indices * np.asarray(exp.spacing) / cell_mm).astype(int)
    unique, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    eroded = exp.offset_mask(-distance)
    lost = ~eroded[tuple(indices.T)]
    removed = np.bincount(inverse, weights=lost, minlength=len(counts)).astype(int)
    percentages = 100.0 * removed / counts
    values = np.full(exp.original.shape, np.nan, dtype=np.float32)
    values[tuple(indices.T)] = percentages[inverse]
    rows = []
    for index, cell in enumerate(unique):
        rows.append({'cell': cell.tolist(), 'baseline_voxels': int(counts[index]),
                     'lost_voxels': int(removed[index]), 'loss_pct': float(percentages[index]),
                     'baseline_ml': float(counts[index] * exp.voxel_volume_ml),
                     'lost_ml': float(removed[index] * exp.voxel_volume_ml),
                     'small_sample': bool(counts[index] < 50)})
    mesh = mesh_geometry(exp.original, exp.start, affine, step_size=1)
    xyz = np.column_stack([mesh[key] for key in ('x', 'y', 'z')])
    ijk = np.rint(np.einsum('nj,ij->ni', xyz - affine[:3, 3], np.linalg.inv(affine[:3, :3]))).astype(int)
    vertex_cells = np.floor(ijk * np.asarray(exp.spacing) / cell_mm).astype(int)
    lookup = {tuple(cell): float(value) for cell, value in zip(unique, percentages)}
    # Boundary vertices can round outside the region; use nearest occupied voxel.
    from scipy.spatial import cKDTree
    tree = cKDTree(full_indices * np.asarray(exp.spacing))
    _, nearest = tree.query(ijk * np.asarray(exp.spacing))
    mesh['intensity'] = [lookup.get(tuple(cell), float(percentages[inverse[n]])) for cell, n in zip(vertex_cells, nearest)]
    return values, rows, mesh


def organ_summary(exp, distance):
    loss = exp.metrics(-distance)
    gain = exp.metrics(distance)
    return {'baseline_ml': loss['baseline_ml'], 'loss_pct': -loss['delta_pct'],
            'gain_pct': gain['delta_pct'], 'span_pct': gain['delta_pct'] - loss['delta_pct'],
            'loss_ml': -loss['delta_ml'], 'gain_ml': gain['delta_ml'],
            'touches_fov': exp.touches_fov,
            'below_voxel_spacing': distance < min(exp.spacing)}
