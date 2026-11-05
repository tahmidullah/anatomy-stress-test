import copy
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from anatomy_lab.dataset import ScanDataset
from anatomy_lab.geometry import StressExperiment
from anatomy_lab.fingerprint import make_profile, compare, summary, Profile
from server import app, SESSIONS


def sample(spacing=(1,2,3)):
    shape=(22,23,24);mask=np.zeros(shape,bool);mask[4:18,4:19,4:20]=True
    dataset=ScanDataset(np.zeros(shape,np.float32),np.diag([*spacing,1.]),'synthetic','test',masks={'organ':mask})
    return dataset,StressExperiment.from_mask(mask,spacing)


def test_snapshot_exact_curve_and_distribution():
    dataset,exp=sample();p=make_profile(dataset,exp,'organ','Original')
    assert sum(p.regional_volume_pct)==pytest.approx(100)
    assert summary(p)['baseline_ml']==pytest.approx(exp.original_count*.006)
    assert all(point.voxels==exp.offset_mask(point.offset_mm).sum() for point in p.curve)
    assert Profile.model_validate_json(p.model_dump_json())==p
    original=p.model_dump_json()
    dataset.masks['organ']=dataset.mask('organ').copy();dataset.masks['organ'][8:12,8:12,8:12]=False
    q=make_profile(dataset,StressExperiment.from_mask(dataset.mask('organ'),dataset.spacing),'organ','Edited')
    result=compare(p,q)
    assert result['same_scan'] and not result['same_mask']
    assert p.model_dump_json()==original
    assert any(abs(d)>0 for d in result['delta_pp'])


def test_identical_profiles_and_grid_content_mismatch():
    dataset,exp=sample();a=make_profile(dataset,exp,'organ','A')
    assert compare(a,a)['delta_pp']==[0]*13
    assert compare(a,a)['same_mask']
    other,exp2=sample((2,2,3));b=make_profile(other,exp2,'organ','B')
    assert not compare(a,b)['same_grid']
    other,exp2=sample();other.image[0,0,0]=1;b=make_profile(other,exp2,'organ','B')
    assert compare(a,b)['same_grid'] and not compare(a,b)['same_scan']


@pytest.mark.parametrize('field,value',[('schema_version',2),('protocol','other'),('spacing_mm',[0,1,1]),('regional_volume_pct',[0]*5),('scan_hash','invalid')])
def test_reject_bad_profiles(field,value):
    ds,exp=sample();p=make_profile(ds,exp,'organ','A').model_dump();p[field]=value
    with pytest.raises(ValidationError):Profile.model_validate(p)


def test_endpoint_capture_compare_and_import():
    with TestClient(app) as client:
        a=client.post('/api/fingerprints',json={'organ':'liver','name':'Before'})
        assert a.status_code==200,a.text
        p=a.json()
        assert client.post('/api/fingerprints/validate',json=p).json()==p
        assert client.post('/api/fingerprints/compare',json={'a':p,'b':p}).json()['same_mask']
        bad=copy.deepcopy(p);bad['curve'][6]['voxels']=0
        assert client.post('/api/fingerprints/validate',json=bad).status_code==422
        assert client.post('/api/fingerprints',json={'organ':'missing','name':'A'}).status_code==404
        assert client.post('/api/fingerprints',json={'organ':'liver','name':' '}).status_code==422


def test_empty_profile_rejected():
    ds,_=sample();ds.masks['organ'][:]=False
    with pytest.raises(ValueError):make_profile(ds,StressExperiment.from_mask(ds.mask('organ'),ds.spacing),'organ','Empty')


def test_displaced_capture_matches_experiment_and_preserves_original():
    with TestClient(app) as client:
        before=client.get('/api/metrics',params={'organ':'liver','offset':0}).json()
        expected=client.get('/api/metrics',params={'organ':'liver','offset':2}).json()
        response=client.post('/api/fingerprints',json={'organ':'liver','name':'Expanded','offset':2})
        assert response.status_code==200,response.text
        p=Profile.model_validate(response.json())
        assert p.captured_offset_mm==2
        assert summary(p)['baseline_ml']==pytest.approx(expected['current_ml'])
        assert p.curve[6].voxels==expected['voxels']
        assert client.get('/api/metrics',params={'organ':'liver','offset':0}).json()==before
        legacy=p.model_dump();legacy.pop('captured_offset_mm')
        assert Profile.model_validate(legacy).captured_offset_mm==0
        assert client.post('/api/fingerprints',json={'organ':'liver','name':'Bad','offset':0.3}).status_code==422


def test_delete_restore_last_segment_and_session_isolation():
    ds,_=sample();key='test-delete-session';SESSIONS[key]=ds
    try:
        with TestClient(app) as client, TestClient(app) as other:
            client.cookies.set('anatomy_session',key,domain='testserver.local')
            result=client.post('/api/segments',json={'operation':'delete','organ':'organ'})
            assert result.status_code==200,result.text
            assert result.json()['organ'] is None
            assert client.get('/api/meta').json()['structures']==[]
            assert other.get('/api/meta').json()['structures']
            restored=client.post('/api/segments',json={'operation':'restore'})
            assert restored.status_code==200,restored.text
            assert restored.json()['organ']=='organ'
            p=client.post('/api/fingerprints',json={'organ':'organ','name':'Restored'})
            assert p.status_code==200,p.text
            assert p.json()['curve'][6]['voxels']==int(ds.mask('organ').sum())
            assert client.post('/api/segments',json={'operation':'restore'}).status_code==422
            SESSIONS.pop(client.cookies.get('anatomy_session'),None)
    finally:
        SESSIONS.pop(key,None)
