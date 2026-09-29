from database import column_names, PostgresConnection


def initialize_schema(connect):
    con = connect()
    try:
        cur = con.cursor()
        if isinstance(con, PostgresConnection):
            cur.execute('SELECT pg_advisory_xact_lock(13745526001)')
        cur.execute("""CREATE TABLE IF NOT EXISTS reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT, reporter TEXT, phone TEXT, location TEXT,
            lat REAL, lon REAL, hazard_type TEXT DEFAULT 'Other', location_method TEXT DEFAULT 'manual',
            severity TEXT, description TEXT, image_name TEXT, status TEXT, created_at INTEGER)""")
        # Backwards-compatible migrations for databases created by earlier hackathon builds.
        report_cols = column_names(cur, "reports")
        if 'hazard_type' not in report_cols:
            cur.execute("ALTER TABLE reports ADD COLUMN hazard_type TEXT DEFAULT 'Other'")
        if 'location_method' not in report_cols:
            cur.execute("ALTER TABLE reports ADD COLUMN location_method TEXT DEFAULT 'manual'")
        cur.execute("""CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER,
            location TEXT,
            level TEXT,
            risk_percent REAL,
            message_en TEXT,
            message_hi TEXT,
            message_as TEXT,
            recommended_action TEXT,
            source TEXT,
            acknowledged INTEGER DEFAULT 0,
            acknowledged_at INTEGER,
            created_at INTEGER
        )""")
        alert_cols = column_names(cur, "alerts")
        if 'acknowledged_at' not in alert_cols:
            cur.execute("ALTER TABLE alerts ADD COLUMN acknowledged_at INTEGER")
        cur.execute("""CREATE TABLE IF NOT EXISTS system_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            detail TEXT,
            created_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS telemetry(
            id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER, station_id TEXT,
            rainfall_intensity REAL, soil_moisture REAL, tilt_deg REAL, vibration_g REAL,
            pore_pressure_kpa REAL, displacement_mm REAL, battery_pct REAL, quality REAL,
            source TEXT, created_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS alert_feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER, outcome TEXT, note TEXT, created_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS source_cache(
            cache_key TEXT PRIMARY KEY, provider TEXT, payload_json TEXT, fetched_at INTEGER, valid_at TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS assessments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER, location TEXT, mode TEXT,
            assessment_kind TEXT, risk_level TEXT, risk_score REAL, data_completeness REAL,
            model_version TEXT, inputs_json TEXT, sources_json TEXT, result_json TEXT, created_at INTEGER
        )""")
        alert_cols = column_names(cur, "alerts")
        for col, ddl in [
            ('lifecycle_status', "TEXT DEFAULT 'DRAFT'"),('advisory_type', "TEXT DEFAULT 'ADVISORY'"),
            ('issued_at', 'INTEGER'),('resolved_at', 'INTEGER'),('updated_at', 'INTEGER')
        ]:
            if col not in alert_cols:
                cur.execute(f"ALTER TABLE alerts ADD COLUMN {col} {ddl}")
        cur.execute("""CREATE TABLE IF NOT EXISTS alert_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER, from_status TEXT, to_status TEXT,
            actor_role TEXT, note TEXT, created_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS notification_recipients(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone_e164 TEXT NOT NULL,
            location_id INTEGER, language TEXT DEFAULT 'en', sms_enabled INTEGER DEFAULT 1,
            whatsapp_enabled INTEGER DEFAULT 0, consent_status TEXT DEFAULT 'ACTIVE',
            consent_at INTEGER, created_at INTEGER, updated_at INTEGER
        )""")
        recipient_cols = column_names(cur, "notification_recipients")
        for col, ddl in [
            ('household_label', 'TEXT'), ('village', 'TEXT'), ('household_size', 'INTEGER'),
            ('registered_by_role', "TEXT DEFAULT 'ADMIN'"), ('registered_by_officer', 'TEXT'),
            ('registered_by_officer_code', 'TEXT'), ('registered_by_posting_location_id', 'INTEGER'),
            ('registration_source', "TEXT DEFAULT 'ADMIN_PORTAL'")
        ]:
            if col not in recipient_cols:
                cur.execute(f"ALTER TABLE notification_recipients ADD COLUMN {col} {ddl}")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notification_recipients_location ON notification_recipients(location_id,consent_status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notification_recipients_officer ON notification_recipients(registered_by_officer_code,location_id)")
        cur.execute("""CREATE TABLE IF NOT EXISTS notification_deliveries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL, recipient_id INTEGER NOT NULL,
            channel TEXT NOT NULL, provider TEXT, provider_message_sid TEXT, status TEXT NOT NULL,
            error_code TEXT, error_message TEXT, attempted_at INTEGER, updated_at INTEGER,
            delivered_at INTEGER, read_at INTEGER,
            UNIQUE(alert_id,recipient_id,channel)
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notification_deliveries_alert ON notification_deliveries(alert_id,channel,status)")
        cur.execute("""CREATE TABLE IF NOT EXISTS flood_basins(
            location_id INTEGER PRIMARY KEY, config_json TEXT NOT NULL, updated_at INTEGER NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS flood_gauges(
            id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL,
            source TEXT NOT NULL, observed_at INTEGER NOT NULL, payload_json TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS flood_assessments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER NOT NULL,
            result_json TEXT NOT NULL, created_at INTEGER NOT NULL, alert_id INTEGER)""")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_flood_gauges ON flood_gauges(location_id,source,observed_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_flood_assessments ON flood_assessments(location_id,id)')
        from broadcasts import initialize_broadcast_schema
        initialize_broadcast_schema(cur)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
