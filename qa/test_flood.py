"""Flash-flood safety and integration regressions; no external network required."""
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['PRAHARI_AUTH_REQUIRED'] = 'false'
os.environ['PRAHARI_ENABLE_TEST_FIXTURES'] = 'true'
os.environ['PRAHARI_DB_PATH'] = str(Path(__file__).resolve().parent / 'prahari_test.db')

import main
from auth import resolve_role
from flood_risk import assess


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'flood.db')
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'flood.db')
    main.init_db()
    main.app.dependency_overrides[resolve_role] = lambda: 'ADMIN'
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def packet():
    now=int(time.time())
    return {
        'availability':'CURRENT','source':'test provider','updated_at':now,
        'valid_time':'fixture','valid_at_epoch':now,
        'soil_moisture_proxy_pct':80,'antecedent_rainfall_72h_mm':240,
        'rain_forecast_1h_mm':38,'rain_forecast_3h_mm':82,'rain_forecast_6h_mm':125,
    }


def configured_body():
    return {
        'name':'QA catchment',
        'context_status':'CONFIGURED',
        'provenance':'QA threshold reference',
        'thresholds_mm':{'1':30,'3':60,'6':100},
        'villages':[{'name':'QA ward','lat':27.3314,'lon':88.6138}],
        'slope_context':'',
        'historical_events_source':'',
        'station_id':'gauge-1',
        'danger_stage_m':3.0,
    }


def configured(client):
    body=configured_body()
    assert client.post('/api/flood/basins/1',json=body).status_code==200
    return body


def test_unconfigured_catchment_never_invents_thresholds(client, monkeypatch):
    monkeypatch.setattr(main,'fetch_live_weather',lambda x:packet())
    r=client.get('/api/flood/screen/1').json()
    assert r['status']=='UNCONFIGURED'
    assert r['level']=='UNKNOWN'
    assert 'catchment_configuration' in r['missing']
    assert all(w['screening_threshold_mm'] is None for w in r['windows'])


def test_test_fixture_replay_cannot_create_public_workflow_draft(client):
    response=client.post('/api/flood/assessments/1?mode=replay')
    assert response.status_code==201
    body=response.json()
    assert body['assessment']['probability'] is None
    assert body['assessment']['validated_lead_time_minutes'] is None
    assert body['assessment']['data_state']=='HISTORICAL_REPLAY'
    assert client.post(f"/api/flood/records/{body['id']}/draft").status_code==409
    assert len(client.get('/api/flood/history/1').json())==1


def test_replay_is_disabled_without_test_flag(client, monkeypatch):
    monkeypatch.setenv('PRAHARI_ENABLE_TEST_FIXTURES','false')
    assert client.get('/api/flood/screen/1?mode=replay').status_code==404


@pytest.mark.parametrize('bad',[None,-1,float('nan'),float('inf')])
def test_bad_rain_is_unknown(client,bad):
    basin=configured(client)
    p=packet();p['rain_forecast_1h_mm']=bad
    r=assess(p,basin,now=int(time.time()))
    assert r['level']=='UNKNOWN'
    assert 'rain_forecast_1h_mm' in r['missing']


def test_actual_zero_is_low_and_empty_window_is_missing(client):
    basin=configured(client)
    p=packet()
    for h in (1,3,6):p[f'rain_forecast_{h}h_mm']=0
    assert assess(p,basin,now=int(time.time()))['level']=='LOW'
    assert main._complete_rain_window([],[],1) is None
    assert main._complete_rain_window([2,None,4],[0,1,2],3) is None
    assert main._complete_rain_window([0,0,0],[0,1,2],3)==0


def test_missing_early_window_does_not_erase_later_thresholds(client):
    basin=configured(client)
    p=packet();p['rain_forecast_1h_mm']=None
    r=assess(p,basin,now=int(time.time()))
    assert r['level']=='UNKNOWN'
    assert r['windows'][0]['screening_threshold_mm'] is not None
    assert r['windows'][1]['screening_threshold_mm'] is not None
    assert r['windows'][2]['screening_threshold_mm'] is not None


def test_sensor_freshness_quality_source_and_matching(client):
    basin=configured(client)
    p=packet();p['valid_at_epoch']=10000
    for h in (1,3,6):p[f'rain_forecast_{h}h_mm']=0
    g={'station_id':'gauge-1','source':'REAL_SENSOR','observed_at':10000,'water_level_m':4,'quality':1}
    assert assess(p,basin,g,10010)['level']=='CRITICAL'
    for change in ({'source':'SIMULATED_HACKATHON'},{'source':'MANUAL_TEST'},{'observed_at':8000},{'observed_at':11000},{'quality':0.5},{'station_id':'other'}):
        assert assess(p,basin,g|change,10010)['level']=='LOW'
    p['availability']='STALE'
    assert not assess(p,basin,g,10010)['sensor_used']


def test_auth_and_station_validation(client):
    configured(client)
    main.app.dependency_overrides[resolve_role]=lambda:'FIELD_OFFICER'
    assert client.post('/api/flood/assessments/1?mode=replay').status_code==403
    assert client.post('/api/flood/basins/1',json=configured_body()).status_code==403
    main.app.dependency_overrides[resolve_role]=lambda:'ADMIN'
    g={'station_id':'wrong','source':'REAL_SENSOR','observed_at':int(time.time()),'water_level_m':2,'quality':1}
    assert client.post('/api/flood/sensors/1',json=g).status_code==400
    g.update(station_id='gauge-1',observed_at=int(time.time())+100)
    assert client.post('/api/flood/sensors/1',json=g).status_code==422
    g.update(observed_at=int(time.time()))
    assert client.post('/api/flood/sensors/1',json=g).status_code==201


def test_non_real_gauge_source_rejected(client):
    configured(client)
    payload={'station_id':'gauge-1','source':'SIMULATED_HACKATHON','observed_at':int(time.time()),'water_level_m':2,'quality':1}
    assert client.post('/api/flood/sensors/1',json=payload).status_code==422


def test_live_draft_is_idempotent_and_separate_hazard(client,monkeypatch):
    configured(client);monkeypatch.setattr(main,'fetch_live_weather',lambda x:packet())
    saved=client.post('/api/flood/assessments/1').json()
    path=f"/api/flood/records/{saved['id']}/draft"
    first=client.post(path);second=client.post(path)
    assert first.status_code==200
    alert=first.json()['alert']
    assert alert['id']==second.json()['alert']['id']
    assert alert['advisory_type']=='FLASH_FLOOD'
    assert alert['lifecycle_status']=='DRAFT'
    assert not alert['public_warning_issued']
    assert client.get(f"/api/flood/records/{saved['id']}").json()['basin']['station_id']=='gauge-1'


def test_stale_missing_and_old_assessments_cannot_draft(client,monkeypatch):
    configured(client)
    for state in ('STALE','MISSING'):
        monkeypatch.setattr(main,'fetch_live_weather',lambda x,state=state:packet()|{'availability':state})
        row=client.post('/api/flood/assessments/1').json()
        assert client.post(f"/api/flood/records/{row['id']}/draft").status_code==409


def test_config_validation_and_bad_location(client):
    bad=configured_body();bad['thresholds_mm']={'1':30,'3':20,'6':100}
    assert client.post('/api/flood/basins/1',json=bad).status_code==422
    missing_source=configured_body();missing_source['provenance']=''
    assert client.post('/api/flood/basins/1',json=missing_source).status_code==422
    assert client.get('/api/flood/screen/999').status_code==404


def test_current_provider_time_must_be_fresh(client):
    basin=configured(client)
    p=packet();p['valid_at_epoch']=int(time.time())-20000
    r=assess(p,basin,now=int(time.time()))
    assert r['level']=='UNKNOWN'
    assert 'current_provider_timestamp' in r['missing']


def test_nonconsecutive_hours_are_missing():
    assert main._complete_rain_window([1,2,3],[0,1,2],3,
        ['2026-09-29T10:00','2026-09-29T12:00','2026-09-29T13:00']) is None


def test_location_search_and_persistence_do_not_require_mock_hazards(client, monkeypatch):
    monkeypatch.setattr(main,'_fetch_json_with_retries',lambda *a,**k:{'results':[{
        'id':123,'name':'Mussoorie','admin1':'Uttarakhand','country_code':'IN',
        'latitude':30.4598,'longitude':78.0644,'elevation':2005,'timezone':'Asia/Kolkata'
    }]})
    results=client.get('/api/locations/search?q=Mussoorie').json()
    assert results[0]['name']=='Mussoorie'
    created=client.post('/api/locations',json={
        'name':'Mussoorie','state':'Uttarakhand','lat':30.4598,'lon':78.0644,'source_ref':'123'
    })
    assert created.status_code==201
    row=created.json()
    assert row['source']=='OPEN_METEO_GEOCODING'
    assert 'risk_level' not in row
