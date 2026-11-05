"""Slice-local brush editing in physical millimeters."""
import numpy as np


def brush(mask, spacing, axis, index, points, radius_mm, erase=False):
    axes = {'axial': (2, 0, 1), 'coronal': (1, 0, 2), 'sagittal': (0, 1, 2)}
    fixed, u, v = axes[axis]
    if not 0 <= index < mask.shape[fixed]:
        raise ValueError('Slice index is out of range.')
    if not points or len(points) > 2000:
        raise ValueError('A stroke needs 1–2000 points.')
    if not np.isfinite(radius_mm) or not .5 <= radius_mm <= 30:
        raise ValueError('Brush radius must be 0.5–30 mm.')
    points = np.asarray(points, dtype=float)
    if points.shape != (len(points), 2) or not np.isfinite(points).all():
        raise ValueError('Invalid brush coordinates.')
    if np.any(points < 0) or np.any(points[:,0] >= mask.shape[u]) or np.any(points[:,1] >= mask.shape[v]):
        raise ValueError('Brush coordinates are outside the image.')
    result = mask.copy()
    plane = [slice(None)] * 3; plane[fixed] = index
    view = result[tuple(plane)]
    samples = [points[0]]
    for a,b in zip(points[:-1],points[1:]):
        steps = max(1, int(np.ceil(np.linalg.norm((b-a)*np.array([spacing[u],spacing[v]])) / max(.25,radius_mm/2))))
        if steps > 20000: raise ValueError('Stroke is too long.')
        samples.extend(np.linspace(a,b,steps+1)[1:])
    for x,y in samples:
        lo = np.maximum(0,np.floor([x-radius_mm/spacing[u],y-radius_mm/spacing[v]]).astype(int))
        hi = np.minimum(view.shape,np.ceil([x+radius_mm/spacing[u],y+radius_mm/spacing[v]]).astype(int)+1)
        xx,yy=np.ogrid[lo[0]:hi[0],lo[1]:hi[1]]
        disk=((xx-x)*spacing[u])**2+((yy-y)*spacing[v])**2 <= radius_mm**2
        patch=view[lo[0]:hi[0],lo[1]:hi[1]]
        patch[disk]=not erase
    return result
