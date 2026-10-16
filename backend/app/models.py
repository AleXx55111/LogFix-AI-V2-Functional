from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal

Cloud = Literal['azure', 'aws', 'gcp']

class LogEntry(BaseModel):
    id: str
    cloud: Cloud
    timestamp: str
    severity: str
    service: str
    resource: str
    message: str

class AgentRun(BaseModel):
    name: str
    status: Literal['completed', 'skipped', 'failed'] = 'completed'
    duration_ms: float = 0
    detail: str = ''

class Evidence(BaseModel):
    log_id: str
    cloud: Cloud
    message: str

class Incident(BaseModel):
    id: str
    title: str
    cloud: Cloud
    severity: str
    service: str
    count: int
    root_cause: str
    recommendation: str
    confidence: str = 'heuristic'
    evidence: list[Evidence]
    status: str = 'open'

class AnalysisResult(BaseModel):
    mode: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    logs: list[LogEntry]
    incidents: list[Incident]
    agents: list[AgentRun]
    stats: dict
    warnings: list[str] = []
    ai_summary: str | None = None

class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    use_llm: bool = False

class ConnectionUpdate(BaseModel):
    azure_workspace_id: str = Field(default='', max_length=160)
    azure_table: Literal['AppTraces', 'AzureDiagnostics', 'Syslog', 'Event', 'ContainerLogV2'] = 'AppTraces'
    aws_region: str = Field(default='us-east-1', pattern=r'^[a-z]{2}(?:-[a-z]+)+-\d$', max_length=40)
    aws_log_group: str = Field(default='', max_length=300)
    gcp_project_id: str = Field(default='', max_length=150)

class SecretUpdate(BaseModel):
    # Empty fields do not erase existing credentials. No API response returns values.
    azure_tenant_id: str = Field(default='', max_length=250)
    azure_client_id: str = Field(default='', max_length=250)
    azure_client_secret: str = Field(default='', max_length=8000)
    aws_access_key_id: str = Field(default='', max_length=300)
    aws_secret_access_key: str = Field(default='', max_length=1000)
    aws_session_token: str = Field(default='', max_length=8000)
    gcp_service_account_json: str = Field(default='', max_length=20000)
    openai_api_key: str = Field(default='', max_length=500)

class AIConfig(BaseModel):
    enable_llm: bool = False
    auto_rca_enabled: bool = False
    openai_model: str = Field(default='gpt-4.1-mini',min_length=2,max_length=100,pattern=r'^[a-zA-Z0-9._-]+$')

class ScheduleUpdate(BaseModel):
    enabled: bool = False
    interval_minutes: Literal[5, 10, 15, 30, 60] = 15
    providers: list[Cloud] = Field(default_factory=lambda:['azure','aws','gcp'],min_length=1,max_length=3)
