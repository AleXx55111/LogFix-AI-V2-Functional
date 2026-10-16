from __future__ import annotations
import logging
import asyncio
import uuid
import json
from contextlib import asynccontextmanager
import os
import secrets
import time
from pathlib import Path
from threading import RLock
from typing import Literal

from fastapi import FastAPI, Request, Depends, HTTPException, Header, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .settings import Settings
from .models import Question, ConnectionUpdate, AgentRun, SecretUpdate, AIConfig, ScheduleUpdate
from .agents_ops import analyze, investigate
from .fixtures import demo_logs, DEMO_REPO
from .repo_agent import analyze_repo, answer_repo, import_zip, RepoError, map_incident_to_code
from .connectors import collect_clouds
from .llm import synthesize
from .sanitize import redact
from .store import HistoryStore

log=logging.getLogger('logfix')
UI_DIR=Path(__file__).resolve().parents[2]/'frontend'/'dist'

class CollectRequest(BaseModel):
    providers: list[Literal['azure','aws','gcp']] = ['azure','aws','gcp']


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or Settings.from_env()
    @asynccontextmanager
    async def lifespan(application):
        application.state.scheduler_next=None
        task=asyncio.create_task(scheduler_loop(application))
        try:yield
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            application.state.store.close()

    api=FastAPI(title='LogFix AI V2',version='2.1.0',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    api.state.config=config
    api.state.last_analysis=None
    api.state.repo=dict(DEMO_REPO)
    api.state.repo_mode='demo'
    api.state.lock=RLock()
    api.state.started=time.time()
    api.state.store=HistoryStore()
    api.state.jobs={}
    api.state.run_lock=asyncio.Lock()
    api.state.scheduler_next=None

    @api.middleware('http')
    async def add_security_headers(request:Request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    def admin_guard(x_admin_key: str | None = Header(default=None)):

        key=api.state.config.admin_key
        if not key or not x_admin_key or not secrets.compare_digest(x_admin_key,key):
            raise HTTPException(401,'Administrator key required')
        return True

    def live_guard():
        if api.state.config.public_demo_only:
            raise HTTPException(403,'Public demo lock is enabled. Real connections and uploads are disabled.')

    def config_copy():
        with api.state.lock:
            values=vars(api.state.config).copy()
            values['runtime_secrets']=dict(api.state.config.runtime_secrets)
        return Settings(**values)

    async def execute_run(run_id:str, providers:list[str], mode:str='manual'):
        job=api.state.jobs[run_id]
        async with api.state.run_lock:
            job['status']='running'
            job['started_at']=time.time()
            logs=[]; warnings=[]; connector_traces=[]
            try:
                snapshot=config_copy()
                for provider in providers:
                    job['current_agent']=provider.upper()+' connector'
                    job['agents'].append({'name':job['current_agent'],'status':'running','detail':'Query in progress','duration_ms':0})
                    started=time.perf_counter()
                    received, errs=await run_in_threadpool(collect_clouds,snapshot,[provider])
                    logs.extend(received);warnings.extend(errs)
                    failed=bool(errs)
                    trace=AgentRun(name=provider.upper()+' read-only connector',status='failed' if failed else 'completed',
                        duration_ms=round((time.perf_counter()-started)*1000,2),
                        detail=('Query failed; see sanitized warning' if failed else f'{len(received)} log events retrieved'))
                    connector_traces.append(trace)
                    job['agents'][-1]=trace.model_dump()
                job['current_agent']='Ingestion & analysis'
                def report(stage):
                    job['agents'].append(stage)
                    job['current_agent']=stage['name']
                result=await run_in_threadpool(analyze,logs[:300],'live-cloud-readonly',report)
                result.agents=connector_traces+result.agents
                result.warnings.extend(warnings)
                if snapshot.enable_llm and snapshot.auto_rca_enabled and snapshot.secret('OPENAI_API_KEY') and result.incidents:
                    job['current_agent']='Optional AI RCA synthesis'
                    started=time.perf_counter()
                    try:
                        context='\n'.join(f'{inc.id} {inc.cloud} {inc.service}: {inc.root_cause} Evidence: '+
                            ' | '.join(f'{e.log_id}: {e.message}' for e in inc.evidence[:3]) for inc in result.incidents[:8])
                        result.ai_summary=await run_in_threadpool(synthesize,
                            'Draft a cautious, evidence-cited RCA summary and verification steps. Label uncertainty.',context,snapshot)
                        trace=AgentRun(name='Optional AI RCA synthesis',status='completed',
                            duration_ms=round((time.perf_counter()-started)*1000,2),detail='Remote model provided draft. Human validation required.')
                    except Exception as error:
                        log.warning('Optional AI RCA failed: %s',type(error).__name__)
                        result.warnings.append('Optional AI RCA failed; deterministic RCA remains available.')
                        trace=AgentRun(name='Optional AI RCA synthesis',status='failed',detail='Model request failed; check AI settings')
                    result.agents.append(trace)
                    job['agents'].append(trace.model_dump())
                with api.state.lock:api.state.last_analysis=result
                job['status']='completed' if not warnings else ('partial' if logs else 'failed')
                job['analysis']=result.model_dump()
                job['current_agent']=None
                api.state.store.save(run_id,job['status'],mode,{'analysis':job['analysis']})
            except Exception as exc:
                log.error('Collection run failure: %s',type(exc).__name__)
                job.update(status='failed',current_agent=None,error='Collection failed; inspect private deployment diagnostics.')
                api.state.store.save(run_id,'failed',mode,{'error':job['error']})
            finally:
                job['finished_at']=time.time()
                if len(api.state.jobs)>100:
                    for old_id in list(api.state.jobs)[:-100]:
                        if api.state.jobs[old_id].get('status') in ('completed','partial','failed'):
                            api.state.jobs.pop(old_id,None)

    def schedule_status():
        settings=api.state.store.get_schedule()
        return {**settings,'next_run_at':api.state.scheduler_next,'note':'In-process scheduler only runs while this instance is awake. Render Free sleeps; use external cron or paid always-on hosting for 24/7 schedules.'}

    async def scheduler_loop(application):
        while True:
            try:
                await asyncio.sleep(2)
                if application.state.config.public_demo_only:continue
                schedule=application.state.store.get_schedule()
                if not schedule.get('enabled'):
                    application.state.scheduler_next=None
                    continue
                now=time.time()
                if application.state.scheduler_next is None:
                    application.state.scheduler_next=now+schedule['interval_minutes']*60
                if now>=application.state.scheduler_next:
                    application.state.scheduler_next=now+schedule['interval_minutes']*60
                    if application.state.run_lock.locked():continue
                    run_id=str(uuid.uuid4())
                    application.state.jobs[run_id]={'id':run_id,'status':'queued','agents':[],'mode':'scheduled'}
                    asyncio.create_task(execute_run(run_id,schedule['providers'],'scheduled'))
            except asyncio.CancelledError:raise
            except Exception as exc:
                log.error('Scheduler tick failed: %s',type(exc).__name__)

    @api.get('/health')
    def health():return {'ok':True,'service':'logfix-ai-v2','version':'2.1.0'}

    @api.get('/api/demo/state')
    def demo_state():
        return {'analysis':analyze(demo_logs(), 'synthetic-demo').model_dump(),
                'repository':analyze_repo(DEMO_REPO,'synthetic-demo'),
                'connections':{'azure':'sample data','aws':'sample data','gcp':'sample data'},
                'capabilities':{'real_logs':False,'remote_llm':False,'code_execution':False}}

    @api.post('/api/demo/run')
    def demo_run():
        # Re-runs only fictional fixtures. No cloud access or database mutations.
        return analyze(demo_logs(),'synthetic-demo').model_dump()

    @api.post('/api/demo/investigate')
    def demo_investigate(body:Question):
        analysis=analyze(demo_logs(),'synthetic-demo')
        result=investigate(body.question,analysis)
        selected={item['incident_id'] for item in result['evidence']}
        result['code_references']=map_incident_to_code([i for i in analysis.incidents if i.id in selected], DEMO_REPO)
        return result

    @api.post('/api/demo/repo/ask')
    def demo_repo_question(body:Question):
        return answer_repo(DEMO_REPO,body.question,analyze_repo(DEMO_REPO,'synthetic-demo'))

    @api.get('/api/admin/config',dependencies=[Depends(admin_guard)])
    def admin_config():return api.state.config.admin_config()

    @api.put('/api/admin/config',dependencies=[Depends(admin_guard)])
    def update_config(body:ConnectionUpdate):
        live_guard()
        with api.state.lock:
            for key,value in body.model_dump().items():setattr(api.state.config,key,value)
            return api.state.config.admin_config()

    @api.put('/api/admin/secrets',dependencies=[Depends(admin_guard)])
    def update_secrets(body:SecretUpdate):
        live_guard()
        incoming=body.model_dump(exclude_unset=True)
        mapping={
            'azure_tenant_id':'AZURE_TENANT_ID','azure_client_id':'AZURE_CLIENT_ID','azure_client_secret':'AZURE_CLIENT_SECRET',
            'aws_access_key_id':'AWS_ACCESS_KEY_ID','aws_secret_access_key':'AWS_SECRET_ACCESS_KEY','aws_session_token':'AWS_SESSION_TOKEN',
            'gcp_service_account_json':'GCP_SERVICE_ACCOUNT_JSON','openai_api_key':'OPENAI_API_KEY'}
        if incoming.get('gcp_service_account_json'):
            try:
                value=json.loads(incoming['gcp_service_account_json'])
                if value.get('type')!='service_account' or not value.get('private_key') or not value.get('client_email'):
                    raise ValueError()
            except (ValueError,TypeError):raise HTTPException(422,'Enter valid GCP service-account JSON')
        with api.state.lock:
            for name,value in incoming.items():
                if value and value.strip():api.state.config.runtime_secrets[mapping[name]]=value.strip()
            return api.state.config.admin_config()

    @api.put('/api/admin/ai',dependencies=[Depends(admin_guard)])
    def update_ai(body:AIConfig):
        live_guard()
        with api.state.lock:
            api.state.config.enable_llm=body.enable_llm
            api.state.config.auto_rca_enabled=body.auto_rca_enabled
            api.state.config.openai_model=body.openai_model
            return api.state.config.admin_config()

    @api.post('/api/admin/ai/test',dependencies=[Depends(admin_guard)])
    async def test_ai():
        live_guard()
        settings=config_copy()
        if not settings.enable_llm or not settings.secret('OPENAI_API_KEY'):
            raise HTTPException(400,'Enable AI and enter the model API key first')
        try:
            output=await run_in_threadpool(synthesize,'Reply with OK only.','Health check, no real data.',settings)
            return {'connected':True,'model':settings.openai_model,'reply':output[:200]}
        except Exception as exc:
            log.warning('Model diagnostic failed: %s',type(exc).__name__)
            raise HTTPException(502,'AI provider check failed: verify API key, model, credits and network')

    @api.post('/api/admin/connections/test',dependencies=[Depends(admin_guard)])
    async def test_connection(body:CollectRequest):
        live_guard()
        snapshot=config_copy()
        report=[]
        for provider in dict.fromkeys(body.providers):
            data,errors=await run_in_threadpool(collect_clouds,snapshot,[provider])
            report.append({'provider':provider,'connected':not errors,'sample_log_count':len(data),
                'message':'Query succeeded; zero logs can mean no events in last 30 minutes' if not errors else errors[0]})
        return {'results':report}

    @api.post('/api/admin/runs/start',dependencies=[Depends(admin_guard)],status_code=202)
    async def run_now(body:CollectRequest):
        live_guard()
        if api.state.run_lock.locked() or any(x.get('status')=='queued' for x in api.state.jobs.values()):
            raise HTTPException(409,'A collection run is already running')
        run_id=str(uuid.uuid4())
        api.state.jobs[run_id]={'id':run_id,'mode':'manual','status':'queued','current_agent':None,'agents':[], 'started_at':None}
        asyncio.create_task(execute_run(run_id,list(dict.fromkeys(body.providers))))
        return {'run_id':run_id,'status':'queued'}

    @api.get('/api/admin/runs',dependencies=[Depends(admin_guard)])
    def list_runs():
        live_guard()
        return {'runs':api.state.store.list_runs()}

    @api.get('/api/admin/runs/{run_id}',dependencies=[Depends(admin_guard)])
    def run_detail(run_id:str):
        live_guard()
        active=api.state.jobs.get(run_id)
        if active:
            # no raw logs until sanitized analysis is complete
            return active
        saved=api.state.store.get(run_id)
        if saved:return saved
        raise HTTPException(404,'Run not found')

    @api.get('/api/admin/schedule',dependencies=[Depends(admin_guard)])
    def get_schedule():
        live_guard()
        return schedule_status()

    @api.put('/api/admin/schedule',dependencies=[Depends(admin_guard)])
    def save_schedule(body:ScheduleUpdate):
        live_guard()
        config=body.model_dump()
        config['providers']=list(dict.fromkeys(config['providers']))
        api.state.store.set_schedule(config)
        api.state.scheduler_next=time.time()+config['interval_minutes']*60 if config['enabled'] else None
        return schedule_status()

    @api.post('/api/admin/collect',dependencies=[Depends(admin_guard)])
    async def collect(body:CollectRequest):
        live_guard()
        # Cloud SDK calls block and can take time. Run them off the async event loop.
        with api.state.lock:
            snapshot=config_copy()
        logs,warnings=await run_in_threadpool(collect_clouds,snapshot,list(dict.fromkeys(body.providers)))
        result=analyze(logs,'live-cloud-readonly')
        connector_traces=[]
        for provider in list(dict.fromkeys(body.providers)):
            failed=any(w.startswith(provider.upper()+' collection failed') for w in warnings)
            connector_traces.append(AgentRun(name=provider.upper()+' read-only connector',
                status='failed' if failed else 'completed',
                detail='See collection warnings; connection not verified' if failed else 'Provider query completed; results may be empty'))
        result.agents=connector_traces+result.agents
        result.warnings.extend(warnings)
        with api.state.lock:api.state.last_analysis=result
        return result.model_dump()

    @api.get('/api/admin/last-analysis',dependencies=[Depends(admin_guard)])
    def last_analysis():
        with api.state.lock:result=api.state.last_analysis
        return result.model_dump() if result else {'message':'No live analysis run this session'}

    @api.get('/api/admin/repository',dependencies=[Depends(admin_guard)])
    def admin_repository():
        live_guard()
        with api.state.lock:repo=dict(api.state.repo);mode=api.state.repo_mode
        return analyze_repo(repo,mode)

    @api.post('/api/admin/repository/upload',dependencies=[Depends(admin_guard)])
    async def upload_repo(file:UploadFile=File(...)):
        live_guard()
        if not file.filename or not file.filename.lower().endswith('.zip'):
            raise HTTPException(400,'Upload a ZIP repository snapshot')
        data=await file.read(2_000_001)
        try:repo=import_zip(data)
        except RepoError as e:raise HTTPException(400,str(e)) from e
        with api.state.lock:
            api.state.repo=repo
            api.state.repo_mode='private-upload-in-memory'
        return analyze_repo(repo,'private-upload-in-memory')

    @api.post('/api/admin/repository/ask',dependencies=[Depends(admin_guard)])
    async def ask_private_repo(body:Question):
        live_guard()
        with api.state.lock:repo=dict(api.state.repo);mode=api.state.repo_mode;settings=config_copy()
        report=analyze_repo(repo,mode)
        result=answer_repo(repo,body.question,report)
        if body.use_llm:
            evidence='\n'.join(f'{r["file"]}:{r["line"]} {r["snippet"]}' for r in result['citations'])
            try:result['answer']=await run_in_threadpool(synthesize,body.question,evidence,settings);result['method']='LLM synthesis of cited snippets'
            except RuntimeError:raise HTTPException(400,'LLM is disabled or no server-side API key is configured')
            except Exception as e:
                log.warning('LLM failure: %s',type(e).__name__)
                raise HTTPException(502,'Model request failed; check server settings')
        return result

    @api.post('/api/admin/investigate',dependencies=[Depends(admin_guard)])
    async def private_investigate(body:Question):
        live_guard()
        with api.state.lock:analysis=api.state.last_analysis;settings=config_copy()
        if analysis is None:raise HTTPException(409,'Fetch live logs first')
        result=investigate(body.question,analysis)
        with api.state.lock:repo=dict(api.state.repo)
        selected={item['incident_id'] for item in result['evidence']}
        result['code_references']=map_incident_to_code([i for i in analysis.incidents if i.id in selected],repo)
        if body.use_llm:
            context='\n'.join(f'{e["log_id"]}: {e["message"]}' for e in result['evidence'])
            try:result['answer']=await run_in_threadpool(synthesize,body.question,context,settings);result['method']='LLM synthesis of cited logs'
            except RuntimeError:raise HTTPException(400,'LLM is disabled or no server-side API key is configured')
            except Exception as e:
                log.warning('LLM failure: %s',type(e).__name__)
                raise HTTPException(502,'Model request failed; check server settings')
        return result

    if (UI_DIR/'index.html').exists():
        assets=UI_DIR/'assets'
        if assets.exists():api.mount('/assets',StaticFiles(directory=str(assets)),name='assets')
        @api.get('/')
        def index():return FileResponse(UI_DIR/'index.html')
        @api.get('/{full_path:path}')
        def frontend_routes(full_path: str):
            if full_path.startswith(('api/','assets/')):raise HTTPException(404,'Not found')
            return FileResponse(UI_DIR/'index.html')
    else:
        @api.get('/')
        def unbuilt_ui():return FileResponse(UI_DIR.parent/'fallback.html')
        @api.get('/fallback.js')
        def fallback_js():return FileResponse(UI_DIR.parent/'fallback.js',media_type='application/javascript')
    return api

app=create_app()
