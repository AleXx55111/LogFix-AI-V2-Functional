"""Core agent and ZIP-import test coverage."""
import io
import zipfile
import pytest
from backend.app.agents_ops import analyze, investigate
from backend.app.fixtures import demo_logs, DEMO_REPO
from backend.app.models import LogEntry
from backend.app.repo_agent import import_zip, RepoError, analyze_repo, answer_repo
from backend.app.sanitize import redact


def make_zip(files):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in files.items():z.writestr(name,content)
    return bio.getvalue()


def test_tri_cloud_pipeline_and_incidents():
    result=analyze(demo_logs())
    assert len(result.logs)==12
    assert set(result.stats['clouds'])=={'azure','aws','gcp'}
    assert len(result.agents)==11
    assert len(result.incidents)==3
    assert {i.severity for i in result.incidents}=={'P0','P1'}
    assert all(i.confidence=='heuristic' and i.evidence for i in result.incidents)
    assert any(e['log_id'] for e in investigate('checkout timeout',result)['evidence'])


def test_secrets_redacted_before_any_output():
    message='Authorization: abcdefghijklmnop api_key=123456789 password=hunter123 user alice@example.com AWS AKIAABCDEFGHIJKLMNOP'
    assert 'hunter123' not in redact(message)
    x=LogEntry(id='id',cloud='aws',timestamp='now',severity='ERROR',service='api',resource='r',message=message)
    result=analyze([x]).model_dump_json()
    for secret in ['hunter123','123456789','alice@example.com','AKIAABCDEFGHIJKLMNOP','abcdefghijklmnop']:
        assert secret not in result


def test_repository_static_analysis_and_citations():
    report=analyze_repo(DEMO_REPO)
    assert report['agents'] and report['files']
    assert any('connection' in f['title'].lower() for f in report['findings'])
    reply=answer_repo(DEMO_REPO,'Suggest a fix for database connection pooling',report)
    assert reply['citations'] and reply['patch_suggestion']


def test_zip_upload_safety():
    z=make_zip({'example/app.py':'print("hello")','../evil.py':'print("escape")','.env':'DO_NOT_READ','node_modules/leak.js':'secret'})
    files=import_zip(z)
    assert files == {'example/app.py':'print("hello")'}
    with pytest.raises(RepoError):import_zip(b'not-a-zip')
    with pytest.raises(RepoError):import_zip(b'x'*2_000_001)
    with pytest.raises(RepoError):import_zip(make_zip({'big.py':'x'*50_001}))


def test_large_compressed_content_is_rejected():
    with pytest.raises(RepoError):import_zip(make_zip({'a.py':'x'*500_001}))


def test_repository_does_not_execute_source(tmp_path):
    marker=tmp_path/'should_not_exist'
    data=make_zip({'malicious.py':f'import os\nopen({str(marker)!r},"w").write("fail")'})
    report=analyze_repo(import_zip(data))
    assert report['files']
    assert not marker.exists()
