"""SQLite locally, PostgreSQL on Render+Neon. No credentials written to the DB."""
from __future__ import annotations
import json, os, threading
from datetime import datetime,timezone
from sqlalchemy import create_engine, text

class HistoryStore:
    def __init__(self, url: str | None = None):
        url=url or os.getenv('DATABASE_URL') or 'sqlite:////tmp/logfix-ai-v2.sqlite3'
        if url.startswith('postgres://'):url='postgresql+psycopg://'+url[len('postgres://'):]
        if url.startswith('postgresql://'):url='postgresql+psycopg://'+url[len('postgresql://'):]
        self.kind='postgres' if url.startswith('postgresql') else 'sqlite'
        self.engine=create_engine(url,pool_pre_ping=True,connect_args={'timeout':15} if self.kind=='sqlite' else {})
        self.lock=threading.RLock()
        with self.engine.begin() as db:
            db.execute(text('CREATE TABLE IF NOT EXISTS logfix_runs (id VARCHAR(60) PRIMARY KEY, created_at VARCHAR(50) NOT NULL, status VARCHAR(20) NOT NULL, mode VARCHAR(40), data TEXT NOT NULL)'))
            db.execute(text('CREATE TABLE IF NOT EXISTS logfix_schedule (id INTEGER PRIMARY KEY, data TEXT NOT NULL)'))

    def save(self, id: str, status: str, mode: str, data: dict):
        created=datetime.now(timezone.utc).isoformat()
        with self.lock,self.engine.begin() as db:
            db.execute(text('INSERT INTO logfix_runs (id,created_at,status,mode,data) VALUES (:id,:created,:status,:mode,:data) ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, data=EXCLUDED.data'),{'id':id,'created':created,'status':status,'mode':mode,'data':json.dumps(data)})
            db.execute(text('DELETE FROM logfix_runs WHERE id NOT IN (SELECT id FROM logfix_runs ORDER BY created_at DESC LIMIT 250)'))

    def list_runs(self, limit=30):
        with self.lock,self.engine.connect() as db:
            rows=db.execute(text('SELECT id,created_at,status,mode,data FROM logfix_runs ORDER BY created_at DESC LIMIT :limit'),{'limit':limit}).fetchall()
        result=[]
        for row in rows:
            entry=json.loads(row.data)
            result.append({'id':row.id,'created_at':row.created_at,'status':row.status,'mode':row.mode,
                'stats':entry.get('analysis',{}).get('stats',{}),'warnings':entry.get('analysis',{}).get('warnings',[]),
                'agent_count':len(entry.get('analysis',{}).get('agents',[]))})
        return result

    def get(self, run_id):
        with self.lock,self.engine.connect() as db:
            row=db.execute(text('SELECT id,created_at,status,mode,data FROM logfix_runs WHERE id=:id'),{'id':run_id}).fetchone()
        if not row:return None
        return {'id':row.id,'created_at':row.created_at,'status':row.status,'mode':row.mode,**json.loads(row.data)}

    def set_schedule(self, schedule):
        with self.lock,self.engine.begin() as db:
            db.execute(text('INSERT INTO logfix_schedule (id,data) VALUES (1,:data) ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data'),{'data':json.dumps(schedule)})

    def get_schedule(self):
        with self.lock,self.engine.connect() as db:
            row=db.execute(text('SELECT data FROM logfix_schedule WHERE id=1')).fetchone()
        return json.loads(row.data) if row else {'enabled':False,'interval_minutes':15,'providers':['azure','aws','gcp']}

    def close(self):self.engine.dispose()
