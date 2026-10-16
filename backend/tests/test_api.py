"""API smoke tests: public demo works, private workflows require explicit unlock."""
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.models import LogEntry


def client(**overrides):
    return TestClient(create_app(Settings(**overrides)))


def test_public_endpoints_and_example_pipelines():
    c = client()
    assert c.get('/health').json()['ok'] is True
    r = c.get('/api/demo/state')
    assert r.status_code == 200
    data = r.json()
    assert data['analysis']['mode'] == 'synthetic-demo'
    assert len(data['analysis']['logs']) == 12
    assert len(data['analysis']['incidents']) == 3
    assert len(data['analysis']['agents']) == 11
    assert len(data['repository']['agents']) == 7
    assert data['capabilities']['real_logs'] is False
    assert c.post('/api/demo/investigate',json={'question':'Why is GCP inventory OOM?'}).json()['evidence']
    repo = c.post('/api/demo/repo/ask',json={'question':'How does the database connection work?'}).json()
    assert repo['citations'] and repo['citations'][0]['file'] == 'app/db.py'
    assert r.headers['Cache-Control'] == 'no-store'
    assert 'X-Frame-Options' in r.headers


def test_protected_public_lock_and_authentication():
    c=client(admin_key='a-long-admin-secret',public_demo_only=True)
    assert c.get('/api/admin/config').status_code == 401
    assert c.get('/api/admin/config',headers={'X-Admin-Key':'wrong'}).status_code == 401
    h={'X-Admin-Key':'a-long-admin-secret'}
    assert c.get('/api/admin/config',headers=h).status_code == 200
    assert c.post('/api/admin/collect',json={'providers':['aws']},headers=h).status_code == 403
    assert c.put('/api/admin/config',json={},headers=h).status_code == 403
    assert c.post('/api/admin/repository/upload',files={'file':('repo.zip',b'dummy','application/zip')},headers=h).status_code == 403
    assert c.post('/api/admin/investigate',json={'question':'what happened'},headers=h).status_code == 403
    assert c.post('/api/admin/repository/ask',json={'question':'where is code'},headers=h).status_code == 403


def test_private_config_and_mock_collection(monkeypatch):
    from backend.app import main
    fake=[LogEntry(id='one',cloud='aws',timestamp='2026-01-01T00:00:00Z',severity='ERROR',service='auth',resource='lambda',message='password=superSecret ERROR timeout')]
    monkeypatch.setattr(main,'collect_clouds',lambda config, providers:(fake,[]))
    c=client(admin_key='private-test-key',public_demo_only=False)
    h={'X-Admin-Key':'private-test-key'}
    assert c.put('/api/admin/config',json={'aws_log_group':'/aws/lambda/auth'},headers=h).status_code == 200
    result=c.post('/api/admin/collect',json={'providers':['aws']},headers=h)
    assert result.status_code == 200, result.text
    assert result.json()['incidents']
    assert 'superSecret' not in str(result.json())
    assert c.get('/api/admin/last-analysis',headers=h).json()['stats']['total_logs'] == 1
    assert c.post('/api/admin/investigate',json={'question':'What happened to auth service?'},headers=h).status_code == 200


def test_no_admin_key_means_no_private_access():
    c=client(public_demo_only=False,admin_key='')
    assert c.get('/api/admin/config',headers={'X-Admin-Key':'guess'}).status_code == 401


def test_input_validation():
    c=client()
    assert c.post('/api/demo/repo/ask',json={'question':'x'}).status_code == 422
    assert c.post('/api/demo/investigate',json={'question':'x'*1001}).status_code == 422
