# PRAHARI v7 — API Quick Reference

Swagger remains the canonical interactive reference: `http://127.0.0.1:8000/docs`.

## People-centred / impact

`GET /api/community/signal/1` — report-derived corroboration score.  
`GET /api/impact/1` — separate impact priority from hazard + exposure + vulnerability.  
`GET /api/response/plan/1` — impact + checklist + offline prototype route.  
`GET /api/geofence/check?lat=27.3314&lon=88.6138&radius_km=25` — location-targeted risk check.

## IoT / edge

`POST /api/iot/telemetry`
```json
{
  "location_id": 1,
  "station_id": "GANGTOK-S01",
  "rainfall_intensity": 38.0,
  "soil_moisture": 91,
  "tilt_deg": 2.8,
  "vibration_g": 0.22,
  "pore_pressure_kpa": 74,
  "displacement_mm": 9.2,
  "battery_pct": 88,
  "quality": 0.96,
  "source": "REAL_SENSOR"
}
```

`GET /api/iot/telemetry/latest?location_id=1`  
`POST /api/iot/demo/1` — explicit SIMULATED_HACKATHON packet.

## Physics screen

`POST /api/geotech/factor-of-safety`
```json
{
  "cohesion_kpa": 18,
  "friction_angle_deg": 29,
  "slope_deg": 42,
  "soil_depth_m": 3,
  "unit_weight_kn_m3": 18,
  "pore_pressure_ratio": 0.55
}
```
The returned FOS is a simplified screening indicator, not a site-certified slope-stability calculation.

## Satellite / low bandwidth

`GET /api/satellite/cache/status`  
`POST /api/satellite/cache/warm?max_zoom=6`  
`GET /api/satellite/tile/{z}/{y}/{x}.jpg`

The frontend uses `/offline/ner_eo_lite.svg` for guaranteed no-internet context and the local tile endpoint for real pre-cached NASA imagery.

## Learning loop

`POST /api/alerts/{id}/feedback`
```json
{"outcome":"CONFIRMED","note":"Field team verified fresh debris movement"}
```
Outcomes: `CONFIRMED`, `FALSE_ALARM`, `PARTIAL`.

`GET /api/alerts/metrics` — only descriptive feedback counts; no claimed calibration until enough verified events exist.
