"""Synthetic queue/worker tests. No external provider calls."""
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from database import connect, insert_row
from database_schema import initialize_schema
import broadcasts as b
from test_database import pg_url


@pytest.fixture(params=['sqlite', 'postgres'])
def factory(request, tmp_path):
    url = request.getfixturevalue('pg_url') if request.param == 'postgres' else ''
    f = lambda: connect(tmp_path / 'broadcast.db', url)
    initialize_schema(f)
    c = f()
    c.execute("INSERT INTO alerts(id,location_id,location,lifecycle_status) VALUES(1,1,'Synthetic area','REVIEWED')")
    for name, phone, area, consent, sms in [('A','+12025550101',1,'ACTIVE',1), ('duplicate','+12025550101',2,'ACTIVE',1), ('B','+12025550102',2,'ACTIVE',1), ('off','+12025550103',1,'REVOKED',1), ('disabled','+12025550104',1,'ACTIVE',0), ('unassigned','+12025550105',None,'ACTIVE',1)]:
        c.execute('INSERT INTO notification_recipients(name,phone_e164,location_id,consent_status,sms_enabled,language) VALUES(?,?,?,?,?,?)',(name,phone,area,consent,sms,'en'))
    c.commit(); c.close()
    return f


def queue(f, scope='ALL_MONITORED', count=3, ttl=3600):
    return b.enqueue(f, 1, scope, 1 if scope!='ALL_MONITORED' else None, 'Synthetic audience',
        {x:{'text':'TEST ONLY synthetic message'} for x in ('en','hi','as')},
        int(time.time())+ttl, 'ADMIN', count)


def rows(f):
    c=f()
    try: return [dict(r) for r in c.execute('SELECT * FROM broadcast_items ORDER BY id').fetchall()]
    finally: c.close()


def test_scope_snapshot_dedup_and_atomic_double_click(factory):
    assert b.preview(factory,1,'SPECIFIC_AREA',1)==1  # NULL is not silently global.
    def attempt():
        try: return queue(factory)
        except ValueError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(x is not None for x in outcomes)==1
    assert len(rows(factory))==3
    assert all(r['attempts']==0 for r in rows(factory))
    assert b.preview(factory,1,'ALL_MONITORED',None)==0


def test_audience_change_and_unreviewed_are_rejected(factory):
    with pytest.raises(ValueError, match='audience changed'): queue(factory,count=4)
    assert rows(factory)==[]
    c=factory();c.execute("UPDATE alerts SET lifecycle_status='DRAFT'");c.commit();c.close()
    with pytest.raises(ValueError, match='reviewed'): queue(factory)


def test_legacy_history_by_phone_prevents_resend(factory):
    c=factory();c.execute("INSERT INTO notification_deliveries(alert_id,recipient_id,channel,status) VALUES(1,2,'sms','DELIVERED')");c.commit();c.close()
    assert b.preview(factory,1,'ALL_MONITORED',None)==2


def test_consent_revoked_after_snapshot_and_new_connection(factory):
    queue(factory)
    c=factory();c.execute("UPDATE notification_recipients SET consent_status='REVOKED' WHERE id=1");c.commit();c.close()
    sent=[]
    assert not b.process_one(factory,lambda *a:sent.append(a))
    assert rows(factory)[0]['status']=='SKIPPED'
    assert sent==[]
    assert b.process_one(factory,lambda *a:{'sid':'SMsynthetic','status':'queued'})
    assert rows(factory)[1]['provider_message_sid']=='SMsynthetic'


def test_global_rate_gate_and_worker_claim_concurrency(factory):
    queue(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed=list(pool.map(lambda _:b.claim(factory,0.1),range(2)))
    assert sum(x is not None for x in claimed)==1
    assert sum(r['status']=='SENDING' for r in rows(factory))==1


def test_unknown_never_retried_and_stale_claim_recovered(factory):
    job=queue(factory)
    def timeout(*_): raise TimeoutError('provider may have accepted')
    assert b.process_one(factory,timeout)
    assert rows(factory)[0]['status']=='UNKNOWN'
    b.control(factory,job['id'],'retry_failed')
    assert rows(factory)[0]['status']=='UNKNOWN'
    c=factory();c.execute("UPDATE broadcast_items SET status='SENDING',updated_at=? WHERE id=?",(int(time.time())-130,rows(factory)[1]['id']));c.commit();c.close()
    b.claim(factory,1)
    assert rows(factory)[1]['status']=='UNKNOWN'


def test_pause_cancel_expiry_and_resolve(factory):
    job=queue(factory)
    b.control(factory,job['id'],'pause'); assert b.claim(factory,1) is None
    b.control(factory,job['id'],'resume')
    c=factory();c.execute("UPDATE alerts SET lifecycle_status='RESOLVED'");c.commit();c.close()
    assert b.claim(factory,1) is None
    assert all(r['status']=='CANCELED' for r in rows(factory))
    b.control(factory,job['id'],'cancel')
    with pytest.raises(ValueError,match='Canceled'): b.control(factory,job['id'],'resume')


def test_expiry_blocks_unsent_and_retry(factory):
    job=queue(factory,ttl=-1)
    assert b.claim(factory,1) is None
    assert all(r['status']=='EXPIRED' for r in rows(factory))
    with pytest.raises(ValueError,match='expired'): b.control(factory,job['id'],'retry_failed')


def test_429_backoff_and_confirmed_rejection(factory):
    queue(factory)
    class Limit(Exception): status=429;code=20429
    def reject(*_): raise Limit()
    assert b.process_one(factory,reject)
    r=rows(factory)[0]
    assert r['status']=='READY' and r['available_at']>time.time()+5
    assert r['attempts']==1


def test_provider_block_pauses_job_and_receipts_do_not_regress(factory):
    queue(factory)
    class Trial(Exception): status=400;code=21608
    def reject(*_): raise Trial()
    b.process_one(factory,reject)
    assert rows(factory)[0]['status']=='FAILED'
    assert b.overview(factory)['jobs'][0]['status']=='PAUSED'
    c=factory();c.execute("UPDATE broadcast_items SET status='QUEUED',provider_message_sid='SMtest' WHERE id=?",(rows(factory)[0]['id'],));c.commit();c.close()
    b.record_status(factory,'SMtest','delivered')
    b.record_status(factory,'SMtest','sent')
    b.record_status(factory,'SMtest','failed')
    assert rows(factory)[0]['status']=='DELIVERED'


def test_trial_account_diagnostic(monkeypatch):
    import notifications as n
    from types import SimpleNamespace
    monkeypatch.setattr(n,'config_status',lambda:{'sms':{'issues':[]}})
    acc=SimpleNamespace(type='Trial',status='active')
    accounts=lambda _:SimpleNamespace(fetch=lambda:acc)
    monkeypatch.setattr(n,'_client',lambda:SimpleNamespace(api=SimpleNamespace(v2010=SimpleNamespace(accounts=accounts))))
    assert not n.production_account_status()['ready']
    acc.type='Full'
    assert n.production_account_status()['ready']
    acc.status='suspended'
    assert not n.production_account_status()['ready']


def test_admin_gate_and_preview_does_not_send(factory,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import broadcast_api as api
    import auth
    monkeypatch.setattr(api,'BROADCAST_PROVIDER','twilio')
    monkeypatch.setattr(auth,'AUTH_REQUIRED',True)
    monkeypatch.setattr(api,'production_account_status',lambda:{'ready':False,'issues':['Trial account'],'account_type':'Trial'})
    app=FastAPI();app.include_router(api.routes(factory,[{'id':1,'name':'Synthetic','state':'Test'}],lambda *a,**k:'TEST ONLY'))
    app.dependency_overrides[api.resolve_role]=lambda:'FIELD_OFFICER'
    c=TestClient(app)
    body={'alert_id':1,'scope':'ALL_MONITORED','expected_recipients':3}
    assert c.post('/api/broadcasts/preview',json=body).status_code==403
    assert c.post('/api/broadcasts',json=body).status_code==403
    app.dependency_overrides[api.resolve_role]=lambda:'ADMIN'
    out=c.post('/api/broadcasts/preview',json=body)
    assert out.status_code==200 and out.json()['recipients']==3
    assert not out.json()['ready']
    assert c.post('/api/broadcasts',json=body).status_code==503
    assert rows(factory)==[]
    monkeypatch.setattr(api,'BROADCAST_ENABLED',True)
    monkeypatch.setattr(api,'DATABASE_URL','configured-test-database')
    monkeypatch.setattr(api,'production_account_status',lambda:{'ready':True,'issues':[],'account_type':'Full'})
    b.claim(factory,1)  # Heartbeat only; there are no queued items yet.
    assert c.post('/api/broadcasts/preview',json=body).json()['ready']
    assert c.post('/api/broadcasts',json={**body,'expected_recipients':1000000}).status_code==409
    assert c.post('/api/broadcasts',json=body).status_code==202
    assert len(rows(factory))==3
    assert c.post('/api/broadcasts',json=body).status_code==409


def test_large_audience_is_queued_without_provider_calls(factory):
    c=factory()
    # Database-side generation avoids making a test HTTP call per recipient.
    from database import PostgresConnection
    if isinstance(c,PostgresConnection):
        c.execute("INSERT INTO notification_recipients(name,phone_e164,location_id) SELECT 'Synthetic large audience', '+1999' || lpad(n::text,7,'0'), 1 FROM generate_series(1,100000) n")
    else:
        c.execute("WITH RECURSIVE nums(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM nums WHERE n<100000) INSERT INTO notification_recipients(name,phone_e164,location_id) SELECT 'Synthetic large audience', '+1999' || printf('%07d',n),1 FROM nums")
    c.commit();c.close()
    out=queue(factory,count=100003)
    assert out['queued']==100003
    summary=b.overview(factory)
    assert summary['jobs'][0]['counts']=={'READY':100003}
