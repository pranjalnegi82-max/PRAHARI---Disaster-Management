"""MSG91 Flow API tests use synthetic Indian numbers and a fake HTTP opener."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from database import connect
from database_schema import initialize_schema
import broadcasts
import msg91_provider as m
from test_database import pg_url

TEMPLATE = {'en':{'template_id':'eng123456', 'body':'PRAHARI for ##VAR1##: ##VAR2##'},
            'hi':{'template_id':'hin123456', 'body':'PRAHARI HI ##VAR1##: ##VAR2##'},
            'as':{'template_id':'asm123456', 'body':'PRAHARI AS ##VAR1##: ##VAR2##'}}
KEY = 'synthetic-secret-for-tests-only'
WEBHOOK_TOKEN = 'synthetic-webhook-secret-of-more-than-32-characters'


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    monkeypatch.setattr(m, 'MSG91_TEMPLATES_JSON',json.dumps(TEMPLATE))
    monkeypatch.setattr(m,'MSG91_AUTHKEY',KEY)
    monkeypatch.setattr(m,'MSG91_TEMPLATES_APPROVED',True)
    monkeypatch.setattr(m,'MSG91_WEBHOOK_TOKEN',WEBHOOK_TOKEN)


@pytest.fixture(params=['sqlite','postgres'])
def factory(request,tmp_path):
    url=request.getfixturevalue('pg_url') if request.param=='postgres' else ''
    f=lambda:connect(tmp_path/'sms.db',url)
    initialize_schema(f)
    c=f();c.execute("INSERT INTO alerts(id,location_id,location,message_en,lifecycle_status) VALUES(1,1,'Synthetic, Test','TEST ONLY no alert','REVIEWED')")
    for name,phone,lang in [('English','+919876543210','en'),('Hindi','+919876543211','hi'),('Assamese','+919876543212','as'),('Foreign','+12025550101','en')]:
        c.execute('INSERT INTO notification_recipients(name,phone_e164,location_id,language,sms_enabled,consent_status) VALUES(?,?,?,?,1,?)',(name,phone,1,lang,'ACTIVE'))
    c.commit();c.close();return f


def plans():
    alert={'location':'Synthetic, Test'}
    return {lang:m.message_plan(alert,lang,'TEST ONLY no alert') for lang in ('en','hi','as')}


def queued(factory):
    return broadcasts.enqueue(factory,1,'ALERT_AREA',1,'Synthetic, Test',plans(),
                              int(time.time())+3600,'ADMIN',3,'msg91')


def records(factory):
    con=factory()
    try:return [dict(x) for x in con.execute('SELECT * FROM broadcast_items ORDER BY id').fetchall()]
    finally:con.close()


def test_requires_approved_templates_and_never_exposes_key(monkeypatch):
    assert m.status()['ready']
    monkeypatch.setattr(m,'MSG91_TEMPLATES_APPROVED',False)
    assert not m.status()['ready']
    assert KEY not in repr(m.status())
    monkeypatch.setattr(m,'MSG91_TEMPLATES_JSON',json.dumps({'en':{'template_id':'abc12345','body':'##VAR1## only'}}))
    assert not m.status()['ready']
    with pytest.raises(ValueError,match='Missing approved'):
        m.message_plan({'location':'Test'},'en','Test')


def test_scope_approved_text_snapshot_and_indian_only(factory):
    assert broadcasts.preview(factory,1,'ALERT_AREA',1,'msg91')==3
    assert broadcasts.audience_languages(factory,1,'ALERT_AREA',1,'msg91')=={'en','hi','as'}
    queued(factory)
    data=records(factory)
    assert len(data)==3
    assert [x['provider'] for x in data]==['msg91']*3
    assert [x['template_id'] for x in data]==['eng123456','hin123456','asm123456']
    assert all(x['message']==plans()[lang]['text'] for lang,x in zip(('en','hi','as'),data))
    assert broadcasts.preview(factory,1,'ALERT_AREA',1,'msg91')==0
    assert broadcasts.preview(factory,1,'ALERT_AREA',1,'twilio')==1


def test_fake_flow_payload_and_no_auto_retry_of_unknown(factory,monkeypatch):
    queued(factory)
    requested=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,size):return b'{"type":"success","message":"1234567890abcdef"}'
    def fake(request,timeout):
        requested.append((request,timeout));return Reply()
    monkeypatch.setattr(m,'urlopen',fake)
    assert broadcasts.process_one(factory,m.send,1,'msg91')
    req,timeout=requested[0]
    assert req.full_url==m.API_URL and timeout==20
    assert req.get_header('Authkey')==KEY
    body=json.loads(req.data)
    row=records(factory)[0]
    assert body=={'template_id':'eng123456','short_url':'0','recipients':[{
        'mobiles':'919876543210','VAR1':'Synthetic, Test','VAR2':'TEST ONLY no alert',
        'CRQID':f"B{row['id']}"}]}
    assert row['status']=='QUEUED' and row['provider_message_sid']=='1234567890abcdef'


def test_changed_template_is_not_silently_sent(factory,monkeypatch):
    queued(factory)
    monkeypatch.setattr(m,'MSG91_TEMPLATES_JSON',json.dumps({**TEMPLATE,'en':{'template_id':'eng123456','body':'CHANGED ##VAR1## ##VAR2##'}}))
    invoked=[]
    with pytest.raises(m.Msg91Rejection,match='rejected'):
        m.send(records(factory)[0],opener=lambda *args:invoked.append(args))
    assert invoked==[]


def test_rejections_pause_and_timeouts_hold(factory,monkeypatch):
    queued(factory)
    class Reject:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,size):return b'{"type":"error","code":301,"message":"Insufficient Balance"}'
    monkeypatch.setattr(m,'urlopen',lambda *a,**k:Reject())
    assert broadcasts.process_one(factory,m.send,1,'msg91')
    assert records(factory)[0]['status']=='FAILED'
    assert broadcasts.overview(factory)['jobs'][0]['status']=='PAUSED'
    broadcasts.control(factory,1,'resume')
    con=factory();con.execute('UPDATE broadcast_runtime SET next_send=0');con.commit();con.close()
    def timeout(*a,**k):raise TimeoutError('Provider might have accepted')
    monkeypatch.setattr(m,'urlopen',timeout)
    broadcasts.process_one(factory,m.send,1,'msg91')
    assert records(factory)[1]['status']=='UNKNOWN'
    broadcasts.control(factory,1,'retry_failed')
    assert records(factory)[1]['status']=='UNKNOWN'


def test_webhook_secret_correlation_phone_and_order(factory,monkeypatch):
    queued(factory)
    import main
    monkeypatch.setattr(main,'db',factory)
    c=TestClient(main.app)
    row=records(factory)[0]
    payload={'CRQID':f"B{row['id']}",'requestId':'1234567890abcdef',
             'telNum':'919876543210','status':'1'}
    url='/api/notification/msg91/status'
    assert c.post(url,json=payload).status_code==403
    assert c.post(url,json=payload,headers={'X-PRAHARI-Webhook-Token':'wrong'}).status_code==403
    assert records(factory)[0]['status']=='READY'
    headers={'X-PRAHARI-Webhook-Token':WEBHOOK_TOKEN}
    assert c.post(url,json={**payload,'telNum':'919876543299'},headers=headers).status_code==204
    assert records(factory)[0]['status']=='READY'
    assert c.post(url,json=payload,headers=headers).status_code==204
    assert records(factory)[0]['status']=='DELIVERED'
    assert c.post(url,json={**payload,'status':'2'},headers=headers).status_code==204
    assert records(factory)[0]['status']=='DELIVERED'
    assert c.post(url,json={**payload,'requestId':'different-remote-id'},headers=headers).status_code==204
    assert records(factory)[0]['provider_message_sid']=='1234567890abcdef'
    assert c.post(url,json={**payload,'CRQID':'0','status':'1'},headers=headers).status_code==204
    assert records(factory)[0]['status']=='DELIVERED'
    assert c.post(url,json={**payload,'CRQID':'B999999'},headers=headers).status_code==204
    assert len(records(factory))==3


def test_consent_revocation_blocks_provider_request(factory,monkeypatch):
    queued(factory)
    c=factory();c.execute("UPDATE notification_recipients SET consent_status='REVOKED' WHERE id=1");c.commit();c.close()
    called=[]
    assert broadcasts.process_one(factory,lambda item:called.append(item),1,'msg91') is False
    assert called==[] and records(factory)[0]['status']=='SKIPPED'
