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

    # ── Seed default email templates (idempotent) ──────────────────────────────
    _seed_default_templates(db)

    # ── Apply verified Resend domain to existing settings row ─────────────────
    # Runs every boot; only updates rows still using the old unverified address
    # or the simulate placeholder so Railway DB is always in sync.
    _apply_resend_defaults(db)

    logger.info("Email CRM schema migrations complete.")


def _apply_resend_defaults(db):
    """
    Idempotent: if email_settings exists with the old unverified from_email
    (noreply@lawcolab.com) or provider 'simulate', update it to use Resend
    with the verified mail.lawcolab.com subdomain.
    Leaves rows already configured differently untouched.
    """
    import os
    try:
        row = db.session.execute(
            text("SELECT id, provider, from_email, api_key FROM email_settings LIMIT 1")
        ).fetchone()

        resend_key = os.environ.get("RESEND_API_KEY", "")

        if row is None:
            # No settings row yet — create one with sensible Resend defaults
            db.session.execute(text("""
                INSERT INTO email_settings
                (provider, from_name, from_email, reply_to,
                 api_key, track_opens, track_clicks,
                 daily_send_limit, updated_at)
                VALUES ('resend', 'LAWCOLAB', 'noreply@mail.lawcolab.com',
                        'noreply@mail.lawcolab.com',
                        :key, TRUE, TRUE, 500, NOW())
            """), {"key": resend_key or None})
            db.session.commit()
            logger.info("Email CRM: created default Resend settings row.")
        else:
            row = dict(row._mapping)
            needs_update = (
                row.get("from_email") in ("noreply@lawcolab.com", "", None)
                or row.get("provider") in ("simulate", "", None)
            )
            if needs_update:
                # Only overwrite fields that are still at the old/unset defaults
                new_provider = "resend" if row.get("provider") in ("simulate", "", None) else row["provider"]
                new_from = (
                    "noreply@mail.lawcolab.com"
                    if row.get("from_email") in ("noreply@lawcolab.com", "", None)
                    else row["from_email"]
                )
                # Only write the env api_key if no key is stored yet
                new_key_sql = (
                    ":key" if (not row.get("api_key") and resend_key)
                    else "api_key"          # keep existing DB value
                )
                db.session.execute(text(f"""
                    UPDATE email_settings
                    SET provider  = :provider,
                        from_email = :from_email,
                        reply_to   = COALESCE(NULLIF(reply_to,''), :from_email),
                        api_key    = COALESCE({new_key_sql}, api_key),
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "provider":   new_provider,
                    "from_email": new_from,
                    "key":        resend_key or None,
                    "id":         row["id"],
                })
                db.session.commit()
                logger.info(
                    "Email CRM: updated settings → provider=%s from=%s",
                    new_provider, new_from,
                )
    except Exception as e:
        db.session.rollback()
        logger.warning("Email CRM: could not apply Resend defaults: %s", e)


def _seed_default_templates(db):
    """Seed built-in email templates if the table is empty."""
    try:
        count = db.session.execute(text("SELECT COUNT(*) FROM email_templates")).scalar()
        if count and count > 0:
            return  # Already seeded

        DEFAULT_TEMPLATES = [
            # Welcome
            {
                "name": "Welcome — New Registration",
                "category": "welcome",
                "subject": "Welcome to LAWCOLAB, {{FirmName}}! 🎉",
                "body_html": """<p>Dear {{ContactName}},</p>
<p>Welcome to <strong>LAWCOLAB</strong> — your complete Legal Operating System.</p>
<p>We're thrilled to have <strong>{{FirmName}}</strong> join our growing community of forward-thinking law firms across {{Country}}.</p>
<p>Here's what you can do right now:</p>
<ul>
  <li>🏛️ Set up your firm profile and case management</li>
  <li>💼 Invite your team members</li>
  <li>📅 Sync your court calendar</li>
  <li>💳 Start generating professional invoices</li>
</ul>
<p>Need help getting started? Our team is always available via WhatsApp: <strong>+2348036622568</strong></p>
<p>Log in now: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Best regards,<br><strong>Abraham Tahbat</strong><br>Lawyer & Founder, LAWCOLAB</p>""",
            },
            # Onboarding
            {
                "name": "Onboarding — Day 3 Check-in",
                "category": "onboarding",
                "subject": "How is {{FirmName}} settling in with LAWCOLAB?",
                "body_html": """<p>Dear {{ContactName}},</p>
<p>It's been 3 days since {{FirmName}} joined LAWCOLAB. We hope you're finding your way around!</p>
<p>A few tips to help you get more from the platform:</p>
<ul>
  <li>📂 Add your first case in the Case Management module</li>
  <li>👥 Invite team members from the Admin panel</li>
  <li>📄 Generate your first invoice and see how easy billing can be</li>
</ul>
<p>Is there anything you need help with? Simply reply to this email or WhatsApp us: +2348036622568</p>
<p>Warm regards,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Trial
            {
                "name": "Trial — Start Your Free Trial",
                "category": "trial",
                "subject": "Your Free LAWCOLAB Trial is Ready, {{FirmName}}",
                "body_html": """<p>Good day,</p>
<p>Your free LAWCOLAB trial is ready and waiting for <strong>{{FirmName}}</strong>.</p>
<p>No credit card required. No setup fees. Just log in and explore:</p>
<ul>
  <li>✅ Full case management</li>
  <li>✅ Invoice generation and tracking</li>
  <li>✅ Client portal access</li>
  <li>✅ Court calendar with smart reminders</li>
  <li>✅ Law Firm Directory listing</li>
</ul>
<p>Start your trial now: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Best,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Demo
            {
                "name": "Demo Invitation",
                "category": "demo",
                "subject": "You're Invited: Live LAWCOLAB Demo for {{FirmName}}",
                "body_html": """<p>Dear {{ContactName}},</p>
<p>I'd love to give <strong>{{FirmName}}</strong> a personalised live demo of LAWCOLAB — just 20 minutes and you'll see exactly how it can transform your practice.</p>
<p>We'll walk through:</p>
<ul>
  <li>📁 Case management tailored for {{PracticeArea}} firms</li>
  <li>💳 Automatic invoice generation and payment tracking</li>
  <li>🏛️ Your firm's public directory listing (like Google My Business for lawyers)</li>
  <li>📊 Real-time analytics and team performance reports</li>
</ul>
<p>Book a time that works for you: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>See you there!<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Cold outreach
            {
                "name": "Cold Outreach — Nigeria",
                "category": "sales",
                "subject": "Streamline {{FirmName}} with LAWCOLAB — Free Trial Inside",
                "body_html": """<p>Good day,</p>
<p>My name is Abraham Tahbat — a lawyer and software developer with 15+ years building technology for legal professionals.</p>
<p>I came across <strong>{{FirmName}}</strong> while researching law firms in {{City}}, and I wanted to introduce LAWCOLAB — a complete Legal Operating System built specifically for Nigerian law firms.</p>
<p>LAWCOLAB helps you:</p>
<ul>
  <li>🗂️ Manage all cases, clients, and documents in one organised hub</li>
  <li>💰 Generate and track invoices — get paid faster</li>
  <li>📅 Never miss a court date with smart calendar alerts</li>
  <li>👤 Give clients 24/7 secure access to their case updates</li>
  <li>🌐 Get your firm listed on our public law firm directory</li>
</ul>
<p>We'd like to give {{FirmName}} <strong>free access</strong> to test the platform for 30 days.</p>
<p>Start here: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Best regards,<br><strong>Abraham Tahbat</strong><br>Lawyer & Software Developer, LAWCOLAB<br>WhatsApp: +2348036622568</p>""",
            },
            # Follow-up
            {
                "name": "Follow-up #1 — After Cold Email",
                "category": "follow_up",
                "subject": "Following Up — LAWCOLAB Free Trial for {{FirmName}}",
                "body_html": """<p>Good day,</p>
<p>I wanted to follow up on my earlier email about LAWCOLAB — I know inboxes get busy!</p>
<p><strong>{{FirmName}}</strong> is exactly the type of firm that gets the most from our platform.</p>
<p>Would you have 15 minutes this week for a quick demo? I can show you exactly how we help {{PracticeArea}} firms in {{City}} work more efficiently.</p>
<p>Book directly: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>Or simply reply with "YES" and I'll reach out to arrange a call.</p>
<p>Warm regards,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Follow-up 2
            {
                "name": "Follow-up #2 — Final Attempt",
                "category": "follow_up",
                "subject": "Last note — LAWCOLAB for {{FirmName}}",
                "body_html": """<p>Good day,</p>
<p>I'll keep this brief — this is my last email to you about LAWCOLAB unless you'd like to hear more.</p>
<p>If now isn't the right time for {{FirmName}}, I completely understand. If you'd ever like to revisit, you can reach me anytime on WhatsApp: +2348036622568</p>
<p>If you ARE interested, here's the link to get started for free: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Wishing {{FirmName}} continued success!</p>
<p>Best,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Support
            {
                "name": "Support — How Can We Help?",
                "category": "support",
                "subject": "How can we help {{FirmName}} today?",
                "body_html": """<p>Dear {{ContactName}},</p>
<p>I hope everything is going well at {{FirmName}}.</p>
<p>I noticed you've been using LAWCOLAB for a while and I wanted to check in — is there anything we can help you with?</p>
<p>Whether it's a technical question, a feature request, or anything else, our team is here for you:</p>
<ul>
  <li>📧 Email: support@lawcolab.com</li>
  <li>💬 WhatsApp: +2348036622568</li>
  <li>🌐 Help Center: {{FreeTrialLink}}</li>
</ul>
<p>We're committed to making sure {{FirmName}} gets the most out of LAWCOLAB.</p>
<p>Best,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB Support</p>""",
            },
            # Renewal
            {
                "name": "Renewal — Subscription Renewal Reminder",
                "category": "renewal",
                "subject": "Your LAWCOLAB subscription is coming up for renewal, {{FirmName}}",
                "body_html": """<p>Dear {{ContactName}},</p>
<p>Your LAWCOLAB subscription for <strong>{{FirmName}}</strong> is coming up for renewal.</p>
<p>We value having you as part of our community. Renew now to continue uninterrupted access to:</p>
<ul>
  <li>✅ Full case and client management</li>
  <li>✅ Invoicing and payment tracking</li>
  <li>✅ Court calendar and deadline alerts</li>
  <li>✅ Client portal and document sharing</li>
  <li>✅ Law Firm Directory listing</li>
</ul>
<p>Renew here: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Any questions? WhatsApp us: +2348036622568</p>
<p>Best,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
            # Re-engagement
            {
                "name": "Re-engagement — We Miss {{FirmName}}",
                "category": "follow_up",
                "subject": "We'd love to reconnect with {{FirmName}} — LAWCOLAB",
                "body_html": """<p>Good day,</p>
<p>We noticed it's been a while since we last connected with {{FirmName}}, and we wanted to reach out.</p>
<p>Since we last spoke, LAWCOLAB has added some exciting features that are particularly useful for {{PracticeArea}} firms in {{City}}:</p>
<ul>
  <li>🆕 Enhanced Law Firm Directory with client reviews</li>
  <li>🆕 AI-powered case analytics</li>
  <li>🆕 Improved billing and payment tracking</li>
  <li>🆕 Multi-team collaboration tools</li>
</ul>
<p>We'd love to show you what's new. Book a 15-minute demo: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>Or explore the updates yourself: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Best,<br><strong>{{SalesRep}}</strong><br>LAWCOLAB</p>""",
            },
        ]

        for t in DEFAULT_TEMPLATES:
            db.session.execute(text("""
                INSERT INTO email_templates (name, category, subject, body_html, is_active, use_count, created_at, updated_at)
                VALUES (:name, :cat, :subj, :body, TRUE, 0, NOW(), NOW())
            """), dict(name=t['name'], cat=t['category'], subj=t['subject'], body=t['body_html']))
        db.session.commit()
        logger.info("Email CRM: seeded %d default templates.", len(DEFAULT_TEMPLATES))
    except Exception as e:
        db.session.rollback()
        logger.debug("Email template seed skipped: %s", str(e)[:120])
