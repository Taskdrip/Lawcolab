"""
Startup schema migrations — safely add new columns to existing tables.
Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS so it's idempotent.
Runs before the app serves any traffic.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migrations(db):
    """Execute all pending column-level migrations against the current DB."""
    migrations = [
        # Security columns added to users table for brute-force protection
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45)",

        # Court-specific fields on calendar_events
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_jurisdiction VARCHAR(150)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_type VARCHAR(100)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_address VARCHAR(400)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS judge_name VARCHAR(200)",

        # Court hearing history table
        """
        CREATE TABLE IF NOT EXISTS court_date_history (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
            hearing_date DATE NOT NULL,
            outcome VARCHAR(200),
            court_notes TEXT,
            recorded_by_id VARCHAR REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_court_history_event ON court_date_history(event_id)",
        "CREATE INDEX IF NOT EXISTS idx_court_history_date ON court_date_history(hearing_date DESC)",
    ]

    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                logger.info("Migration OK: %s", sql[:80])
            except Exception as exc:
                # Log but don't crash — column may already exist on some drivers
                # that don't support IF NOT EXISTS (psycopg2 on PG does support it)
                logger.warning("Migration skipped (%s): %s", exc.__class__.__name__, sql[:80])
        conn.commit()

    logger.info("Schema migrations complete.")
