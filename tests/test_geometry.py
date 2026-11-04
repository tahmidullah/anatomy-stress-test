import numpy as np
import pytest
from anatomy_lab.dataset import make_synthetic_demo
from anatomy_lab.geometry import StressExperiment, OFFSETS_MM, mesh_geometry


def test_synthetic_dataset_contains_nonempty_structures():
    d=make_synthetic_demo()
    assert d.kind=='synthetic'
    assert len(d.structures)==8
    assert d.image.shape==(116,112,102)
    for name in d.structures:
        assert d.mask(name).sum()>0


def test_zero_offset_is_exact_identity():
    d=make_synthetic_demo()
    m=d.mask('liver')
    e=StressExperiment.from_mask(m,d.spacing)
    assert np.array_equal(e.offset_mask(0),e.original)
    assert e.metrics(0)['delta_ml']==0
    assert e.metrics(0)['delta_pct']==0
    assert e.metrics(0)['voxels']==m.sum()


def test_volume_monotonic_over_all_offsets():
    d=make_synthetic_demo()
    exp=StressExperiment.from_mask(d.mask('kidney_left'),d.spacing)
    counts=[p['voxels'] for p in exp.curve()]
    assert all(x<=y for x,y in zip(counts,counts[1:]))
    assert len(counts)==13
    assert counts[0]<counts[6]<counts[-1]


def test_physical_voxel_volume():
    m=np.zeros((20,20,20),bool);m[8:10,8:10,8:10]=1
    exp=StressExperiment.from_mask(m,(2,3,4))
    assert exp.metrics(0)['baseline_ml']==pytest.approx(8*24/1000)


def test_boundary_offsets_are_limited():
    m=np.zeros((12,12,12),bool);m[3:9,3:9,3:9]=1
    exp=StressExperiment.from_mask(m,(1,1,1))
    with pytest.raises(ValueError):exp.offset_mask(3.5)
    with pytest.raises(ValueError):exp.offset_mask(float('nan'))


def test_mesh_is_physical_space_and_has_faces():
    m=np.zeros((20,20,20),bool);m[5:15,5:15,5:15]=1
    exp=StressExperiment.from_mask(m,(1.5,2.0,3.0))
    affine=np.diag([1.5,2,3,1])
    mesh=mesh_geometry(exp.original,exp.start,affine,step_size=2)
    assert len(mesh['x'])>0
    assert len(mesh['i'])>0
    assert min(mesh['x'])>=0
    assert max(mesh['z'])<=60


def test_erosion_and_expansion_at_scan_edge():
    m=np.zeros((22,24,30),bool);m[0:8,5:13,10:20]=1
    exp=StressExperiment.from_mask(m,(1,1,1))
    assert exp.touches_fov
    assert exp.offset_mask(2).sum()>exp.original.sum()
    assert exp.offset_mask(-2).sum()<exp.original.sum()
