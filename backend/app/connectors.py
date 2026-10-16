"""Explicit bounded read-only queries. SDK authentication comes only from server environment."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import re
from .models import LogEntry
from .settings import Settings

ALLOWED_TABLES={'AppTraces','AzureDiagnostics','Syslog','Event','ContainerLogV2'}

def stable_id(cloud: str, value: str) -> str:
    return cloud.upper()+'-'+sha256(value.encode()).hexdigest()[:12]

def iso(value) -> str:
    if isinstance(value,datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,(int,float)):
        return datetime.fromtimestamp(value / 1000 if value > 10**11 else value,timezone.utc).isoformat()
    return str(value or datetime.now(timezone.utc).isoformat())


def azure_logs(config: Settings, limit: int = 100) -> list[LogEntry]:
    if not config.azure_workspace_id:
        raise ValueError('Azure workspace ID is not configured')
    if config.azure_table not in ALLOWED_TABLES:
        raise ValueError('Azure table is not allowlisted')
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus
    tenant, client_id, secret = (config.secret(k) for k in ('AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET'))
    if any((tenant,client_id,secret)) and not all((tenant,client_id,secret)):
        raise ValueError('Azure credential triple is incomplete')
    credential=ClientSecretCredential(tenant,client_id,secret) if tenant else DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client=LogsQueryClient(credential)
    # Table names are strictly allowlisted. No browser-supplied KQL.
    query=f'{config.azure_table} | order by TimeGenerated desc | take {min(limit,100)}'
    response=client.query_workspace(config.azure_workspace_id,query,timespan=timedelta(minutes=30),server_timeout=30)
    if response.status == LogsQueryStatus.PARTIAL:
        raise RuntimeError('Azure partial query result; check workspace query permissions')
    output=[]
    for table in response.tables:
        cols=[c.name if hasattr(c,'name') else str(c) for c in table.columns]
        for n,row in enumerate(table.rows):
            data=dict(zip(cols,row))
            msg=str(next((data[k] for k in ['Message','message','RenderedDescription','SyslogMessage','LogMessage','ResultDescription','Description'] if data.get(k)),str(data)))
            sev=str(next((data[k] for k in ['SeverityLevel','Level','Severity','EventLevelName'] if data.get(k) is not None),'INFO')).upper()
            if sev.isdigit(): sev={'0':'INFO','1':'INFO','2':'WARN','3':'ERROR','4':'CRITICAL'}.get(sev,'INFO')
            output.append(LogEntry(id=stable_id('azure',msg+str(n)+str(data.get('TimeGenerated',''))),cloud='azure',
                timestamp=iso(data.get('TimeGenerated')),severity=sev,service=str(data.get('AppRoleName') or data.get('Computer') or config.azure_table),
                resource=str(data.get('_ResourceId') or config.azure_workspace_id),message=msg[:2000]))
    return output[:limit]


def aws_logs(config: Settings, limit: int = 100) -> list[LogEntry]:
    if not config.aws_log_group:
        raise ValueError('AWS log group is not configured')
    import boto3
    access,secret,token=(config.secret(k) for k in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'))
    if bool(access)!=bool(secret):
        raise ValueError('AWS access and secret keys must both be provided')
    session=boto3.Session(aws_access_key_id=access or None,aws_secret_access_key=secret or None,aws_session_token=token or None,region_name=config.aws_region)
    client=session.client('logs')
    start=int((datetime.now(timezone.utc)-timedelta(minutes=30)).timestamp()*1000)
    output=[]; token=None; seen=set()
    for _ in range(5):
        kwargs={'logGroupName':config.aws_log_group,'startTime':start,'limit':min(limit,100)}
        if token: kwargs['nextToken']=token
        res=client.filter_log_events(**kwargs)
        for event in res.get('events',[]):
            msg=str(event.get('message',''))[:2000]
            sev=next((s for s in ('CRITICAL','ERROR','WARN','INFO') if re.search(r'\b'+s+r'\b',msg,re.I)),None)
            if not sev:sev='ERROR' if re.search(r'(?i)timeout|exception|failed|outofmemory|\boom\b',msg) else 'INFO'
            eid=event.get('eventId') or stable_id('aws',msg+str(event.get('timestamp')))
            if eid in seen:continue
            seen.add(eid)
            output.append(LogEntry(id=str(eid),cloud='aws',timestamp=iso(event.get('timestamp')),severity=sev,
                service=config.aws_log_group.rsplit('/',1)[-1],resource=str(event.get('logStreamName','-')),message=msg))
            if len(output)>=limit:return output
        nxt=res.get('nextToken')
        if not nxt or nxt==token:break
        token=nxt
    return output


def gcp_logs(config: Settings,limit: int=100) -> list[LogEntry]:
    if not config.gcp_project_id:
        raise ValueError('GCP project ID is not configured')
    from google.cloud import logging_v2
    from google.auth import default
    # Use application default credentials; restrict assigned IAM role to Logs Viewer.
    credential_json=config.secret('GCP_SERVICE_ACCOUNT_JSON')
    if credential_json:
        import json
        from google.oauth2 import service_account
        info=json.loads(credential_json)
        if info.get('type')!='service_account':raise ValueError('GCP service account JSON required')
        creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/logging.read'])
    else:
        creds, _ = default(scopes=['https://www.googleapis.com/auth/logging.read'])
    client=logging_v2.Client(project=config.gcp_project_id,credentials=creds)
    since=(datetime.now(timezone.utc)-timedelta(minutes=30)).isoformat()
    entries=client.list_entries(resource_names=[f'projects/{config.gcp_project_id}'],filter_=f'timestamp >= "{since}"',
                                order_by='timestamp desc',max_results=limit,page_size=min(limit,100))
    output=[]
    for entry in entries:
        payload=entry.payload
        msg=str(payload if isinstance(payload,str) else payload.get('message',payload) if isinstance(payload,dict) else payload)
        severity=getattr(entry.severity,'name',str(entry.severity or 'INFO')).upper()
        sev={'DEFAULT':'INFO','NOTICE':'INFO','WARNING':'WARN','ALERT':'CRITICAL','EMERGENCY':'CRITICAL','500':'ERROR','600':'CRITICAL','400':'WARN'}.get(severity,severity)
        output.append(LogEntry(id=stable_id('gcp',str(entry.insert_id)+msg),cloud='gcp',timestamp=iso(entry.timestamp),severity=sev,
            service=str(getattr(entry.resource,'type','gcp-resource')),
            resource=str(getattr(entry,'log_name','gcp-log')),message=msg[:2000]))
    return output

PROVIDERS={'azure':azure_logs,'aws':aws_logs,'gcp':gcp_logs}

def collect_clouds(config: Settings, providers: list[str]) -> tuple[list[LogEntry],list[str]]:
    if config.public_demo_only:
        raise PermissionError('Real cloud queries are disabled on this public demo')
    logs=[]; warnings=[]
    for name in providers:
        if name not in PROVIDERS:continue
        try: logs.extend(PROVIDERS[name](config))
        except Exception as e:
            # Do not surface SDK errors that could include identifiers, tokens or request details.
            warnings.append(f'{name.upper()} collection failed ({type(e).__name__}); inspect private server logs and IAM settings.')
    return logs[:300], warnings
