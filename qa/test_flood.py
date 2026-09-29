"""SIH26192 safety and integration regressions; no external network required."""
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['PRAHARI_AUTH_REQUIRED'] = 'false'
os.environ['PRAHARI_DB_PATH'] = str(Path(__file__).resolve().parent / 'prahari_test.db')
import main
from auth import resolve_role
from flood_api import Basin
from flood_risk import assess


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'flood.db')
    # main.db uses DB_PATH rather than the legacy DB alias in some versions.
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'flood.db')
    main.init_db()
    main.app.dependency_overrides[resolve_role] = lambda: 'ADMIN'
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def packet():
    return {'availability': 'CURRENT', 'source': 'test provider', 'updated_at': int(time.time()),
            'valid_time': 'fixture', 'valid_at_epoch': int(time.time()), 'soil_moisture_proxy_pct': 80, 'antecedent_rainfall_72h_mm': 240,
            'rain_forecast_1h_mm': 38, 'rain_forecast_3h_mm': 82, 'rain_forecast_6h_mm': 125}


def configured(client):
    b=client.get('/api/flood/basins/1').json()
    b.update(context_status='CONFIGURED', station_id='gauge-1', danger_stage_m=3)
    assert client.post('/api/flood/basins/1',json=b).status_code==200
    return b


def test_demo_cannot_create_public_workflow_draft(client):
    response=client.post('/api/flood/assessments/1?mode=replay')
    assert response.status_code==201
    r=response.json()
    assert r['assessment']['level']=='CRITICAL'
    assert r['assessment']['probability'] is None
    assert r['assessment']['validated_lead_time_minutes'] is None
    assert r['assessment']['source']=='Synthetic flash flood scenario'
    assert client.post(f"/api/flood/records/{r['id']}/draft").status_code==409
    assert len(client.get('/api/flood/history/1').json())==1


@pytest.mark.parametrize('bad',[None,-1,float('nan'),float('inf')])
def test_bad_rain_is_unknown(client,bad):
    p=packet();p['rain_forecast_1h_mm']=bad
    r=assess(p,client.get('/api/flood/basins/1').json(),now=int(time.time()))
    assert r['level']=='UNKNOWN'
    assert 'rain_forecast_1h_mm' in r['missing']


def test_actual_zero_is_low_and_empty_window_is_missing(client):
    p=packet()
    for h in (1,3,6):p[f'rain_forecast_{h}h_mm']=0
    assert assess(p,client.get('/api/flood/basins/1').json(),now=int(time.time()))['level']=='LOW'
    assert main._complete_rain_window([],[],1) is None
    assert main._complete_rain_window([2,None,4],[0,1,2],3) is None
    assert main._complete_rain_window([0,0,0],[0,1,2],3)==0


def test_sensor_freshness_quality_source_and_matching(client):
    b=configured(client);p=packet();p['valid_at_epoch']=10000
    for h in (1,3,6):p[f'rain_forecast_{h}h_mm']=0
    g={'station_id':'gauge-1','source':'REAL_SENSOR','observed_at':10000,'water_level_m':4,'quality':1}
    assert assess(p,b,g,10010)['level']=='CRITICAL'
    for change in ({'source':'SIMULATED_HACKATHON'},{'source':'MANUAL_TEST'},{'observed_at':8000},{'observed_at':11000},{'quality':0.5},{'station_id':'other'}):
        assert assess(p,b,g|change,10010)['level']=='LOW'
    p['availability']='STALE'
    assert not assess(p,b,g,10010)['sensor_used']


def test_auth_and_station_validation(client):
    configured(client)
    main.app.dependency_overrides[resolve_role]=lambda:'FIELD_OFFICER'
    assert client.post('/api/flood/assessments/1?mode=replay').status_code==403
    b=client.get('/api/flood/basins/1').json()
    assert client.post('/api/flood/basins/1',json=b).status_code==403
    main.app.dependency_overrides[resolve_role]=lambda:'ADMIN'
    g={'station_id':'wrong','source':'REAL_SENSOR','observed_at':int(time.time()),'water_level_m':2,'quality':1}
    assert client.post('/api/flood/sensors/1',json=g).status_code==400
    g.update(station_id='gauge-1',observed_at=int(time.time())+100)
    assert client.post('/api/flood/sensors/1',json=g).status_code==422
    g.update(observed_at=int(time.time()))
    assert client.post('/api/flood/sensors/1',json=g).status_code==201


def test_live_draft_is_idempotent_and_separate_hazard(client,monkeypatch):
    configured(client);monkeypatch.setattr(main,'fetch_live_weather',lambda x:packet())
    saved=client.post('/api/flood/assessments/1').json()
    path=f"/api/flood/records/{saved['id']}/draft"
    first=client.post(path);second=client.post(path)
    assert first.status_code==200
    a=first.json()['alert']
    assert a['id']==second.json()['alert']['id']
    assert a['advisory_type']=='FLASH_FLOOD' and a['lifecycle_status']=='DRAFT'
    assert 'Flash flood' in a['message']
    assert not a['public_warning_issued']
    assert client.get(f"/api/flood/records/{saved['id']}").json()['basin']['station_id']=='gauge-1'


def test_stale_missing_and_old_assessments_cannot_draft(client,monkeypatch):
    configured(client)
    for state in ('STALE','MISSING'):
        monkeypatch.setattr(main,'fetch_live_weather',lambda x:packet()|{'availability':state})
        r=client.post('/api/flood/assessments/1').json()
        assert client.post(f"/api/flood/records/{r['id']}/draft").status_code==409


def test_config_validation_and_bad_location(client):
    b=client.get('/api/flood/basins/1').json()
    b['thresholds_mm']={'1':30,'3':20,'6':100}
    assert client.post('/api/flood/basins/1',json=b).status_code==422
    assert client.get('/api/flood/screen/999?mode=replay').status_code==404


def test_current_provider_time_must_be_fresh(client):
    p=packet();p['valid_at_epoch']=int(time.time())-20000
    r=assess(p,client.get('/api/flood/basins/1').json(),now=int(time.time()))
    assert r['level']=='UNKNOWN'
    assert 'current_provider_timestamp' in r['missing']


def test_nonconsecutive_hours_are_missing():
    assert main._complete_rain_window([1,2,3],[0,1,2],3,
        ['2026-09-29T10:00','2026-09-29T12:00','2026-09-29T13:00']) is None
