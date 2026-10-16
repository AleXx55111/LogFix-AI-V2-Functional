"""Runtime settings. Secrets are write-only through protected admin API, never serialized."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

def enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {'true', '1', 'yes', 'on'}

@dataclass
class Settings:
    public_demo_only: bool = True
    admin_key: str = ''
    azure_workspace_id: str = ''
    azure_table: str = 'AppTraces'
    aws_region: str = 'us-east-1'
    aws_log_group: str = ''
    gcp_project_id: str = ''
    enable_llm: bool = False
    auto_rca_enabled: bool = False
    openai_model: str = 'gpt-4.1-mini'
    # Optional credentials supplied through protected UI (RAM only) or environment.
    runtime_secrets: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_env(cls):
        return cls(public_demo_only=enabled('PUBLIC_DEMO_ONLY', True),admin_key=os.getenv('APP_ADMIN_KEY', ''),
            azure_workspace_id=os.getenv('AZURE_WORKSPACE_ID', ''),azure_table=os.getenv('AZURE_LOG_TABLE', 'AppTraces'),
            aws_region=os.getenv('AWS_REGION', 'us-east-1'),aws_log_group=os.getenv('AWS_LOG_GROUP', ''),
            gcp_project_id=os.getenv('GCP_PROJECT_ID', ''),enable_llm=enabled('ENABLE_LLM'),auto_rca_enabled=enabled('AI_RCA_ON_RUN'),
            openai_model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))

    def secret(self, name: str) -> str:
        return self.runtime_secrets.get(name) or os.getenv(name, '')

    def public_status(self):
        return {'public_demo_only':self.public_demo_only,'azure':bool(self.azure_workspace_id),
            'aws':bool(self.aws_log_group),'gcp':bool(self.gcp_project_id),
            'llm_enabled':self.enable_llm and bool(self.secret('OPENAI_API_KEY'))}

    def admin_config(self):
        return {**self.public_status(), 'azure_workspace_id':self.azure_workspace_id,
            'azure_table':self.azure_table,'aws_region':self.aws_region,'aws_log_group':self.aws_log_group,
            'gcp_project_id':self.gcp_project_id,'openai_model':self.openai_model,'enable_llm':self.enable_llm,'auto_rca_enabled':self.auto_rca_enabled,
            'secret_status': {name: bool(self.secret(name)) for name in [
                'AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET',
                'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN',
                'GCP_SERVICE_ACCOUNT_JSON','OPENAI_API_KEY']},
            'credentials_note':'Write-only fields; secrets remain in memory until restart, or can be configured through host secrets.'}
