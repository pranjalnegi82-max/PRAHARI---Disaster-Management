"""Admin-only broadcast routes; no outgoing SMS is sent by these handlers."""
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth import resolve_role, require_role
import broadcasts
from notifications import production_account_status
from msg91_provider import status as msg91_status, message_plan
from settings import BROADCAST_ENABLED, DATABASE_URL, BROADCAST_REQUESTS_PER_SECOND, BROADCAST_PROVIDER


class BroadcastRequest(BaseModel):
    alert_id: int = Field(gt=0)
    scope: Literal['ALERT_AREA','SPECIFIC_AREA','ALL_MONITORED'] = 'ALERT_AREA'
    target_location_id: int | None = None
    expires_in_minutes: int = Field(default=60, ge=5, le=1440)
    expected_recipients: int = Field(default=0, ge=0, le=1000000)


class BroadcastAction(BaseModel):
    action: Literal['pause','resume','cancel','retry_failed']


def routes(connect, locations, make_text):
    router = APIRouter(prefix='/api/broadcasts', tags=['Bulk SMS'])

    def admin(role):
        require_role(role, 'ADMIN')

    def context(body):
        con = connect()
        try:
            row = con.execute('SELECT * FROM alerts WHERE id=?', (body.alert_id,)).fetchone()
        finally:
            con.close()
        if not row:
            raise HTTPException(404, 'Advisory not found')
        alert = dict(row)
        if alert['lifecycle_status'] not in ('REVIEWED','ISSUED'):
            raise HTTPException(409, 'Select an advisory that has been reviewed and is ready to issue.')
        target = None if body.scope == 'ALL_MONITORED' else body.target_location_id if body.scope == 'SPECIFIC_AREA' else alert.get('location_id')
        loc = next((x for x in locations if x['id'] == target), None)
        if body.scope != 'ALL_MONITORED' and not loc:
            raise HTTPException(400, 'Select a valid target area')
        label = 'All monitored areas' if body.scope == 'ALL_MONITORED' else f"{loc['name']}, {loc['state']}"
        return alert, target, label

    def ready():
        issues = []
        if not BROADCAST_ENABLED:
            issues.append('Bulk sending is not enabled. Configure the production SMS account and separate broadcast worker first.')
        if not DATABASE_URL:
            issues.append('Bulk sending requires PostgreSQL storage.')
        worker = broadcasts.overview(connect)
        if not worker['worker_online'] or worker['worker_provider'] != BROADCAST_PROVIDER:
            issues.append('The broadcast worker is offline or not ready.')
        provider = msg91_status() if BROADCAST_PROVIDER == 'msg91' else production_account_status()
        if BROADCAST_PROVIDER not in ('msg91', 'twilio'):
            issues.append('Choose a supported broadcast provider.')
        return issues + provider['issues'], provider

    def plans(alert):
        out = {}
        for language in ('en', 'hi', 'as'):
            plain = make_text(alert, language, sms=True)
            if BROADCAST_PROVIDER == 'msg91':
                try:
                    out[language] = message_plan(alert, language, plain)
                except ValueError:
                    out[language] = {'text': 'No approved MSG91 template is configured for this language.'}
            else:
                out[language] = {'text': plain}
        return out

    @router.get('')
    def listing(role: str = Depends(resolve_role)):
        admin(role)
        return {**broadcasts.overview(connect), 'enabled': BROADCAST_ENABLED,
                'provider': BROADCAST_PROVIDER,
                'note': 'Queued means waiting to submit; only provider receipts confirm delivery.'}

    @router.post('/preview')
    def preview(body: BroadcastRequest, role: str = Depends(resolve_role)):
        admin(role); alert, target, label = context(body)
        issues, provider = ready()
        recipients = broadcasts.preview(connect, body.alert_id, body.scope, target, BROADCAST_PROVIDER)
        seconds = recipients / BROADCAST_REQUESTS_PER_SECOND
        if seconds > body.expires_in_minutes * 60:
            issues.append('The audience exceeds the configured submission capacity before expiry. Increase the expiry or provision sufficient worker/provider throughput.')
        return {'recipients': recipients, 'minimum_submission_seconds': seconds,
                'target_label': label, 'messages': {lang: plan['text'] for lang,plan in plans(alert).items()},
                'issues': issues, 'ready': not issues, 'provider': provider,
                'note': 'Unique opted-in Indian numbers with no prior attempt for this advisory. Final billing depends on provider SMS segments.'}

    @router.post('', status_code=202)
    def create(body: BroadcastRequest, role: str = Depends(resolve_role)):
        admin(role); alert, target, label = context(body)
        issues, _ = ready()
        if issues:
            raise HTTPException(503, ' '.join(issues))
        if body.expected_recipients / BROADCAST_REQUESTS_PER_SECOND > body.expires_in_minutes * 60:
            raise HTTPException(409, 'The audience cannot fit within the selected expiry at the configured submission rate. Preview again after changing capacity or expiry.')
        try:
            return broadcasts.enqueue(connect, body.alert_id, body.scope, target, label,
                plans(alert), int(time.time()) + body.expires_in_minutes * 60,
                role, body.expected_recipients, BROADCAST_PROVIDER)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @router.post('/{job_id}/control')
    def control(job_id: int, body: BroadcastAction, role: str = Depends(resolve_role)):
        admin(role)
        if body.action in ('resume', 'retry_failed'):
            issues, _ = ready()
            if issues:
                raise HTTPException(503, ' '.join(issues))
        try:
            broadcasts.control(connect, job_id, body.action)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {'ok': True}

    @router.get('/{job_id}/items')
    def items(job_id: int, after: int = 0, role: str = Depends(resolve_role)):
        admin(role); con = connect()
        try:
            rows = con.execute('''SELECT id,recipient_id,status,attempts,error_code,error_message,updated_at
                FROM broadcast_items WHERE job_id=? AND id>? ORDER BY id LIMIT 100''', (job_id, after)).fetchall()
            data = [dict(r) for r in rows]
            return {'items': data, 'next_after': data[-1]['id'] if len(data) == 100 else None}
        finally:
            con.close()

    return router
