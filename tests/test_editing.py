import gzip
import io
import zipfile
import nibabel as nib
import numpy as np
from fastapi.testclient import TestClient
from anatomy_lab.editing import brush
from server import app, SESSIONS


def test_physical_brush_axes_and_erase():
    mask=np.zeros((20,21,22),bool)
    for axis,fixed in [('axial',2),('coronal',1),('sagittal',0)]:
        edited=brush(mask,(1,2,3),axis,10,[[8,8]],3)
        assert edited.any() and not mask.any()
        positions=np.where(edited)
        assert np.all(positions[fixed]==10)
        assert not brush(edited,(1,2,3),axis,10,[[8,8]],3,True).any()
    edited=brush(mask,(1,2,3),'axial',10,[[8,8]],3)
    assert edited[11,8,10] and not edited[8,10,10]


def test_create_paint_undo_rename_export_isolation():
    SESSIONS.clear()
    with TestClient(app) as client, TestClient(app) as other:
        response=client.post('/api/segments',json={'operation':'create','label':'My lesion'})
        assert response.status_code==200,response.text
        organ=response.json()['organ']
        assert len(other.get('/api/meta').json()['structures'])==8
        assert client.get('/api/metrics',params={'organ':organ}).json()['empty']
        assert client.get('/api/scene',params={'organ':organ}).status_code==200
        assert client.get('/api/fragility',params={'organ':organ}).status_code==422
        payload={'operation':'stroke','organ':organ,'axis':'axial','index':50,'points':[[50,50],[55,50]],'radius_mm':3}
        assert client.post('/api/segments',json=payload).status_code==200
        count=client.get('/api/metrics',params={'organ':organ}).json()['voxels']
        assert count>0
        assert client.post('/api/segments',json={'operation':'rename','organ':organ,'label':'Renamed'}).status_code==200
        assert next(s for s in client.get('/api/meta').json()['structures'] if s['name']==organ)['label']=='Renamed'
        clone=client.post('/api/segments',json={'operation':'duplicate','organ':organ,'label':'Copy'}).json()['organ']
        assert client.get('/api/metrics',params={'organ':clone}).json()['voxels']==count
        assert client.post('/api/segments',json={**payload,'erase':True}).status_code==200
        assert client.get('/api/metrics',params={'organ':organ}).json()['voxels']==0
        assert client.post('/api/segments',json={'operation':'undo','organ':organ}).status_code==200
        assert client.get('/api/metrics',params={'organ':organ}).json()['voxels']==count
        response=client.get('/api/export',params={'organ':organ})
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            nii=nib.Nifti1Image.from_bytes(gzip.decompress(bundle.read('segmentation.nii.gz')))
            assert nii.get_fdata().sum()==count
        assert client.post('/api/segments',json={**payload,'index':9999}).status_code==422
        assert client.get('/api/metrics',params={'organ':organ}).json()['voxels']==count
    SESSIONS.clear()
