"""Inspectable, deterministic agent stages. No automatic infrastructure changes."""
from __future__ import annotations
import hashlib
import re
import time
from collections import defaultdict, Counter
from .models import LogEntry, AnalysisResult, Incident, Evidence, AgentRun
from .sanitize import redact

STAGES = [
    'Ingestion', 'PII & secret sanitizer', 'Noise filter', 'Deduplication',
    'Severity classifier', 'Context enrichment', 'Event correlation',
    'Root-cause hypothesis', 'Remediation planner', 'RCA documenter', 'Notification planner'
]

def fingerprint(message: str) -> str:
    return re.sub(r'\b\d+(?:\.\d+)?\b', '#', message.lower()).strip()

def label(msg: str) -> tuple[str,str]:
    text = msg.lower()
    if any(p in text for p in ['timeout','connection pool','postgres']):
        return ('Database connection pressure', 'Check database capacity, pool sizing and slow queries; validate before changes.')
    if any(p in text for p in ['503','dependency probe','upstream','service unavailable']):
        return ('Unhealthy upstream dependency', 'Check upstream health, recent deploys and service dependencies; roll back only with approval.')
    if any(p in text for p in ['outofmemory','memory limit','memory utilization','oom']):
        return ('Memory limit exceeded', 'Inspect workload memory profile and resource limits; tune after capacity review.')
    return ('Unclassified application error', 'Review related traces, timestamps, deployment changes and dependency health.')

def analyze(logs: list[LogEntry], mode: str = 'demo', on_stage=None) -> AnalysisResult:
    traces: list[AgentRun] = []
    def stage(name, detail, start):
        entry=AgentRun(name=name, duration_ms=round((time.perf_counter()-start)*1000,3), detail=detail)
        traces.append(entry)
        if on_stage: on_stage(entry.model_dump())

    start = time.perf_counter()
    logs = logs[:300]
    stage(STAGES[0], f'{len(logs)} records acquired', start)

    start = time.perf_counter()
    safe = [log.model_copy(update={'message':redact(log.message),'resource':redact(log.resource),'service':redact(log.service)}) for log in logs]
    stage(STAGES[1], 'Messages and identifiers redacted before analysis', start)

    start = time.perf_counter()
    actionable = [log for log in safe if log.severity.upper() in ('ERROR','CRITICAL','WARN','WARNING','FATAL')]
    stage(STAGES[2], f'{len(actionable)} actionable records; informational events retained in explorer',start)

    start = time.perf_counter()
    grouped: dict[tuple, list[LogEntry]] = defaultdict(list)
    for log in actionable:
        cause, _ = label(log.message)
        grouped[(log.cloud,log.service,cause)].append(log)
    stage(STAGES[3], f'{len(grouped)} related incident groups', start)

    start = time.perf_counter()
    priorities = {}
    for key, items in grouped.items():
        priorities[key] = 'P0' if any(l.severity.upper() in ('CRITICAL','FATAL') for l in items) else 'P1' if any(l.severity.upper() == 'ERROR' for l in items) else 'P2'
    stage(STAGES[4], 'Prioritized P0/P1/P2 by event severity', start)

    start = time.perf_counter()
    contexts = {k: Counter(l.resource for l in items).most_common(1)[0][0] for k,items in grouped.items()}
    stage(STAGES[5], 'Cloud/service/resource metadata attached', start)

    start = time.perf_counter()
    stage(STAGES[6], 'Grouped by cloud, service and failure signature; no cross-cloud causal assertion', start)

    start = time.perf_counter()
    incidents=[]
    for key,items in grouped.items():
        cloud,service,cause=key
        _, fix=label(items[0].message)
        digest=hashlib.sha256('|'.join(key).encode()).hexdigest()[:8].upper()
        incidents.append(Incident(id=f'INC-{digest}', title=cause, cloud=cloud, severity=priorities[key],service=service,
            count=len(items), root_cause=f'Possible {cause.lower()} affecting {service} on {contexts[key]}. This is a hypothesis, not verified causation.',
            recommendation=fix, evidence=[Evidence(log_id=l.id,cloud=l.cloud,message=l.message) for l in items[:4]]))
    stage(STAGES[7], f'{len(incidents)} evidence-linked hypotheses generated', start)

    start=time.perf_counter()
    stage(STAGES[8], 'Read-only recommendations drafted; no commands executed', start)
    start=time.perf_counter()
    stage(STAGES[9], 'Incident summaries and evidence references prepared', start)
    start=time.perf_counter()
    stage(STAGES[10], 'Notification recommendations only; no outbound delivery configured', start)
    incidents.sort(key=lambda i: ('P0','P1','P2').index(i.severity))
    return AnalysisResult(mode=mode,logs=safe,incidents=incidents,agents=traces,
        stats={'total_logs':len(safe),'actionable_logs':len(actionable),'incidents':len(incidents),
               'critical':sum(i.severity=='P0' for i in incidents), 'clouds':dict(Counter(l.cloud for l in safe))})

def investigate(question: str, result: AnalysisResult) -> dict:
    q=question.lower()
    tokens=set(re.findall(r'[a-z0-9_-]{3,}',q)) - {'what','with','from','have','this','that','show','please','logs','last','why','the','and','for'}
    scored=[]
    for i in result.incidents:
        hay=' '.join([i.cloud,i.service,i.title,i.root_cause]+[e.message for e in i.evidence]).lower()
        score=len([t for t in tokens if t in hay])
        if i.cloud in tokens: score+=3
        if score: scored.append((score,i))
    scored.sort(key=lambda x:x[0],reverse=True)
    relevant=[i for _,i in scored[:3]] if scored else result.incidents[:3]
    answer='Based on the available logs (not proof of causality): '+ ('; '.join(f'{i.service} ({i.cloud}): {i.root_cause} Suggested next step: {i.recommendation}' for i in relevant) if relevant else 'No actionable incident found.')
    evidence=[{'incident_id':i.id,'log_id':e.log_id,'message':e.message} for i in relevant for e in i.evidence[:2]]
    return {'answer':answer,'evidence':evidence,'method':'rule-based evidence retrieval','notice':'For AI-assisted synthesis, enable a model only in the authenticated admin workspace.'}
