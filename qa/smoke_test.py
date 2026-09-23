"""PRAHARI v8 research-synthesis preflight smoke test.
Run while backend is active: python qa/smoke_test.py
The test intentionally does NOT require public internet or warm NASA cache.
"""
import json, sys
from urllib.request import Request, urlopen

BASE=sys.argv[1].rstrip('/') if len(sys.argv)>1 else 'http://127.0.0.1:8000'
PASS=[]; FAIL=[]; WARN=[]

def req(path, method='GET', data=None, timeout=12):
    body=None; headers={}
    if data is not None:
        body=json.dumps(data).encode(); headers['Content-Type']='application/json'
    r=Request(BASE+path,data=body,method=method,headers=headers)
    with urlopen(r,timeout=timeout) as resp:
        raw=resp.read().decode(); return resp.status, json.loads(raw) if raw else None

def check(name,fn):
    try:
        detail=fn(); PASS.append((name,detail)); print(f'[PASS] {name}: {detail}')
    except Exception as e:
        FAIL.append((name,str(e))); print(f'[FAIL] {name}: {e}')

def main():
    def root_check():
        d=req('/')[1]
        if d.get('service')!='PRAHARI' or d.get('version')!='8.0.0': raise RuntimeError(d)
        return f"{d['service']} v{d['version']}"
    check('API root / v8 branding',root_check)
    check('System health',lambda:req('/api/system/health')[1].get('status'))

    def ml_check():
        d=req('/api/ml/status')[1]
        if not d.get('model_loaded'): raise RuntimeError('research ensemble did not load')
        return d.get('model_type')
    check('Hybrid research ensemble',ml_check)
    check('Research evidence matrix',lambda:req('/api/research/evidence-matrix')[1].get('unique_papers_reviewed'))
    check('Research model card',lambda:req('/api/research/model-card')[1].get('engine'))
    check('Research data-readiness manifest',lambda:len(req('/api/research/data-readiness')[1].get('next_real_datasets',[])))
    check('8 monitored locations',lambda:len(req('/api/locations')[1]))

    def live_check():
        d=req('/api/live/locations')[1]
        if not d: raise RuntimeError('no data')
        live=sum(1 for x in d if x.get('live_weather'))
        if live==0: WARN.append('Public weather unavailable; transparent fallback is active (expected behavior).')
        return f'{len(d)} locations / {live} public-live feeds'
    check('Live/fallback regional fusion',live_check)
    check('Forecast risk trajectory',lambda:len(req('/api/forecast-risk/1')[1].get('points',[])))

    safe={"rainfall":34,"antecedent_rainfall_72h":70,"cumulative_rainfall_7d":145,"effective_rainfall_11d":135,"rain_forecast_24h":18,"max_hourly_rain_24h":5,"soil_moisture":42,"slope":19,"elevation":850,"historical_risk":0.22,"ndvi":0.76,"location_name":"QA Stable"}
    critical={"rainfall":225,"antecedent_rainfall_72h":480,"cumulative_rainfall_7d":910,"effective_rainfall_11d":760,"rain_forecast_24h":95,"max_hourly_rain_24h":34,"soil_moisture":93,"slope":52,"elevation":1650,"historical_risk":0.86,"ndvi":0.55,"location_id":1,"location_name":"QA Critical"}
    def pred(payload,danger=False):
        d=req('/api/predict-risk','POST',payload)[1]
        for k in ('risk_level','risk_percent','susceptibility_percent','dynamic_trigger_percent','ensemble_agreement_pct','decision_interval_pct','rainfall_regime','soil_water_stress_pct','model_probabilities','shap_local','physics_guardrail_applied'):
            if k not in d: raise RuntimeError(k+' missing')
        if danger and d['risk_level'] not in ('HIGH','CRITICAL'): raise RuntimeError(d)
        return f"{d['risk_level']} {d['risk_percent']}% / agreement {d['ensemble_agreement_pct']}%"
    check('Stable hazard path',lambda:pred(safe))
    check('Critical hazard + alert path',lambda:pred(critical,True))

    def fs():
        d=req('/api/geotech/factor-of-safety','POST',{"cohesion_kpa":18,"friction_angle_deg":29,"slope_deg":42,"soil_depth_m":3,"unit_weight_kn_m3":18,"pore_pressure_ratio":.55})[1]
        return f"FOS {d['factor_of_safety']} {d['state']}"
    check('Physics/geotechnical FOS screen',fs)

    check('Community corroboration API',lambda:req('/api/community/signal/1')[1].get('level'))
    check('Impact-based warning API',lambda:req('/api/impact/1')[1].get('priority'))
    check('Offline response/Dijkstra API',lambda:req('/api/response/plan/1')[1]['safe_route']['algorithm'])
    check('Geo-fence targeting API',lambda:req('/api/geofence/check?lat=27.3314&lon=88.6138&radius_km=25')[1].get('inside_monitored_geofence'))

    def iot():
        d=req('/api/iot/demo/1','POST')[1]
        q=req('/api/iot/telemetry/latest?location_id=1')[1]
        if not q.get('available'): raise RuntimeError('telemetry not stored')
        return f"{d['edge_state']} / {q['telemetry']['source']}"
    check('Edge IoT ingest + local rule',iot)
    check('Sensor-fusion endpoint',lambda:len(req('/api/sensors/1')[1].get('nodes',[])))

    def sat():
        d=req('/api/satellite/1')[1]
        return f"{d['risk_level']} / {d['nasa_gibs']['mode']}"
    check('Satellite intelligence packet',sat)
    def cache():
        d=req('/api/satellite/cache/status')[1]
        if d.get('cached_tiles',0)==0: WARN.append('NASA cache is empty. Run prepare_offline_satellite.bat on good internet before demo; Offline EO Lite is already local.')
        return f"{d.get('cached_tiles')}/{d.get('expected_tiles')} cached / Offline EO Lite does not require cache"
    check('Low-bandwidth satellite cache status',cache)

    check('Alerts',lambda:len(req('/api/alerts')[1]))
    check('Routes',lambda:len(req('/api/routes')[1]))
    check('Infrastructure',lambda:len(req('/api/infrastructure')[1]))
    check('Citizen reports',lambda:len(req('/api/reports')[1]))
    check('Alert feedback metrics',lambda:req('/api/alerts/metrics')[1].get('feedback_total'))

    print('\n=== PRAHARI v8 RESEARCH-SYNTHESIS PRE-FLIGHT ===')
    print(f'PASS: {len(PASS)}  FAIL: {len(FAIL)}  WARN: {len(WARN)}')
    for w in WARN: print('[WARN]',w)
    if FAIL:
        print('Result: NOT READY — fix failed checks.')
        return 1
    print('Result: READY — critical path is operational; public-data/cache warnings are non-blocking by design.')
    return 0

if __name__=='__main__': sys.exit(main())
