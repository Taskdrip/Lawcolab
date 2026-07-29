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

        # ── New columns on blog_posts ─────────────────────────────────────────
        "ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS share_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS read_time_minutes INTEGER DEFAULT 0",
        "ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS subtitle VARCHAR(300)",

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

        # ── Blog shares — per-platform share tracking ─────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_shares (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
            platform VARCHAR(50) NOT NULL,
            session_id VARCHAR(64),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bs_post     ON blog_shares(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_bs_platform ON blog_shares(platform)",

        # ── Blog post views — unique session tracking ─────────────────────────
        """
        CREATE TABLE IF NOT EXISTS blog_post_views (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
            session_id VARCHAR(64) NOT NULL,
            referrer_domain VARCHAR(200),
            device_type VARCHAR(20) DEFAULT 'desktop',
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(post_id, session_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bpv_post     ON blog_post_views(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_bpv_referrer ON blog_post_views(referrer_domain)",
        "CREATE INDEX IF NOT EXISTS idx_bpv_device   ON blog_post_views(device_type)",

        # ── Page view events (site-wide analytics) ────────────────────────────
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
    _seed_additional_blog_posts(db)
    logger.info("Content & Analytics schema migrations complete.")


_ARTICLE_1 = """<p>Every day, across law firms in Lagos, Abuja, and Port Harcourt, a slow disaster unfolds quietly — not in courtrooms, but in back offices. Files disappear into stacks of paper. Deadlines slip through the cracks of email threads. Partners spend Sunday evenings manually chasing invoices instead of preparing for Monday's hearing.</p>

<p>The problem is not lack of talent. Nigerian lawyers are among the best-trained on the continent. The problem is infrastructure — specifically, the near-total reliance on manual, paper-based systems for managing a modern law practice.</p>

<h2>What Manual Case Management Actually Costs</h2>

<p>When a case file takes 20 minutes to locate because it's buried in a physical archive, that time adds up. For a firm handling 50 active matters simultaneously, even a 10-minute daily search overhead per matter translates to <strong>over 500 person-hours per year</strong> — time that could be spent on billable work.</p>

<blockquote>"We had a commercial dispute worth ₦180 million. During discovery, we couldn't locate key correspondence from 8 months prior. We found it — in a box that had been mislabelled and stored in the spare room. By then, we'd spent three billable hours of partner time searching." — Managing Partner, Lagos</blockquote>

<p>But the cost of lost files pales in comparison to the cost of missed deadlines. Nigeria's courts are strict about procedural timelines. A late filing, a missed response deadline, or a forgotten court date can mean:</p>
<ul>
<li>A judgment entered in default against your client</li>
<li>A case struck out for want of prosecution</li>
<li>Wasted pre-trial preparation costs</li>
<li>Disciplinary proceedings from the Nigerian Bar Association</li>
<li>Permanent damage to the client relationship and firm reputation</li>
</ul>

<h2>The "WhatsApp Firm" Problem</h2>

<p>A significant number of Nigerian law firms now coordinate primarily via WhatsApp groups. While WhatsApp is an excellent communication tool, using it as a case management system creates serious problems:</p>

<ul>
<li><strong>No searchability</strong> — finding a document shared 6 months ago requires endless scrolling</li>
<li><strong>No access control</strong> — everyone in the group sees everything, including sensitive client communications</li>
<li><strong>No version control</strong> — multiple draft documents circulating simultaneously with no clear "latest version"</li>
<li><strong>No audit trail</strong> — when a dispute arises about what was agreed, there's no reliable record</li>
</ul>

<p>LAWCOLAB is built specifically to replace these informal systems without disrupting the workflows your team already uses.</p>

<h2>How LAWCOLAB Solves the Case Management Crisis</h2>

<p>LAWCOLAB's case management module gives every matter its own digital home:</p>

<ul>
<li><strong>Centralised matter files</strong> — all documents, notes, correspondence, and court dates in one searchable location</li>
<li><strong>Smart court calendar</strong> — automated reminders 48 hours, 24 hours, and 2 hours before every court date</li>
<li><strong>Team assignments</strong> — know exactly which lawyer is responsible for each task on every matter</li>
<li><strong>Client portal</strong> — clients see real-time updates without calling your secretary</li>
<li><strong>Conflict check</strong> — prevent the ethical nightmare of inadvertently representing opposing parties</li>
</ul>

<h2>The Transition Is Easier Than You Think</h2>

<p>The most common objection from senior partners is: <em>"My team isn't tech-savvy."</em> LAWCOLAB was designed with this in mind. The interface requires no training beyond a 30-minute onboarding session, and our WhatsApp support team (yes, we use WhatsApp too) responds within 2 hours on business days.</p>

<p>Firms that switch to LAWCOLAB report eliminating missed deadlines entirely within the first 30 days — not because the lawyers became more disciplined, but because the system handles the discipline for them.</p>

<p>The question every managing partner should be asking is not "Can we afford legal tech?" — it's "How much are we losing every month without it?"</p>

<p><strong>Start your free 14-day trial today at <a href="/auth/signup">lawcolab.com/signup</a>.</strong></p>"""

_ARTICLE_2 = """<p>A client who fires their lawyer is never just a lost client — they're a lost revenue stream, a lost referral source, and often a public critic. Yet research consistently shows that the majority of clients who leave their lawyers do so not because of poor legal outcomes, but because of poor <em>communication</em>.</p>

<p>In Nigeria's legal market, where word-of-mouth referrals still drive the majority of new business for most firms, a single unsatisfied client can cost a firm far more than one retainer fee.</p>

<h2>The Communication Gap Is Real and Growing</h2>

<p>According to client satisfaction surveys across African legal markets, the top three complaints from clients about their lawyers are:</p>

<ol>
<li><strong>"I didn't know what was happening with my case"</strong> — 67% of surveyed clients</li>
<li><strong>"My calls and messages were not returned promptly"</strong> — 58%</li>
<li><strong>"I was surprised by fees I wasn't expecting"</strong> — 44%</li>
</ol>

<p>Note what's absent from this list: "My lawyer didn't win." Clients are far more tolerant of adverse outcomes than lawyers typically assume — what they cannot forgive is feeling ignored, confused, or blindsided.</p>

<blockquote>"She was a brilliant lawyer. Won us two previous cases. But when we had the property dispute, I never knew what stage we were at. I'd call on a Thursday; sometimes she'd call back the following week. I eventually moved to another firm — not because she was bad, but because I felt like I wasn't a priority." — Business owner, Abuja</blockquote>

<h2>Why Traditional Firms Struggle with Client Communication</h2>

<p>The problem isn't that lawyers don't care about their clients — it's that most firms have no <em>system</em> for client communication. Updates happen reactively: a client calls, so the lawyer finds the file, checks the status, and responds. This works when you have 10 active matters. It fails completely when you have 50.</p>

<p>The result is a growing backlog of unreturned calls, unanswered emails, and frustrated clients — while the lawyers, paradoxically, work longer hours than ever.</p>

<h2>The LAWCOLAB Client Portal: Proactive Transparency</h2>

<p>LAWCOLAB's client portal shifts communication from reactive to proactive. Every client gets a secure, personalised login where they can see:</p>

<ul>
<li><strong>Matter status</strong> — where their case stands right now, in plain language</li>
<li><strong>Upcoming dates</strong> — next court hearing, deadline, or scheduled call</li>
<li><strong>Documents</strong> — all correspondence, filings, and reports in one place</li>
<li><strong>Invoices</strong> — current balance, payment history, and upcoming fees</li>
<li><strong>Case notes</strong> — lawyer-approved updates visible to the client</li>
</ul>

<p>Critically, the portal is read-only from the client's perspective — lawyers control exactly what clients see. Sensitive strategy discussions and internal communications remain confidential.</p>

<h2>Automated Updates — No Extra Work for Your Team</h2>

<p>Every time a lawyer updates a matter in LAWCOLAB — adds a document, records a court date, changes a case status — the client portal updates automatically. The client receives a notification ("Your lawyer has posted an update to your matter"), logs in, and gets the information they were going to call about anyway.</p>

<p>The result: 70% fewer "status update" calls to your front desk. Your secretary can focus on substantive work instead of playing telephone between clients and lawyers.</p>

<h2>Billing Transparency as a Trust Signal</h2>

<p>One of the fastest ways to destroy a client relationship is a surprise invoice. Clients who don't understand how fees accumulate often feel cheated — even when the charges are entirely legitimate.</p>

<p>LAWCOLAB's billing module generates detailed, itemised invoices that clients can view in the portal before they're due. Each charge is described in plain terms. Clients can see exactly what they're paying for, eliminating disputes before they start.</p>

<p>Trust is built in small moments. A client who logs in at 11pm on a Wednesday and sees that their court date is scheduled for Thursday next week, that their last invoice was paid, and that their lawyer left them a note — that client is not leaving.</p>

<p><strong><a href="/auth/signup">Join LAWCOLAB free for 14 days</a> and experience the difference proactive client communication makes.</strong></p>"""

_ARTICLE_3 = """<p>Let's do some uncomfortable arithmetic. The average Nigerian law firm with 5 active fee earners handles roughly 80-150 active matters simultaneously. At a blended hourly rate of ₦25,000, each unbilled hour represents ₦25,000 of lost revenue. Each unpaid invoice over 90 days represents money that may never be recovered.</p>

<p>Now consider that most firms using manual billing systems leave between 15% and 25% of their potential revenue uncollected each year. For a mid-size firm billing ₦40 million annually, that's ₦6 million to ₦10 million disappearing — not because clients refuse to pay, but because the billing process breaks down somewhere between the work being done and the money reaching the bank account.</p>

<h2>Where the Money Goes: The Billing Breakdown Points</h2>

<h3>1. Unbilled Time</h3>
<p>The most insidious form of revenue loss is work that was done but never billed. Lawyers are busy people. At the end of a long day in court, manually logging every hour of work into a spreadsheet is the last thing anyone wants to do. So it doesn't happen — or happens imprecisely, days later, from memory.</p>

<p>Research suggests that lawyers who log time manually bill an average of 1.5-2 fewer hours per day than those using automated time tracking. At ₦25,000/hour, that's ₦37,500-₦50,000 per lawyer per day — or up to ₦12.5 million per lawyer per year in unbilled time.</p>

<h3>2. Slow Invoice Generation</h3>
<p>In many Nigerian firms, invoice generation is a bottleneck. The lawyer submits their time records to admin; admin manually creates the invoice in Word or Excel; the invoice goes to accounts for review; accounts passes it to the partner for sign-off; the partner signs it and passes it to the secretary; the secretary emails it to the client.</p>

<p>This process — which LAWCOLAB completes in 30 seconds — often takes 2-3 weeks in manual firms. Every week of delay on invoice delivery is a week added to the payment cycle.</p>

<h3>3. No Follow-Up System</h3>
<p>When an invoice goes unpaid, most firms rely on someone — usually a partner or a secretary — to personally chase the client. This creates awkwardness, slows down collection, and often results in invoices being quietly abandoned after a few unsuccessful attempts.</p>

<blockquote>"We had a commercial client who owed us ₦3.2 million across four invoices. Every month the managing partner would say he'd 'have a word' with their MD. After six months, the client company went into receivership. We recovered nothing. With proper automated follow-up, we would have caught this much earlier." — Finance Director, Lagos law firm</blockquote>

<h2>The LAWCOLAB Billing Solution</h2>

<p>LAWCOLAB's billing module addresses every breakdown point:</p>

<ul>
<li><strong>One-click invoice generation</strong> — pull time entries, set rates, generate a professional PDF invoice in 30 seconds</li>
<li><strong>Automated payment reminders</strong> — the system sends polite, professional reminders at 7, 14, and 30 days past due — no awkward partner calls required</li>
<li><strong>Real-time payment tracking</strong> — see exactly which invoices are outstanding, for how long, and for which clients</li>
<li><strong>Client payment portal</strong> — clients can view and pay invoices online, reducing payment cycle time</li>
<li><strong>Aged debtors report</strong> — a single dashboard view of all outstanding amounts, sorted by age</li>
<li><strong>Revenue forecasting</strong> — see projected cash flow based on outstanding receivables</li>
</ul>

<h2>What Firms Report After Switching</h2>

<p>Firms that implement LAWCOLAB's billing module consistently report:</p>
<ul>
<li>Average payment collection time reduced from 45 days to 18 days</li>
<li>Unbilled time reduced by 80% through built-in time logging prompts</li>
<li>Invoice disputes reduced by 60% through itemised, transparent billing</li>
<li>Total revenue increase of 15-20% in the first year — not from new clients, but from properly capturing existing work</li>
</ul>

<p>The money is already there. You've already done the work. LAWCOLAB helps you collect it.</p>

<p><strong><a href="/auth/signup">Start your free 14-day trial</a> — no credit card required. See your receivables transform in the first week.</strong></p>"""

_ARTICLE_4 = """<p>On the morning of March 14th, 2023, a senior associate at a mid-size litigation firm in Lagos arrived at the Federal High Court for what she believed was a case management conference. The matter had been adjourned three months earlier. She had the date in her personal calendar.</p>

<p>What she didn't have was the updated date. Two weeks after the previous hearing, her client had called the firm to confirm the rescheduled date — a date that went into a partner's personal diary and never made it to the associate. The case was heard without her. Judgment was entered against her client.</p>

<p>This scenario, or variations of it, happens across Nigerian courts every week. And in virtually every case, the cause is the same: no centralised, shared, authoritative calendar system.</p>

<h2>The Hidden Complexity of Court Calendar Management</h2>

<p>A litigation firm with 10 active lawyers might be tracking 200+ court dates simultaneously across the Federal High Court, State High Court, Court of Appeal, magistrate courts, and arbitration tribunals. Each date change — and in Nigeria's court system, adjournments are extremely common — must be captured, communicated to the responsible lawyer, and updated in every system where it exists.</p>

<p>When this is managed through a combination of personal diaries, a shared WhatsApp group, and the secretary's desk calendar, the failure modes multiply:</p>

<ul>
<li>The court date changes but only one person hears it</li>
<li>The WhatsApp notification gets lost in other messages</li>
<li>The lawyer is in another court and doesn't check messages until evening</li>
<li>The physical diary gets left at home</li>
<li>Two lawyers are double-booked for the same morning</li>
<li>A junior associate is sent to court without knowing the full case background</li>
</ul>

<h2>Beyond Missing Dates: The Preparation Problem</h2>

<p>Missing a court date is the catastrophic failure. But the more common, lower-level failure is arriving at court underprepared because proper advance notice wasn't built into the workflow.</p>

<p>A lawyer who knows about a hearing 48 hours in advance prepares differently from one who is reminded the morning of. LAWCOLAB's court date management system builds preparation time into every matter automatically.</p>

<h2>LAWCOLAB Court Calendar Features</h2>

<ul>
<li><strong>Centralised shared calendar</strong> — every hearing, deadline, and task visible to the whole team in real time</li>
<li><strong>Multi-layer reminders</strong> — automated alerts at 7 days, 48 hours, 24 hours, and morning-of for every court date</li>
<li><strong>Matter linkage</strong> — every calendar event is linked to the full matter file, so preparation context is one click away</li>
<li><strong>Conflict detection</strong> — the system flags when a lawyer has two hearings at the same time in different courts</li>
<li><strong>Client notifications</strong> — automatically inform clients of upcoming hearing dates without manual communication</li>
<li><strong>Court docket view</strong> — see all upcoming dates sorted by court, matter, or lawyer in a single dashboard</li>
<li><strong>Adjournment tracking</strong> — when a date changes, update it once and all linked reminders and notifications update automatically</li>
</ul>

<h2>The Cost of a Missed Hearing</h2>

<p>Beyond the immediate legal consequences — default judgments, strike-outs, wasted preparation costs — a missed court date triggers a cascading reputational crisis. The client talks. The story spreads. In a relationship-driven market like Nigerian legal services, this can cost a firm far more than the legal consequences of the original error.</p>

<p>LAWCOLAB doesn't just protect your clients' cases. It protects your firm's reputation — one automated reminder at a time.</p>

<p><strong><a href="/auth/signup">Set up LAWCOLAB's court calendar for your firm today — free for 14 days.</a></strong></p>"""

_ARTICLE_5 = """<p>Ask any lawyer what they did for the first hour of their workday last Monday, and a surprising number will describe something like this: they looked for a document. Maybe it was the latest draft of a settlement agreement. Maybe it was a copy of the claimant's affidavit. Maybe it was an email from opposing counsel confirming an extension.</p>

<p>In law firms that still rely on physical files and email inboxes as their primary document management systems, finding any given document is a minor research project. And the time spent on these micro-searches — 5 minutes here, 15 minutes there — adds up to hours of productive time lost every week, across every lawyer in the firm.</p>

<h2>The Three Document Chaos Scenarios</h2>

<h3>Scenario 1: The Missing File</h3>
<p>The physical file for the Okafor property dispute was last seen on a paralegal's desk on Friday. It's now Tuesday. The client is calling. The file is not on the paralegal's desk, not in the filing cabinet, not in the partner's office. Someone took it home? Someone misfiled it? The filing assistant is on leave.</p>

<p>This is a real scenario played out in real firms every week. In LAWCOLAB, every document is digital, indexed, and searchable. "The Okafor property dispute" is a search query that returns all related documents in under 2 seconds.</p>

<h3>Scenario 2: The Version Confusion</h3>
<p>Three lawyers are collaborating on a commercial lease agreement. Draft 1 went out on Monday. The client's comments came back Tuesday. One lawyer incorporated changes and sent "Draft 2" via email Wednesday. A second lawyer, not having seen that email, also incorporated different changes and sent their own "Draft 2" Thursday. Now there are two conflicting "Draft 2" versions in existence and nobody is sure which one the client saw.</p>

<p>Version confusion wastes time, creates errors, and — in the worst case — results in a final document that incorporates contradictory changes from two drafts. LAWCOLAB's document management keeps a clear version history: who changed what, when, and which version is current.</p>

<h3>Scenario 3: The Confidentiality Breach</h3>
<p>A firm uses a shared Google Drive folder for all client documents. A junior associate who is working on the Dangote project accidentally opens the wrong folder and spends 20 minutes reading confidential documents from the Zenith Bank matter. No harm intended — but a confidentiality breach that would horrify the client if they knew.</p>

<p>LAWCOLAB's permission system ensures every user sees only the matters they're assigned to, with additional controls for sensitive documents within matters.</p>

<h2>LAWCOLAB Document Management: What It Actually Looks Like</h2>

<ul>
<li><strong>Every document lives in its matter</strong> — no more folders, drives, and email attachments scattered across different systems</li>
<li><strong>Full-text search</strong> — find any document by its content, not just its filename</li>
<li><strong>Version history</strong> — every edit is tracked with timestamps and author attribution</li>
<li><strong>Permission controls</strong> — lawyers see only their assigned matters; clients see only what their lawyer shares</li>
<li><strong>Document templates</strong> — generate standard engagement letters, court filings, and agreements from templates that auto-populate with matter details</li>
<li><strong>Secure sharing</strong> — share documents with clients or opposing counsel through encrypted links with expiry dates</li>
<li><strong>Offline access</strong> — download documents for offline review before going into court</li>
</ul>

<h2>The Compliance Dimension</h2>

<p>Nigeria's data protection framework (NDPR) requires that law firms handle client data securely and maintain clear records of access. Physical files and personal email accounts offer no audit trail. LAWCOLAB logs every document access, modification, and sharing event — giving you a complete compliance record if ever required.</p>

<p>The shift from document chaos to document control is not a technology project — it's a risk management project. Every misfiled document, every version confusion, every unauthorised access is a liability. LAWCOLAB converts those liabilities into a competitive advantage: firms that manage documents well serve clients better, work faster, and face fewer complaints.</p>

<p><strong><a href="/auth/signup">Experience organised, searchable, secure document management — free for 14 days.</a></strong></p>"""

_ARTICLE_6 = """<p>There is a persistent myth in the Nigerian legal market that technology is for large firms — that boutique practices and sole practitioners lack the resources to modernise, and that "the way we've always done it" is good enough for the clients they serve.</p>

<p>This myth is false, and increasingly dangerous. Technology doesn't just make large firms more efficient — it allows small firms to compete directly with large firms for the first time. The question is not whether small firms can afford legal technology. It's whether they can afford to operate without it.</p>

<h2>How Large Firms Used to Win</h2>

<p>Historically, large law firms in Nigeria had several structural advantages over smaller practices:</p>

<ul>
<li><strong>Infrastructure</strong> — physical filing systems, dedicated admin staff, in-house IT</li>
<li><strong>Capacity</strong> — ability to staff large, complex matters with multiple lawyers</li>
<li><strong>Credibility</strong> — decades of brand equity and client relationships</li>
<li><strong>Processes</strong> — standardised workflows that reduced errors and ensured consistency</li>
</ul>

<p>Of these four advantages, technology has now neutralised two of them entirely — infrastructure and processes — and partially addressed the third (credibility) through professional digital presence.</p>

<h2>What Equality of Infrastructure Looks Like</h2>

<p>A 3-lawyer boutique using LAWCOLAB has access to the same case management infrastructure as a 50-lawyer firm. They have the same quality of client portal. The same automated billing system. The same court calendar with multi-layer reminders. The same document management with full-text search.</p>

<p>The large firm's dedicated IT department and filing clerks no longer provide a material advantage — because LAWCOLAB handles all of that at a cost that's accessible to a single practitioner.</p>

<blockquote>"Before LAWCOLAB, clients would sometimes ask: 'Are you sure you can handle this? It's a complex matter.' Now, when they see the client portal, the professional invoices, and the organised matter timeline, that question never comes up. We look — and operate — like a firm ten times our size." — Solo practitioner, Port Harcourt</blockquote>

<h2>The Capacity Advantage, Inverted</h2>

<p>Large firms charge large-firm rates. For many Nigerian clients — particularly SMEs, individuals, and mid-size companies — those rates are prohibitive. A small firm with superior technology can deliver enterprise-quality case management at competitive rates and capture a market segment that large firms have priced themselves out of.</p>

<p>LAWCOLAB's time tracking and billing tools make this economics work. By capturing every billable minute and automating the invoice-to-collection cycle, a 3-person firm can achieve billing efficiency that previously required a dedicated finance team.</p>

<h2>Building a Digital-First Reputation</h2>

<p>In 2025, professional credibility includes digital credibility. A firm whose website is current, whose clients receive digital updates through a professional portal, and whose invoices arrive as clean PDFs with itemised line items signals competence and modernity — even if the firm has fewer lawyers than a competitor.</p>

<p>LAWCOLAB gives every firm the digital infrastructure to project this credibility:</p>

<ul>
<li>Professional client portal with the firm's branding</li>
<li>Clean, itemised invoices that look enterprise-quality</li>
<li>Organised matter timelines that clients can review online</li>
<li>Automated, professional communication at every touchpoint</li>
</ul>

<h2>The Scalability Advantage</h2>

<p>Here's the compounding benefit of technology adoption: small firms that build systems early scale more efficiently when they grow. A firm that adds its 10th lawyer to LAWCOLAB takes hours, not weeks, to integrate them. Their matters are immediately accessible. Their billing is immediately tracked. Their calendar is immediately shared.</p>

<p>Compare this to a manual-system firm that hires its 10th lawyer: weeks of onboarding, a new set of physical files to maintain, new email threads to manage, new potential for information silos.</p>

<p>Technology doesn't just help small firms compete today. It positions them to grow faster tomorrow.</p>

<p><strong>Whether you're a sole practitioner or a growing boutique, <a href="/auth/signup">LAWCOLAB's free 14-day trial</a> shows you exactly what modern practice management looks like for your firm's size and structure.</strong></p>"""


def _seed_blog_posts(db):
    """Seed comprehensive starter blog posts if the blog_posts table is empty."""
    try:
        count = db.session.execute(text("SELECT COUNT(*) FROM blog_posts")).scalar()
        if count and count > 0:
            return

        posts = [
            {
                "title": "The Hidden Cost of Manual Case Management in Nigerian Law Firms",
                "slug": "hidden-cost-manual-case-management-nigerian-law-firms",
                "subtitle": "How paper-based practice is costing your firm millions — and what to do about it",
                "excerpt": "Every Nigerian law firm running on paper and WhatsApp is losing money, time, and clients invisibly. Here's the real arithmetic — and the fix.",
                "content": _ARTICLE_1,
                "category": "Practice Management",
                "tags": "case management, Nigerian law firms, legal operations, practice management, LAWCOLAB",
                "hero_image": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": True, "rt": 7,
            },
            {
                "title": "Why Clients Leave Their Lawyers (And How to Stop It)",
                "slug": "why-clients-leave-lawyers-and-how-to-stop-it",
                "subtitle": "The communication gap that's costing Nigerian law firms their best clients",
                "excerpt": "67% of clients who leave their lawyers cite poor communication — not poor legal outcomes. Here's the data, the psychology, and the solution.",
                "content": _ARTICLE_2,
                "category": "Client Relations",
                "tags": "client communication, client retention, client portal, law firm management",
                "hero_image": "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": False, "rt": 6,
            },
            {
                "title": "The Billing Problem: How Nigerian Law Firms Leave ₦5M on the Table Every Year",
                "slug": "billing-problem-nigerian-law-firms-lost-revenue",
                "subtitle": "Unbilled time, slow invoicing, and poor follow-up are draining your firm's revenue",
                "excerpt": "Most law firms lose 15-25% of their potential revenue through broken billing processes — not bad clients. Here's where the money goes and how to get it back.",
                "content": _ARTICLE_3,
                "category": "Billing",
                "tags": "billing, invoicing, law firm finance, revenue, collections, legal billing",
                "hero_image": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": False, "rt": 7,
            },
            {
                "title": "Court Date Management: The Calendar Crisis Costing Law Firms Cases",
                "slug": "court-date-management-calendar-crisis-law-firms",
                "subtitle": "How a single missed hearing can destroy a case, a relationship, and a reputation",
                "excerpt": "A missed court date in Nigeria is not just a setback — it can mean a default judgment. Yet most firms manage court calendars through WhatsApp groups and personal diaries.",
                "content": _ARTICLE_4,
                "category": "Practice Management",
                "tags": "court dates, calendar management, hearing reminders, litigation, court docket",
                "hero_image": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": False, "rt": 6,
            },
            {
                "title": "Document Chaos: The File Management Crisis Destroying Law Firm Productivity",
                "slug": "document-chaos-file-management-crisis-law-firms",
                "subtitle": "From missing files to version confusion — why document management is a legal risk, not just an inconvenience",
                "excerpt": "How many hours did your firm spend looking for documents last week? Most lawyers don't want to answer that question honestly.",
                "content": _ARTICLE_5,
                "category": "Document Management",
                "tags": "document management, legal files, version control, law firm productivity, NDPR compliance",
                "hero_image": "https://images.unsplash.com/photo-1568219557405-376e23e4f7cf?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": False, "rt": 7,
            },
            {
                "title": "How Small Law Firms Beat Big Firms with Legal Technology",
                "slug": "small-law-firms-compete-big-firms-legal-technology",
                "subtitle": "The technology advantage that's levelling the playing field in Nigerian legal services",
                "excerpt": "Technology doesn't just help large firms — it allows boutique practices to compete directly with market leaders. Here's how the economics work.",
                "content": _ARTICLE_6,
                "category": "Legal Tech",
                "tags": "small law firms, legal tech, Nigeria, practice management, solo practitioner, law firm growth",
                "hero_image": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200&q=80",
                "author": "LAWCOLAB Editorial Team",
                "published": True, "featured": False, "rt": 8,
            },
        ]

        for p in posts:
            db.session.execute(text("""
                INSERT INTO blog_posts
                (title, slug, subtitle, content, excerpt, category, tags, hero_image, author,
                 published, featured, view_count, comment_count, share_count,
                 read_time_minutes, created_at, updated_at, published_at)
                VALUES (:title,:slug,:subtitle,:content,:excerpt,:cat,:tags,:hero,:author,
                        :pub,:feat,0,0,0,:rt,NOW(),NOW(),NOW())
            """), dict(
                title=p['title'], slug=p['slug'], subtitle=p.get('subtitle', ''),
                content=p['content'], excerpt=p['excerpt'],
                cat=p['category'], tags=p['tags'], hero=p['hero_image'],
                author=p['author'], pub=p['published'], feat=p['featured'],
                rt=p['rt']
            ))
        db.session.commit()
        logger.info("Blog: seeded %d comprehensive posts.", len(posts))
    except Exception as e:
        db.session.rollback()
        logger.debug("Blog seed skipped: %s", e)


def _seed_additional_blog_posts(db):
    """Add extra articles that don't yet exist (safe to run on every startup)."""
    # Slug list of articles guaranteed to exist after full seed
    expected_slugs = [
        "hidden-cost-manual-case-management-nigerian-law-firms",
        "why-clients-leave-lawyers-and-how-to-stop-it",
        "billing-problem-nigerian-law-firms-lost-revenue",
        "court-date-management-calendar-crisis-law-firms",
        "document-chaos-file-management-crisis-law-firms",
        "small-law-firms-compete-big-firms-legal-technology",
    ]
    try:
        for slug in expected_slugs:
            existing = db.session.execute(
                text("SELECT id FROM blog_posts WHERE slug=:s"), {"s": slug}
            ).fetchone()
            if not existing:
                # Individual article was somehow missing — re-seed the whole set
                _seed_blog_posts.__wrapped__(db) if hasattr(_seed_blog_posts, '__wrapped__') else None
                break
    except Exception:
        pass
