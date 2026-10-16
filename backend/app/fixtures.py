"""Synthetic incidents only; not production logs."""
from datetime import datetime, timezone, timedelta
from .models import LogEntry

DATA = [
    ('aws','ERROR','checkout-api','payments-prod','Connection timeout connecting to postgres:5432 after 5000ms'),
    ('aws','ERROR','checkout-api','payments-prod','Connection timeout connecting to postgres:5432 after 5000ms'),
    ('aws','WARN','checkout-api','payments-prod','Database connection pool utilization above 95 percent'),
    ('aws','INFO','checkout-api','payments-prod','Checkout request volume increased to 1600 requests/min'),
    ('azure','ERROR','identity-service','vm-identity-01','HTTP 503 Service Unavailable returned by upstream token service'),
    ('azure','ERROR','identity-service','vm-identity-01','HTTP 503 Service Unavailable returned by upstream token service'),
    ('azure','WARN','identity-service','vm-identity-01','Service dependency probe unhealthy for 3 consecutive attempts'),
    ('azure','INFO','identity-service','vm-identity-01','Deployment succeeded version 2.4.1'),
    ('gcp','CRITICAL','inventory-api','inventory-cluster','OutOfMemoryError: container killed after exceeding memory limit'),
    ('gcp','WARN','inventory-api','inventory-cluster','Memory utilization reached 98 percent'),
    ('gcp','INFO','inventory-api','inventory-cluster','Pod inventory-api-7f9c scheduled on node pool'),
    ('aws','INFO','checkout-api','payments-prod','Health check passed on /ready'),
]

def demo_logs() -> list[LogEntry]:
    base = datetime.now(timezone.utc) - timedelta(minutes=14)
    return [LogEntry(id=f'DEMO-{i+1:03}',cloud=c,severity=sev,service=s,resource=r,
            timestamp=(base+timedelta(seconds=i*65)).isoformat(),message=m)
            for i,(c,sev,s,r,m) in enumerate(DATA)]

DEMO_REPO = {
    'README.md': '# Checkout API\nPython FastAPI checkout service. PostgreSQL stores orders. /health is used by load balancers.\n',
    'app/main.py': '''from fastapi import FastAPI\nfrom .db import get_connection\n\napp = FastAPI()\n\n@app.get("/health")\ndef health():\n    return {"status": "ok"}\n\n@app.post("/checkout")\ndef checkout(order: dict):\n    conn = get_connection()\n    result = conn.execute("INSERT INTO orders VALUES (...) ")\n    return {"result": str(result)}\n''',
    'app/db.py': '''import os\nimport psycopg2\n\nDATABASE_URL = os.environ.get("DATABASE_URL", "")\n\ndef get_connection():\n    return psycopg2.connect(DATABASE_URL, connect_timeout=5)\n''',
    'tests/test_health.py': '''from fastapi.testclient import TestClient\nfrom app.main import app\n\ndef test_health():\n    client = TestClient(app)\n    assert client.get("/health").status_code == 200\n''',
    'requirements.txt': 'fastapi\npsycopg2-binary\nuvicorn\n',
    'Dockerfile': 'FROM python:3.12-slim\nCOPY . /app\nWORKDIR /app\nRUN pip install -r requirements.txt\nCMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]\n'
}
