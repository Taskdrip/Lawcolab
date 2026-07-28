"""
Email CRM schema migrations — idempotent, run at startup.
Adds tables and columns required by the Communications / Email CRM module.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_email_migrations(db):
    """Execute Email CRM schema changes."""
    migrations = [
        # ── Extended tracking columns on outreach_messages ─────────────────────
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS bounced_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS spam_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS clicked_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS forwarded_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS tracking_token VARCHAR(64)",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS provider VARCHAR(50) DEFAULT 'simulate'",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(200)",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS scheduled_timezone VARCHAR(100)",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS reply_to VARCHAR(200)",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS cc_emails TEXT",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS bcc_emails TEXT",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS internal_note TEXT",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS template_id INTEGER",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS open_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS click_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'normal'",
        "ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS tags TEXT",

        # ── email_settings ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS email_settings (
            id SERIAL PRIMARY KEY,
            provider VARCHAR(50) NOT NULL DEFAULT 'simulate',
            smtp_host VARCHAR(200),
            smtp_port INTEGER DEFAULT 587,
            smtp_user VARCHAR(200),
            smtp_password TEXT,
            smtp_use_tls BOOLEAN DEFAULT TRUE,
            api_key TEXT,
            from_name VARCHAR(200) DEFAULT 'LAWCOLAB',
            from_email VARCHAR(200) DEFAULT 'noreply@lawcolab.com',
            reply_to VARCHAR(200),
            signature_html TEXT,
            email_footer TEXT,
            brand_color VARCHAR(10) DEFAULT '#0d1b4b',
            company_logo_url VARCHAR(500),
            track_opens BOOLEAN DEFAULT TRUE,
            track_clicks BOOLEAN DEFAULT TRUE,
            unsubscribe_footer TEXT,
            daily_send_limit INTEGER DEFAULT 500,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── firm_contacts ──────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS firm_contacts (
            id SERIAL PRIMARY KEY,
            firm_id INTEGER NOT NULL REFERENCES directory_law_firms(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            email VARCHAR(200),
            phone VARCHAR(100),
            whatsapp VARCHAR(100),
            job_title VARCHAR(200),
            department VARCHAR(200),
            preferred_language VARCHAR(50) DEFAULT 'English',
            photo_url VARCHAR(500),
            notes TEXT,
            is_primary BOOLEAN DEFAULT FALSE,
            last_contacted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_firm_contacts_firm ON firm_contacts(firm_id)",
        "CREATE INDEX IF NOT EXISTS idx_firm_contacts_email ON firm_contacts(email)",

        # ── email_templates ────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS email_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            category VARCHAR(100) DEFAULT 'custom',
            subject VARCHAR(500),
            body_html TEXT NOT NULL,
            body_text TEXT,
            merge_tags TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            is_default BOOLEAN DEFAULT FALSE,
            use_count INTEGER DEFAULT 0,
            created_by_id VARCHAR REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_email_templates_category ON email_templates(category)",

        # ── email_automations ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS email_automations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            trigger_type VARCHAR(100) NOT NULL,
            trigger_conditions TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            run_count INTEGER DEFAULT 0,
            created_by_id VARCHAR REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── email_automation_steps ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS email_automation_steps (
            id SERIAL PRIMARY KEY,
            automation_id INTEGER NOT NULL REFERENCES email_automations(id) ON DELETE CASCADE,
            step_order INTEGER NOT NULL DEFAULT 0,
            action_type VARCHAR(50) NOT NULL DEFAULT 'send_email',
            delay_days INTEGER DEFAULT 0,
            delay_hours INTEGER DEFAULT 0,
            template_id INTEGER REFERENCES email_templates(id),
            subject VARCHAR(500),
            body_html TEXT,
            conditions TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_automation_steps_auto ON email_automation_steps(automation_id)",

        # ── tracking pixel log ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS email_tracking_events (
            id SERIAL PRIMARY KEY,
            message_id INTEGER REFERENCES outreach_messages(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            ip_address VARCHAR(45),
            user_agent TEXT,
            url_clicked VARCHAR(1000),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_track_events_msg ON email_tracking_events(message_id)",
        "CREATE INDEX IF NOT EXISTS idx_outreach_tracking_token ON outreach_messages(tracking_token)",
    ]

    for sql in migrations:
        try:
            db.session.execute(text(sql.strip()))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.debug("Email migration skipped (likely already applied): %s", str(e)[:120])

    logger.info("Email CRM schema migrations complete.")
