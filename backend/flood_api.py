"""Separate flood routes, provenance, persistence and operator-reviewed draft creation."""
import json
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from auth import resolve_role, require_role
from database import insert_row
from flood_risk import assess


class Village(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str = Field(min_length=2, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Basin(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str = Field(min_length=2, max_length=150)
    context_status: Literal['DEMO', 'CONFIGURED'] = 'DEMO'
    provenance: str = Field(min_length=10, max_length=1000)
    thresholds_mm: dict[str, float]
    villages: list[Village] = Field(min_length=1, max_length=100)
    slope_context: str = Field(default='Unverified terrain context', max_length=1000)
    historical_events_source: str = Field(default='No verified event inventory loaded', max_length=1000)
    station_id: str | None = Field(default=None, min_length=1, max_length=80)
    danger_stage_m: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode='after')
    def thresholds(self):
        values = self.thresholds_mm
        if set(values) != {'1', '3', '6'} or not all(0 < v <= 2000 for v in values.values()):
            raise ValueError('Provide positive 1, 3 and 6 hour rainfall thresholds (mm)')
        if not values['1'] <= values['3'] <= values['6']:
            raise ValueError('Accumulation thresholds must increase with duration')
        if bool(self.station_id) != (self.danger_stage_m is not None):
            raise ValueError('Station ID and danger stage must be configured together')
        return self


class Gauge(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    station_id: str = Field(min_length=1, max_length=80)
    source: Literal['REAL_SENSOR', 'SIMULATED_HACKATHON', 'MANUAL_TEST']
    water_level_m: float = Field(ge=0, le=100)
    quality: float = Field(ge=0, le=1)
    observed_at: int = Field(gt=0)


def routes(db, locations, weather, replay, localized_alert):
    router = APIRouter(prefix='/api/flood', tags=['Flash Floods · SIH26192'])

    def location(location_id):
        x = next((x for x in locations if x['id'] == location_id), None)
        if not x: raise HTTPException(404, 'Unknown monitored area')
        return x

    def basin_for(location_id):
        x = location(location_id)
        con = db()
        try: row = con.execute('SELECT config_json FROM flood_basins WHERE location_id=?', (location_id,)).fetchone()
        finally: con.close()
        if row: return json.loads(row['config_json'])
        return Basin(name=f"{x['name']} demonstration catchment", provenance='Synthetic configuration for workflow demonstration; no surveyed catchment boundary.',
            thresholds_mm={'1': 30, '3': 60, '6': 100},
            villages=[Village(name=f"{x['name']} demo settlement", lat=x['lat'], lon=x['lon'])],
            slope_context=f"Seed slope {x['slope']} degrees; not a slope stability calculation.").model_dump()

    @router.get('/basins/{location_id}')
    def basin_get(location_id: int):
        return basin_for(location_id)

    @router.post('/basins/{location_id}')
    def basin_save(location_id: int, body: Basin, role: str = Depends(resolve_role)):
        require_role(role, 'ADMIN'); location(location_id)
        con = db()
        try:
            con.execute('INSERT INTO flood_basins(location_id,config_json,updated_at) VALUES(?,?,?) ON CONFLICT(location_id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at',
                        (location_id, body.model_dump_json(), int(time.time())))
            con.commit()
        finally: con.close()
        return body

    @router.post('/sensors/{location_id}', status_code=201)
    def sensor_ingest(location_id: int, body: Gauge, role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR')
        basin = basin_for(location_id); now = int(time.time())
        if body.station_id != basin.get('station_id'): raise HTTPException(400, 'Station does not match the configured catchment')
        if body.observed_at > now or now - body.observed_at > 86400: raise HTTPException(422, 'Sensor timestamp must be within the past 24 hours')
        con = db()
        try:
            sid = insert_row(con.cursor(), 'INSERT INTO flood_gauges(location_id,source,observed_at,payload_json) VALUES(?,?,?,?)',
                             (location_id, body.source, body.observed_at, body.model_dump_json()))
            con.commit()
        finally: con.close()
        return {'id': sid, 'accepted': True, 'note': 'Only fresh REAL_SENSOR packets with quality >= 0.8 can affect current screening.'}

    def calculate(location_id, mode):
        x = location(location_id); basin = basin_for(location_id)
        packet = dict(replay(x) if mode == 'replay' else weather(x))
        if mode == 'replay':
            # Synthetic storm fixture, never represented as a historical observed event.
            packet.update(source='Synthetic flash flood scenario', rain_forecast_1h_mm=38,
                          rain_forecast_3h_mm=82, rain_forecast_6h_mm=125)
        con = db()
        try:
            row = con.execute("SELECT payload_json FROM flood_gauges WHERE location_id=? AND source='REAL_SENSOR' ORDER BY observed_at DESC,id DESC LIMIT 1", (location_id,)).fetchone()
        finally: con.close()
        result = assess(packet, basin, json.loads(row['payload_json']) if row and mode == 'live' else None, int(time.time()))
        result.update(location_id=location_id, location=x['name'], mode=mode, created_at=int(time.time()))
        return result

    @router.get('/screen/{location_id}')
    def screen(location_id: int, mode: Literal['live', 'replay'] = 'live'):
        return calculate(location_id, mode)

    @router.post('/assessments/{location_id}', status_code=201)
    def record(location_id: int, mode: Literal['live', 'replay'] = 'live', role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR'); result = calculate(location_id, mode)
        con = db()
        try:
            aid = insert_row(con.cursor(), 'INSERT INTO flood_assessments(location_id,result_json,created_at) VALUES(?,?,?)',
                             (location_id, json.dumps(result), result['created_at']))
            con.commit()
        finally: con.close()
        return {'id': aid, 'assessment': result}

    @router.get('/history/{location_id}')
    def history(location_id: int, limit: int = Query(20, ge=1, le=100)):
        location(location_id); con = db()
        try: rows = con.execute('SELECT id,result_json FROM flood_assessments WHERE location_id=? ORDER BY id DESC LIMIT ?', (location_id, limit)).fetchall()
        finally: con.close()
        return [{'id': r['id'], 'assessment': json.loads(r['result_json'])} for r in rows]

    @router.get('/records/{assessment_id}')
    def record_get(assessment_id: int):
        con = db()
        try: row = con.execute('SELECT result_json FROM flood_assessments WHERE id=?', (assessment_id,)).fetchone()
        finally: con.close()
        if not row: raise HTTPException(404, 'Assessment not found')
        return json.loads(row['result_json'])

    @router.post('/records/{assessment_id}/draft')
    def draft(assessment_id: int, role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR'); result = record_get(assessment_id)
        if (result['mode'] != 'live' or result['data_state'] != 'CURRENT' or result['basin']['context_status'] != 'CONFIGURED'
                or result['status'] != 'SCREENED' or result['level'] not in ('HIGH', 'CRITICAL')
                or int(time.time()) - result['created_at'] > 900):
            raise HTTPException(409, 'Draft requires a complete, current, high/critical live assessment under 15 minutes old with a configured catchment.')
        names = ', '.join(v['name'] for v in result['basin']['villages'])
        message = (f"Flash flood screening advisory for {result['location']}: {result['level']}. "
                   f"Configured settlements: {names}. Review rainfall and stream observations; prepare local response. "
                   'Experimental screening; flood arrival time and evacuation lead time are unvalidated. Follow official authority instructions.')
        con = db()
        try:
            # Serialize concurrent draft requests on the assessment row on both databases.
            con.execute('UPDATE flood_assessments SET created_at=created_at WHERE id=?', (assessment_id,))
            old = con.execute('SELECT alert_id FROM flood_assessments WHERE id=?', (assessment_id,)).fetchone()
            if old['alert_id']:
                alert_id = old['alert_id']
            else:
                now = int(time.time()); cur = con.cursor()
                alert_id = insert_row(cur, 'INSERT INTO alerts(location_id,location,level,message_en,source,created_at,lifecycle_status,advisory_type,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (result['location_id'], result['location'], result['level'], message, f'flood-assessment-{assessment_id}', now, 'DRAFT', 'FLASH_FLOOD', now))
                cur.execute('INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at) VALUES(?,?,?,?,?,?)',
                            (alert_id, None, 'DRAFT', role, f'Flash flood assessment {assessment_id}; area-based recipient delivery', now))
                cur.execute('UPDATE flood_assessments SET alert_id=? WHERE id=?', (alert_id, assessment_id))
            con.commit()
            row = con.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone()
        finally: con.close()
        return {'alert': localized_alert(row, 'en'), 'note': 'Review and issue through Reports & Alerts. SMS recipients remain scoped to the monitored area.'}

    return router
