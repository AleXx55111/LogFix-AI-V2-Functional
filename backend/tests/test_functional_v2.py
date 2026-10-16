"""Integration diagnostics for the actual HTTP endpoints, persistence and scheduler."""
import os, time, uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.models import LogEntry

KEY='strong-private-test-admin-key'
HEAD={'X-Admin-Key':KEY}

def test_public_demo_execution_and_private_lock(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/demo.db')
    with TestClient(create_app(Settings(public_demo_only=True,admin_key=KEY))) as c:
        r=c.post('/api/demo/run');assert r.status_code==200
        assert len(r.json()['agents'])==11 and len(r.json()['logs'])==12
        for route in ['/api/admin/schedule','/api/admin/runs']:
            assert c.get(route,headers=HEAD).status_code==403
        assert c.put('/api/admin/secrets',headers=HEAD,json={'openai_api_key':'secret-should-never-leak'}).status_code==403
        assert c.get('/api/admin/config').status_code==401

def test_admin_secrets_model_and_ai_are_write_only(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/secret.db')
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c:
        secret='supersecret-sentinel-xyz'
        r=c.put('/api/admin/secrets',headers=HEAD,json={
            'azure_tenant_id':'00000000-0000-0000-0000-000000000001',
            'azure_client_id':'00000000-0000-0000-0000-000000000002',
            'azure_client_secret':secret,'aws_access_key_id':'test-key',
            'aws_secret_access_key':secret,'openai_api_key':secret})
        assert r.status_code==200,r.text
        assert secret not in r.text
        conf=c.get('/api/admin/config',headers=HEAD)
        assert conf.status_code==200
        assert secret not in conf.text
        assert conf.json()['secret_status']['OPENAI_API_KEY'] is True
        assert c.put('/api/admin/ai',headers=HEAD,json={'enable_llm':True,'openai_model':'gpt-4.1-mini'}).status_code==200
        assert c.get('/api/admin/config',headers=HEAD).json()['llm_enabled'] is True
        r=c.put('/api/admin/secrets',headers=HEAD,json={'gcp_service_account_json':'not-valid-json'})
        assert r.status_code==422 and 'not-valid-json' not in r.text
        r=c.put('/api/admin/secrets',headers=HEAD,json={'gcp_service_account_json':'{"type":"service_account", "private_key":"x", "client_email":"a@b.c"}'})
        assert r.status_code==200 and 'private_key' not in r.text

def test_manual_collection_live_agent_trace_and_archive_persistence(tmp_path,monkeypatch):
    db=f'sqlite:///{tmp_path}/archive.db'
    monkeypatch.setenv('DATABASE_URL',db)
    import backend.app.main as main
    def fake_collect(config,providers):
        assert not config.public_demo_only
        return ([LogEntry(id='aws-1',cloud='aws',timestamp='2026-10-01T00:00:00Z',severity='ERROR',service='checkout',resource='vm-1',message='ERROR database timeout password=never_expose_me')],[])
    monkeypatch.setattr(main,'collect_clouds',fake_collect)
    run_id=None
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c:
        assert c.put('/api/admin/config',headers=HEAD,json={'aws_log_group':'/aws/lambda/checkout'}).status_code==200
        check=c.post('/api/admin/connections/test',headers=HEAD,json={'providers':['aws']})
        assert check.status_code==200 and check.json()['results'][0]['connected'] is True
        r=c.post('/api/admin/runs/start',headers=HEAD,json={'providers':['aws']})
        assert r.status_code==202,r.text
        run_id=r.json()['run_id']
        for _ in range(100):
            detail=c.get('/api/admin/runs/'+run_id,headers=HEAD)
            if detail.json()['status'] in ('completed','partial','failed'):break
            time.sleep(.03)
        result=detail.json()
        assert result['status']=='completed',result
        assert len(result['agents'])==12
        assert result['analysis']['stats']['incidents']==1
        assert 'never_expose_me' not in str(result)
        assert result['analysis']['incidents'][0]['evidence']
        history=c.get('/api/admin/runs',headers=HEAD)
        assert any(r['id']==run_id for r in history.json()['runs'])
    # New app instance, same DB: incident RCA survives an app restart.
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c2:
        saved=c2.get('/api/admin/runs/'+run_id,headers=HEAD)
        assert saved.status_code==200,saved.text
        assert saved.json()['analysis']['incidents'][0]['root_cause']
        assert 'never_expose_me' not in saved.text

def test_scheduler_configuration_persists_and_rejects_bad_intervals(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/schedule.db')
    body={'enabled':True,'interval_minutes':5,'providers':['azure','gcp']}
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c:
        r=c.put('/api/admin/schedule',headers=HEAD,json=body)
        assert r.status_code==200 and r.json()['next_run_at'] is not None
        assert c.put('/api/admin/schedule',headers=HEAD,json={'enabled':True,'interval_minutes':1,'providers':['aws']}).status_code==422
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c2:
        data=c2.get('/api/admin/schedule',headers=HEAD).json()
        assert data['enabled'] is True and data['providers']==['azure','gcp']
        assert c2.put('/api/admin/schedule',headers=HEAD,json={**body,'enabled':False}).json()['next_run_at'] is None

def test_scheduler_tick_actually_executes(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/tick.db')
    import backend.app.main as main
    monkeypatch.setattr(main,'collect_clouds',lambda config,providers:([LogEntry(id='x',cloud='aws',timestamp='2026-01-01T00:00:00Z',severity='WARN',service='system',resource='x',message='error timeout')],[]))
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY))) as c:
        c.put('/api/admin/schedule',headers=HEAD,json={'enabled':True,'interval_minutes':5,'providers':['aws']})
        c.app.state.scheduler_next=time.time()-.1
        for _ in range(80):
            runs=c.get('/api/admin/runs',headers=HEAD).json()['runs']
            if any(x['mode']=='scheduled' for x in runs):break
            time.sleep(.05)
        assert any(x['mode']=='scheduled' for x in runs),runs

def test_ai_assisted_rca_only_when_explicitly_enabled(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/ai.db')
    import backend.app.main as main
    hits=[]
    monkeypatch.setattr(main,'collect_clouds',lambda cfg,providers:([LogEntry(
        id='ai-evidence-1',cloud='azure',timestamp='2026-10-15T00:00:00Z',severity='CRITICAL',
        service='api',resource='vm1',message='Database connection timeout ERROR password=not_for_llm')],[]))
    def fake_synthesize(q,evidence,settings):
        hits.append((q,evidence,settings.openai_model))
        assert 'not_for_llm' not in evidence
        return 'DRAFT: Verify database pool saturation; evidence ai-evidence-1.'
    monkeypatch.setattr(main,'synthesize',fake_synthesize)
    with TestClient(create_app(Settings(public_demo_only=False,admin_key=KEY,
                                     enable_llm=True,auto_rca_enabled=True,
                                     runtime_secrets={'OPENAI_API_KEY':'server-secret'}))) as c:
        r=c.post('/api/admin/runs/start',headers=HEAD,json={'providers':['azure']})
        run_id=r.json()['run_id']
        for _ in range(90):
            j=c.get('/api/admin/runs/'+run_id,headers=HEAD).json()
            if j['status'] in ('completed','failed','partial'):break
            time.sleep(.03)
        assert j['status']=='completed',j
        assert len(hits)==1
        assert j['analysis']['ai_summary'].startswith('DRAFT:')
        assert any(a['name']=='Optional AI RCA synthesis' and a['status']=='completed' for a in j['agents'])
        assert 'server-secret' not in str(j)
        assert 'not_for_llm' not in str(j)

def test_dependency_free_fallback_ui_respects_script_csp(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/fallback.db')
    with TestClient(create_app(Settings())) as c:
        home=c.get('/')
        assert home.status_code==200
        assert '<script src="/fallback.js"></script>' in home.text
        assert 'onclick=' not in home.text
        assert "script-src 'self'" in home.headers['content-security-policy']
        js=c.get('/fallback.js')
        assert js.status_code==200
        assert 'application/javascript' in js.headers['content-type']
        assert 'async function runNow' in js.text
