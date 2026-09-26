"""Explicit, atomic copy from a SQLite backup into an EMPTY PostgreSQL database.

Run from backend: python migrate_sqlite_to_postgres.py --source /path/backup.db
Set PRAHARI_DATABASE_URL privately first. This never deletes or updates source data.
"""
import argparse
import json
from pathlib import Path
import sqlite3

from database import TABLES, column_names, connect
from database_schema import initialize_schema


def migrate(source_path, database_url):
    if not database_url:
        raise ValueError('Set PRAHARI_DATABASE_URL before running the migration.')
    path = Path(source_path).resolve(strict=True)
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    target = None
    try:
        source.execute('BEGIN')  # Read one consistent snapshot.
        tables = {r['name'] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not tables or tables - set(TABLES):
            raise ValueError('Source must be a PRAHARI database with only recognized tables.')
        initialize_schema(lambda: connect(None, database_url))
        target = connect(None, database_url)
        cur = target.cursor()
        cur.execute('LOCK TABLE ' + ','.join(TABLES) + ' IN EXCLUSIVE MODE')
        if any(cur.execute(f'SELECT COUNT(*) AS n FROM {t}').fetchone()['n'] for t in TABLES):
            raise ValueError('Destination is not empty. No data was copied; use a new empty database.')
        counts = {}
        for table in TABLES:
            if table not in tables:
                counts[table] = 0
                continue
            rows = source.execute(f'SELECT * FROM {table}')
            columns = [c[0] for c in rows.description]
            if not set(columns).issubset(column_names(cur, table)):
                raise ValueError(f'Unsupported source columns in {table}. No data was copied.')
            quoted = ','.join('"' + c + '"' for c in columns)
            placeholders = ','.join('?' for _ in columns)
            count = 0
            for row in rows:
                cur.execute(f'INSERT INTO {table} ({quoted}) VALUES ({placeholders})', tuple(row))
                count += 1
            counts[table] = count
            if 'id' in columns:
                cur.execute(f"SELECT setval(pg_get_serial_sequence(?, 'id'), COALESCE((SELECT MAX(id) FROM {table}),1), EXISTS(SELECT 1 FROM {table}))", (table,))
            if cur.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n'] != count:
                raise RuntimeError('Record count verification failed; migration rolled back.')
        target.commit()
        return counts
    except Exception:
        if target:
            target.rollback()
        raise
    finally:
        source.close()
        if target:
            target.close()


if __name__ == '__main__':
    from settings import DATABASE_URL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Existing SQLite backup file (read only)')
    args = parser.parse_args()
    try:
        print(json.dumps({'copied_rows': migrate(args.source, DATABASE_URL)}))
    except Exception as exc:
        # Driver errors can include row data; don't print raw database exceptions.
        message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError, RuntimeError)) else 'Migration failed and was rolled back. Check the database connection and source backup.'
        parser.exit(1, message + '\n')
