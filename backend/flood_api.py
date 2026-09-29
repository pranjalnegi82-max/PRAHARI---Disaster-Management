"""Flash-flood configuration, live screening, gauge ingestion and traceable records."""
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth import require_role, resolve_role
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
    context_status: Literal['UNCONFIGURED', 'CONFIGURED'] = 'UNCONFIGURED'
    provenance: str = Field(default='', max_length=1000)
    thresholds_mm: dict[str, float] | None = None
    villages: list[Village] = Field(default_factory=list, max_length=100)
    slope_context: str = Field(default='', max_length=1000)
    historical_events_source: str = Field(default='', max_length=1000)
    station_id: str | None = Field(default=None, min_length=1, max_length=80)
    danger_stage_m: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode='after')
    def validate_configuration(self):
        if bool(self.station_id) != (self.danger_stage_m is not None):
            raise ValueError('Station ID and danger stage must be configured together')
        if self.context_status == 'CONFIGURED':
            if len(self.provenance.strip()) < 5:
                raise ValueError('A documented threshold/configuration source is required')
            if not self.villages:
                raise ValueError('At least one village or ward coordinate is required')
            values = self.thresholds_mm
            if not isinstance(values, dict) or set(values) != {'1', '3', '6'}:
                raise ValueError('Provide 1, 3 and 6 hour rainfall thresholds')
            if not all(0 < float(v) <= 2000 for v in values.values()):
                raise ValueError('Rainfall thresholds must be positive')
            if not float(values['1']) <= float(values['3']) <= float(values['6']):
                raise ValueError('Accumulation thresholds must increase with duration')
        return self


class Gauge(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    station_id: str = Field(min_length=1, max_length=80)
    source: Literal['REAL_SENSOR'] = 'REAL_SENSOR'
    water_level_m: float = Field(ge=0, le=100)
    quality: float = Field(ge=0, le=1)
    observed_at: int = Field(gt=0)


def routes(db, locations, weather, replay, localized_alert):
    router = APIRouter(prefix='/api/flood', tags=['Flash Floods'])

    def location(location_id):
        x = next((x for x in locations if x['id'] == location_id), None)
        if not x:
            raise HTTPException(404, 'Unknown monitored area')
        return x

    def basin_for(location_id):
        x = location(location_id)
        con = db()
        try:
            row = con.execute('SELECT config_json FROM flood_basins WHERE location_id=?', (location_id,)).fetchone()
        finally:
            con.close()
        if row:
            return json.loads(row['config_json'])
        return Basin(
            name=f"{x['name']} monitoring point",
            context_status='UNCONFIGURED',
            provenance='',
            thresholds_mm=None,
            villages=[],
        ).model_dump()

    @router.get('/basins/{location_id}')
    def basin_get(location_id: int):
        return basin_for(location_id)

    @router.post('/basins/{location_id}')
    def basin_save(location_id: int, body: Basin, role: str = Depends(resolve_role)):
        require_role(role, 'ADMIN')
        location(location_id)
        con = db()
        try:
            con.execute(
                'INSERT INTO flood_basins(location_id,config_json,updated_at) VALUES(?,?,?) '
                'ON CONFLICT(location_id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at',
                (location_id, body.model_dump_json(), int(time.time())),
            )
            con.commit()
        finally:
            con.close()
        return body

    @router.post('/sensors/{location_id}', status_code=201)
    def sensor_ingest(location_id: int, body: Gauge, role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR')
        basin = basin_for(location_id)
        now = int(time.time())
        if basin.get('context_status') != 'CONFIGURED':
            raise HTTPException(409, 'Configure the catchment before registering gauge telemetry')
        if body.station_id != basin.get('station_id'):
            raise HTTPException(400, 'Station does not match the configured catchment')
        if body.observed_at > now or now - body.observed_at > 86400:
            raise HTTPException(422, 'Sensor timestamp must be within the past 24 hours')
        con = db()
        try:
            sid = insert_row(
                con.cursor(),
                'INSERT INTO flood_gauges(location_id,source,observed_at,payload_json) VALUES(?,?,?,?)',
                (location_id, body.source, body.observed_at, body.model_dump_json()),
            )
            con.commit()
        finally:
            con.close()
        return {'id': sid, 'accepted': True}

    def calculate(location_id, mode):
        x = location(location_id)
        basin = basin_for(location_id)
        packet = dict(replay(x) if mode == 'replay' else weather(x))
        con = db()
        try:
            row = con.execute(
                "SELECT payload_json FROM flood_gauges WHERE location_id=? AND source='REAL_SENSOR' "
                'ORDER BY observed_at DESC,id DESC LIMIT 1',
                (location_id,),
            ).fetchone()
        finally:
            con.close()
        sensor = json.loads(row['payload_json']) if row and mode == 'live' else None
        result = assess(packet, basin, sensor, int(time.time()))
        result.update(location_id=location_id, location=x['name'], state=x.get('state'), mode=mode, created_at=int(time.time()))
        return result

    @router.get('/screen/{location_id}')
    def screen(location_id: int, mode: Literal['live', 'replay'] = 'live'):
        return calculate(location_id, mode)

    @router.post('/assessments/{location_id}', status_code=201)
    def record(location_id: int, mode: Literal['live', 'replay'] = 'live', role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR')
        result = calculate(location_id, mode)
        con = db()
        try:
            aid = insert_row(
                con.cursor(),
                'INSERT INTO flood_assessments(location_id,result_json,created_at) VALUES(?,?,?)',
                (location_id, json.dumps(result), result['created_at']),
            )
            con.commit()
        finally:
            con.close()
        return {'id': aid, 'assessment': result}

    @router.get('/history/{location_id}')
    def history(location_id: int, limit: int = Query(20, ge=1, le=100)):
        location(location_id)
        con = db()
        try:
            rows = con.execute(
                'SELECT id,result_json FROM flood_assessments WHERE location_id=? ORDER BY id DESC LIMIT ?',
                (location_id, limit),
            ).fetchall()
        finally:
            con.close()
        return [{'id': r['id'], 'assessment': json.loads(r['result_json'])} for r in rows]

    @router.get('/records/{assessment_id}')
    def record_get(assessment_id: int):
        con = db()
        try:
            row = con.execute('SELECT result_json FROM flood_assessments WHERE id=?', (assessment_id,)).fetchone()
        finally:
            con.close()
        if not row:
            raise HTTPException(404, 'Assessment not found')
        return json.loads(row['result_json'])

    @router.post('/records/{assessment_id}/draft')
    def draft(assessment_id: int, role: str = Depends(resolve_role)):
        require_role(role, 'OPERATOR')
        result = record_get(assessment_id)
        age = int(time.time()) - int(result.get('created_at') or 0)
        eligible = (
            result.get('mode') == 'live'
            and result.get('data_state') == 'CURRENT'
            and result.get('status') == 'SCREENED'
            and result.get('level') in ('HIGH', 'CRITICAL')
            and result.get('basin', {}).get('context_status') == 'CONFIGURED'
            and 0 <= age <= 900
        )
        if not eligible:
            raise HTTPException(409, 'Assessment is not eligible for an advisory draft')
        con = db()
        try:
            existing = con.execute('SELECT alert_id FROM flood_assessments WHERE id=?', (assessment_id,)).fetchone()
            alert_id = existing['alert_id'] if existing else None
            if alert_id:
                row = con.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone()
                if row:
                    return {'alert': localized_alert(dict(row), 'en'), 'assessment_id': assessment_id}
            x = location(result['location_id'])
            now = int(time.time())
            message = (
                f"Flash-flood {result['level'].lower()} draft for {x['name']}, {x['state']}. "
                f"Configured rainfall thresholds were exceeded; review current gauge and field conditions before issuance."
            )
            aid = insert_row(
                con.cursor(),
                'INSERT INTO alerts(location_id,location,level,risk_percent,message_en,message_hi,message_as,'
                'recommended_action,source,acknowledged,created_at,lifecycle_status,advisory_type,updated_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    x['id'], f"{x['name']}, {x['state']}", result['level'], None,
                    message, message, message, 'Review local observations and authorized response procedures.',
                    f"flash-flood-assessment:{assessment_id}", 0, now, 'DRAFT', 'FLASH_FLOOD', now,
                ),
            )
            con.execute('UPDATE flood_assessments SET alert_id=? WHERE id=?', (aid, assessment_id))
            con.execute(
                'INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at) VALUES(?,?,?,?,?,?)',
                (aid, None, 'DRAFT', role, f'Created from flash-flood assessment {assessment_id}', now),
            )
            con.commit()
            row = con.execute('SELECT * FROM alerts WHERE id=?', (aid,)).fetchone()
        finally:
            con.close()
        return {'alert': localized_alert(dict(row), 'en'), 'assessment_id': assessment_id}

    return router
