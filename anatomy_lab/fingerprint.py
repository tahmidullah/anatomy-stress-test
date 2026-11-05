"""Versioned, portable descriptions of segmentation boundary sensitivity."""
from datetime import datetime, timezone
import hashlib
import uuid
import numpy as np
from pydantic import BaseModel, Field, model_validator
from typing import List, Literal
from .geometry import OFFSETS_MM

PROTOCOL = 'voxel-center-edt-v1; offsets=-3:0.5:3; regions=10mm; regional-erosion=2mm'

class Point(BaseModel):
    offset_mm: float = Field(allow_inf_nan=False)
    voxels: int = Field(ge=0)

class Profile(BaseModel):
    schema_version: Literal[1] = 1
    captured_offset_mm: float = Field(0, ge=-3, le=3, allow_inf_nan=False)
    protocol: Literal['voxel-center-edt-v1; offsets=-3:0.5:3; regions=10mm; regional-erosion=2mm'] = PROTOCOL
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    organ: str = Field(min_length=1, max_length=120)
    created_at: str = Field(max_length=50)
    source: str = Field(max_length=30)
    scan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    mask_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    shape: List[int] = Field(min_length=3, max_length=3)
    spacing_mm: List[float] = Field(min_length=3, max_length=3)
    affine: List[List[float]] = Field(min_length=4, max_length=4)
    touches_fov: bool
    curve: List[Point] = Field(min_length=13, max_length=13)
    regional_volume_pct: List[float] = Field(min_length=5,max_length=5)
    region_count: int = Field(ge=1)
    small_region_count: int = Field(ge=0)

    @model_validator(mode='after')
    def validate_measurements(self):
        if self.captured_offset_mm * 2 != round(self.captured_offset_mm * 2): raise ValueError('Invalid capture displacement.')
        if not self.name.strip(): raise ValueError('Profile name is empty.')
        try:
            timestamp=datetime.fromisoformat(self.created_at.replace('Z','+00:00'))
            if timestamp.tzinfo is None: raise ValueError('Timestamp must have a timezone.')
        except ValueError as exc:
            raise ValueError('Invalid profile timestamp.') from exc
        spacing=np.asarray(self.spacing_mm); affine=np.asarray(self.affine)
        if any(x<=0 for x in self.shape) or not np.isfinite(spacing).all() or np.any(spacing<=0):
            raise ValueError('Invalid profile dimensions or spacing.')
        if affine.shape!=(4,4) or not np.isfinite(affine).all() or not np.allclose(affine[3],[0,0,0,1]):
            raise ValueError('Invalid affine.')
        if not np.allclose((affine[:3,:3]/spacing).T @ (affine[:3,:3]/spacing),np.eye(3),atol=1e-4):
            raise ValueError('Sheared grids are unsupported.')
        if not np.allclose(np.linalg.norm(affine[:3,:3],axis=0),spacing):
            raise ValueError('Affine and spacing disagree.')
        counts=[p.voxels for p in self.curve]
        if [p.offset_mm for p in self.curve]!=OFFSETS_MM or counts!=sorted(counts) or counts[6]<=0 or max(counts)>np.prod(self.shape,dtype=float):
            raise ValueError('Invalid response curve.')
        hist=np.asarray(self.regional_volume_pct)
        if not np.isfinite(hist).all() or np.any(hist<0) or np.any(hist>100) or not np.isclose(hist.sum(),100,atol=.001):
            raise ValueError('Regional distribution must sum to 100%.')
        if self.small_region_count>self.region_count: raise ValueError('Invalid region counts.')
        return self


def digest(array):
    data=np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(data).cast('B')).hexdigest()


def make_profile(dataset, exp, organ, name, captured_offset=0):
    if not exp.original_count: raise ValueError('Paint or select a nonempty segment first.')
    if not name.strip(): raise ValueError('Enter a profile name.')
    if not hasattr(dataset,'fingerprint_scan_hash'):
        dataset.fingerprint_scan_hash=digest(dataset.image)
    indices=np.asarray(np.where(exp.original)).T
    cells=np.floor((indices+np.asarray(exp.start))*np.asarray(exp.spacing)/10).astype(int)
    unique,inverse,counts=np.unique(cells,axis=0,return_inverse=True,return_counts=True)
    lost=~exp.offset_mask(-2)[tuple(indices.T)]
    losses=np.bincount(inverse,weights=lost,minlength=len(counts))/counts*100
    hist,_=np.histogram(losses,bins=[0,20,40,60,80,100],weights=counts)
    return Profile(captured_offset_mm=captured_offset,id=uuid.uuid4().hex,name=name.strip(),organ=organ,created_at=datetime.now(timezone.utc).isoformat(),
        source=dataset.kind,scan_hash=dataset.fingerprint_scan_hash,mask_hash=digest(np.packbits(dataset.mask(organ))),
        shape=list(dataset.image.shape),spacing_mm=list(exp.spacing),affine=dataset.affine.tolist(),touches_fov=exp.touches_fov,
        curve=[Point(offset_mm=d,voxels=int(exp.offset_mask(d).sum())) for d in OFFSETS_MM],
        regional_volume_pct=(hist/exp.original_count*100).tolist(),region_count=len(unique),small_region_count=int((counts<50).sum()))


def summary(profile):
    baseline=profile.curve[6].voxels
    changes=[100*(p.voxels/baseline-1) for p in profile.curve]
    fixed=[]
    for d in [1,2,3]:
        loss=-changes[6-2*d];gain=changes[6+2*d]
        fixed.append({'distance_mm':d,'loss_pct':loss,'gain_pct':gain,'span_pct':loss+gain,'asymmetry_pp':gain-loss})
    return {'baseline_ml':baseline*float(np.prod(profile.spacing_mm))/1000,'changes_pct':changes,'fixed':fixed}


def compare(a,b):
    same_grid=a.shape==b.shape and np.allclose(a.affine,b.affine,rtol=0,atol=1e-5)
    same_scan=same_grid and a.scan_hash==b.scan_hash
    sa,sb=summary(a),summary(b)
    return {'same_grid':same_grid,'same_scan':same_scan,'same_mask':same_scan and a.mask_hash==b.mask_hash,
            'a':sa,'b':sb,'delta_pp':[y-x for x,y in zip(sa['changes_pct'],sb['changes_pct'])],
            'warnings':([] if same_scan else ['Different scan content or geometry: interpret as a descriptive comparison, not paired validation.'])+
                (['At least one mask reaches the scan boundary; expansion may be clipped.'] if a.touches_fov or b.touches_fov else [])+
                ['Confirm both profiles represent the intended anatomy. These curves do not measure segmentation accuracy.']}
