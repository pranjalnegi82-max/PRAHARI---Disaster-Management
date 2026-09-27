"""Run separately: python broadcast_worker.py. Never starts from an API request."""
import logging
import signal
import time

from database import connect
from database_schema import initialize_schema
from settings import DATABASE_URL, DB_PATH, BROADCAST_ENABLED, BROADCAST_REQUESTS_PER_SECOND
from notifications import send, fetch_status, production_account_status
from broadcasts import process_one, record_status

log = logging.getLogger('prahari.broadcast')
stop = False


def connection():
    return connect(DB_PATH, DATABASE_URL)


def reconcile_one(factory=connection, fetch=fetch_status):
    con = factory(); now = time.time()
    try:
        row = con.execute('''SELECT id,provider_message_sid FROM broadcast_items
            WHERE provider_message_sid IS NOT NULL AND status IN ('ACCEPTED','QUEUED','SENDING','SENT')
            AND available_at<=? ORDER BY available_at,id LIMIT 1''', (now,)).fetchone()
        if not row:
            return
        con.execute('UPDATE broadcast_items SET available_at=? WHERE id=?', (now + 60, row['id']))
        con.commit()
    finally:
        con.close()
    try:
        result = fetch(row['provider_message_sid'])
        record_status(factory, row['provider_message_sid'], result.get('status'), str(result.get('error_code') or '') or None)
    except Exception:
        log.warning('Receipt reconciliation deferred; provider unavailable.')


def main():
    if not BROADCAST_ENABLED or not DATABASE_URL:
        raise SystemExit('Configure PostgreSQL and PRAHARI_BROADCAST_ENABLED=true before starting the broadcast worker.')
    initialize_schema(connection)
    next_check = 0; next_receipt = 0; ready = False
    while not stop:
        try:
            if time.time() >= next_check:
                account = production_account_status(); ready = account['ready']
                next_check = time.time() + (300 if ready else 30)
                if not ready:
                    log.warning('Broadcast paused: %s', ' '.join(account['issues']))
            if ready:
                process_one(connection, send, BROADCAST_REQUESTS_PER_SECOND)
                if time.time() >= next_receipt:
                    reconcile_one(); next_receipt = time.time() + 1
        except Exception:
            # Do not log database URLs, phone numbers or provider request bodies.
            log.error('Worker operation failed; durable queue retained. Check database/provider health.')
            time.sleep(2)
        time.sleep(max(0.01, min(0.5, 1 / BROADCAST_REQUESTS_PER_SECOND)))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    def shutdown(*_):
        global stop
        stop = True
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
