"""Provider failures and optional terrain cannot fabricate inputs or block flood screening."""
from test_v9 import client, clean_db
import main
import pytest


def test_dedicated_elevation_api(client,monkeypatch):
    main.TERRAIN_CONTEXT_CACHE.clear()
    monkeypatch.setattr(main,'_load_source_cache',lambda *a:None)
    monkeypatch.setattr(main,'_persist_source_cache',lambda *a,**k:None)
    calls=[]
    def provider(url,timeout,attempts):
        calls.append((url,timeout,attempts))
        return {'elevation':[2000,2100,1900,2050,1950]*len(main.LOCATIONS)}
    monkeypatch.setattr(main,'_fetch_json_with_retries',provider)
    assert main.terrain_context_map()[1]['slope_deg']>0
    assert '/v1/elevation?' in calls[0][0] and 'current=' not in calls[0][0]
    assert calls[0][1]<=10 and calls[0][2]==1
    main.TERRAIN_CONTEXT_CACHE.clear()


def test_failed_terrain_cooldown(client,monkeypatch):
    main.TERRAIN_CONTEXT_CACHE.clear()
    monkeypatch.setattr(main,'_load_source_cache',lambda *a:None)
    calls=[]
    def failed(*args,**kwargs):
        calls.append(1);raise TimeoutError('provider unavailable')
    monkeypatch.setattr(main,'_fetch_json_with_retries',failed)
    assert main.terrain_context_map()=={}
    assert main.terrain_context_map()=={}
    assert len(calls)==1
    main.TERRAIN_CONTEXT_CACHE.clear()


def test_flood_does_not_fetch_terrain(client,monkeypatch):
    main.TERRAIN_CONTEXT_CACHE.clear()
    monkeypatch.setattr(main,'_load_source_cache',lambda *a:None)
    monkeypatch.setattr(main,'_fetch_json_with_retries',lambda *a,**k:pytest.fail('Terrain must not block flood'))
    assert main.terrain_context_map(allow_fetch=False)=={}
    assert client.get('/api/flood/screen/1').status_code==200


def test_terrain_relay_neither_fetches_weather_nor_caches(client,monkeypatch):
    monkeypatch.setattr(main,'fetch_live_weather',lambda *a,**k:pytest.fail('Must not fetch weather'))
    main.TERRAIN_CONTEXT_CACHE.clear()
    assert client.post('/api/terrain/1/browser-relay',json={'elevations':[None]*5}).status_code==422
    assert client.post('/api/terrain/999/browser-relay',json={'elevations':[1]*5}).status_code==404
    r=client.post('/api/terrain/1/browser-relay',json={'elevations':[2000,2100,1900,2050,1950]})
    assert r.status_code==200 and r.json()['slope']>0
    assert r.json()['terrain_transport']=='BROWSER_RELAY'
    assert not main.TERRAIN_CONTEXT_CACHE.get('data')


def test_record_preserves_recovered_terrain_without_drafting(client,monkeypatch):
    from test_v9 import live_packet
    p=live_packet();p.pop('terrain_slope_deg')
    monkeypatch.setattr(main,'fetch_live_weather',lambda *a,**k:p)
    response=client.post('/api/assessments/1',json={'terrain_elevations':[2000,3100,900,2050,1950]})
    assert response.status_code==200
    result=response.json()
    assert result['assessment']['slope']>0
    assert result['assessment']['terrain_transport']=='BROWSER_RELAY'
    assert result['draft_advisory'] is None
    assert client.post('/api/assessments/1',json={'terrain_elevations':[None]*5}).status_code==422
