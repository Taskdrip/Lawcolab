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
