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

        # ── crm_campaigns table (v2) ──────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS crm_campaigns (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            status VARCHAR(30) DEFAULT 'draft',
            target_country VARCHAR(100),
            target_practice_area VARCHAR(200),
            created_by_id VARCHAR REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            total_leads INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            replies_received INTEGER DEFAULT 0,
            meetings_booked INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0
        )
        """,

        # ── outreach_messages table (v2) ──────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS outreach_messages (
            id SERIAL PRIMARY KEY,
            firm_id INTEGER NOT NULL REFERENCES directory_law_firms(id) ON DELETE CASCADE,
            campaign_id INTEGER REFERENCES crm_campaigns(id) ON DELETE SET NULL,
            created_by_id VARCHAR REFERENCES users(id),
            channel VARCHAR(30) DEFAULT 'email',
            message_type VARCHAR(50) DEFAULT 'cold_outreach',
            subject VARCHAR(300),
            body TEXT NOT NULL,
            recipient_name VARCHAR(200),
            recipient_email VARCHAR(200),
            recipient_phone VARCHAR(100),
            status VARCHAR(30) DEFAULT 'draft',
            ai_generated BOOLEAN DEFAULT FALSE,
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
            opened_at TIMESTAMP,
            replied_at TIMESTAMP,
            reply_text TEXT,
            reply_classification VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── lead_tasks table (v2) ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS lead_tasks (
            id SERIAL PRIMARY KEY,
            firm_id INTEGER NOT NULL REFERENCES directory_law_firms(id) ON DELETE CASCADE,
            assigned_to_id VARCHAR REFERENCES users(id),
            created_by_id VARCHAR REFERENCES users(id),
            title VARCHAR(300) NOT NULL,
            description TEXT,
            task_type VARCHAR(50) DEFAULT 'follow_up',
            priority VARCHAR(20) DEFAULT 'normal',
            status VARCHAR(30) DEFAULT 'open',
            due_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── directory_law_firms: v2 columns ───────────────────────────────────
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS pipeline_stage VARCHAR(50) DEFAULT 'new'",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS lead_score INTEGER DEFAULT 0",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 0",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(100)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS founding_year INTEGER",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS firm_size VARCHAR(50)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS num_lawyers INTEGER",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS decision_makers_json TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS social_links_json TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS opening_hours_json TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS website_status VARCHAR(20) DEFAULT 'unknown'",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS enrichment_source VARCHAR(100)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS assigned_to_id VARCHAR REFERENCES users(id)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS next_followup_at TIMESTAMP",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMP",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS tags_json TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS campaign_id INTEGER REFERENCES crm_campaigns(id) ON DELETE SET NULL",

        # ── Indexes for performance ────────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_dlf_pipeline ON directory_law_firms(pipeline_stage)",
        "CREATE INDEX IF NOT EXISTS idx_dlf_lead_score ON directory_law_firms(lead_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_dlf_campaign ON directory_law_firms(campaign_id)",
        "CREATE INDEX IF NOT EXISTS idx_dlf_assigned ON directory_law_firms(assigned_to_id)",

        # ── AI pitch fields on directory_law_firms ────────────────────────────
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS gmb_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS ai_pitch_email TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS ai_call_script TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS ai_pitch_generated_at TIMESTAMP",

        # ── Social communities table ──────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS social_communities (
            id SERIAL PRIMARY KEY,
            platform VARCHAR(50) NOT NULL,
            community_name VARCHAR(300) NOT NULL,
            url VARCHAR(600),
            join_link VARCHAR(600),
            member_count INTEGER,
            member_count_display VARCHAR(50),
            description TEXT,
            join_instructions TEXT,
            category VARCHAR(100),
            country_focus VARCHAR(100),
            language VARCHAR(50) DEFAULT 'English',
            source VARCHAR(50) DEFAULT 'robot',
            is_active BOOLEAN DEFAULT TRUE,
            is_verified BOOLEAN DEFAULT FALSE,
            outreach_status VARCHAR(50) DEFAULT 'not_contacted',
            ai_outreach_messages_json TEXT,
            last_outreach_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sc_platform ON social_communities(platform)",
        "CREATE INDEX IF NOT EXISTS idx_sc_outreach_status ON social_communities(outreach_status)",

        # ── admin_notifications table ─────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS admin_notifications (
            id SERIAL PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            message TEXT NOT NULL,
            notification_type VARCHAR(50) DEFAULT 'general',
            link_url VARCHAR(500),
            firm_id INTEGER REFERENCES directory_law_firms(id) ON DELETE SET NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_an_is_read ON admin_notifications(is_read)",
        "CREATE INDEX IF NOT EXISTS idx_an_type ON admin_notifications(notification_type)",

        # ── message_templates table ───────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS message_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            template_type VARCHAR(50) NOT NULL,
            channel VARCHAR(50) NOT NULL,
            message_subtype VARCHAR(50),
            subject_template VARCHAR(500),
            body_template TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            is_default BOOLEAN DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── directory_law_firms claim fields ──────────────────────────────────
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_pending BOOLEAN DEFAULT FALSE",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_contact_name VARCHAR(200)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_contact_email VARCHAR(200)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_contact_phone VARCHAR(100)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_contact_role VARCHAR(100)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_description TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_tagline VARCHAR(300)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_social_json TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_logo_url VARCHAR(500)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_bg_url VARCHAR(500)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_website VARCHAR(500)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_address TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS claim_submitted_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS idx_dlf_claim_pending ON directory_law_firms(claim_pending)",

        # ── Blog tables ───────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            slug VARCHAR(300) UNIQUE NOT NULL,
            content TEXT,
            excerpt VARCHAR(500),
            category VARCHAR(100) DEFAULT 'General',
            tags VARCHAR(500),
            hero_image VARCHAR(500),
            author VARCHAR(200) DEFAULT 'LAWCOLAB Team',
            published BOOLEAN DEFAULT FALSE,
            featured BOOLEAN DEFAULT FALSE,
            view_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            published_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS blog_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER,
            name VARCHAR(100),
            email VARCHAR(200),
            content TEXT,
            approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS blog_likes (
            id SERIAL PRIMARY KEY,
            post_id INTEGER,
            session_id VARCHAR(64),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug)",
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(published)",
        "CREATE INDEX IF NOT EXISTS idx_blog_comments_post ON blog_comments(post_id)",

        # ── Page analytics tracking ───────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS page_analytics (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64),
            page_path VARCHAR(500),
            referrer VARCHAR(500),
            ip_hash VARCHAR(64),
            country VARCHAR(100) DEFAULT 'Unknown',
            device_type VARCHAR(20) DEFAULT 'desktop',
            browser VARCHAR(100) DEFAULT 'Other',
            os_name VARCHAR(100) DEFAULT 'Unknown',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pa_session ON page_analytics(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_pa_path ON page_analytics(page_path)",
        "CREATE INDEX IF NOT EXISTS idx_pa_created ON page_analytics(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_pa_device ON page_analytics(device_type)",
        "CREATE INDEX IF NOT EXISTS idx_pa_country ON page_analytics(country)",
        # ── site_settings (key-value store for Google/SEO config) ─────────────
        """
        CREATE TABLE IF NOT EXISTS site_settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── contact_inquiries (public contact form submissions) ────────────────
        """
        CREATE TABLE IF NOT EXISTS contact_inquiries (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(100),
            company VARCHAR(200),
            country VARCHAR(100),
            inquiry_type VARCHAR(100),
            message TEXT NOT NULL,
            newsletter BOOLEAN DEFAULT FALSE,
            status VARCHAR(50) DEFAULT 'new',
            notes TEXT,
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ci_status ON contact_inquiries(status)",
        "CREATE INDEX IF NOT EXISTS idx_ci_email ON contact_inquiries(email)",
        "CREATE INDEX IF NOT EXISTS idx_ci_created ON contact_inquiries(created_at)",

        # ── contact_inquiry_emails (email thread per inquiry) ─────────────────
        """
        CREATE TABLE IF NOT EXISTS contact_inquiry_emails (
            id SERIAL PRIMARY KEY,
            inquiry_id INTEGER NOT NULL REFERENCES contact_inquiries(id) ON DELETE CASCADE,
            direction VARCHAR(10) DEFAULT 'out',
            subject VARCHAR(500),
            body_html TEXT,
            body_text TEXT,
            sent_by_name VARCHAR(200),
            provider VARCHAR(50),
            success BOOLEAN DEFAULT TRUE,
            error_msg TEXT,
            sent_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cie_inquiry ON contact_inquiry_emails(inquiry_id)",

        # ── directory_law_firms: edit-feature columns ─────────────────────────
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS contact_person VARCHAR(200)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS ai_summary TEXT",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS source_url VARCHAR(500)",
        "ALTER TABLE directory_law_firms ADD COLUMN IF NOT EXISTS is_draft BOOLEAN DEFAULT FALSE",

        # ── social_communities: edit-feature columns ──────────────────────────
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS contact_person VARCHAR(200)",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500)",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS email VARCHAR(200)",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS phone VARCHAR(100)",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(100)",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS tags_json TEXT",
        "ALTER TABLE social_communities ADD COLUMN IF NOT EXISTS is_draft BOOLEAN DEFAULT FALSE",

        # ── crm_edit_logs table ────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS crm_edit_logs (
            id SERIAL PRIMARY KEY,
            record_type VARCHAR(50) NOT NULL,
            record_id INTEGER NOT NULL,
            record_name VARCHAR(300),
            field_name VARCHAR(100),
            old_value TEXT,
            new_value TEXT,
            edit_type VARCHAR(30) DEFAULT 'form',
            edited_by_id VARCHAR REFERENCES users(id) ON DELETE SET NULL,
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cel_record ON crm_edit_logs(record_type, record_id)",
        "CREATE INDEX IF NOT EXISTS idx_cel_created ON crm_edit_logs(created_at)",
    ]

    # Detect SQLite so we can translate PostgreSQL-specific syntax
    is_sqlite = str(db.engine.url).startswith("sqlite")

    with db.engine.connect() as conn:
        for sql in migrations:
            exec_sql = sql
            if is_sqlite:
                # SQLite doesn't support IF NOT EXISTS on ALTER TABLE — skip those
                if "ALTER TABLE" in exec_sql and "ADD COLUMN IF NOT EXISTS" in exec_sql:
                    # Rewrite to plain ADD COLUMN and let the except handle duplicates
                    exec_sql = exec_sql.replace(" IF NOT EXISTS", "")
                # Replace PostgreSQL auto-increment with SQLite INTEGER PRIMARY KEY
                exec_sql = exec_sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                # Replace NOW() with SQLite's CURRENT_TIMESTAMP
                exec_sql = exec_sql.replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
                exec_sql = exec_sql.replace(" NOW()", " CURRENT_TIMESTAMP")
                # ON DELETE CASCADE foreign-key syntax is fine in SQLite
            try:
                conn.execute(text(exec_sql))
                logger.info("Migration OK: %s", exec_sql[:80])
            except Exception as exc:
                # Log but don't crash — column may already exist on some drivers
                # that don't support IF NOT EXISTS (psycopg2 on PG does support it)
                logger.warning("Migration skipped (%s): %s", exc.__class__.__name__, exec_sql[:80])
        conn.commit()

    logger.info("Schema migrations complete.")
