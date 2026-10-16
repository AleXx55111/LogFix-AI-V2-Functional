from backend.app import connectors
from backend.app.settings import Settings
from backend.app.models import LogEntry
import pytest


def test_real_collection_is_locked_by_default():
    with pytest.raises(PermissionError):connectors.collect_clouds(Settings(public_demo_only=True),['aws'])


def test_fault_is_sanitized_without_losing_other_clouds(monkeypatch):
    def fail(*_args,**_kwargs):
        raise RuntimeError('Credential secret-password-token leaked')
    def success(*_args,**_kwargs):
        return [LogEntry(id='okay',cloud='gcp',timestamp='2026-01-01T00:00:00Z',severity='INFO',service='s',resource='r',message='hello')]
    monkeypatch.setitem(connectors.PROVIDERS,'aws',fail)
    monkeypatch.setitem(connectors.PROVIDERS,'gcp',success)
    results,warnings=connectors.collect_clouds(Settings(public_demo_only=False),['aws','gcp'])
    assert len(results)==1 and results[0].cloud=='gcp'
    assert len(warnings)==1
    assert 'secret-password-token' not in warnings[0]


def test_query_table_allowlist():
    assert 'AppTraces' in connectors.ALLOWED_TABLES
    with pytest.raises(ValueError):connectors.azure_logs(Settings(azure_workspace_id='w',azure_table='AppTraces | delete'))
