"""Storage regressions; PostgreSQL tests use a disposable CI database only."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from database import TABLES, connect, insert_row, postgres_sql, storage_status
from database_schema import initialize_schema
from migrate_sqlite_to_postgres import migrate


def test_bound_parameters_preserve_question_marks_and_percent():
    sql = "SELECT '?' AS literal, ? AS value, '50%' AS label -- ? in comment"
    assert postgres_sql(sql) == "SELECT '?' AS literal, %s AS value, '50%%' AS label -- ? in comment"


def test_sqlite_reinitialization_preserves_data(tmp_path):
    factory = lambda: connect(tmp_path / 'nested' / 'test.db')
    initialize_schema(factory)
    con = factory()
    rid = insert_row(con.cursor(), 'INSERT INTO notification_recipients(name,phone_e164) VALUES(?,?)', ('Test household', '+12025550101'))
    con.commit(); con.close()
    initialize_schema(factory)
    con = factory()
    assert con.execute('SELECT name FROM notification_recipients WHERE id=?', (rid,)).fetchone()['name'] == 'Test household'
    con.close()


def test_invalid_remote_database_never_creates_local_file(tmp_path):
    path = tmp_path / 'fallback.db'
    with pytest.raises(RuntimeError, match='PostgreSQL connection URL'):
        connect(path, 'mysql://invalid')
    assert not path.exists()


def test_storage_status_contains_no_connection_credentials():
    assert storage_status('postgresql://name:private@host/db')['backend'] == 'postgresql'
    assert 'private' not in str(storage_status('postgresql://name:private@host/db'))
    assert storage_status('', hosted=True)['warning']


def test_failed_postgres_connection_does_not_fall_back_or_leak_secrets(tmp_path, monkeypatch):
    import psycopg
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('sensitive connection details')
    monkeypatch.setattr(psycopg, 'connect', fail)
    path = tmp_path / 'fallback.db'
    with pytest.raises(RuntimeError, match='PostgreSQL connection failed') as error:
        connect(path, 'postgresql://user:private@host/db')
    assert 'private' not in str(error.value) and 'sensitive' not in str(error.value)
    assert not path.exists()


@pytest.fixture
def pg_url():
    url = os.getenv('PRAHARI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Disposable PostgreSQL is provided by the storage CI job')
    # Use a unique schema, never truncate an existing database or public schema.
    import uuid
    import psycopg
    schema = 'prahari_test_' + uuid.uuid4().hex
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(f'CREATE SCHEMA {schema}')
    # connection URL remains a URL; pass the schema through libpq options.
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query)); query['options'] = f'-csearch_path={schema}'
    scoped = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    yield scoped
    admin.execute(f'DROP SCHEMA {schema} CASCADE'); admin.close()


def test_postgres_registration_survives_new_process_and_login(pg_url, tmp_path):
    env = {**os.environ, 'PRAHARI_DATABASE_URL': pg_url,
           'PRAHARI_DB_PATH': str(tmp_path / 'must-not-exist.db'),
           'PRAHARI_ENV': 'production', 'PRAHARI_AUTH_REQUIRED': 'true',
           'PRAHARI_ADMIN_KEY': 'test-admin-only', 'PRAHARI_SMS_ENABLED': 'false'}
    common = '''
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as client:
    response=client.post('/api/auth/login',json={'portal':'ADMIN','access_key':'test-admin-only'})
    assert response.status_code==200,response.text
    headers={'X-PRAHARI-Key':'test-admin-only'}
'''
    create = common + '''
    r=client.post('/api/field/households',headers=headers,json={'name':"Test ? O'Brien",'phone_e164':'+12025550101','location_id':2,'consent_confirmed':True})
    assert r.status_code==200,r.text
    r=client.post('/api/alerts',headers=headers,json={'location_id':2,'level':'HIGH','message':'TEST ONLY - storage regression advisory'})
    assert r.status_code==201,r.text
    main._persist_source_cache('test','test',{'value':1})
    main._persist_source_cache('test','test',{'value':2})
'''
    read = common + '''
    r=client.get('/api/field/households',headers=headers)
    assert r.status_code==200,r.text
    assert len(r.json())==1 and r.json()[0]['name']=="Test ? O'Brien",r.text
    assert r.json()[0]['location_id']==2
    assert client.get('/api/field/households?location_id=1',headers=headers).json()==[]
    alerts=client.get('/api/alerts',headers=headers).json()
    assert len(alerts)==1 and alerts[0]['lifecycle_status']=='DRAFT'
    c=main.db()
    assert c.execute("SELECT payload_json FROM source_cache WHERE cache_key=?",('test',)).fetchone()['payload_json']=='{"value": 2}'
    c.close()
    assert client.get('/api/system/status').json()['database_storage']['backend']=='postgresql'
'''
    for script in (create, read):
        run = subprocess.run([sys.executable, '-c', script], cwd=ROOT / 'backend', env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
    assert not (tmp_path / 'must-not-exist.db').exists()


def test_atomic_migration_preserves_ids_and_refuses_nonempty_target(pg_url, tmp_path):
    source = tmp_path / 'backup.db'
    initialize_schema(lambda: connect(source))
    con = connect(source)
    con.execute('INSERT INTO notification_recipients(id,name,phone_e164,consent_status) VALUES(?,?,?,?)', (41, 'Backup test', '+12025550102', 'ACTIVE'))
    con.commit(); con.close()
    before = source.read_bytes()
    assert migrate(source, pg_url)['notification_recipients'] == 1
    assert source.read_bytes() == before
    con = connect(None, pg_url)
    rid = insert_row(con.cursor(), 'INSERT INTO notification_recipients(name,phone_e164) VALUES(?,?)', ('Next test', '+12025550103'))
    con.commit(); con.close()
    assert rid > 41
    with pytest.raises(ValueError, match='not empty'):
        migrate(source, pg_url)
    con = connect(None, pg_url)
    assert con.execute('SELECT COUNT(*) AS n FROM notification_recipients').fetchone()['n'] == 2
    con.close()


def test_failed_copy_rolls_back_all_rows(pg_url, tmp_path):
    source = tmp_path / 'invalid-backup.db'
    con = connect(source)
    # An older/corrupted backup: the second recipient violates current NOT NULL.
    con.execute('CREATE TABLE notification_recipients(id INTEGER, name TEXT, phone_e164 TEXT)')
    con.execute('INSERT INTO notification_recipients VALUES(1,?,?)', ('Valid first row', '+12025550104'))
    con.execute('INSERT INTO notification_recipients VALUES(2,NULL,?)', ('+12025550105',))
    con.commit(); con.close()
    import psycopg
    with pytest.raises(psycopg.errors.NotNullViolation):
        migrate(source, pg_url)
    con = connect(None, pg_url)
    assert con.execute('SELECT COUNT(*) AS n FROM notification_recipients').fetchone()['n'] == 0
    con.close()
