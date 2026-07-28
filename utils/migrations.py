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
        # Full-access flag for team members (admin-granted firm-wide visibility)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_full_access BOOLEAN NOT NULL DEFAULT FALSE",

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
        # ── law_firm_showcases: new profile fields ────────────────────────────
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS tagline VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS phone VARCHAR(50)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(50)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS website_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS youtube_url VARCHAR(300)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS founded_year INTEGER",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS firm_size VARCHAR(50)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS practice_areas_json TEXT",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS locations_json TEXT",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS team_json TEXT",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS submission_status VARCHAR(20) NOT NULL DEFAULT 'draft'",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS approved_by_id VARCHAR REFERENCES users(id)",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
        "ALTER TABLE law_firm_showcases ADD COLUMN IF NOT EXISTS showcase_order INTEGER DEFAULT 0",
        # ── public_law_firm_reviews: new fields ───────────────────────────────
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS reviewer_email VARCHAR(300)",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS reviewer_company VARCHAR(200)",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS reviewer_location VARCHAR(200)",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS review_title VARCHAR(300)",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS is_featured BOOLEAN DEFAULT FALSE",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45)",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS user_agent TEXT",
        "ALTER TABLE public_law_firm_reviews ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP",
        # ── directory_law_firms table (create if not yet present) ─────────────
        """
        CREATE TABLE IF NOT EXISTS directory_law_firms (
            id SERIAL PRIMARY KEY,
            name VARCHAR(300) NOT NULL,
            description TEXT,
            phone VARCHAR(100),
            email VARCHAR(200),
            website VARCHAR(500),
            address TEXT,
            city VARCHAR(100),
            state VARCHAR(100),
            country VARCHAR(100) DEFAULT 'Nigeria',
            postal_code VARCHAR(20),
            latitude FLOAT,
            longitude FLOAT,
            google_place_id VARCHAR(200) UNIQUE,
            google_rating NUMERIC(3,1),
            google_reviews_count INTEGER DEFAULT 0,
            google_maps_url VARCHAR(500),
            practice_areas_json TEXT,
            source VARCHAR(50) DEFAULT 'manual',
            has_website BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            is_claimed BOOLEAN DEFAULT FALSE,
            claimed_firm_id INTEGER REFERENCES law_firms(id),
            crm_status VARCHAR(50) DEFAULT 'new',
            logo_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        # ── directory_notes table ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS directory_notes (
            id SERIAL PRIMARY KEY,
            firm_id INTEGER NOT NULL REFERENCES directory_law_firms(id) ON DELETE CASCADE,
            created_by_id VARCHAR REFERENCES users(id),
            note_text TEXT NOT NULL,
            note_type VARCHAR(50) DEFAULT 'general',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        # ── public_law_firm_messages: extra fields ────────────────────────────
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS sender_phone VARCHAR(50)",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS sender_company VARCHAR(200)",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(50) DEFAULT 'inquiry'",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS is_replied BOOLEAN DEFAULT FALSE",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'normal'",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45)",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS user_agent TEXT",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP",
        "ALTER TABLE public_law_firm_messages ADD COLUMN IF NOT EXISTS replied_at TIMESTAMP",

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
