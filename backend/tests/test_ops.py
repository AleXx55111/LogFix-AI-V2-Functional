from backend.app.fixtures import demo_logs
from backend.app.agents_ops import analyze, investigate, STAGES
from backend.app.models import LogEntry


def test_agent_pipeline_and_incidents():
    result=analyze(demo_logs(),'synthetic-demo')
    assert len(result.logs)==12
    assert len(result.agents)==len(STAGES)==11
    assert all(a.status=='completed' for a in result.agents)
    assert len(result.incidents)==3
    assert result.stats['critical']==1
    assert {i.cloud for i in result.incidents}=={'aws','azure','gcp'}
    assert all(i.evidence and i.root_cause.startswith('Possible ') for i in result.incidents)


def test_sanitization_before_display():
    logs=[LogEntry(id='secret-1',cloud='aws',timestamp='2026-01-01T00:00:00Z',severity='ERROR',service='test',resource='user@example.com',message='Failure api_key=very-secret-token password=badpass user=abc@example.com')]
    result=analyze(logs)
    assert 'very-secret-token' not in result.model_dump_json()
    assert 'badpass' not in result.model_dump_json()
    assert 'abc@example.com' not in result.model_dump_json()
    assert '[REDACTED]' in result.logs[0].message


def test_evidence_cites_present_ids():
    result=analyze(demo_logs())
    answer=investigate('Why is checkout failing on AWS?',result)
    assert 'checkout-api' in answer['answer']
    assert answer['evidence']
    ids={log.id for log in result.logs}
    assert all(e['log_id'] in ids for e in answer['evidence'])


def test_empty_results():
    result=analyze([])
    assert result.stats['incidents']==0
    assert len(result.agents)==11
