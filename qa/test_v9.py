"""Consequential regression tests for PRAHARI v9.
Run from the project root with: python -m pytest qa/test_v9.py -q
"""
from __future__ import annotations
import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TEST_DB = ROOT / "qa" / "prahari_test.db"
os.environ["PRAHARI_DB_PATH"] = str(TEST_DB)
os.environ["PRAHARI_AUTH_REQUIRED"] = "false"

import main  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    if TEST_DB.exists():
        TEST_DB.unlink()
    main.init_db()
    main.LIVE_REGIONAL_CACHE["data"] = None
    main.LIVE_REGIONAL_CACHE["ts"] = 0
    main.LIVE_WEATHER_CACHE.clear()
    yield
    main.LIVE_REGIONAL_CACHE["data"] = None
    main.LIVE_REGIONAL_CACHE["ts"] = 0
    main.LIVE_WEATHER_CACHE.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def test_replay_is_explicit_and_assessable(client):
    r = client.get("/api/live/locations/1?mode=replay")
    assert r.status_code == 200
    body = r.json()
    assert body["data_state"] == "HISTORICAL_REPLAY"
    assert body["assessment_status"] == "ASSESSED"
    assert body["risk_probability"] is None
    assert body["risk_percent"] is not None
    assert any(s["state"] == "HISTORICAL_REPLAY" for s in body["sources"])


def test_provider_failure_is_missing_not_low(monkeypatch, client):
    main.LIVE_WEATHER_CACHE.clear()
    monkeypatch.setattr(main, "_load_source_cache", lambda key: None)
    def fail(*args, **kwargs):
        raise main.URLError("offline")
    monkeypatch.setattr(main, "urlopen", fail)
    r = client.get("/api/live/locations/1?mode=live&force=true")
    assert r.status_code == 200
    body = r.json()
    assert body["data_state"] == "MISSING"
    assert body["assessment_status"] == "INSUFFICIENT_DATA"
    assert body["risk_level"] == "UNKNOWN"
    assert body["risk_percent"] is None


def test_stale_real_packet_is_labeled_stale(monkeypatch, client):
    now = int(main.time.time())
    packet = main.build_replay_packet(main.LOCATIONS[0])
    packet.update({
        "availability": "CURRENT", "live": True, "source": "Open-Meteo test packet",
        "updated_at": now, "valid_time": "2026-09-16T12:00",
    })
    main.LIVE_WEATHER_CACHE[1] = {"packet": packet, "cached_at": now}
    def fail(*args, **kwargs):
        raise main.URLError("offline")
    monkeypatch.setattr(main, "urlopen", fail)
    r = client.get("/api/weather/1?force=true")
    assert r.status_code == 200
    assert r.json()["availability"] == "STALE"
    assert r.json()["live"] is False


def test_invalid_location_returns_404(client):
    assert client.get("/api/live/locations/999?mode=replay").status_code == 404


def test_assessment_persists_and_exports(client):
    r = client.post("/api/assessments/1?mode=replay")
    assert r.status_code == 200
    aid = r.json()["assessment_id"]
    history = client.get("/api/assessments/1/history").json()
    assert history and history[0]["id"] == aid
    exported = client.get(f"/api/assessment-records/{aid}/export?format=json")
    assert exported.status_code == 200
    out = exported.json()
    assert out["mode"] == "replay"
    assert out["risk_index"] is not None
    assert out["sources"]
    with sqlite3.connect(TEST_DB) as con:
        assert con.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 1


def test_duplicate_draft_alert_is_prevented(client):
    one = client.post("/api/assessments/1?mode=replay")
    two = client.post("/api/assessments/1?mode=replay")
    assert one.status_code == two.status_code == 200
    alerts = client.get("/api/alerts").json()
    matching = [a for a in alerts if a["source"] == "assessment-replay" and a["location_id"] == 1]
    assert len(matching) == 1
    assert matching[0]["lifecycle_status"] == "DRAFT"
    assert not matching[0]["public_warning_issued"]


def test_alert_lifecycle_and_authorization_boundary(monkeypatch, client):
    import auth
    auth.AUTH_REQUIRED = True
    auth.OPERATOR_KEY = "operator-test"
    auth.REVIEWER_KEY = "reviewer-test"
    auth.ADMIN_KEY = "admin-test"
    try:
        created = client.post("/api/assessments/1?mode=replay", headers={"X-PRAHARI-Key":"operator-test"})
        assert created.status_code == 200
        alert = client.get("/api/alerts").json()[0]
        aid = alert["id"]
        assert client.patch(f"/api/alerts/{aid}/transition", json={"to_status":"REVIEWED"}).status_code == 403
        assert client.patch(f"/api/alerts/{aid}/transition", headers={"X-PRAHARI-Key":"operator-test"}, json={"to_status":"ISSUED"}).status_code == 403
        assert client.patch(f"/api/alerts/{aid}/transition", headers={"X-PRAHARI-Key":"operator-test"}, json={"to_status":"REVIEWED"}).status_code == 200
        assert client.patch(f"/api/alerts/{aid}/transition", headers={"X-PRAHARI-Key":"operator-test"}, json={"to_status":"ISSUED"}).status_code == 403
        issued = client.patch(f"/api/alerts/{aid}/transition", headers={"X-PRAHARI-Key":"reviewer-test"}, json={"to_status":"ISSUED"})
        assert issued.status_code == 200
        assert issued.json()["alert"]["public_warning_issued"] is True
    finally:
        auth.AUTH_REQUIRED = False


def test_invalid_upload_signature_is_rejected(client):
    data = {
        "reporter":"Field observer", "phone":"", "location":"Gangtok, Sikkim",
        "lat":"27.3314", "lon":"88.6138", "hazard_type":"Surface crack",
        "location_method":"manual", "severity":"HIGH",
        "description":"A widening crack is visible across the slope shoulder."
    }
    files = {"image": ("fake.jpg", b"not-a-jpeg", "image/jpeg")}
    r = client.post("/api/reports", data=data, files=files)
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]


def test_report_persists_and_requires_operator_for_status(monkeypatch, client):
    data = {
        "reporter":"Field observer", "phone":"", "location":"Gangtok, Sikkim",
        "lat":"27.3314", "lon":"88.6138", "hazard_type":"Slope movement",
        "location_method":"manual", "severity":"MODERATE",
        "description":"Slow visible movement and fresh small cracks after rain."
    }
    r = client.post("/api/reports", data=data)
    assert r.status_code == 200
    rid = r.json()["report"]["id"]
    assert client.get("/api/reports").json()[0]["id"] == rid
    import auth
    auth.AUTH_REQUIRED = True; auth.OPERATOR_KEY = "operator-test"
    try:
        assert client.patch(f"/api/reports/{rid}/status?status=VERIFIED").status_code == 403
        ok = client.patch(f"/api/reports/{rid}/status?status=VERIFIED", headers={"X-PRAHARI-Key":"operator-test"})
        assert ok.status_code == 200
    finally:
        auth.AUTH_REQUIRED = False


def test_simulated_iot_cannot_escalate_live_alert(client):
    before = len(client.get("/api/alerts").json())
    r = client.post("/api/iot/demo/1")
    assert r.status_code == 200
    assert r.json()["source"] == "SIMULATED_HACKATHON"
    assert r.json()["draft_advisory_created"] is False
    after = len(client.get("/api/alerts").json())
    assert after == before


def test_satellite_endpoint_does_not_claim_model_inference(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_live_weather", lambda x, **kwargs: main.build_replay_packet(x))
    r = client.get("/api/satellite/1")
    assert r.status_code == 200
    body = r.json()
    assert body["pipeline_status"] == "SCENE_DISCOVERY_IMPLEMENTED"
    assert body["analysis_mode"] == "SENTINEL2_SCENE_QA_PLUS_VISUAL_CONTEXT"
    assert body["detection_module"]["status"] == "CHECK_MODEL_STATUS_ENDPOINT"
    assert "candidate_polygons" not in body


def _make_reviewed_alert(client):
    created = client.post('/api/assessments/1?mode=replay')
    assert created.status_code == 200
    alert = client.get('/api/alerts').json()[0]
    aid = alert['id']
    reviewed = client.patch(f'/api/alerts/{aid}/transition', json={'to_status':'REVIEWED','note':'verified for notification test'})
    assert reviewed.status_code == 200
    return aid


def test_notification_recipient_requires_explicit_consent(client):
    r = client.post('/api/notification/recipients', json={
        'name':'Test resident','phone_e164':'+919876543210','location_id':1,'language':'en',
        'sms_enabled':True,'consent_confirmed':False,
    })
    assert r.status_code == 400
    assert 'consent' in r.json()['detail'].lower()


def test_admin_issue_and_notify_tracks_sms(monkeypatch, client):
    aid = _make_reviewed_alert(client)
    enrolled = client.post('/api/notification/recipients', json={
        'name':'Opted-in resident','phone_e164':'+919876543210','location_id':1,'language':'en',
        'sms_enabled':True,'consent_confirmed':True,
    })
    assert enrolled.status_code == 200

    monkeypatch.setattr(main, 'notification_config_status', lambda: {
        'provider':'twilio','credentials_configured':True,
        'sms':{'enabled':True,'ready':True,'sender_configured':True},
        'status_callback':None,'signature_validation':True,
    })
    sent=[]
    def fake_send(channel,to,body):
        sent.append((channel,to,body))
        return {'provider':'twilio','sid':f'SMTEST{len(sent)}','status':'queued','to':to,'channel':channel}
    monkeypatch.setattr(main, 'send_notification', fake_send)

    r = client.post(f'/api/alerts/{aid}/issue-and-notify', json={})
    assert r.status_code == 200
    body=r.json()
    assert body['accepted_or_queued'] == 1
    assert [x[0] for x in sent] == ['sms']
    alert=client.get('/api/alerts').json()[0]
    assert alert['lifecycle_status'] == 'ISSUED'
    deliveries=client.get(f'/api/alerts/{aid}/deliveries').json()
    assert len(deliveries) == 1
    assert deliveries[0]['channel'] == 'sms'
    assert deliveries[0]['status'] == 'QUEUED'

    # A repeated admin action does not duplicate already-attempted delivery.
    again = client.post(f'/api/alerts/{aid}/issue-and-notify', json={})
    assert again.status_code == 200
    assert len(sent) == 1
    assert all(x['status']=='SKIPPED_DUPLICATE' for x in again.json()['results'])


def test_twilio_callback_updates_delivery_confirmation(monkeypatch, client):
    aid = _make_reviewed_alert(client)
    recipient=client.post('/api/notification/recipients', json={
        'name':'Test resident','phone_e164':'+919876543210','location_id':1,'language':'en',
        'sms_enabled':True,'consent_confirmed':True,
    }).json()['recipient']
    main._upsert_delivery(aid,recipient['id'],'sms',status='SENT',sid='SMCALLBACK1')
    monkeypatch.setattr(main,'validate_twilio_signature',lambda url,form,signature: True)
    cb=client.post('/api/notification/twilio/status', data={'MessageSid':'SMCALLBACK1','MessageStatus':'delivered'})
    assert cb.status_code == 204
    deliveries=client.get(f'/api/alerts/{aid}/deliveries').json()
    assert deliveries[0]['status'] == 'DELIVERED'
    assert deliveries[0]['delivered_at'] is not None


def test_external_notification_management_is_admin_only(client):
    import auth
    auth.AUTH_REQUIRED = True
    auth.OPERATOR_KEY = 'operator-test'
    auth.ADMIN_KEY = 'admin-test'
    try:
        payload={
            'name':'Opted-in resident','phone_e164':'+919876543210','location_id':1,'language':'en',
            'sms_enabled':True,'consent_confirmed':True,
        }
        denied=client.post('/api/notification/recipients',headers={'X-PRAHARI-Key':'operator-test'},json=payload)
        assert denied.status_code == 403
        allowed=client.post('/api/notification/recipients',headers={'X-PRAHARI-Key':'admin-test'},json=payload)
        assert allowed.status_code == 200
    finally:
        auth.AUTH_REQUIRED = False


def test_field_officer_enrollment_is_locked_to_posting(client):
    import auth
    auth.AUTH_REQUIRED = True
    auth.FIELD_OFFICERS = [{
        'name':'Gangtok Field Officer','officer_code':'FO-GTK-01','location_id':1,'key':'field-gangtok-test'
    }]
    try:
        headers={'X-PRAHARI-Key':'field-gangtok-test'}
        status=client.get('/api/auth/status',headers=headers)
        assert status.status_code == 200
        assert status.json()['current_role'] == 'FIELD_OFFICER'
        assert status.json()['actor']['posting_location_id'] == 1

        created=client.post('/api/field/households',headers=headers,json={
            'name':'Tashi Household','phone_e164':'+919811111111','location_id':2,'language':'en',
            'household_label':'House 4','village':'Upper Ranka','household_size':5,'consent_confirmed':True,
        })
        assert created.status_code == 200
        record=created.json()['recipient']
        assert record['location_id'] == 1  # body area cannot override officer posting
        assert record['registered_by_officer_code'] == 'FO-GTK-01'
        assert record['registration_source'] == 'FIELD_OFFICER_PORTAL'

        rows=client.get('/api/field/households?location_id=2',headers=headers).json()
        assert len(rows) == 1 and rows[0]['location_id'] == 1
        denied=client.post('/api/notification/recipients',headers=headers,json={
            'name':'Outside posting','phone_e164':'+919822222222','location_id':2,'language':'en',
            'sms_enabled':True,'consent_confirmed':True,
        })
        assert denied.status_code == 403
    finally:
        auth.AUTH_REQUIRED = False
        auth.FIELD_OFFICERS = []


def test_admin_can_broadcast_to_specific_or_all_monitored_areas(monkeypatch, client):
    aid = _make_reviewed_alert(client)
    for name,phone,location_id in [
        ('Gangtok resident','+919833333331',1),('Aizawl resident','+919833333332',2)
    ]:
        r=client.post('/api/notification/recipients',json={
            'name':name,'phone_e164':phone,'location_id':location_id,'language':'en',
            'sms_enabled':True,'consent_confirmed':True,
        })
        assert r.status_code == 200
    monkeypatch.setattr(main, 'notification_config_status', lambda: {
        'provider':'twilio','credentials_configured':True,
        'sms':{'enabled':True,'ready':True,'sender_configured':True},
        'status_callback':None,'signature_validation':True,
    })
    sent=[]
    monkeypatch.setattr(main,'send_notification',lambda channel,to,body: (sent.append(to) or {'provider':'twilio','sid':f'SMSCOPE{len(sent)}','status':'queued'}))

    preview=client.get(f'/api/alerts/{aid}/notification-preview?scope=SPECIFIC_AREA&target_location_id=2')
    assert preview.status_code == 200
    assert preview.json()['sms_recipients'] == 1
    assert 'Aizawl' in preview.json()['target_label']

    out=client.post(f'/api/alerts/{aid}/issue-and-notify',json={'scope':'ALL_MONITORED'})
    assert out.status_code == 200
    assert out.json()['eligible_recipients'] == 2
    assert out.json()['target_label'] == 'All monitored areas'
    assert len(sent) == 2


def test_separate_admin_portal_login(client, monkeypatch):
    import auth
    monkeypatch.setattr(main, 'ADMIN_KEY', 'admin-portal-test')
    monkeypatch.setattr(main, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(auth, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(auth, 'ADMIN_KEY', 'admin-portal-test')

    denied = client.post('/api/auth/login', json={'portal':'ADMIN','access_key':'wrong'})
    assert denied.status_code == 401
    ok = client.post('/api/auth/login', json={'portal':'ADMIN','access_key':'admin-portal-test'})
    assert ok.status_code == 200
    assert ok.json()['portal'] == 'ADMIN'
    assert ok.json()['current_role'] == 'ADMIN'

    status = client.get('/api/auth/status', headers={'X-PRAHARI-Key':'admin-portal-test'})
    assert status.status_code == 200
    assert status.json()['current_role'] == 'ADMIN'


def test_separate_field_officer_portal_login_is_posting_scoped(client, monkeypatch):
    import auth
    officers=[{'name':'Gangtok Field Officer','officer_code':'FO-GTK-01','location_id':1,'key':'field-portal-test'}]
    monkeypatch.setattr(auth, 'FIELD_OFFICERS', officers)

    mismatch = client.post('/api/auth/login', json={
        'portal':'FIELD_OFFICER','officer_code':'FO-AIZ-99','access_key':'field-portal-test'
    })
    assert mismatch.status_code == 401

    ok = client.post('/api/auth/login', json={
        'portal':'FIELD_OFFICER','officer_code':'FO-GTK-01','access_key':'field-portal-test'
    })
    assert ok.status_code == 200
    body=ok.json()
    assert body['portal'] == 'FIELD_OFFICER'
    assert body['current_role'] == 'FIELD_OFFICER'
    assert body['actor']['posting_location_id'] == 1
    assert 'Gangtok' in body['actor']['posting']

    # A field-officer key cannot become an admin just by selecting the admin portal.
    denied_admin = client.post('/api/auth/login', json={'portal':'ADMIN','access_key':'field-portal-test'})
    # If no admin key is configured, local development admin access is intentionally open.
    # Configure an admin key for this boundary test.
    monkeypatch.setattr(main, 'ADMIN_KEY', 'real-admin-key')
    denied_admin = client.post('/api/auth/login', json={'portal':'ADMIN','access_key':'field-portal-test'})
    assert denied_admin.status_code == 401
