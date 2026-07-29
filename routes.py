from flask import session, render_template, redirect, url_for, send_from_directory, make_response, request, flash
from flask_login import current_user
from app import app, db
from models import User, LawFirm, Project, ProjectAssignment
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

# Import blueprint modules
from auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.admin import admin_bp
from blueprints.clients import clients_bp
from blueprints.projects import projects_bp
from blueprints.team import team_bp
from blueprints.public import public_bp
from blueprints.chat import chat_bp
from blueprints.superadmin import superadmin_bp
from blueprints.enhanced_chat import enhanced_chat_bp
from blueprints.support_requests import support_bp

# Import invoice blueprints
from blueprints.invoices.routes import invoices_bp
from blueprints.invoice_chat.routes import invoice_chat_bp

# Import sales blueprint
from blueprints.sales import sales_bp

# Import showcase blueprint
from blueprints.showcase import showcase_bp
from blueprints.showcase_profile import showcase_profile_bp
from blueprints.directory import directory_bp
from blueprints.directory_admin import dir_admin_bp

# Import payment management blueprints
from blueprints.payment_management import payment_mgmt_bp
from blueprints.escrow_public import escrow_bp
from simple_checkout import simple_checkout_bp

# Import calendar blueprint
from blueprints.calendar import calendar_bp

# Import CRM & social communities blueprints
from blueprints.crm import crm_bp
from blueprints.social_communities import social_communities_bp

# Import claim blueprint
from blueprints.claim import claim_bp

# Import Email CRM blueprint
from blueprints.email_crm import email_crm_bp

# Import payment models
import models_payment  # noqa: F401

# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(clients_bp, url_prefix="/clients")
app.register_blueprint(projects_bp, url_prefix="/projects")
app.register_blueprint(team_bp, url_prefix="/team")
app.register_blueprint(public_bp, url_prefix="/public")
app.register_blueprint(chat_bp, url_prefix="/chat")
app.register_blueprint(superadmin_bp, url_prefix="/superadmin")
app.register_blueprint(support_bp, url_prefix="/support")
app.register_blueprint(enhanced_chat_bp, url_prefix='/enhanced-chat')
app.register_blueprint(invoices_bp, url_prefix="/invoices")
app.register_blueprint(invoice_chat_bp, url_prefix="/invoice-chat")
app.register_blueprint(sales_bp, url_prefix="/sales")
app.register_blueprint(showcase_bp, url_prefix="/showcase")
app.register_blueprint(showcase_profile_bp, url_prefix="/showcase-profile")
app.register_blueprint(directory_bp, url_prefix="/directory")
app.register_blueprint(dir_admin_bp, url_prefix="/superadmin/directory")
app.register_blueprint(payment_mgmt_bp)  # Payment management
app.register_blueprint(escrow_bp)  # Escrow system
app.register_blueprint(simple_checkout_bp, url_prefix="/payment")  # Simple payment checkout
app.register_blueprint(calendar_bp, url_prefix="/calendar")  # Calendar & scheduling
app.register_blueprint(crm_bp, url_prefix="/superadmin/crm")  # CRM
app.register_blueprint(social_communities_bp, url_prefix="/superadmin/crm/communities")  # Social communities CRM
app.register_blueprint(claim_bp, url_prefix="/directory/claim")  # Listing claim flow
app.register_blueprint(email_crm_bp, url_prefix="/superadmin/crm/email")  # Email CRM

# Import & register blog blueprint
from blueprints.blog import blog_bp
app.register_blueprint(blog_bp, url_prefix="/blog")  # Public blog & news

# Import & register SEO analytics blueprint
from blueprints.seo_analytics import seo_analytics_bp
app.register_blueprint(seo_analytics_bp, url_prefix="/superadmin/analytics")  # SEO & Analytics dashboard


# ── Page analytics helpers ──────────────────────────────────────────────────
def _detect_device(ua: str) -> str:
    u = ua.lower()
    if any(x in u for x in ['ipad', 'tablet', 'kindle', 'playbook']):
        return 'tablet'
    if any(x in u for x in ['mobile', 'android', 'iphone', 'ipod', 'blackberry',
                             'windows phone', 'opera mini', 'fennec']):
        return 'mobile'
    return 'desktop'

def _detect_browser(ua: str) -> str:
    u = ua.lower()
    if 'edg/' in u or 'edge/' in u:
        return 'Edge'
    if 'opr/' in u or 'opera' in u:
        return 'Opera'
    if 'chrome/' in u and 'chromium' not in u:
        return 'Chrome'
    if 'firefox/' in u:
        return 'Firefox'
    if 'safari/' in u and 'chrome' not in u:
        return 'Safari'
    if 'msie' in u or 'trident' in u:
        return 'IE'
    return 'Other'

def _detect_os(ua: str) -> str:
    u = ua.lower()
    if 'windows' in u:
        return 'Windows'
    if 'macintosh' in u or 'mac os' in u:
        return 'macOS'
    if 'iphone' in u or 'ipad' in u:
        return 'iOS'
    if 'android' in u:
        return 'Android'
    if 'linux' in u:
        return 'Linux'
    return 'Other'

import hashlib as _hashlib
import secrets as _secrets

_TRACK_SKIP_PREFIXES = ('/static', '/superadmin', '/favicon', '/__', '/admin',
                         '/auth/logout', '/track')
_TRACK_SKIP_EXTS = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico',
                    '.svg', '.woff', '.woff2', '.ttf', '.map', '.json')

def _should_track(path: str) -> bool:
    for p in _TRACK_SKIP_PREFIXES:
        if path.startswith(p):
            return False
    for e in _TRACK_SKIP_EXTS:
        if path.endswith(e):
            return False
    return True


# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True


@app.before_request
def track_page_view():
    """Log every public GET page view to page_analytics (fire-and-forget)."""
    if request.method != 'GET':
        return
    path = request.path
    if not _should_track(path):
        return
    try:
        from sqlalchemy import text as _text
        ua = request.headers.get('User-Agent', '')
        # Stable session cookie (set in response via after_request)
        sid = request.cookies.get('_lc_sid') or _secrets.token_hex(16)
        session['_lc_sid_pending'] = sid
        ip_raw = (request.headers.get('X-Forwarded-For') or
                  request.headers.get('X-Real-IP') or
                  request.remote_addr or '')
        ip = ip_raw.split(',')[0].strip()
        ip_hash = _hashlib.sha256(ip.encode()).hexdigest()[:32]
        referrer = (request.referrer or '')[:400]
        device  = _detect_device(ua)
        browser = _detect_browser(ua)
        os_name = _detect_os(ua)
        db.session.execute(_text("""
            INSERT INTO page_analytics
                (session_id, page_path, referrer, ip_hash, device_type, browser, os_name, created_at)
            VALUES (:sid, :path, :ref, :ip, :dev, :br, :os, NOW())
        """), dict(sid=sid, path=path[:400], ref=referrer, ip=ip_hash,
                   dev=device, br=browser, os=os_name))
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


@app.after_request
def set_analytics_cookie(response):
    """Persist session cookie so visits are correctly de-duplicated."""
    sid = session.pop('_lc_sid_pending', None)
    if sid and not request.cookies.get('_lc_sid'):
        response.set_cookie('_lc_sid', sid, max_age=365 * 86400,
                            samesite='Lax', httponly=True)
    return response

@app.route('/robots.txt')
def robots_txt():
    """SEO: robots.txt — allow all, point to sitemap."""
    content = """User-agent: *
Allow: /
Disallow: /superadmin/
Disallow: /admin/
Disallow: /auth/
Disallow: /dashboard/
Disallow: /clients/
Disallow: /invoices/
Disallow: /team/
Disallow: /projects/
Disallow: /chat/
Disallow: /payment/
Disallow: /calendar/
Disallow: /superadmin/crm/

Sitemap: https://lawcolab.com/sitemap.xml
"""
    return make_response(content, 200, {'Content-Type': 'text/plain; charset=utf-8'})


@app.route('/sitemap.xml')
def sitemap_xml():
    """SEO: XML sitemap for all public pages."""
    from datetime import date as _date
    base = 'https://lawcolab.com'
    today = _date.today().isoformat()

    # Static public pages
    static_pages = [
        ('/', '1.0', 'weekly'),
        ('/pricing', '0.9', 'monthly'),
        ('/directory', '0.9', 'daily'),
        ('/blog', '0.9', 'daily'),
        ('/about', '0.7', 'monthly'),
        ('/contact', '0.7', 'monthly'),
        ('/auth/signup', '0.8', 'monthly'),
        ('/auth/login',  '0.6', 'monthly'),
    ]
    urls = []
    for path, priority, freq in static_pages:
        urls.append(f"""  <url>
    <loc>{base}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    # Blog posts
    try:
        from sqlalchemy import text as _text
        rows = db.session.execute(
            _text("SELECT slug, updated_at FROM blog_posts WHERE published=TRUE ORDER BY published_at DESC LIMIT 200")
        ).fetchall()
        for row in rows:
            slug = row[0]
            mod  = (row[1].date().isoformat() if row[1] else today)
            urls.append(f"""  <url>
    <loc>{base}/blog/{slug}</loc>
    <lastmod>{mod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
    except Exception:
        pass

    # Directory firms
    try:
        from sqlalchemy import text as _text2
        firms = db.session.execute(
            _text2("SELECT id FROM directory_law_firms WHERE is_active=TRUE LIMIT 500")
        ).fetchall()
        for f in firms:
            urls.append(f"""  <url>
    <loc>{base}/directory/firm/{f[0]}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>""")
    except Exception:
        pass

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>'
    return make_response(xml, 200, {'Content-Type': 'application/xml; charset=utf-8'})


@app.route('/popup')
def popup_page():
    """Simple clean landing page with automatic popup redirect after 7 seconds"""
    from models import PopupSettings, ROLE_SUPER_ADMIN
    settings = PopupSettings.query.first()
    if settings and not settings.popup_enabled:
        is_super = current_user.is_authenticated and current_user.role == ROLE_SUPER_ADMIN
        if not is_super:
            return render_template('sales/sales_disabled.html'), 403
    referrer = request.headers.get('Referer', '')
    auto_popup = 'sales/popup' not in referrer
    return render_template('simple_popup_landing.html', auto_popup=auto_popup)

@app.route('/')
def index():
    """Main landing page - shows public landing if not authenticated, redirects to dashboard if authenticated"""
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on role
        if current_user.is_super_admin():
            return redirect(url_for('superadmin.dashboard'))
        elif current_user.is_admin():
            return redirect(url_for('admin.admin_dashboard'))
        elif current_user.is_team_member():
            return redirect(url_for('dashboard.team_member_dashboard'))
        else:
            return redirect(url_for('dashboard.client_dashboard'))
    
    # Show public landing page with popup settings
    from models import PopupSettings, CustomerReview, LawFirmShowcase
    from sqlalchemy import desc
    
    # Get popup settings for comprehensive popup — always persisted
    settings = PopupSettings.query.first()
    if not settings:
        from app import db
        settings = PopupSettings(
            starter_price=39.00, growth_price=90.00,
            enterprise_price=350.00, founders_price=1745.00,
            lifetime_price=999.00,
        )
        db.session.add(settings)
        db.session.commit()
    
    # Get featured reviews
    reviews = CustomerReview.query.filter_by(is_active=True).order_by(desc(CustomerReview.is_featured), CustomerReview.id).limit(20).all()
    
    # Get featured law firm showcases
    featured_showcases = LawFirmShowcase.query.filter_by(
        is_featured=True, 
        is_active=True
    ).order_by(LawFirmShowcase.showcase_order.asc()).limit(6).all()
    
    return render_template('index.html', settings=settings, reviews=reviews, featured_showcases=featured_showcases)

@app.route('/subscription-expired')
def subscription_expired():
    """Subscription expired page with upgrade options"""
    return render_template('subscription_expired.html')

@app.route('/trial-dashboard')
def trial_dashboard():
    """Trial dashboard with countdown and feature overview"""
    from flask_login import login_required, current_user
    from utils.trial_access import trial_warning_context, get_trial_notification
    
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    
    if not current_user.law_firm or current_user.law_firm.subscription_period != '3days':
        return redirect(url_for('index'))
    
    context = trial_warning_context()
    trial_notification = get_trial_notification()
    
    return render_template('trial_dashboard.html', 
                         trial_notification=trial_notification,
                         **context)

# Global context processor for trial notifications + admin notification count
@app.context_processor
def inject_trial_context():
    """Inject trial context, notifications, and admin badge count into all templates"""
    from utils.trial_access import trial_warning_context, get_trial_notification

    if current_user.is_authenticated:
        context = trial_warning_context()
        trial_notification = get_trial_notification()

        # Admin notification badge count for super admins
        admin_notif_count = 0
        try:
            if current_user.role == 'super_admin':
                from models import AdminNotification
                admin_notif_count = AdminNotification.query.filter_by(is_read=False).count()
        except Exception:
            pass

        return {
            'trial_context': context,
            'trial_notification': trial_notification,
            'admin_notif_count': admin_notif_count,
        }
    return {}

@app.route('/landing')
def landing():
    """Comprehensive landing page"""
    return render_template('landing.html')

@app.route('/pricing')
def pricing():
    """Pricing plans page"""
    from models import PopupSettings
    
    # Get pricing settings — always persisted so defaults are never None
    settings = PopupSettings.query.first()
    if not settings:
        from app import db
        settings = PopupSettings(
            starter_price=39.00, growth_price=90.00,
            enterprise_price=350.00, founders_price=1745.00,
            lifetime_price=999.00,
        )
        db.session.add(settings)
        db.session.commit()
    
    return render_template('pricing.html', settings=settings)

@app.route('/about')
def about():
    """About Taskdrip and LawColab page"""
    response = render_template('about.html')
    # Add cache control headers to prevent caching issues
    from flask import make_response
    resp = make_response(response)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page - saves submissions to contact_inquiries table for super admin inbox."""
    if request.method == 'POST':
        try:
            first_name   = request.form.get('firstName', '').strip()
            last_name    = request.form.get('lastName', '').strip()
            email        = request.form.get('email', '').strip()
            phone        = request.form.get('phone', '').strip()
            company      = request.form.get('company', '').strip()
            country      = request.form.get('country', '').strip()
            inquiry_type = request.form.get('inquiryType', '').strip()
            message      = request.form.get('message', '').strip()
            newsletter   = bool(request.form.get('newsletter'))

            if not all([first_name, last_name, email, inquiry_type, message]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('contact'))

            ip_addr = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr or '')
            if ip_addr and ',' in ip_addr:
                ip_addr = ip_addr.split(',')[0].strip()

            from datetime import datetime as _dt
            _now = _dt.utcnow()
            db.session.execute(text("""
                INSERT INTO contact_inquiries
                    (first_name, last_name, email, phone, company, country,
                     inquiry_type, message, newsletter, status, ip_address, created_at, updated_at)
                VALUES
                    (:fn, :ln, :em, :ph, :co, :ct, :it, :ms, :nl, 'new', :ip, :now, :now)
            """), dict(fn=first_name, ln=last_name, em=email, ph=phone or None,
                       co=company or None, ct=country or None, it=inquiry_type,
                       ms=message, nl=newsletter, ip=ip_addr[:45] if ip_addr else None,
                       now=_now))
            db.session.commit()

            flash(f"__SUCCESS__{first_name}", 'success')
        except Exception as exc:
            import traceback; traceback.print_exc()
            db.session.rollback()
            flash('There was an error sending your message. Please try WhatsApp or email us directly.', 'error')

        return redirect(url_for('contact'))

    resp = make_response(render_template('contact.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/registration-success')
def registration_success():
    """Thank you page after law firm registration"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return render_template('auth/registration_success.html')

@app.route('/chat-support', methods=['GET', 'POST'])
def chat_support():
    """Redirect to enhanced chat support system"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('enhanced_chat.support_chat'))

# Legal pages routes
@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('legal/privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('legal/terms_of_service.html')

@app.route('/cookie-policy')
def cookie_policy():
    """Cookie Policy page"""
    return render_template('legal/cookie_policy.html')

@app.route('/gdpr')
def gdpr():
    """GDPR page"""
    return render_template('legal/gdpr.html')

@app.route('/features')
def features():
    """Features page"""
    return render_template('features.html')

# Test route to verify pages are working
@app.route('/test-pages')
def test_pages():
    """Simple test page to verify About and Contact pages"""
    return send_from_directory('.', 'test_pages.html')

# Add route to serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Invoice blueprints already registered above

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('403.html'), 404  # Use same template for simplicity


# ── Blog seed (run once at startup if blog_posts is empty) ────────────────────
def _seed_blog_posts():
    """Insert sample blog posts if none exist."""
    try:
        from sqlalchemy import text as _t
        count = db.session.execute(_t("SELECT COUNT(*) FROM blog_posts")).scalar()
        if count and count > 0:
            return
        posts = [
            {
                "title": "How to Manage Your Law Firm's Cases More Efficiently",
                "slug": "manage-law-firm-cases-efficiently",
                "excerpt": "From intake to resolution, these proven systems help Nigerian law firms eliminate the chaos of manual case tracking.",
                "content": """<p>Managing cases across multiple clients, hearing dates, documents, and team members is one of the biggest operational challenges facing law firms today — especially in fast-growing practices.</p>
<h2>The Problem with Manual Case Management</h2>
<p>Most small and mid-size law firms in Nigeria still rely on spreadsheets, WhatsApp groups, and paper files. The result? Missed deadlines, duplicated effort, and clients left in the dark.</p>
<h2>5 Systems That Make the Difference</h2>
<ol>
<li><strong>Centralised case register</strong> — every case in one place, searchable by client, court, status, and date.</li>
<li><strong>Automated deadline reminders</strong> — no more relying on memory. The system alerts you 7, 3, and 1 day before critical dates.</li>
<li><strong>Digital document library</strong> — upload pleadings, affidavits, and evidence once; share securely with colleagues and clients.</li>
<li><strong>Task assignment</strong> — assign research, drafting, and court appearances to specific team members with due dates.</li>
<li><strong>Client portal</strong> — let clients check case status without calling your office every day.</li>
</ol>
<h2>Getting Started</h2>
<p>The good news: you don't need a six-figure IT budget. LAWCOLAB gives every law firm all five systems in one platform, starting with a free 14-day trial. Set up your first case in under 10 minutes.</p>""",
                "category": "Practice Management",
                "tags": "case management,law firm,Nigeria,efficiency",
                "hero_image": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1200&q=70",
                "author": "Abraham Tahbat",
                "published": True, "featured": True,
            },
            {
                "title": "The Rise of Legal Technology in Africa: What It Means for Your Firm",
                "slug": "legal-technology-africa-law-firms",
                "excerpt": "Legal tech adoption is accelerating across Nigeria, Kenya, and South Africa. Here's what forward-thinking firms are doing differently.",
                "content": """<p>In 2020, fewer than 15% of Nigerian law firms used any form of dedicated practice management software. By 2024, that number had risen to over 40% — and it's still climbing.</p>
<h2>Why Africa Is the Next Frontier for Legal Tech</h2>
<p>Three forces are converging: mobile-first internet access, a growing middle class demanding professional legal services, and a generation of lawyers who grew up digital. The result is one of the fastest-growing legal tech markets in the world.</p>
<h2>What Leading Firms Are Doing</h2>
<blockquote>The firms winning new clients aren't necessarily the most experienced — they're the most organised and most responsive. Technology is the great equaliser.</blockquote>
<p>Top-performing Nigerian law firms are investing in:</p>
<ul>
<li>Cloud-based case management platforms accessible from any device</li>
<li>Digital invoicing with online payment links</li>
<li>Client portals that provide 24/7 case status updates</li>
<li>Public law firm directory listings to attract new clients</li>
</ul>
<h2>The Competitive Advantage</h2>
<p>A firm that responds to a client query within two hours, provides real-time case updates, and sends a professional invoice by email will win over a firm that phones back three days later every single time.</p>""",
                "category": "Legal Tech",
                "tags": "legal tech,Africa,Nigeria,digital transformation",
                "hero_image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&q=70",
                "author": "LAWCOLAB Team",
                "published": True, "featured": False,
            },
            {
                "title": "Court Calendar Management: How Modern Law Firms Never Miss a Deadline",
                "slug": "court-calendar-management-law-firms",
                "excerpt": "A missed hearing date can end a career and cost a client everything. Here's the system top Nigerian litigation firms use.",
                "content": """<p>In litigation, missing a court date is catastrophic. Yet it happens — even in top-tier firms — because most practices still manage court calendars using generic tools that weren't built for legal work.</p>
<h2>Why Generic Calendars Fail Lawyers</h2>
<p>Google Calendar and Outlook don't understand adjournments. They can't link a court date to a specific case, attach relevant documents, or notify the right team member automatically when a date changes.</p>
<h2>What a Legal Court Calendar Must Do</h2>
<ol>
<li><strong>Link to cases</strong> — every date ties to a specific matter, with client name, court, and judge visible at a glance.</li>
<li><strong>Multi-tier reminders</strong> — automatic notifications at 7 days, 3 days, 1 day, and morning of hearing.</li>
<li><strong>Team visibility</strong> — your entire litigation team sees the same calendar in real time.</li>
<li><strong>Adjournment tracking</strong> — when a date is adjourned, the old date is archived and the new one is automatically added.</li>
<li><strong>iCal sync</strong> — export to personal phone calendar for offline access.</li>
</ol>
<h2>Building the Habit</h2>
<p>The best calendar system is worthless if your team doesn't use it. Block 15 minutes every Friday to review the following week's dates as a team. Every newly filed matter should have its first court date entered before the file leaves reception.</p>""",
                "category": "Litigation",
                "tags": "court calendar,litigation,deadlines,Nigeria",
                "hero_image": "https://images.unsplash.com/photo-1505664194779-8beaceb93744?w=1200&q=70",
                "author": "Abraham Tahbat",
                "published": True, "featured": False,
            },
            {
                "title": "5 Things Every Nigerian Law Firm Should Know About Client Portals",
                "slug": "client-portal-guide-nigerian-law-firms",
                "excerpt": "Clients who feel informed are clients who pay faster, refer more, and complain less. A client portal is the single best investment most firms can make.",
                "content": """<p>The most common complaint lawyers hear from clients is: "Why don't you ever update me?" It's not malicious — lawyers are busy and assume clients trust them. But clients interpret silence as neglect.</p>
<h2>What Is a Client Portal?</h2>
<p>A client portal is a secure, private web page where each client can log in and see exactly what's happening with their case — documents, updates, invoices, and messages — without calling your office.</p>
<h2>5 Things You Must Know</h2>
<h3>1. It doesn't replace communication — it enhances it</h3>
<p>Clients still want to speak with their lawyer. But they want to check the basics themselves without waiting. A portal handles the routine, freeing you for the substantive.</p>
<h3>2. It dramatically reduces "where are we?" calls</h3>
<p>Firms using LAWCOLAB report a 60–70% reduction in routine client status calls after launching their portal.</p>
<h3>3. It gets you paid faster</h3>
<p>When invoices are visible in the portal with a "Pay Now" button, collection cycles shorten significantly. Clients pay faster when they can act immediately.</p>
<h3>4. Security is non-negotiable</h3>
<p>Every portal must be password-protected and served over HTTPS. Never share client documents via public links or email attachments.</p>
<h3>5. It's a competitive differentiator right now</h3>
<p>Fewer than 20% of Nigerian law firms offer a client portal today. If you have one and your competitors don't, you win the mandate before the first meeting.</p>""",
                "category": "Client Relations",
                "tags": "client portal,communication,billing,law firm",
                "hero_image": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=1200&q=70",
                "author": "LAWCOLAB Team",
                "published": True, "featured": False,
            },
            {
                "title": "Professional Invoicing for Law Firms: A Complete Guide",
                "slug": "professional-invoicing-law-firms-guide",
                "excerpt": "Sloppy invoices get paid last. Here's how to create invoices that get paid on time, every time.",
                "content": """<p>Billing is often the last thing lawyers want to think about — but it's the lifeblood of the practice. Firms that have a professional, consistent invoicing process get paid faster and have fewer disputes.</p>
<h2>What Makes a Legal Invoice Professional</h2>
<ul>
<li>Your firm's letterhead, logo, and contact details</li>
<li>A unique invoice number (for tracking)</li>
<li>The client's full name and address</li>
<li>A clear description of each service rendered</li>
<li>Hours worked and applicable rate (for time-based billing)</li>
<li>VAT / tax calculation where applicable</li>
<li>Your bank account details with NUBAN number</li>
<li>A clear due date (not just "upon receipt")</li>
</ul>
<h2>Common Invoicing Mistakes Law Firms Make</h2>
<p><strong>Vague descriptions</strong> — "Legal services rendered" tells the client nothing. Be specific: "Drafting of commercial lease agreement — 4.5 hours @ ₦25,000/hr".</p>
<p><strong>No follow-up system</strong> — Send a gentle reminder 3 days before the due date, on the due date, and 7 days after. Automate this.</p>
<p><strong>Only accepting cash</strong> — Offer bank transfer, online payment, and mobile money. The easier you make it to pay, the faster you get paid.</p>
<h2>The Digital Advantage</h2>
<p>LAWCOLAB generates polished, branded PDF invoices in seconds. Clients receive them by email with a payment link. The system tracks payment status and sends automatic reminders — so you never have to chase an invoice manually again.</p>""",
                "category": "Billing & Finance",
                "tags": "invoicing,billing,finance,law firm Nigeria",
                "hero_image": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1200&q=70",
                "author": "Abraham Tahbat",
                "published": True, "featured": False,
            },
        ]
        for p in posts:
            db.session.execute(_t("""
                INSERT INTO blog_posts
                    (title, slug, content, excerpt, category, tags, hero_image, author,
                     published, featured, view_count, comment_count, created_at, updated_at, published_at)
                VALUES
                    (:title,:slug,:content,:excerpt,:cat,:tags,:hero,:author,
                     :pub,:feat,0,0,NOW(),NOW(),NOW())
                ON CONFLICT (slug) DO NOTHING
            """), dict(title=p['title'], slug=p['slug'], content=p['content'],
                       excerpt=p['excerpt'], cat=p['category'], tags=p['tags'],
                       hero=p['hero_image'], author=p['author'],
                       pub=p['published'], feat=p['featured']))
        db.session.commit()
        logger.info("Blog: seeded %d sample posts.", len(posts))
    except Exception as e:
        db.session.rollback()
        logger.warning("Blog seed skipped: %s", e)


with app.app_context():
    _seed_blog_posts()