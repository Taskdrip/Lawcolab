"""
Content & Analytics schema migrations — blog + page view tracking.
Idempotent — safe to run on every startup.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_content_migrations(db):
    migrations = [
        # ── Blog posts ────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            content TEXT NOT NULL,
            excerpt VARCHAR(500),
            category VARCHAR(100) DEFAULT 'Legal Tech',
            tags TEXT,
            hero_image VARCHAR(600),
            author VARCHAR(200) DEFAULT 'LAWCOLAB Team',
            published BOOLEAN NOT NULL DEFAULT FALSE,
            featured BOOLEAN NOT NULL DEFAULT FALSE,
            view_count INTEGER NOT NULL DEFAULT 0,
            comment_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            published_at TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bp_slug      ON blog_posts(slug)",
        "CREATE INDEX IF NOT EXISTS idx_bp_published ON blog_posts(published, published_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_bp_category  ON blog_posts(category)",
        "CREATE INDEX IF NOT EXISTS idx_bp_featured  ON blog_posts(featured)",

        # ── Blog comments ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(200),
            content TEXT NOT NULL,
            approved BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bc_post ON blog_comments(post_id, approved)",

        # ── Blog likes ────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_likes (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
            session_id VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(post_id, session_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bl_post ON blog_likes(post_id)",

        # ── Page view events ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS page_view_events (
            id SERIAL PRIMARY KEY,
            path VARCHAR(500) NOT NULL,
            session_id VARCHAR(64),
            referrer VARCHAR(500),
            referrer_domain VARCHAR(100),
            ip_address VARCHAR(45),
            user_agent VARCHAR(500),
            device_type VARCHAR(20) DEFAULT 'desktop',
            browser VARCHAR(50),
            country VARCHAR(80),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pve_created  ON page_view_events(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_pve_session  ON page_view_events(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_pve_path     ON page_view_events(path)",
        "CREATE INDEX IF NOT EXISTS idx_pve_device   ON page_view_events(device_type)",
        "CREATE INDEX IF NOT EXISTS idx_pve_country  ON page_view_events(country)",
    ]

    for sql in migrations:
        try:
            db.session.execute(text(sql.strip()))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.debug("Content migration skipped: %s", str(e)[:120])

    _seed_blog_posts(db)
    logger.info("Content & Analytics schema migrations complete.")


def _seed_blog_posts(db):
    """Seed 3 starter blog posts if the table is empty."""
    try:
        count = db.session.execute(text("SELECT COUNT(*) FROM blog_posts")).scalar()
        if count and count > 0:
            return

        posts = [
            {
                "title": "How Nigerian Law Firms Are Embracing Legal Tech in 2025",
                "slug": "nigerian-law-firms-legal-tech-2025",
                "excerpt": "A new wave of technology is reshaping legal practice in Nigeria. Discover the tools top firms are using to work smarter.",
                "content": """<p>The legal industry in Nigeria is undergoing a quiet revolution. While courtrooms remain traditional, the back offices of leading law firms are increasingly powered by software that automates billing, tracks cases, and gives clients real-time updates.</p>

<h2>The Challenge of Paper-Based Practice</h2>
<p>For decades, Nigerian law firms have relied on paper files, manual invoicing, and email chains to manage their work. The result? Missed court dates, unpaid invoices, and frustrated clients. A partner at a Lagos firm recently told us: <em>"We had a case file go missing for two weeks. The client was furious. That's when we knew we needed a system."</em></p>

<h2>What Modern Practice Management Looks Like</h2>
<p>Platforms like <strong>LAWCOLAB</strong> centralise every aspect of a law firm's operations:</p>
<ul>
<li><strong>Case Management</strong> — all files, notes, and deadlines in one searchable hub</li>
<li><strong>Automated Billing</strong> — generate and track invoices in seconds</li>
<li><strong>Court Calendar</strong> — smart alerts 48 hours before every hearing</li>
<li><strong>Client Portal</strong> — 24/7 secure access for clients to track their cases</li>
</ul>

<h2>The Results Are Real</h2>
<p>Firms using LAWCOLAB report a 40% reduction in administrative time, allowing lawyers to take on more cases without hiring additional staff. For small and mid-size firms competing with larger practices, this efficiency advantage is transformational.</p>

<h2>Getting Started</h2>
<p>The barrier to adoption is lower than ever. LAWCOLAB offers a <a href="/auth/signup">14-day free trial</a> — no credit card required. Set up takes under 30 minutes, and our team provides onboarding support via WhatsApp.</p>

<p>The question for Nigerian law firms is no longer <em>whether</em> to adopt legal tech — it's <em>how quickly</em>.</p>""",
                "category": "Legal Tech",
                "tags": "Nigeria, law firm software, legal tech, case management",
                "hero_image": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1200&q=80",
                "author": "Abraham Tahbat",
                "published": True, "featured": True,
            },
            {
                "title": "5 Signs Your Law Firm Needs Practice Management Software",
                "slug": "5-signs-law-firm-needs-practice-management-software",
                "excerpt": "Missing deadlines, lost files, unpaid invoices — if these sound familiar, it may be time to upgrade your firm's operations.",
                "content": """<p>Running a law firm is demanding. Between court appearances, client meetings, and legal research, administrative tasks often fall through the cracks. Here are five clear signs that your firm is ready for practice management software.</p>

<h2>1. You've Missed a Deadline</h2>
<p>A missed court date or filing deadline is every lawyer's nightmare. If you're relying on a personal calendar or a shared spreadsheet, the risk is real. Practice management software centralises all deadlines with automated reminders — giving you 48-hour, 24-hour, and morning-of alerts.</p>

<h2>2. Invoices Are Sitting Unpaid for Months</h2>
<p>Cash flow is the lifeblood of any firm. If you're chasing clients for payments weeks after issuing invoices, it's time to automate. LAWCOLAB generates professional invoices in seconds and tracks every payment, partial payment, and outstanding balance.</p>

<h2>3. Clients Are Asking "What's the Status?"</h2>
<p>When clients call or WhatsApp you to ask for updates on their case, it's a sign they lack visibility — and trust. A client portal solves this immediately, giving clients 24/7 read-only access to their case notes, documents, and next court date.</p>

<h2>4. Files Are Scattered Across Email, WhatsApp, and USB Drives</h2>
<p>Document chaos slows every aspect of legal work. A centralised document management system ensures every file is tagged, searchable, and backed up securely.</p>

<h2>5. You Can't See Your Firm's Performance at a Glance</h2>
<p>How many active cases do you have? Which lawyers are handling the most? What's the firm's revenue this month? If you need to compile a spreadsheet to answer these questions, you're working blind. Real-time dashboards put this data at your fingertips.</p>

<p><strong>Ready to transform your practice?</strong> <a href="/auth/signup">Start your free 14-day LAWCOLAB trial today</a>.</p>""",
                "category": "Practice Management",
                "tags": "practice management, law firm tips, productivity, billing",
                "hero_image": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&q=80",
                "author": "LAWCOLAB Team",
                "published": True, "featured": False,
            },
            {
                "title": "Understanding the Nigerian Law Firm Directory: A Guide for Clients",
                "slug": "nigerian-law-firm-directory-guide-clients",
                "excerpt": "Finding the right lawyer in Nigeria just got easier. Here's how the LAWCOLAB Law Firm Directory helps clients connect with qualified legal professionals.",
                "content": """<p>Finding a qualified lawyer in Nigeria has traditionally been a word-of-mouth exercise — you ask a friend, a colleague, or your bank manager. The LAWCOLAB Law Firm Directory changes that by bringing verified Nigerian law firms online in a searchable, transparent format.</p>

<h2>What Is the LAWCOLAB Directory?</h2>
<p>The LAWCOLAB Law Firm Directory is Nigeria's most comprehensive online listing of law firms — think Google My Business, but specifically built for the legal sector. Every listing includes:</p>
<ul>
<li>Firm name, address, and contact details</li>
<li>Practice areas (corporate, litigation, family law, property, etc.)</li>
<li>Verification status (⭐ verified firms are confirmed active practices)</li>
<li>Client reviews and ratings</li>
<li>Direct contact options</li>
</ul>

<h2>How to Find the Right Lawyer</h2>
<p>Visit <a href="/directory">lawcolab.com/directory</a> and use the filters to narrow by:</p>
<ul>
<li><strong>Location</strong> — Lagos, Abuja, Port Harcourt, and all 36 states</li>
<li><strong>Practice Area</strong> — corporate law, criminal, family, property, IP, and more</li>
<li><strong>Verification</strong> — show only verified firms</li>
</ul>

<h2>For Law Firms: Claim Your Listing</h2>
<p>Is your firm already in our directory but you haven't claimed it? Claiming your listing takes 5 minutes and gives you full control over your profile, photos, practice areas, and contact information. <a href="/directory">Browse the directory</a> to find your firm and click "Claim This Listing".</p>

<p>Or <a href="/auth/signup">create a LAWCOLAB account</a> to set up your firm's full practice management suite — and get a premium directory listing included free.</p>""",
                "category": "Directory",
                "tags": "law firm directory Nigeria, find a lawyer Nigeria, legal directory",
                "hero_image": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=1200&q=80",
                "author": "LAWCOLAB Team",
                "published": True, "featured": False,
            },
        ]

        for p in posts:
            db.session.execute(text("""
                INSERT INTO blog_posts
                (title, slug, content, excerpt, category, tags, hero_image, author,
                 published, featured, view_count, comment_count, created_at, updated_at, published_at)
                VALUES (:title,:slug,:content,:excerpt,:cat,:tags,:hero,:author,
                        :pub,:feat,0,0,NOW(),NOW(),NOW())
            """), dict(
                title=p['title'], slug=p['slug'], content=p['content'],
                excerpt=p['excerpt'], cat=p['category'], tags=p['tags'],
                hero=p['hero_image'], author=p['author'],
                pub=p['published'], feat=p['featured']
            ))
        db.session.commit()
        logger.info("Blog: seeded %d starter posts.", len(posts))
    except Exception as e:
        db.session.rollback()
        logger.debug("Blog seed skipped: %s", e)
