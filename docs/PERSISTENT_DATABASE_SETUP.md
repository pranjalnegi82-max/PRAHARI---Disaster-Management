# Keep civilian records after login, sleep and deployment

PRAHARI previously used a local `backend/prahari.db` SQLite file. Render's free web-service filesystem is ephemeral, so this file can disappear after a restart, deployment or idle spin-down. Login itself does not delete civilians.

This change supports hosted PostgreSQL for all database tables. SQLite remains available for local development. When a PostgreSQL URL is configured, a connection failure stops startup instead of creating a replacement SQLite database. The admin enrollment list now defaults to all monitored areas; field-officer posting restrictions remain enforced.

## Set up Neon without sharing passwords

1. Create an account at https://neon.com/ and select its Free plan for this prototype. Check the current plan limits before using it for an operational service.
2. Create a project named **PRAHARI**. Choose a region near the Render backend where available.
3. In the project dashboard, click **Connect**. Copy the PostgreSQL connection string. The pooled connection is supported; keep its TLS parameters, including `sslmode=require` and any channel-binding parameter supplied by Neon. Copy the URI only, not a `psql` command or surrounding quotes.
4. On Render, open the **backend** service `prahari-sih26001-pranjal-api`, then **Environment**. The new backend version needs:
   - Key: `PRAHARI_DATABASE_URL`
   - Value: the private PostgreSQL connection URI from Neon.
5. Coordinate this environment change with deployment of the PostgreSQL-support PR. The old version does not understand this setting; saving an environment change redeploys the old service and can erase remaining SQLite data. Capture any remaining records first and pause enrollment during cutover.
6. Deploy the PostgreSQL-support version once the connection is configured. PRAHARI creates its tables on startup. Do not put the URI in GitHub, chat, screenshots, or a `VITE_` variable.

The backend also accepts the conventional `DATABASE_URL`; `PRAHARI_DATABASE_URL` takes precedence. If both are unset, the app continues to use SQLite and shows a storage warning on Render. Merely adding a database URL to the old application does not migrate data.

## Preserve existing data before switching

If the old database is already gone, connecting PostgreSQL cannot recover those lost records. If records are still visible, retain an authorized private copy before any deploy. A PostgreSQL deployment begins with an empty registry unless data is explicitly imported.

If you have a SQLite database backup, the provided migration script copies all recognized application tables, including consent, advisories, delivery history and audit records. It opens the source read-only, refuses a non-empty destination, checks row counts, preserves IDs and updates sequences. It copies data in one destination transaction; a failed copy rolls back. Stop writers during the copy and verify counts before resuming registration. The script never sends SMS.

With the PostgreSQL URL set privately in the environment:

```bash
cd backend
python migrate_sqlite_to_postgres.py --source /private/path/prahari-backup.db
```

Use a fresh empty PostgreSQL database. Do not commit or upload a civilian database to a public repository. The migration copies database rows, not uploaded report photographs; those image files still need persistent file/object storage separately.

## Verify the fix

- Open `/api/system/status`: `database_storage.backend` must be `postgresql`, and `storage` must be `external_database`. An `online` database alone does not prove persistent storage.
- Register a clearly labeled test civilian with your own opted-in number.
- Sign out, sign in, and verify the record under **All monitored areas**.
- Restart the backend, then verify the same record remains.
- Revoke the test enrollment when finished. Sending an SMS is not required for this check.

## Sources

- Render file-storage limitations: https://render.com/docs/free#local-files-lost-on-redeploy
- Neon connection details: https://neon.com/docs/connect/connect-from-any-app
- Neon TLS requirements: https://neon.com/docs/connect/connect-securely
