"""Repeatable, non-billable local health checks. No real cloud or model calls."""
import json, tempfile, os, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.settings import Settings

def main():
    with tempfile.TemporaryDirectory() as d:
        os.environ['DATABASE_URL']='sqlite:///'+str(Path(d)/'diagnostic.db')
        with TestClient(create_app(Settings(public_demo_only=True,admin_key='only-for-diagnostics'))) as app:
            health=app.get('/health');demo=app.post('/api/demo/run')
            lock=app.post('/api/admin/runs/start',json={'providers':['aws']},headers={'X-Admin-Key':'only-for-diagnostics'})
            assert health.status_code==200 and health.json()['ok']
            assert demo.status_code==200
            data=demo.json()
            assert (len(data['logs']),len(data['agents']),len(data['incidents']))==(12,11,3)
            assert lock.status_code==403
            print(json.dumps({'health':'PASS','public_run':'PASS','logs':len(data['logs']),
                'agents':len(data['agents']),'incidents':len(data['incidents']),
                'public_private_lock':'PASS','real_cloud_access':'NOT TESTED (no credentials)',
                'remote_ai':'NOT TESTED (no API key)'},indent=2))
if __name__=='__main__':main()
