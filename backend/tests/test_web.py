import io
import zipfile
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.settings import Settings


def test_demo_public_and_headers():
    c=TestClient(create_app(Settings(public_demo_only=True, admin_key='random-long-key-123')))
    assert c.get('/health').json()['ok'] is True
    r=c.get('/api/demo/state')
    assert r.status_code==200 and len(r.json()['analysis']['agents'])==11
    assert r.headers['Cache-Control']=='no-store'
    assert r.headers['X-Content-Type-Options']=='nosniff'
    assert c.post('/api/demo/investigate',json={'question':'Why does AWS time out?'}).status_code==200
    assert c.post('/api/demo/repo/ask',json={'question':'Show database connection'}).status_code==200
    assert c.post('/api/demo/investigate',json={'question':'a'}).status_code==422


def test_public_demo_admin_denied_even_with_valid_key():
    c=TestClient(create_app(Settings(public_demo_only=True,admin_key='random-long-key-123')))
    key={'X-Admin-Key':'random-long-key-123'}
    assert c.get('/api/admin/config').status_code==401
    assert c.get('/api/admin/config',headers=key).status_code==200
    assert c.put('/api/admin/config',headers=key,json={}).status_code==403
    assert c.post('/api/admin/collect',headers=key,json={}).status_code==403
    assert c.get('/api/admin/repository',headers=key).status_code==403
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('file.py','print(1)')
    assert c.post('/api/admin/repository/upload',headers=key,files={'file':('repo.zip',b.getvalue(),'application/zip')}).status_code==403


def test_private_configuration_and_repo_upload():
    c=TestClient(create_app(Settings(public_demo_only=False,admin_key='random-long-key-123')))
    key={'X-Admin-Key':'random-long-key-123'}
    data={'azure_workspace_id':'workspace-sample','azure_table':'AppTraces','aws_region':'us-east-1','aws_log_group':'my-group','gcp_project_id':'demo-123'}
    r=c.put('/api/admin/config',headers=key,json=data)
    assert r.status_code==200
    assert r.json()['gcp_project_id']=='demo-123'
    assert 'openai_api_key' not in str(r.json())
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('code.py','def hello():\n  return 3\n')
    r=c.post('/api/admin/repository/upload',headers=key,files={'file':('repo.zip',b.getvalue(),'application/zip')})
    assert r.status_code==200 and len(r.json()['files'])==1
    q=c.post('/api/admin/repository/ask',headers=key,json={'question':'Where is hello defined?'})
    assert q.status_code==200


def test_no_admin_key_means_no_admin():
    c=TestClient(create_app(Settings(public_demo_only=False,admin_key='')))
    assert c.get('/api/admin/config',headers={'X-Admin-Key':'abc'}).status_code==401
