"""Read-only code intelligence with bounded ZIP import, no code execution."""
from __future__ import annotations
import ast
import io
import re
import time
import zipfile
from collections import Counter
from pathlib import PurePosixPath
from .fixtures import DEMO_REPO
from .models import AgentRun
from .sanitize import redact

MAX_UPLOAD = 2_000_000
MAX_FILES = 80
MAX_FILE_SIZE = 50_000
MAX_TOTAL_TEXT = 500_000
EXTS = {'.py','.js','.jsx','.ts','.tsx','.json','.md','.yml','.yaml','.toml','.txt','.html','.css','.sh','.sql','.dockerfile'}
IGNORED = {'.git','node_modules','.venv','venv','dist','build','__pycache__','.next','.env'}

class RepoError(ValueError): pass


def import_zip(data:bytes)->dict[str,str]:
    if len(data)>MAX_UPLOAD:raise RepoError('ZIP exceeds 2 MB limit')
    try: archive=zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile,ValueError):raise RepoError('Please upload a valid ZIP archive')
    try:
        entries=archive.infolist()
        if len(entries)>MAX_FILES*4:raise RepoError('Archive has too many entries')
        total=0; output={}
        for ent in entries:
            if ent.is_dir():continue
            name=ent.filename
            p=PurePosixPath(name)
            if (p.is_absolute() or '..' in p.parts or '\\' in name or '\x00' in name or
                len(name)>220 or any(x in IGNORED for x in p.parts) or p.name.startswith('.env')):continue
            # Unix symlinks never extracted or read.
            if (ent.external_attr>>16)&0o170000 == 0o120000:continue
            if p.suffix.lower() not in EXTS and p.name.lower()!='dockerfile':continue
            if ent.file_size>MAX_FILE_SIZE or ent.flag_bits & 0x1:continue
            total+=ent.file_size
            if total>MAX_TOTAL_TEXT:raise RepoError('ZIP contains too much source text')
            if len(output)>=MAX_FILES:raise RepoError('ZIP exceeds 80 supported source files')
            raw=archive.read(ent, pwd=None)
            if len(raw)>MAX_FILE_SIZE:continue
            try: content=raw.decode('utf-8')
            except UnicodeDecodeError:continue
            output[str(p)] = redact(content,max_length=MAX_FILE_SIZE)
        if not output:raise RepoError('No supported source files were found')
        return output
    finally:archive.close()


def analyze_repo(files:dict[str,str],mode='demo')->dict:
    traces=[]
    def trace(name,detail,start):traces.append(AgentRun(name=name,duration_ms=round((time.perf_counter()-start)*1000,3),detail=detail).model_dump())
    t=time.perf_counter();paths=list(files);trace('Repository discovery',f'Indexed {len(paths)} safe source files',t)
    t=time.perf_counter();languages=dict(Counter({'.py':'Python','.js':'JavaScript','.jsx':'React JSX','.ts':'TypeScript','.tsx':'React TSX','.md':'Markdown','.json':'JSON'}.get(PurePosixPath(p).suffix,'Other') for p in paths))
    trace('Language & framework detector',f'{len(languages)} file types recognized',t)
    t=time.perf_counter();architecture=[]
    if any('fastapi' in c.lower() for c in files.values()):architecture.append('FastAPI application')
    if any('react' in c.lower() for c in files.values()):architecture.append('React frontend')
    if any('psycopg' in c.lower() for c in files.values()):architecture.append('PostgreSQL connector')
    if 'Dockerfile' in files:architecture.append('Docker container')
    trace('Architecture mapper',', '.join(architecture) or 'Source inventory built',t)
    t=time.perf_counter();findings=[]
    for path,content in files.items():
        for line_no,line in enumerate(content.splitlines(),1):
            if re.search(r'\b(eval|exec)\s*\(',line):
                findings.append({'severity':'high','file':path,'line':line_no,'title':'Dynamic code execution','detail':'Review eval/exec inputs; no code was executed.'})
            if re.search(r'verify\s*=\s*False',line):
                findings.append({'severity':'high','file':path,'line':line_no,'title':'TLS verification disabled','detail':'Avoid verify=False on network requests.'})
            if re.search(r'(\b(password|secret|api_key|token)\s*=\s*[\'"][^\'"]{4,})',line,re.I) and '[REDACTED]' not in line:
                findings.append({'severity':'medium','file':path,'line':line_no,'title':'Possible hardcoded credential','detail':'Use environment secrets; review this line.'})
            if 'psycopg2.connect(' in line and not any('pool' in x.lower() for x in files.values()):
                findings.append({'severity':'medium','file':path,'line':line_no,'title':'Per-request database connection','detail':'Consider bounded pooling, reuse, close in finally, and connection budgets.'})
        if path.endswith('.py'):
            try:ast.parse(content)
            except SyntaxError as err:findings.append({'severity':'medium','file':path,'line':err.lineno or 1,'title':'Python syntax error','detail':str(err.msg)})
    trace('Static analyzer',f'{len(findings)} review hints; heuristic only',t)
    t=time.perf_counter()
    test_count=sum('/test_' in '/'+p or p.startswith('test_') for p in files)
    trace('Test coverage inspector',f'{test_count} test files (coverage not executed)',t)
    t=time.perf_counter();trace('Index & retrieval builder','Line-addressable text chunks ready for read-only Q&A',t)
    t=time.perf_counter();trace('Patch planning agent','Can propose text-only changes; never writes to uploaded source',t)
    return {'mode':mode,'files':[{'path':p,'lines':len(c.splitlines()),'language':PurePosixPath(p).suffix or 'other'} for p,c in files.items()],
            'languages':languages,'architecture':architecture,'findings':findings[:40], 'agents':traces,
            'summary':f'{len(files)} files analyzed, {len(findings)} review hints. No code executed.'}

STOP={'which','where','what','with','from','that','this','your','does','will','how','the','for','and','tell','show','please','code','file','find','explain','could','would','should','there','when','work','works','working'}

def answer_repo(files:dict[str,str],question:str,report:dict)->dict:
    tokens={w for w in re.findall(r'[a-z0-9_]{3,}',question.lower()) if w not in STOP}
    snippets=[]
    for path,content in files.items():
        lines=content.splitlines()
        for n,line in enumerate(lines,1):
            low=line.lower(); score=sum(token in low for token in tokens)*2+sum(token in path.lower() for token in tokens)
            if score:snippets.append((score,path,n,line[:240]))
    snippets.sort(key=lambda row:(-row[0],row[1],row[2]))
    top=snippets[:6]
    if not top:
        return {'answer':'I could not find supporting code for that question in the indexed repository. Try naming a module, endpoint, or error.',
                'citations':[],'method':'local source search','patch_suggestion':None}
    refs=[{'file':p,'line':line,'snippet':value} for _,p,line,value in top]
    # This is deliberately framed as code retrieval, not an invented AI conclusion.
    explanation='Relevant source references: '+ '; '.join(f'{r["file"]}:{r["line"]} — {r["snippet"].strip()[:100]}' for r in refs[:3])
    patch=None
    if any(word in question.lower() for word in ['fix','improve','patch','connection pool']):
        if any('psycopg2.connect' in f for f in files.values()):
            patch='Suggested approach (review manually): use psycopg2.pool.ThreadedConnectionPool with bounded maxconn, return connections in finally, and add tests. No source was modified.'
        else:
            patch='Review cited call sites, implement a narrowly scoped change, and add a regression test. No source was modified.'
    return {'answer':explanation,'citations':refs,'method':'local source search','patch_suggestion':patch}


def demo_repo_report():return analyze_repo(DEMO_REPO,'demo')


def map_incident_to_code(incidents, files: dict[str,str]) -> list[dict]:
    """Heuristic correlation hints; never assert a log is caused by this code."""
    references=[]
    for incident in incidents[:4]:
        cause=incident.title.lower()
        hints=(('psycopg2','get_connection','database_url') if 'database' in cause
               else ('health','upstream','request') if 'upstream' in cause
               else ('memory','limit','container') if 'memory' in cause else ('error',))
        scored=[]
        for path,content in files.items():
            for line_num,line in enumerate(content.splitlines(),1):
                score=sum(word in line.lower() for word in hints)
                if score:
                    scored.append((score,path,line_num,line[:200]))
        scored.sort(key=lambda t:(-t[0],t[1],t[2]))
        for _,path,line_num,snippet in scored[:2]:
            references.append({'incident_id':incident.id,'file':path,'line':line_num,
                               'snippet':snippet,'notice':'Keyword match only; causality not established'})
    return references[:6]
