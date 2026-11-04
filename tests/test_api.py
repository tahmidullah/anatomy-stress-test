from fastapi.testclient import TestClient
from server import app

client=TestClient(app)


def test_main_page_and_assets():
    assert client.get('/').status_code==200
    assert 'Anatomy Stress Test' in client.get('/').text
    assert client.get('/static/app.js').status_code==200


def test_metadata_and_metrics():
    m=client.get('/api/meta').json()
    assert m['source']=='synthetic'
    assert len(m['structures'])==8
    v=client.get('/api/metrics',params={'organ':'liver','offset':2}).json()
    assert v['delta_pct']>0
    assert v['baseline_ml']>0
    assert len(v['centroid_ijk'])==3


def test_scene_and_curve():
    s=client.get('/api/scene',params={'organ':'liver','offset':1}).json()
    assert len(s['traces'])>=2
    assert len(s['traces'][-1]['mesh']['i'])>50
    curve=client.get('/api/curve',params={'organ':'liver'}).json()['points']
    assert len(curve)==13


def test_slice_is_valid_png():
    resp=client.get('/api/slice',params={'organ':'liver','axis':'axial','index':60,
                                          'offset':1.5,'i':77,'j':65,'k':60})
    assert resp.status_code==200
    assert resp.content[:8]==b'\x89PNG\r\n\x1a\n'


def test_bad_inputs_are_rejected():
    assert client.get('/api/metrics',params={'organ':'liver','offset':9}).status_code==422
    assert client.get('/api/metrics',params={'organ':'fake'}).status_code==404
    assert client.get('/api/slice',params={'organ':'liver','axis':'bad'}).status_code==422
    assert client.get('/api/slice',params={'organ':'liver','axis':'axial','index':999}).status_code==422
