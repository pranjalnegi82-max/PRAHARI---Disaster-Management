"""SQLite for local development; external PostgreSQL for durable hosted data.

The application uses bound qmark parameters. Only the PostgreSQL cursor adapts
those placeholders; values are always passed separately to the driver.
"""
from pathlib import Path
import re
import sqlite3


TABLES = (
    'flood_basins', 'flood_gauges', 'flood_assessments',
    'reports', 'alerts', 'system_events', 'telemetry', 'alert_feedback',
    'source_cache', 'assessments', 'alert_audit', 'notification_recipients',
    'notification_deliveries', 'broadcast_jobs', 'broadcast_items', 'broadcast_runtime',
)
_SQL_TOKENS = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*[\s\S]*?\*/|\?")


def postgres_sql(sql):
    # Escape literal percent signs for psycopg's parameter protocol as well.
    sql = sql.replace('%', '%%')
    return _SQL_TOKENS.sub(lambda m: '%s' if m.group() == '?' else m.group(), sql)


class PostgresCursor:
    def __init__(self, cursor):
        self.raw = cursor

    def execute(self, sql, parameters=None):
        if sql.lstrip().upper().startswith('CREATE TABLE'):
            sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY')
        if parameters is None:
            self.raw.execute(sql)
        else:
            self.raw.execute(postgres_sql(sql), parameters)
        return self

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()

    @property
    def rowcount(self):
        return self.raw.rowcount


class PostgresConnection:
    def __init__(self, raw):
        self.raw = raw

    def cursor(self):
        return PostgresCursor(self.raw.cursor())

    def execute(self, sql, parameters=None):
        return self.cursor().execute(sql, parameters)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect(sqlite_path, database_url=''):
    if database_url:
        if not database_url.startswith(('postgres://', 'postgresql://')):
            raise RuntimeError('PRAHARI_DATABASE_URL must be a PostgreSQL connection URL.')
        import psycopg
        from psycopg.rows import dict_row
        try:
            raw = psycopg.connect(database_url, row_factory=dict_row,
                                  connect_timeout=10, prepare_threshold=None)
        except psycopg.Error:
            # Do not leak credentials or silently create an empty local database.
            raise RuntimeError('PostgreSQL connection failed. Check the database connection configured on the backend.') from None
        return PostgresConnection(raw)
    path = Path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def column_names(cursor, table):
    if table not in TABLES:
        raise ValueError('Unknown PRAHARI table')
    if isinstance(cursor, PostgresCursor):
        rows = cursor.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?', (table,)).fetchall()
        return {r['column_name'] for r in rows}
    return {r['name'] for r in cursor.execute(f'PRAGMA table_info({table})').fetchall()}


def insert_row(cursor, sql, parameters):
    """Return an inserted identifier with the same semantics on both databases."""
    return cursor.execute(sql.rstrip().rstrip(';') + ' RETURNING id', parameters).fetchone()['id']


def storage_status(database_url='', hosted=False):
    if database_url:
        return {'backend': 'postgresql', 'storage': 'external_database',
                'warning': None}
    return {'backend': 'sqlite', 'storage': 'local_file',
            'warning': ('Civilian records are stored on the server filesystem. On Render without a persistent disk they can be lost after sleep, restart or deployment. Configure PostgreSQL before relying on saved records.' if hosted else None)}
