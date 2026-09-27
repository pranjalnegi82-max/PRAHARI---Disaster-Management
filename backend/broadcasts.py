"""Durable SMS outbox. Enqueue never contacts recipients; only the worker sends.

A unique (alert, phone) snapshot prevents repeated clicks and overlapping audiences
from duplicating a warning. Unknown outcomes are held for investigation, not retried.
"""
import time
from database import PostgresConnection, insert_row


def initialize_broadcast_schema(cur):
    cur.execute('''CREATE TABLE IF NOT EXISTS broadcast_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL,
        scope TEXT NOT NULL, target_location_id INTEGER, target_label TEXT NOT NULL,
        status TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        note TEXT, actor_role TEXT NOT NULL)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS broadcast_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL,
        alert_id INTEGER NOT NULL, recipient_id INTEGER NOT NULL,
        phone_e164 TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, available_at DOUBLE PRECISION NOT NULL,
        updated_at INTEGER NOT NULL, provider_message_sid TEXT,
        error_code TEXT, error_message TEXT,
        UNIQUE(alert_id,phone_e164))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS broadcast_runtime(
        id INTEGER PRIMARY KEY AUTOINCREMENT, heartbeat INTEGER, next_send DOUBLE PRECISION)''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_ready ON broadcast_items(status,available_at,id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_job ON broadcast_items(job_id,status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_sid ON broadcast_items(provider_message_sid)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_phone ON notification_recipients(phone_e164,consent_status)')


def _lock(con):
    if isinstance(con, PostgresConnection):
        con.execute('SELECT pg_advisory_xact_lock(13745526002)')
    else:
        con.execute('BEGIN IMMEDIATE')


def audience_where(scope, location_id):
    if scope not in ('ALL_MONITORED', 'SPECIFIC_AREA', 'ALERT_AREA'):
        raise ValueError('Invalid audience scope')
    clause = "r.consent_status='ACTIVE' AND r.sms_enabled=1"
    params = []
    if scope != 'ALL_MONITORED':
        if location_id is None:
            raise ValueError('Choose a specific target area for this advisory')
        clause += ' AND r.location_id=?'
        params.append(location_id)
    return clause, params


def audience(con, alert_id, scope, location_id):
    clause, params = audience_where(scope, location_id)
    # Legacy attempts are excluded too, even when the same phone has multiple rows.
    return f'''SELECT MIN(r.id) AS id, r.phone_e164 FROM notification_recipients r
        WHERE {clause}
        AND NOT EXISTS (SELECT 1 FROM broadcast_items b WHERE b.alert_id=? AND b.phone_e164=r.phone_e164)
        AND NOT EXISTS (SELECT 1 FROM notification_deliveries d
            JOIN notification_recipients old ON old.id=d.recipient_id
            WHERE d.alert_id=? AND d.channel='sms' AND old.phone_e164=r.phone_e164)
        GROUP BY r.phone_e164''', [*params, alert_id, alert_id]


def preview(connect, alert_id, scope, location_id):
    con = connect()
    try:
        sql, args = audience(con, alert_id, scope, location_id)
        return con.execute('SELECT COUNT(*) AS n FROM (' + sql + ') eligible', args).fetchone()['n']
    finally:
        con.close()


def enqueue(connect, alert_id, scope, location_id, label, messages, expires_at,
            actor_role, expected_count):
    now = int(time.time()); con = connect()
    try:
        _lock(con)
        alert = con.execute('SELECT * FROM alerts WHERE id=?' + (' FOR UPDATE' if isinstance(con, PostgresConnection) else ''), (alert_id,)).fetchone()
        if not alert or alert['lifecycle_status'] not in ('REVIEWED', 'ISSUED'):
            raise ValueError('Only reviewed or issued advisories can be broadcast')
        sql, args = audience(con, alert_id, scope, location_id)
        count = con.execute('SELECT COUNT(*) AS n FROM (' + sql + ') eligible', args).fetchone()['n']
        if not count:
            raise ValueError('No new opted-in recipients. Previously queued or attempted numbers are excluded.')
        if count != expected_count:
            raise ValueError('The audience changed. Preview again before confirming.')
        jid = insert_row(con.cursor(), '''INSERT INTO broadcast_jobs
            (alert_id,scope,target_location_id,target_label,status,created_at,expires_at,actor_role)
            VALUES(?,?,?,?,?,?,?,?)''', (alert_id, scope, location_id, label, 'RUNNING', now, expires_at, actor_role))
        # Materialize in one bounded-memory database operation, not 100,000 HTTP requests.
        inserted = con.execute('''INSERT INTO broadcast_items
            (job_id,alert_id,recipient_id,phone_e164,message,status,available_at,updated_at)
            SELECT ?,?,r.id,r.phone_e164,
            CASE r.language WHEN 'hi' THEN ? WHEN 'as' THEN ? ELSE ? END,'READY',?,?
            FROM notification_recipients r JOIN (''' + sql + ''') eligible ON eligible.id=r.id
            ON CONFLICT(alert_id,phone_e164) DO NOTHING''',
            [jid, alert_id, messages['hi'], messages['as'], messages['en'], now, now, *args])
        if inserted.rowcount != count:
            raise ValueError('The audience changed. Preview again before confirming.')
        if alert['lifecycle_status'] == 'REVIEWED':
            con.execute("UPDATE alerts SET lifecycle_status='ISSUED',issued_at=?,updated_at=? WHERE id=?", (now, now, alert_id))
            con.execute('''INSERT INTO alert_audit(alert_id,from_status,to_status,actor_role,note,created_at)
                VALUES(?,'REVIEWED','ISSUED',?,?,?)''', (alert_id, actor_role, f'Explicit bulk broadcast #{jid}', now))
        con.execute('INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)',
                    ('BROADCAST_QUEUED', f'Broadcast {jid}; advisory {alert_id}; {count} recipients; actor {actor_role}', now))
        con.commit()
        return {'id': jid, 'queued': count, 'status': 'RUNNING'}
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def overview(connect):
    con = connect()
    try:
        jobs = con.execute('SELECT * FROM broadcast_jobs ORDER BY id DESC LIMIT 30').fetchall()
        output = []
        for row in jobs:
            job = dict(row)
            job['counts'] = {r['status']: r['n'] for r in con.execute(
                'SELECT status,COUNT(*) AS n FROM broadcast_items WHERE job_id=? GROUP BY status', (job['id'],)).fetchall()}
            job['total'] = sum(job['counts'].values()); output.append(job)
        worker = con.execute('SELECT heartbeat FROM broadcast_runtime WHERE id=1').fetchone()
        hb = worker['heartbeat'] if worker else 0
        return {'jobs': output, 'worker_online': bool(hb and time.time() - hb < 90), 'last_heartbeat': hb}
    finally:
        con.close()


def control(connect, job_id, action):
    con = connect(); now = int(time.time())
    try:
        _lock(con)
        job = con.execute('SELECT * FROM broadcast_jobs WHERE id=?', (job_id,)).fetchone()
        if not job:
            raise ValueError('Broadcast not found')
        if action not in ('pause', 'resume', 'cancel', 'retry_failed'):
            raise ValueError('Invalid broadcast action')
        if job['status'] == 'CANCELED':
            raise ValueError('Canceled broadcasts cannot be restarted')
        if action in ('resume', 'retry_failed') and job['expires_at'] <= now:
            raise ValueError('This advisory broadcast has expired. Create and review a new advisory.')
        if action == 'retry_failed':
            con.execute("UPDATE broadcast_items SET status='READY',available_at=?,updated_at=?,provider_message_sid=NULL,error_code=NULL,error_message=NULL,attempts=0 WHERE job_id=? AND status IN ('FAILED','UNDELIVERED')", (now, now, job_id))
        if action == 'cancel':
            con.execute("UPDATE broadcast_items SET status='CANCELED',updated_at=? WHERE job_id=? AND status='READY'", (now, job_id))
        status = {'pause': 'PAUSED', 'resume': 'RUNNING', 'cancel': 'CANCELED', 'retry_failed': 'RUNNING'}[action]
        con.execute('UPDATE broadcast_jobs SET status=?,note=? WHERE id=?', (status, f'Admin action: {action}', job_id))
        con.execute('INSERT INTO system_events(event_type,detail,created_at) VALUES(?,?,?)', ('BROADCAST_CONTROL', f'Broadcast {job_id}: {action}', now))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def claim(connect, requests_per_second):
    """Global transactional rate gate works across worker processes."""
    now = time.time(); con = connect()
    try:
        _lock(con)
        con.execute('''INSERT INTO broadcast_runtime(id,heartbeat,next_send) VALUES(1,?,0)
            ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat''', (int(now),))
        con.execute("UPDATE broadcast_items SET status='UNKNOWN',error_message='Worker interrupted during submission; investigate before any resend.',updated_at=? WHERE status='SENDING' AND updated_at<?", (int(now), int(now)-120))
        con.execute("UPDATE broadcast_items SET status='EXPIRED',updated_at=? WHERE status='READY' AND job_id IN (SELECT id FROM broadcast_jobs WHERE expires_at<=?)", (int(now), int(now)))
        con.execute("UPDATE broadcast_items SET status='CANCELED',updated_at=? WHERE status='READY' AND alert_id IN (SELECT id FROM alerts WHERE lifecycle_status NOT IN ('ISSUED','ACKNOWLEDGED'))", (int(now),))
        con.execute("UPDATE broadcast_jobs SET status='COMPLETE' WHERE status='RUNNING' AND NOT EXISTS (SELECT 1 FROM broadcast_items i WHERE i.job_id=broadcast_jobs.id AND i.status IN ('READY','SENDING'))")
        gate = con.execute('SELECT next_send FROM broadcast_runtime WHERE id=1').fetchone()['next_send']
        if gate > now:
            con.commit(); return None
        item = con.execute('''SELECT i.* FROM broadcast_items i JOIN broadcast_jobs j ON j.id=i.job_id
            WHERE i.status='READY' AND i.available_at<=? AND j.status='RUNNING' AND j.expires_at>?
            ORDER BY i.id LIMIT 1''', (now, int(now))).fetchone()
        if not item:
            con.commit(); return None
        item = dict(item)
        # Recheck consent, phone and location immediately before submitting.
        job = con.execute('SELECT scope,target_location_id FROM broadcast_jobs WHERE id=?', (item['job_id'],)).fetchone()
        recipient = con.execute('SELECT * FROM notification_recipients WHERE id=?', (item['recipient_id'],)).fetchone()
        eligible = recipient and recipient['consent_status'] == 'ACTIVE' and recipient['sms_enabled'] == 1 and recipient['phone_e164'] == item['phone_e164']
        if eligible and job['scope'] != 'ALL_MONITORED':
            eligible = recipient['location_id'] == job['target_location_id']
        if not eligible:
            con.execute("UPDATE broadcast_items SET status='SKIPPED',error_message='Consent, phone or area changed before sending.',updated_at=? WHERE id=?", (int(now), item['id']))
            con.commit(); return None
        con.execute("UPDATE broadcast_items SET status='SENDING',attempts=attempts+1,updated_at=? WHERE id=?", (int(now), item['id']))
        con.execute('UPDATE broadcast_runtime SET next_send=? WHERE id=1', (now + 1 / requests_per_second,))
        con.commit(); item['attempts'] += 1
        return item
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def process_one(connect, send, requests_per_second=1):
    item = claim(connect, requests_per_second)
    if not item:
        return False
    sid = None; code = None; error = None; available = time.time(); pause = False
    try:
        result = send('sms', item['phone_e164'], item['message'])
        sid = result.get('sid')
        status = str(result.get('status') or 'ACCEPTED').upper() if sid else 'UNKNOWN'
        code = str(result.get('error_code') or '') or None
        error = 'Provider returned no message ID; investigate before resending.' if not sid else result.get('error_message')
    except Exception as exc:
        code = str(getattr(exc, 'code', '') or '') or None
        http = getattr(exc, 'status', None)
        if http == 429 and item['attempts'] < 5:
            status = 'READY'; available += min(300, 5 * 2 ** item['attempts'])
            error = 'Provider rate limit; retry scheduled.'
        elif http and 400 <= http < 500:
            status = 'FAILED'; error = f'Provider rejected the request (HTTP {http}, code {code or "unknown"}).'
        else:
            status = 'UNKNOWN'; error = 'Submission outcome uncertain. Inspect provider logs; no automatic resend.'
        pause = code in ('21608', '20003', '21408', '21606') or http in (401, 403)
    con = connect()
    try:
        con.execute('''UPDATE broadcast_items SET status=?,provider_message_sid=?,error_code=?,error_message=?,available_at=?,updated_at=?
            WHERE id=? AND status IN ('SENDING','UNKNOWN')''', (status, sid, code, error, available, int(time.time()), item['id']))
        if pause:
            con.execute("UPDATE broadcast_jobs SET status='PAUSED',note=? WHERE id=? AND status='RUNNING'", ('Provider configuration or recipient restriction: ' + (code or 'access denied'), item['job_id']))
        con.commit()
    finally:
        con.close()
    return True


PROVIDER_STATES = {'ACCEPTED', 'QUEUED', 'SENDING', 'SENT', 'DELIVERED', 'READ', 'FAILED', 'UNDELIVERED', 'CANCELED'}


def record_status(connect, sid, status, code=None):
    status = (status or '').upper()
    if status not in PROVIDER_STATES:
        return
    con = connect()
    try:
        _lock(con)
        # Receipt progression must not regress when callbacks arrive out of order.
        row = con.execute('SELECT id,status FROM broadcast_items WHERE provider_message_sid=?', (sid,)).fetchone()
        if not row:
            return
        ranks = {'ACCEPTED': 0, 'QUEUED': 1, 'SENDING': 2, 'SENT': 3, 'FAILED': 4, 'UNDELIVERED': 4, 'CANCELED': 4, 'DELIVERED': 5, 'READ': 6}
        if ranks.get(row['status'], -1) > ranks[status]:
            return
        con.execute('UPDATE broadcast_items SET status=?,error_code=?,updated_at=? WHERE id=?', (status, code, int(time.time()), row['id']))
        con.commit()
    finally:
        con.close()
