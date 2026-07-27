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
        # ── users table ───────────────────────────────────────────────────────
        # Security columns for brute-force protection
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45)",
        # Company-specific fields for client organisations
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name VARCHAR(200)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_description TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS industry VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS website_url VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_size VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS headquarters VARCHAR(200)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS founded_year INTEGER",
        # Professional fields for lawyers / team members
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS specialization VARCHAR(200)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS years_experience INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS education TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS certifications TEXT",
        # Enhanced address fields for professional invoices
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line_1 VARCHAR(200)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line_2 VARCHAR(200)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS state_province VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS country VARCHAR(100)",

        # ── law_firms table ───────────────────────────────────────────────────
        # Banking details for receiving payments
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS bank_name VARCHAR(100)",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS account_number VARCHAR(50)",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS routing_number VARCHAR(20)",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS swift_code VARCHAR(20)",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS account_holder_name VARCHAR(100)",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS tax_id VARCHAR(50)",
        # Subscription management
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS admin_access_granted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS admin_access_expires TIMESTAMP",
        "ALTER TABLE law_firms ADD COLUMN IF NOT EXISTS subscription_period VARCHAR(20)",

        # ── popup_settings table ──────────────────────────────────────────────
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS welcome_video_url VARCHAR(500)",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS thankyou_video_url VARCHAR(500)",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS trial_duration_days INTEGER DEFAULT 3",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS founders_price NUMERIC(10,2) DEFAULT 750.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS lifetime_price NUMERIC(10,2) DEFAULT 999.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS starter_regular_price NUMERIC(10,2) DEFAULT 70.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS growth_regular_price NUMERIC(10,2) DEFAULT 210.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS enterprise_regular_price NUMERIC(10,2) DEFAULT 840.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS founders_regular_price NUMERIC(10,2) DEFAULT 840.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS checkout_currency VARCHAR(3) NOT NULL DEFAULT 'USD'",
        # NGN pricing columns
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS starter_price_ngn NUMERIC(12,2) DEFAULT 60000.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS growth_price_ngn NUMERIC(12,2) DEFAULT 140000.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS enterprise_price_ngn NUMERIC(12,2) DEFAULT 550000.00",
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS founders_price_ngn NUMERIC(12,2) DEFAULT 2750000.00",
        # Auto geo-currency flag
        "ALTER TABLE popup_settings ADD COLUMN IF NOT EXISTS auto_geo_currency BOOLEAN NOT NULL DEFAULT TRUE",

        # ── law_firm_showcases table ──────────────────────────────────────────
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS logo_image_url VARCHAR(500)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS facebook_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS linkedin_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS twitter_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS instagram_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS total_reviews INTEGER DEFAULT 0",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS average_rating NUMERIC(3,2) DEFAULT 5.0",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS total_views INTEGER DEFAULT 0",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS verified_date TIMESTAMP",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS verified_by_id VARCHAR REFERENCES users(id)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS verification_reason VARCHAR(200)",

        # ── calendar_events table ─────────────────────────────────────────────
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_jurisdiction VARCHAR(150)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_type VARCHAR(100)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS court_address VARCHAR(400)",
        "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS judge_name VARCHAR(200)",

        # ── court_date_history table ──────────────────────────────────────────
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
