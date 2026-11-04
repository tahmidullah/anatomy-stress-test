import gzip
import io
import json
import zipfile
import nibabel as nib
import numpy as np
import nrrd
import pytest
import SimpleITK as sitk
from fastapi.testclient import TestClient
from anatomy_lab.importers import build_dataset, volume, read_ct
from server import app, SESSIONS

@pytest.fixture(autouse=True)
def clean():
    SESSIONS.clear()
    yield
    SESSIONS.clear()


def test_upload_export_and_isolation():
    affine = np.diag([1., 2., 3., 1.])
    image = np.zeros((12, 13, 14), dtype=np.float32)
    mask = np.zeros(image.shape, dtype=np.uint8)
    mask[3:7, 3:7, 3:7] = 1
    mask[8:10, 8:10, 8:10] = 2
    with TestClient(app) as client, TestClient(app) as other:
        result = client.post('/api/import', files=[('ct', ('ct.nii', nib.Nifti1Image(image, affine).to_bytes())), ('mask', ('organs.nii', nib.Nifti1Image(mask, affine).to_bytes()))])
        assert result.status_code == 200, result.text
        meta = client.get('/api/meta').json()
        assert len(meta['structures']) == 2
        assert other.get('/api/meta').json()['source'] == 'synthetic'
        organ = meta['structures'][0]['name']
        response = client.get('/api/export', params={'organ': organ, 'offset': 1, 'label': 'Liver'})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            nii = nib.Nifti1Image.from_bytes(gzip.decompress(bundle.read('segmentation.nii.gz')))
            settings = json.loads(bundle.read('settings.json'))
            assert nii.shape == image.shape
            assert np.allclose(nii.affine, affine)
            assert nii.get_fdata().sum() == settings['metrics']['voxels']
            assert settings['label'] == 'Liver'
        bad_affine = affine.copy(); bad_affine[0, 3] = .5
        response = client.post('/api/import', files=[('ct', ('ct.nii', nib.Nifti1Image(image, affine).to_bytes())), ('mask', ('mask.nii', nib.Nifti1Image(mask, bad_affine).to_bytes()))])
        assert response.status_code == 422
        assert client.get('/api/meta').json() == meta


def test_cropped_slicer_overlapping_segments(tmp_path):
    data = np.zeros((2, 4, 5, 6), dtype=np.uint8)
    data[0, 1:3, 1:3, 1:3] = 1
    data[1, 1:4, 1:4, 1:4] = 1
    header = {'space': 'right-anterior-superior', 'space directions': [[np.nan]*3, [1,0,0],[0,2,0],[0,0,3]], 'space origin': [2,4,6], 'kinds': ['list','domain','domain','domain']}
    for i in range(2):
        header.update({f'Segment{i}_ID': str(i), f'Segment{i}_Name': f'organ{i}', f'Segment{i}_Layer': str(i), f'Segment{i}_LabelValue': '1'})
    path = tmp_path / 'mask.seg.nrrd'
    nrrd.write(str(path), data, header)
    ds = build_dataset((np.zeros((12,13,14)), np.diag([1.,2.,3.,1.])), [path])
    assert [ds.mask(n).sum() for n in ds.structures] == [8,27]
    assert ds.mask('organ0')[3,3,3]


def test_nrrd_lps(tmp_path):
    img = sitk.GetImageFromArray(np.ones((5,6,7), dtype=np.int16))
    img.SetSpacing((1,2,3)); img.SetOrigin((10,20,30))
    path = tmp_path / 'ct.nrrd'; sitk.WriteImage(img, str(path))
    array, affine = volume(path)
    assert array.shape == (7,6,5)
    assert np.allclose(affine[:3,3], [-16,-30,30])


def test_dicom_series_and_zip(tmp_path):
    folder = tmp_path / 'dicom'; folder.mkdir()
    for series in range(2):
        for z in range(3):
            image = sitk.GetImageFromArray(np.full((8,9), 40+z, dtype=np.int16))
            tags = {'0008|0060':'CT','0020|000e':f'1.2.826.0.1.3680043.2.1125.{series+1}', '0020|000d':'1.2.826.0.1.3680043.2.1125.100', '0020|0032':f'0\\0\\{z*2}', '0020|0037':'1\\0\\0\\0\\1\\0', '0028|0030':'1\\1', '0018|0050':'2'}
            for key,value in tags.items(): image.SetMetaData(key,value)
            writer=sitk.ImageFileWriter(); writer.KeepOriginalImageUIDOn(); writer.SetFileName(str(folder / f'{series}_{z}.dcm')); writer.Execute(image)
    paths=list(folder.iterdir())
    ct, choices=read_ct(paths,tmp_path)
    assert ct is None and len(choices)==2
    ct, _=read_ct(paths,tmp_path,choices[0]['uid'])
    assert ct[0].shape==(9,8,3)
    assert np.allclose(np.linalg.norm(ct[1][:3,:3],axis=0),[1,1,2])
    archive=tmp_path/'scan.zip'
    with zipfile.ZipFile(archive,'w') as out:
        for path in paths: out.write(path,'nested/'+path.name)
    destination=tmp_path/'zip'; destination.mkdir()
    _, choices=read_ct([archive],destination)
    assert len(choices)==2
