import io
import gzip
import json
import zipfile
import numpy as np
import nibabel as nib
from fastapi.testclient import TestClient
from anatomy_lab.geometry import StressExperiment
from anatomy_lab.fragility import regional_map, organ_summary
from server import app


def test_regional_conservation_and_physical_units():
    mask = np.zeros((25,26,27), bool);mask[3:22,4:23,5:24]=True
    affine=np.diag([1.,2.,3.,1.])
    exp=StressExperiment.from_mask(mask,(1,2,3))
    values,regions,mesh=regional_map(exp,affine,2)
    assert sum(r['baseline_voxels'] for r in regions)==mask.sum()
    assert sum(r['lost_voxels'] for r in regions)==mask.sum()-exp.offset_mask(-2).sum()
    assert np.isnan(values[~exp.original]).all()
    assert np.isfinite(values[exp.original]).all()
    assert all(0<=x<=100 for x in mesh['intensity'])
    assert len(mesh['intensity'])==len(mesh['x'])
    assert np.isclose(sum(r['lost_ml'] for r in regions),sum(r['lost_voxels'] for r in regions)*.006)


def test_thin_structure_has_higher_loss():
    thick=np.zeros((30,30,30),bool);thick[5:25,5:25,5:25]=True
    thin=np.zeros_like(thick);thin[5:25,5:25,14:16]=True
    summaries=[organ_summary(StressExperiment.from_mask(m,(1,1,1)),2) for m in [thick,thin]]
    assert summaries[1]['loss_pct']==100
    assert summaries[1]['loss_pct']>summaries[0]['loss_pct']


def test_subvoxel_and_zero_shift_validation():
    mask=np.zeros((9,9,9),bool);mask[2:7,2:7,2:7]=True
    exp=StressExperiment.from_mask(mask,(2,2,2))
    values,_,_=regional_map(exp,np.diag([2.,2.,2.,1.]),.5)
    assert (values[exp.original]==0).all()
    with TestClient(app) as client:
        assert client.get('/api/fragility?organ=liver&distance=0').status_code==422
        assert client.get('/api/fragility?organ=missing').status_code==404


def test_export_roundtrip_and_ranking():
    with TestClient(app) as client:
        result=client.get('/api/fragility?organ=liver&distance=2')
        assert result.status_code==200
        data=result.json()
        response=client.get('/api/fragility/export?organ=liver&distance=2')
        assert response.status_code==200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            nii=nib.Nifti1Image.from_bytes(gzip.decompress(archive.read('regional_loss_pct.nii.gz')))
            settings=json.loads(archive.read('settings.json'))
            assert nii.shape==tuple(client.get('/api/meta').json()['shape'])
            assert np.allclose(nii.affine,settings['affine_ras_mm'])
            assert np.isclose(np.nanmean(nii.get_fdata()),data['summary']['loss_pct'],atol=.01)
            organs=json.loads(archive.read('organs.json'))['organs']
            assert len(organs)==8
            assert [r['span_pct'] for r in organs]==sorted([r['span_pct'] for r in organs],reverse=True)
