import io
import zipfile
import pytest
from backend.app.fixtures import DEMO_REPO
from backend.app.repo_agent import import_zip, analyze_repo, answer_repo, RepoError


def create_zip(files:dict[str,str])->bytes:
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,content in files.items():z.writestr(name,content)
    return f.getvalue()


def test_repo_pipeline_and_retrieval():
    report=analyze_repo(DEMO_REPO,'synthetic-demo')
    assert len(report['agents'])==7
    assert 'FastAPI application' in report['architecture']
    assert 'PostgreSQL connector' in report['architecture']
    assert any(x['title']=='Per-request database connection' for x in report['findings'])
    answer=answer_repo(DEMO_REPO,'Where is psycopg2 connect called?',report)
    assert answer['citations']
    assert any(x['file']=='app/db.py' for x in answer['citations'])


def test_archive_rejects_secrets_and_traversal():
    archive=create_zip({'README.md':'hello','../escape.py':'print(1)','app/.env':'PASSWORD=abc','app/keys.py':'API_KEY="test12345"'})
    repo=import_zip(archive)
    assert '../escape.py' not in repo
    assert 'app/.env' not in repo
    assert 'app/keys.py' in repo
    assert 'test12345' not in repo['app/keys.py']


def test_repo_upload_rejects_large_and_invalid():
    with pytest.raises(RepoError):import_zip(b'nope')
    with pytest.raises(RepoError):import_zip(b'x'*2_000_001)


def test_repo_zip_never_runs_source():
    # We only index and AST-parse; uploaded content must not execute.
    data=create_zip({'evil.py':'raise RuntimeError("executed")\n'})
    repo=import_zip(data)
    report=analyze_repo(repo)
    assert report['summary'].endswith('No code executed.')
