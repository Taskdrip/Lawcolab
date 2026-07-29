from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from utils.decorators import require_super_admin
from app import db
from models import (User, LawFirm, Project, SupportRequest, DashboardSlider, LegalNews,
                    PlatformNotification, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_CLIENT,
                    ROLE_TEAM_MEMBER, NOTIF_TYPE_RENEWAL, NOTIF_TYPE_EXPIRY,
                    NOTIF_TYPE_SUSPENDED, NOTIF_TYPE_GENERAL, NOTIF_TYPE_UPGRADE)
import os
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func, inspect, text
from datetime import datetime, timedelta
import uuid

superadmin_bp = Blueprint('superadmin', __name__)

@superadmin_bp.route('/dashboard')
@require_super_admin
def dashboard():
    """Super admin dashboard showing all law firms and platform statistics"""
    now = datetime.now()

    # Get platform-wide statistics
    total_law_firms    = LawFirm.query.count()
    total_users        = User.query.count()
    total_admins       = User.query.filter_by(role=ROLE_ADMIN).count()
    total_team_members = User.query.filter_by(role=ROLE_TEAM_MEMBER).count()
    total_clients      = User.query.filter_by(role=ROLE_CLIENT).count()
    total_projects     = Project.query.count()

    # Subscription health
    active_subs   = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires > now
    ).count()
    expired_subs  = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires <= now
    ).count()
    expiring_soon = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires > now,
        LawFirm.admin_access_expires <= now + timedelta(days=7)
    ).all()
    expired_firms = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires <= now
    ).all()

    # Get recent law firms
    recent_law_firms = LawFirm.query.order_by(LawFirm.created_at.desc()).limit(10).all()

    # Get recent admin signups
    recent_admins = User.query.filter_by(role=ROLE_ADMIN).order_by(User.created_at.desc()).limit(10).all()

    # Get support requests
    support_requests = SupportRequest.query.order_by(SupportRequest.created_at.desc()).limit(5).all()

    stats = {
        'total_law_firms':    total_law_firms,
        'total_users':        total_users,
        'total_admins':       total_admins,
        'total_team_members': total_team_members,
        'total_clients':      total_clients,
        'total_projects':     total_projects,
        'active_subs':        active_subs,
        'expired_subs':       expired_subs,
        'pending_access':     LawFirm.query.filter_by(admin_access_granted=False).count(),
    }

    return render_template('superadmin/dashboard.html',
                           stats=stats,
                           recent_law_firms=recent_law_firms,
                           recent_admins=recent_admins,
                           support_requests=support_requests,
                           expiring_soon=expiring_soon,
                           expired_firms=expired_firms)

@superadmin_bp.route('/users')
@require_super_admin
def manage_users():
    """Manage all users on the platform"""
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    page = request.args.get('page', 1, type=int)
    
    query = User.query
    if search:
        query = query.filter(
            or_(
                User.email.contains(search),
                User.first_name.contains(search),
                User.last_name.contains(search)
            )
        )
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('superadmin/manage_users.html', users=users, search=search, role_filter=role_filter)

@superadmin_bp.route('/users/toggle-status', methods=['POST'])
@require_super_admin
def toggle_user_status():
    """Activate/deactivate user account"""
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    user.active = not user.active
    db.session.commit()
    
    status = "activated" if user.active else "deactivated"
    flash(f'User {user.email} has been {status}.', 'success')
    return redirect(request.referrer or url_for('superadmin.manage_users'))

def _sa_cleanup_user_fk(uid):
    """Remove FK-dependent records before hard-deleting a user (superadmin version).

    IMPORTANT: all steps run in ONE transaction with no per-step rollback.
    A per-step rollback would undo earlier deletes, leaving orphan FK rows that
    cause NOT NULL violations when SQLAlchemy tries to nullify created_by_id on
    calendar_events (or similar nullable=False columns) during the user delete.
    """
    steps = [
        # Nullify soft back-references first so they don't block later deletes
        "UPDATE support_requests SET resolved_by_id=NULL WHERE resolved_by_id=:u",
        "UPDATE project_assignments SET assigned_by_id=NULL WHERE assigned_by_id=:u",
        # Calendar: remove attendee rows (children) before events (parent)
        "DELETE FROM calendar_event_attendees WHERE user_id=:u",
        ("DELETE FROM calendar_event_attendees WHERE event_id IN "
         "(SELECT id FROM calendar_events WHERE created_by_id=:u)"),
        "DELETE FROM calendar_events WHERE created_by_id=:u",
        # Messages / chat
        "DELETE FROM project_messages WHERE user_id=:u",
        "DELETE FROM direct_messages WHERE sender_id=:u OR receiver_id=:u",
        "DELETE FROM chat_conversations WHERE user1_id=:u OR user2_id=:u",
        # Support
        "DELETE FROM support_requests WHERE user_id=:u",
        # Notes
        "DELETE FROM client_notes WHERE client_id=:u OR created_by_id=:u",
        # Invoices (children before parent)
        "DELETE FROM invoice_chat_attachments WHERE uploaded_by_id=:u",
        "DELETE FROM invoice_chat_messages WHERE sender_id=:u",
        "DELETE FROM invoice_chats WHERE client_id=:u OR created_by_id=:u",
        "DELETE FROM invoice_notifications WHERE user_id=:u",
        "DELETE FROM payment_records WHERE recorded_by_id=:u",
        ("DELETE FROM invoice_line_items WHERE invoice_id IN "
         "(SELECT id FROM invoices WHERE client_id=:u OR created_by_id=:u)"),
        "DELETE FROM invoices WHERE client_id=:u OR created_by_id=:u",
        # Projects (children before parent)
        "DELETE FROM project_files WHERE uploaded_by_id=:u",
        ("DELETE FROM project_messages WHERE project_id IN "
         "(SELECT id FROM projects WHERE created_by_id=:u)"),
        ("DELETE FROM project_files WHERE project_id IN "
         "(SELECT id FROM projects WHERE created_by_id=:u)"),
        ("DELETE FROM project_assignments WHERE project_id IN "
         "(SELECT id FROM projects WHERE created_by_id=:u)"),
        "DELETE FROM project_assignments WHERE user_id=:u",
        "DELETE FROM projects WHERE created_by_id=:u",
    ]
    for sql in steps:
        db.session.execute(text(sql), {"u": uid})
    # Flush all cleanup to the DB before the caller does db.session.delete(user),
    # so no FK references to this user remain when the ORM removes the user row.
    db.session.flush()

@superadmin_bp.route('/users/delete', methods=['POST'])
@require_super_admin
def delete_user():
    """Delete user account"""
    import logging as _log
    _logger = _log.getLogger(__name__)
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    if user.is_super_admin():
        flash('Cannot delete super admin account.', 'error')
        return redirect(request.referrer or url_for('superadmin.manage_users'))
    
    try:
        email = user.email
        _sa_cleanup_user_fk(user.id)
        db.session.delete(user)
        db.session.commit()
        flash(f'User {email} has been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        _logger.error("superadmin delete_user error: %s", e)
        flash(f'Failed to delete user. Error: {str(e)[:120]}', 'error')

    return redirect(url_for('superadmin.manage_users'))

@superadmin_bp.route('/analytics')
@require_super_admin
def platform_analytics():
    """Comprehensive platform analytics"""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Time-based analytics
    last_30_days = datetime.now() - timedelta(days=30)
    last_7_days = datetime.now() - timedelta(days=7)
    
    # User growth metrics
    total_users = User.query.count()
    new_users_30_days = User.query.filter(User.created_at >= last_30_days).count()
    new_users_7_days = User.query.filter(User.created_at >= last_7_days).count()
    
    # Law firm metrics
    total_firms = LawFirm.query.count()
    new_firms_30_days = LawFirm.query.filter(LawFirm.created_at >= last_30_days).count()
    
    # Project metrics
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='active').count()
    
    # User role breakdown
    role_stats = db.session.query(
        User.role, func.count(User.id)
    ).group_by(User.role).all()
    
    analytics = {
        'total_users': total_users,
        'new_users_30_days': new_users_30_days,
        'new_users_7_days': new_users_7_days,
        'total_firms': total_firms,
        'new_firms_30_days': new_firms_30_days,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'role_stats': dict(role_stats),
        'user_growth_rate': round((new_users_30_days / total_users * 100), 2) if total_users > 0 else 0
    }
    
    return render_template('superadmin/analytics.html', analytics=analytics)

@superadmin_bp.route('/web-analytics')
@require_super_admin
def web_analytics():
    """Advanced web analytics dashboard with AI robot recommendations."""
    from sqlalchemy import text
    import json as _json

    days = request.args.get('days', 30, type=int)
    if days not in (7, 30, 90):
        days = 30

    # Use Python datetime params for DB-agnostic queries (SQLite + PostgreSQL)
    now_dt   = datetime.now()
    start_dt = now_dt - timedelta(days=days)
    prev_dt  = now_dt - timedelta(days=days * 2)
    today_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_ago  = now_dt - timedelta(hours=24)

    def _q(sql, params=None):
        try:
            return db.session.execute(text(sql), params or {}).fetchall()
        except Exception:
            return []

    def _scalar(sql, params=None):
        try:
            return db.session.execute(text(sql), params or {}).scalar() or 0
        except Exception:
            return 0

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_visits = _scalar(
        "SELECT COUNT(*) FROM page_analytics WHERE created_at >= :s",
        {"s": start_dt})
    unique_sessions = _scalar(
        "SELECT COUNT(DISTINCT session_id) FROM page_analytics WHERE created_at >= :s",
        {"s": start_dt})
    prev_visits = _scalar(
        "SELECT COUNT(*) FROM page_analytics WHERE created_at >= :p AND created_at < :s",
        {"p": prev_dt, "s": start_dt})
    visits_delta = round(((total_visits - prev_visits) / prev_visits * 100), 1) if prev_visits > 0 else 0

    # Bounce rate: sessions with only 1 page view
    total_sessions = unique_sessions
    single_page_sessions = _scalar(
        """SELECT COUNT(*) FROM (
              SELECT session_id FROM page_analytics
              WHERE created_at >= :s
              GROUP BY session_id HAVING COUNT(*) = 1
           ) sub""",
        {"s": start_dt})
    bounce_rate = round((single_page_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0.0

    # Pages per session
    pages_per_session = round((total_visits / unique_sessions), 2) if unique_sessions > 0 else 0.0

    # Unique countries count
    unique_countries = _scalar(
        """SELECT COUNT(DISTINCT country) FROM page_analytics
           WHERE created_at >= :s AND country IS NOT NULL AND country != '' AND country != 'Unknown'""",
        {"s": start_dt})

    # Today's visits
    today_visits = _scalar(
        "SELECT COUNT(*) FROM page_analytics WHERE created_at >= :t",
        {"t": today_dt})

    # ── Daily visits trend (Python-side aggregation for DB-compat) ────────────
    all_rows = _q(
        "SELECT created_at FROM page_analytics WHERE created_at >= :s ORDER BY created_at",
        {"s": start_dt})
    from collections import defaultdict
    daily_counts = defaultdict(int)
    for row in all_rows:
        dt_val = row[0]
        if isinstance(dt_val, str):
            try:
                dt_val = datetime.fromisoformat(dt_val)
            except Exception:
                continue
        daily_counts[dt_val.strftime('%b %d')] += 1
    # Build ordered labels for last `days` days
    daily_labels = []
    daily_data   = []
    for i in range(days - 1, -1, -1):
        label = (now_dt - timedelta(days=i)).strftime('%b %d')
        daily_labels.append(label)
        daily_data.append(daily_counts.get(label, 0))

    # ── Hourly breakdown (last 24h, Python-side) ──────────────────────────────
    hourly_rows_raw = _q(
        "SELECT created_at FROM page_analytics WHERE created_at >= :s",
        {"s": day_ago})
    hourly_map = defaultdict(int)
    for row in hourly_rows_raw:
        dt_val = row[0]
        if isinstance(dt_val, str):
            try:
                dt_val = datetime.fromisoformat(dt_val)
            except Exception:
                continue
        hourly_map[dt_val.hour] += 1
    hourly_labels = [f'{h:02d}:00' for h in range(24)]
    hourly_data   = [hourly_map.get(h, 0) for h in range(24)]

    # Peak hour
    peak_hour = max(range(24), key=lambda h: hourly_map.get(h, 0)) if hourly_map else None
    peak_hour_label = f'{peak_hour:02d}:00–{(peak_hour+1)%24:02d}:00' if peak_hour is not None else 'N/A'

    # ── Top pages ─────────────────────────────────────────────────────────────
    top_pages_rows = _q(
        """SELECT page_path, COUNT(*) as visits,
                  COUNT(DISTINCT session_id) as unique_vis
           FROM page_analytics
           WHERE created_at >= :s
           GROUP BY page_path ORDER BY visits DESC LIMIT 10""",
        {"s": start_dt})
    top_pages = [{'page_path': r[0], 'visits': r[1], 'unique_vis': r[2]} for r in top_pages_rows]

    # ── Device breakdown ──────────────────────────────────────────────────────
    device_rows = _q(
        """SELECT device_type, COUNT(*) as cnt
           FROM page_analytics WHERE created_at >= :s
           GROUP BY device_type ORDER BY cnt DESC""",
        {"s": start_dt})
    device_labels = [r[0].title() for r in device_rows]
    device_data   = [r[1] for r in device_rows]
    device_pcts   = {}
    if device_rows:
        _total = sum(r[1] for r in device_rows) or 1
        for r in device_rows:
            device_pcts[r[0]] = round(r[1] / _total * 100, 1)

    # ── Browser breakdown ─────────────────────────────────────────────────────
    browser_rows = _q(
        """SELECT browser, COUNT(*) as cnt
           FROM page_analytics WHERE created_at >= :s
           GROUP BY browser ORDER BY cnt DESC LIMIT 8""",
        {"s": start_dt})
    browser_labels = [r[0] for r in browser_rows]
    browser_data   = [r[1] for r in browser_rows]

    # ── OS breakdown ──────────────────────────────────────────────────────────
    os_rows = _q(
        """SELECT os_name, COUNT(*) as cnt
           FROM page_analytics WHERE created_at >= :s
           GROUP BY os_name ORDER BY cnt DESC LIMIT 6""",
        {"s": start_dt})

    # ── Top referrers ─────────────────────────────────────────────────────────
    ref_rows = _q(
        """SELECT referrer, COUNT(*) as cnt
           FROM page_analytics
           WHERE referrer IS NOT NULL AND referrer != ''
             AND created_at >= :s
           GROUP BY referrer ORDER BY cnt DESC LIMIT 10""",
        {"s": start_dt})
    top_referrers = [{'referrer': r[0][:80], 'cnt': r[1]} for r in ref_rows]

    # ── Country breakdown ─────────────────────────────────────────────────────
    country_rows = _q(
        """SELECT country, COUNT(*) as cnt
           FROM page_analytics WHERE created_at >= :s
           GROUP BY country ORDER BY cnt DESC LIMIT 15""",
        {"s": start_dt})

    # ── New vs Returning (approximate by session first-seen) ──────────────────
    new_sessions = _scalar(
        """SELECT COUNT(DISTINCT session_id) FROM page_analytics
           WHERE created_at >= :s
             AND session_id NOT IN (
               SELECT DISTINCT session_id FROM page_analytics
               WHERE created_at < :s
             )""",
        {"s": start_dt})
    returning_sessions = max(0, unique_sessions - new_sessions)
    new_pct = round(new_sessions / unique_sessions * 100, 1) if unique_sessions > 0 else 0

    # ── AI Robot Recommendations ──────────────────────────────────────────────
    recs = []

    # Bounce rate recommendation
    if bounce_rate > 70:
        recs.append({'type':'danger','icon':'fa-exclamation-triangle','priority':1,
            'title':f'Critical: Bounce Rate at {bounce_rate:.0f}%',
            'text':'Over 70% of visitors leave after a single page. Immediate actions: (1) Strengthen your above-the-fold headline to match visitor search intent, (2) Add a clear, prominent CTA above the fold, (3) Reduce page load time below 3 seconds, (4) Add 3–5 internal links on every page.',
            'actions':['Audit page load speed','Add internal links','Improve CTAs']})
    elif bounce_rate > 50:
        recs.append({'type':'warning','icon':'fa-chart-line','priority':2,
            'title':f'Bounce Rate at {bounce_rate:.0f}% — Room to Improve',
            'text':'Half your visitors leave after one page. Add "Related Articles" sections, a sticky CTA bar, and ensure your navigation clearly shows what the site offers.',
            'actions':['Add related content','Improve navigation','Add sticky CTA']})
    else:
        recs.append({'type':'success','icon':'fa-check-circle','priority':5,
            'title':f'Excellent Bounce Rate: {bounce_rate:.0f}%',
            'text':'Visitors are exploring multiple pages — your content and navigation are working well. Sustain this by publishing regular blog posts and maintaining fast page loads.',
            'actions':['Keep publishing content','Monitor weekly']})

    # Mobile traffic
    mobile_pct = device_pcts.get('mobile', 0)
    if mobile_pct > 60:
        recs.append({'type':'info','icon':'fa-mobile-alt','priority':2,
            'title':f'{mobile_pct:.0f}% Mobile Traffic — Optimise for Small Screens',
            'text':'The majority of visitors are on mobile. Google uses mobile-first indexing, so mobile UX directly impacts rankings. Check: tap targets ≥44px, font size ≥16px, hero images compressed, forms easy to fill.',
            'actions':['Run Mobile-Friendly Test','Compress images','Check tap targets']})
    elif mobile_pct > 0:
        recs.append({'type':'info','icon':'fa-desktop','priority':4,
            'title':f'Balanced Desktop ({100-mobile_pct:.0f}%) / Mobile ({mobile_pct:.0f}%) Split',
            'text':'Your audience uses both desktop and mobile. Ensure your design and content work well across all screen sizes.',
            'actions':['Test on mobile','Test on desktop']})

    # Traffic volume
    if total_visits < 200:
        recs.append({'type':'warning','icon':'fa-search','priority':1,
            'title':'Priority: Grow Organic Traffic with SEO Blog Content',
            'text':'Publishing 2–3 SEO-optimised articles per week is the highest-ROI growth tactic. Target: "law firm software Nigeria", "case management Africa", "legal billing software". Each post builds permanent Google ranking authority.',
            'actions':['Publish 2x/week','Research keywords','Submit sitemap']})
    elif total_visits < 1000:
        recs.append({'type':'info','icon':'fa-rocket','priority':3,
            'title':'Scale Traffic with Link Building & Social',
            'text':'You have a solid foundation. Accelerate by sharing posts in bar association groups, LinkedIn legal networks, and WhatsApp communities. Each external backlink boosts your Google Domain Authority.',
            'actions':['Share in LinkedIn groups','Get backlinks','Guest post outreach']})
    else:
        recs.append({'type':'success','icon':'fa-trophy','priority':4,
            'title':'Strong Traffic Volume — Focus on Conversion',
            'text':f'Great volume ({total_visits:,} views). Now focus on converting visitors to trial signups. A/B test your hero CTA, add social proof, and create a dedicated landing page for each key feature.',
            'actions':['A/B test hero CTA','Add testimonials','Track conversions in GA4']})

    # Top page conversion
    if top_pages:
        top = top_pages[0]
        recs.append({'type':'info','icon':'fa-star','priority':3,
            'title':f'Top Page: {top["page_path"]} — Maximise Conversions',
            'text':f'Your highest-traffic page ({top["visits"]:,} views) is your best conversion asset. Add: a "Start Free Trial" CTA, a trust badge ("500+ law firms"), one compelling testimonial, and a comparison table vs competitors.',
            'actions':['Add CTA to top page','Add trust badge','Add testimonial']})

    # Pages per session
    if pages_per_session < 1.5:
        recs.append({'type':'warning','icon':'fa-sitemap','priority':2,
            'title':f'Low Engagement: {pages_per_session} Pages/Session',
            'text':'Visitors view fewer than 2 pages per visit. Fix with: contextual internal links in every post, a "You might also like" section, a features overview in the nav, and a footer with links to key pages.',
            'actions':['Add internal links','Add related posts','Improve footer nav']})

    # Google Analytics
    ga4_active = bool(os.environ.get('GA4_MEASUREMENT_ID') or _get_site_setting('ga4_measurement_id') or True)
    recs.append({'type':'success','icon':'fa-chart-bar','priority':4,
        'title':'GA4 Active: G-EPSVWPRWPZ',
        'text':'Google Analytics 4 is firing on every page. To unlock the full power of GA4: set up conversion events (free trial signup, contact form), create an audience for visitors who viewed pricing, and connect GA4 to Google Search Console for integrated search + behaviour data.',
        'actions':['Set up GA4 conversions','Link to Search Console','Create remarketing audience']})

    # Sitemap
    recs.append({'type':'info','icon':'fa-sitemap','priority':4,
        'title':'Submit Sitemap to Google Search Console',
        'text':'Your sitemap is live at /sitemap.xml. In Search Console → Sitemaps, submit this URL. Google then crawls every public page, blog post, and directory listing — accelerating indexing and improving rankings.',
        'actions':['Submit sitemap','Verify in Search Console','Monitor coverage']})

    # Country-specific
    if country_rows:
        top_country = country_rows[0][0] if country_rows else 'Nigeria'
        if top_country and top_country not in ('Unknown',):
            recs.append({'type':'info','icon':'fa-globe-africa','priority':5,
                'title':f'Top Market: {top_country} — Localise Your Content',
                'text':f'{top_country} drives your most traffic. Ensure your content, pricing (NGN), and case studies speak directly to {top_country} law firms. Add country-specific testimonials and mention local bar associations.',
                'actions':[f'Add {top_country} case studies','Show NGN pricing','Add local testimonials']})

    recs = sorted(recs, key=lambda x: x['priority'])

    # ── Google / SEO Settings ─────────────────────────────────────────────────
    ga4_id_env  = os.environ.get('GA4_MEASUREMENT_ID', '')
    gsc_env     = os.environ.get('GSC_VERIFICATION', '')
    ga4_id_db   = _get_site_setting('ga4_measurement_id')
    gsc_db      = _get_site_setting('gsc_verification')
    gtm_db      = _get_site_setting('gtm_id', 'GTM-TVF3MJPP')
    domain_db   = _get_site_setting('site_domain', 'lawcolab.com')

    # Always default to G-EPSVWPRWPZ if nothing is set
    effective_ga4 = ga4_id_env or ga4_id_db or 'G-EPSVWPRWPZ'

    google_settings = {
        'ga4_measurement_id': effective_ga4,
        'ga4_source':         'env' if ga4_id_env else ('db' if ga4_id_db else 'default'),
        'gsc_verification':   gsc_env or gsc_db,
        'gsc_source':         'env' if gsc_env else ('db' if gsc_db else 'none'),
        'gtm_id':             gtm_db,
        'site_domain':        domain_db,
        'sitemap_url':        f'https://{domain_db}/sitemap.xml',
        'robots_url':         f'https://{domain_db}/robots.txt',
    }

    return render_template('superadmin/web_analytics.html',
        days=days,
        total_visits=total_visits,
        unique_sessions=unique_sessions,
        prev_visits=prev_visits,
        visits_delta=visits_delta,
        bounce_rate=bounce_rate,
        pages_per_session=pages_per_session,
        unique_countries=unique_countries,
        today_visits=today_visits,
        new_sessions=new_sessions,
        returning_sessions=returning_sessions,
        new_pct=new_pct,
        peak_hour_label=peak_hour_label,
        daily_labels=_json.dumps(daily_labels),
        daily_data=_json.dumps(daily_data),
        hourly_labels=_json.dumps(hourly_labels),
        hourly_data=_json.dumps(hourly_data),
        hourly_data_list=hourly_data,
        top_pages=top_pages,
        top_pages_labels=_json.dumps([p['page_path'][:30] for p in top_pages]),
        top_pages_data=_json.dumps([p['visits'] for p in top_pages]),
        device_labels=_json.dumps(device_labels),
        device_data=_json.dumps(device_data),
        device_pcts=device_pcts,
        browser_labels=_json.dumps(browser_labels),
        browser_data=_json.dumps(browser_data),
        os_rows=os_rows,
        top_referrers=top_referrers,
        country_rows=country_rows,
        recs=recs,
        google=google_settings,
    )


@superadmin_bp.route('/law-firms')
@require_super_admin
def manage_law_firms():
    """Manage all law firms on the platform"""
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    
    query = LawFirm.query
    if search:
        query = query.filter(
            or_(
                LawFirm.name.contains(search),
                LawFirm.email.contains(search),
                LawFirm.description.contains(search)
            )
        )
    
    law_firms = query.order_by(LawFirm.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    return render_template('superadmin/lawfirms.html', 
                         law_firms=law_firms, 
                         search=search)

@superadmin_bp.route('/law-firms/<int:firm_id>')
@require_super_admin
def view_law_firm(firm_id):
    """View detailed information about a specific law firm"""
    firm = LawFirm.query.get_or_404(firm_id)
    
    # Get firm statistics
    firm_users = User.query.filter_by(law_firm_id=firm_id).all()
    firm_admins = [u for u in firm_users if u.role == ROLE_ADMIN]
    firm_team_members = [u for u in firm_users if u.role == ROLE_TEAM_MEMBER]
    firm_clients = [u for u in firm_users if u.role == ROLE_CLIENT]
    firm_projects = Project.query.filter_by(law_firm_id=firm_id).all()
    
    return render_template('superadmin/law_firm_detail.html',
                         law_firm=firm,
                         firm=firm,
                         firm_users=firm_users,
                         firm_admins=firm_admins,
                         firm_team_members=firm_team_members,
                         firm_clients=firm_clients,
                         firm_projects=firm_projects)

@superadmin_bp.route('/create-super-admin', methods=['GET', 'POST'])
@require_super_admin
def create_super_admin():
    """Create a new super admin user"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not first_name or not last_name or not password:
            flash('All fields are required.', 'error')
            return render_template('superadmin/create_super_admin.html')
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('A user with this email already exists.', 'error')
            return render_template('superadmin/create_super_admin.html')
        
        # Create super admin user
        super_admin = User()
        super_admin.id = str(uuid.uuid4())
        super_admin.email = email
        super_admin.first_name = first_name
        super_admin.last_name = last_name
        super_admin.role = ROLE_SUPER_ADMIN
        super_admin.active = True
        super_admin.law_firm_id = None  # Super admins don't belong to any specific law firm
        super_admin.set_password(password)
        
        try:
            db.session.add(super_admin)
            db.session.commit()
            flash(f'Super admin {super_admin.full_name} created successfully!', 'success')
            return redirect(url_for('superadmin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating super admin. Please try again.', 'error')
    
    return render_template('superadmin/create_super_admin.html')

@superadmin_bp.route('/grant-admin-access', methods=['POST'])
@require_super_admin  
def grant_admin_access():
    """Grant admin access to a law firm after payment verification"""
    data = request.get_json()
    action = data.get('action')
    
    if action == 'grant_access':
        firm_id = data.get('firm_id')
        period = data.get('period', '1year')  # Default to 1 year
        
        law_firm = LawFirm.query.get_or_404(firm_id)
        
        # Find the owner/first user of the law firm
        owner = law_firm.users[0] if law_firm.users else None
        
        if not owner:
            return jsonify({
                'success': False,
                'message': 'No users found in this law firm.'
            }), 400
        
        # Calculate expiry date based on period
        from datetime import datetime, timedelta
        now = datetime.now()
        
        if period == '30days':
            expiry = now + timedelta(days=30)
        elif period == '1month':
            expiry = now + timedelta(days=30)
        elif period == '3months':
            expiry = now + timedelta(days=90)
        elif period == '6months':
            expiry = now + timedelta(days=180)
        elif period == '1year':
            expiry = now + timedelta(days=365)
        else:
            expiry = now + timedelta(days=365)  # Default to 1 year
        
        # Grant admin privileges
        owner.role = ROLE_ADMIN
        owner.active = True  # Ensure user is active when granting access
        law_firm.admin_access_granted = True
        law_firm.admin_access_expires = expiry
        law_firm.subscription_period = period
        
        try:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Admin access granted to {owner.full_name} for {law_firm.name} until {expiry.strftime("%B %d, %Y")}.'
            })
        except Exception as e:
            print(f"Error granting admin access: {e}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Error granting admin access: {str(e)}'
            }), 500
    
    elif action == 'revoke_access':
        firm_id = data.get('firm_id')
        law_firm = LawFirm.query.get_or_404(firm_id)
        
        # Find the admin user
        admin = next((u for u in law_firm.users if u.role == ROLE_ADMIN), None)
        
        if admin:
            admin.role = 'lawfirm_owner'  # Downgrade to owner
            admin.active = False  # Deactivate user when revoking access
        
        law_firm.admin_access_granted = False
        law_firm.admin_access_expires = None
        law_firm.subscription_period = None
        
        try:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Admin access revoked for {law_firm.name}.'
            })
        except Exception as e:
            print(f"Error revoking admin access: {e}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Error revoking admin access: {str(e)}'
            }), 500
    
    return jsonify({
        'success': False,
        'message': 'Invalid action.'
    }), 400

@superadmin_bp.route('/deactivate-user', methods=['POST'])
@require_super_admin
def deactivate_user():
    """Deactivate a user account"""
    data = request.get_json()
    user_id = data.get('user_id')
    
    user = User.query.get_or_404(user_id)
    
    # Deactivate the user
    user.active = False
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'{user.full_name} has been deactivated successfully.'
        })
    except Exception as e:
        print(f"Error deactivating user: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deactivating user: {str(e)}'
        }), 500

@superadmin_bp.route('/grant-admin-privileges', methods=['POST'])
@require_super_admin
def grant_admin_privileges():
    """Grant admin privileges to an existing user or create new admin"""
    data = request.get_json()
    action = data.get('action')  # 'promote' or 'create'
    
    if action == 'promote':
        user_id = data.get('user_id')
        user = User.query.get_or_404(user_id)
        
        # Promote user to admin
        user.role = ROLE_ADMIN
        
        # If user doesn't have a law firm, create one
        if not user.law_firm_id:
            user.create_law_firm_if_admin()
        
        try:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'{user.full_name} has been promoted to admin.'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'Error promoting user to admin.'
            }), 500
            
    elif action == 'create':
        email = data.get('email', '').strip().lower()
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        law_firm_name = data.get('law_firm_name', '').strip()
        password = data.get('password', '').strip()
        
        if not all([email, first_name, last_name, law_firm_name, password]):
            return jsonify({
                'success': False,
                'message': 'All fields are required.'
            }), 400
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'message': 'A user with this email already exists.'
            }), 400
        
        try:
            # Create law firm first
            new_firm = LawFirm(
                name=law_firm_name,
                description=f"Legal practice managed by {first_name} {last_name}",
                email=email,
                created_at=datetime.now()
            )
            db.session.add(new_firm)
            db.session.flush()  # Get the ID
            
            # Create admin user
            admin_user = User()
            admin_user.id = str(uuid.uuid4())
            admin_user.email = email
            admin_user.first_name = first_name
            admin_user.last_name = last_name
            admin_user.role = ROLE_ADMIN
            admin_user.active = True
            admin_user.law_firm_id = new_firm.id
            admin_user.set_password(password)
            
            db.session.add(admin_user)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Admin {admin_user.full_name} and law firm "{law_firm_name}" created successfully!'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'Error creating admin and law firm.'
            }), 500
    
    return jsonify({
        'success': False,
        'message': 'Invalid action.'
    }), 400

@superadmin_bp.route('/lawfirms')
@require_super_admin
def lawfirms():
    """Manage all law firms"""
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    
    query = LawFirm.query
    
    if search:
        query = query.filter(LawFirm.name.contains(search))
    
    law_firms = query.order_by(LawFirm.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    return render_template('superadmin/lawfirms.html',
                         law_firms=law_firms,
                         search=search)

@superadmin_bp.route('/platform-users')
@require_super_admin
def platform_users():
    """View all users across all law firms"""
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = User.query

    if search:
        query = query.filter(
            or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search)
            )
        )

    if role_filter:
        query = query.filter_by(role=role_filter)

    if status_filter == 'active':
        query = query.filter_by(active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(active=False)

    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False)

    law_firms = LawFirm.query.order_by(LawFirm.name).all()

    return render_template('superadmin/platform_users.html',
                           users=users,
                           search=search,
                           role_filter=role_filter,
                           status_filter=status_filter,
                           law_firms=law_firms,
                           now_dt=datetime.now())


@superadmin_bp.route('/users/<user_id>/set-password', methods=['POST'])
@require_super_admin
def set_user_password(user_id):
    """Reset a user's password via form from the super admin user management panel."""
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(request.referrer or url_for('superadmin.platform_users'))
    user.set_password(new_password)
    try:
        db.session.commit()
        flash(f'Password for {user.email} has been reset successfully.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error resetting password. Please try again.', 'error')
    return redirect(request.referrer or url_for('superadmin.platform_users'))


@superadmin_bp.route('/users/<user_id>/change-role', methods=['POST'])
@require_super_admin
def change_user_role(user_id):
    """Change a user's role from super admin panel."""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role', '').strip()
    valid_roles = [ROLE_CLIENT, ROLE_TEAM_MEMBER, ROLE_ADMIN, ROLE_SUPER_ADMIN]
    if new_role not in valid_roles:
        flash('Invalid role selected.', 'error')
        return redirect(request.referrer or url_for('superadmin.platform_users'))
    if user.is_super_admin() and new_role != ROLE_SUPER_ADMIN:
        flash('Cannot demote another super admin.', 'error')
        return redirect(request.referrer or url_for('superadmin.platform_users'))
    old_role = user.role
    user.role = new_role
    try:
        db.session.commit()
        flash(f'{user.full_name} role changed from {old_role.replace("_"," ").title()} to {new_role.replace("_"," ").title()}.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error changing role. Please try again.', 'error')
    return redirect(request.referrer or url_for('superadmin.platform_users'))


@superadmin_bp.route('/users/<user_id>/extend-subscription', methods=['POST'])
@require_super_admin
def extend_user_firm_subscription(user_id):
    """Extend the subscription for the law firm of a given user."""
    user = User.query.get_or_404(user_id)
    if not user.law_firm_id:
        flash('This user does not belong to a law firm.', 'error')
        return redirect(request.referrer or url_for('superadmin.platform_users'))
    firm = LawFirm.query.get_or_404(user.law_firm_id)
    period = request.form.get('period', '1year')
    period_map = {'30days': 30, '1month': 30, '3months': 90, '6months': 180, '1year': 365, '2years': 730}
    days = period_map.get(period, 365)
    now = datetime.now()
    if firm.admin_access_expires and firm.admin_access_expires > now:
        expiry = firm.admin_access_expires + timedelta(days=days)
    else:
        expiry = now + timedelta(days=days)
    firm.admin_access_granted = True
    firm.admin_access_expires = expiry
    firm.subscription_period = period
    user.active = True
    try:
        db.session.commit()
        flash(f'Subscription for {firm.name} extended until {expiry.strftime("%B %d, %Y")}.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error extending subscription.', 'error')
    return redirect(request.referrer or url_for('superadmin.platform_users'))

# ── Legal News Management (Super Admin Only) ──────────────────────────────────

NEWS_UPLOAD_FOLDER = 'static/uploads/news'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@superadmin_bp.route('/news')
@require_super_admin
def manage_news():
    news_items = (LegalNews.query
                  .order_by(LegalNews.sort_order, LegalNews.created_at.desc())
                  .all())
    return render_template('superadmin/manage_news.html', news_items=news_items)


@superadmin_bp.route('/news/add', methods=['GET', 'POST'])
@require_super_admin
def add_news():
    if request.method == 'POST':
        item = LegalNews()
        item.title       = request.form.get('title', '').strip()
        item.subtitle    = request.form.get('subtitle', '').strip()
        item.content     = request.form.get('content', '').strip()
        item.category    = request.form.get('category', 'Legal Update').strip()
        item.icon        = request.form.get('icon', 'fas fa-newspaper').strip()
        item.bg_color    = request.form.get('bg_color', '#0d1b4b').strip()
        item.link_url    = request.form.get('link_url', '').strip()
        item.link_text   = request.form.get('link_text', 'Read More').strip()
        item.sort_order  = int(request.form.get('sort_order', 0) or 0)
        item.is_active   = 'is_active' in request.form
        item.created_by_id = current_user.id

        file = request.files.get('bg_image')
        if file and file.filename and _allowed_img(file.filename):
            os.makedirs(NEWS_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(NEWS_UPLOAD_FOLDER, fname))
            item.bg_image = f"uploads/news/{fname}"

        if not item.title:
            flash('Title is required.', 'error')
            return render_template('superadmin/news_form.html', item=None, action='add')

        db.session.add(item)
        db.session.commit()
        flash('News post added successfully!', 'success')
        return redirect(url_for('superadmin.manage_news'))

    return render_template('superadmin/news_form.html', item=None, action='add')


@superadmin_bp.route('/news/<int:news_id>/edit', methods=['GET', 'POST'])
@require_super_admin
def edit_news(news_id):
    item = LegalNews.query.get_or_404(news_id)
    if request.method == 'POST':
        item.title      = request.form.get('title', '').strip()
        item.subtitle   = request.form.get('subtitle', '').strip()
        item.content    = request.form.get('content', '').strip()
        item.category   = request.form.get('category', 'Legal Update').strip()
        item.icon       = request.form.get('icon', 'fas fa-newspaper').strip()
        item.bg_color   = request.form.get('bg_color', '#0d1b4b').strip()
        item.link_url   = request.form.get('link_url', '').strip()
        item.link_text  = request.form.get('link_text', 'Read More').strip()
        item.sort_order = int(request.form.get('sort_order', 0) or 0)
        item.is_active  = 'is_active' in request.form

        file = request.files.get('bg_image')
        if file and file.filename and _allowed_img(file.filename):
            os.makedirs(NEWS_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(NEWS_UPLOAD_FOLDER, fname))
            item.bg_image = f"uploads/news/{fname}"

        if not item.title:
            flash('Title is required.', 'error')
            return render_template('superadmin/news_form.html', item=item, action='edit')

        db.session.commit()
        flash('News post updated!', 'success')
        return redirect(url_for('superadmin.manage_news'))

    return render_template('superadmin/news_form.html', item=item, action='edit')


@superadmin_bp.route('/news/<int:news_id>/delete', methods=['POST'])
@require_super_admin
def delete_news(news_id):
    item = LegalNews.query.get_or_404(news_id)
    db.session.delete(item)
    db.session.commit()
    flash('News post deleted.', 'success')
    return redirect(url_for('superadmin.manage_news'))


@superadmin_bp.route('/news/<int:news_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_news(news_id):
    item = LegalNews.query.get_or_404(news_id)
    item.is_active = not item.is_active
    db.session.commit()
    return redirect(url_for('superadmin.manage_news'))


# ── Dashboard Slider Management (Super Admin Only) ────────────────────────────

SLIDER_UPLOAD_FOLDER = 'static/uploads/sliders'

def _seed_platform_sliders():
    """Create platform-default slider slides if none exist."""
    defaults = [
        dict(title="Manage Cases Effortlessly", subtitle="All your active matters in one place",
             description="Track deadlines, documents and progress across every case.",
             cta_text="View Projects", cta_link="/projects/",
             bg_color="#0d1b4b", icon="fas fa-briefcase", sort_order=0),
        dict(title="Professional Invoicing", subtitle="Get paid faster with smart invoices",
             description="Generate beautiful PDF invoices and track payments.",
             cta_text="Go to Invoices", cta_link="/invoices/",
             bg_color="#1a3a2a", icon="fas fa-file-invoice-dollar", sort_order=1),
        dict(title="Real-Time Team Chat", subtitle="Collaborate without leaving the platform",
             description="Message your team and clients instantly.",
             cta_text="Open Chat", cta_link="/enhanced-chat/support",
             bg_color="#3a1a0d", icon="fas fa-comments", sort_order=2),
    ]
    for d in defaults:
        db.session.add(DashboardSlider(law_firm_id=None, **d))
    db.session.commit()


@superadmin_bp.route('/sliders')
@require_super_admin
def manage_sliders():
    sliders = (DashboardSlider.query
               .filter_by(law_firm_id=None)
               .order_by(DashboardSlider.sort_order)
               .all())
    if not sliders:
        _seed_platform_sliders()
        sliders = (DashboardSlider.query
                   .filter_by(law_firm_id=None)
                   .order_by(DashboardSlider.sort_order)
                   .all())
    return render_template('superadmin/manage_sliders.html', sliders=sliders)


@superadmin_bp.route('/sliders/add', methods=['GET', 'POST'])
@require_super_admin
def add_slider():
    if request.method == 'POST':
        slide = DashboardSlider()
        slide.law_firm_id = None  # Platform-wide
        slide.title       = request.form.get('title', '').strip()
        slide.subtitle    = request.form.get('subtitle', '').strip()
        slide.description = request.form.get('description', '').strip()
        slide.cta_text    = request.form.get('cta_text', 'Learn More').strip()
        slide.cta_link    = request.form.get('cta_link', '#').strip()
        slide.bg_color    = request.form.get('bg_color', '#0d1b4b').strip()
        slide.icon        = request.form.get('icon', 'fas fa-star').strip()
        slide.sort_order  = int(request.form.get('sort_order', 0) or 0)
        slide.is_active   = 'is_active' in request.form

        file = request.files.get('bg_image')
        if file and file.filename and _allowed_img(file.filename):
            os.makedirs(SLIDER_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(SLIDER_UPLOAD_FOLDER, fname))
            slide.bg_image = f"uploads/sliders/{fname}"

        if not slide.title:
            flash('Title is required.', 'error')
            return render_template('superadmin/slider_form.html', slide=None, action='add')

        db.session.add(slide)
        db.session.commit()
        flash('Slide added!', 'success')
        return redirect(url_for('superadmin.manage_sliders'))

    return render_template('superadmin/slider_form.html', slide=None, action='add')


@superadmin_bp.route('/sliders/<int:slider_id>/edit', methods=['GET', 'POST'])
@require_super_admin
def edit_slider(slider_id):
    slide = DashboardSlider.query.get_or_404(slider_id)
    if request.method == 'POST':
        slide.title       = request.form.get('title', '').strip()
        slide.subtitle    = request.form.get('subtitle', '').strip()
        slide.description = request.form.get('description', '').strip()
        slide.cta_text    = request.form.get('cta_text', 'Learn More').strip()
        slide.cta_link    = request.form.get('cta_link', '#').strip()
        slide.bg_color    = request.form.get('bg_color', '#0d1b4b').strip()
        slide.icon        = request.form.get('icon', 'fas fa-star').strip()
        slide.sort_order  = int(request.form.get('sort_order', 0) or 0)
        slide.is_active   = 'is_active' in request.form

        file = request.files.get('bg_image')
        if file and file.filename and _allowed_img(file.filename):
            os.makedirs(SLIDER_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(SLIDER_UPLOAD_FOLDER, fname))
            slide.bg_image = f"uploads/sliders/{fname}"

        if not slide.title:
            flash('Title is required.', 'error')
            return render_template('superadmin/slider_form.html', slide=slide, action='edit')

        db.session.commit()
        flash('Slide updated!', 'success')
        return redirect(url_for('superadmin.manage_sliders'))

    return render_template('superadmin/slider_form.html', slide=slide, action='edit')


@superadmin_bp.route('/sliders/<int:slider_id>/delete', methods=['POST'])
@require_super_admin
def delete_slider(slider_id):
    slide = DashboardSlider.query.get_or_404(slider_id)
    db.session.delete(slide)
    db.session.commit()
    flash('Slide deleted.', 'success')
    return redirect(url_for('superadmin.manage_sliders'))


@superadmin_bp.route('/sliders/<int:slider_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_slider(slider_id):
    slide = DashboardSlider.query.get_or_404(slider_id)
    slide.is_active = not slide.is_active
    db.session.commit()
    return redirect(url_for('superadmin.manage_sliders'))


# ── Password Reset ─────────────────────────────────────────────────────────────

@superadmin_bp.route('/users/reset-password', methods=['POST'])
@require_super_admin
def reset_user_password():
    """Super admin resets any user's password."""
    data = request.get_json()
    user_id  = data.get('user_id')
    new_pass = (data.get('new_password') or '').strip()

    if not new_pass or len(new_pass) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters.'}), 400

    user = User.query.get_or_404(user_id)
    if user.is_super_admin() and user.id != current_user.id:
        return jsonify({'success': False, 'message': 'Cannot reset another super-admin\'s password.'}), 403

    user.set_password(new_pass)
    user.failed_login_attempts = 0
    user.locked_until = None
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': f'Password for {user.email} has been reset.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Delete Law Firm ────────────────────────────────────────────────────────────

@superadmin_bp.route('/law-firms/<int:firm_id>/delete', methods=['POST'])
@require_super_admin
def delete_law_firm(firm_id):
    """Permanently delete a law firm and ALL associated data."""
    firm = LawFirm.query.get_or_404(firm_id)
    firm_name = firm.name
    try:
        # Nullify user FK references before deleting (users stay, unattached)
        for u in list(firm.users):
            u.law_firm_id = None
            if u.role == ROLE_ADMIN:
                u.role = ROLE_CLIENT  # downgrade
        db.session.flush()

        db.session.delete(firm)
        db.session.commit()
        flash(f'Law firm "{firm_name}" and all its data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting law firm: {e}', 'error')
    return redirect(url_for('superadmin.manage_law_firms'))


# ── Extend / Modify Subscription ───────────────────────────────────────────────

@superadmin_bp.route('/bulk-grant-trial', methods=['POST'])
@require_super_admin
def bulk_grant_trial():
    """Grant a 14-day free trial (from today) to ALL law firms."""
    trial_end = datetime.now() + timedelta(days=14)
    firms = LawFirm.query.all()
    count = 0
    for firm in firms:
        firm.admin_access_granted = True
        firm.admin_access_expires = trial_end
        firm.subscription_period  = '14days'
        count += 1
    try:
        db.session.commit()
        flash(f'✅ 2-week free trial granted to {count} law firm(s). Access expires {trial_end.strftime("%B %d, %Y")}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error granting trials: {e}', 'danger')
    return redirect(url_for('superadmin.dashboard'))


@superadmin_bp.route('/law-firms/<int:firm_id>/extend-subscription', methods=['POST'])
@require_super_admin
def extend_subscription(firm_id):
    """Extend or change a law firm's subscription period."""
    firm   = LawFirm.query.get_or_404(firm_id)
    data   = request.get_json()
    period = data.get('period', '1year')
    action = data.get('action', 'extend')   # extend | set

    period_map = {
        '30days': 30, '1month': 30, '3months': 90,
        '6months': 180, '1year': 365, '2years': 730
    }
    days = period_map.get(period, 365)

    now = datetime.now()
    if action == 'extend' and firm.admin_access_expires and firm.admin_access_expires > now:
        expiry = firm.admin_access_expires + timedelta(days=days)
    else:
        expiry = now + timedelta(days=days)

    firm.admin_access_granted = True
    firm.admin_access_expires = expiry
    firm.subscription_period  = period

    # Also make sure the admin user is active
    admin = next((u for u in firm.users if u.role == ROLE_ADMIN), None)
    if admin:
        admin.active = True

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Subscription {"extended" if action == "extend" else "set"} until {expiry.strftime("%B %d, %Y")} for {firm.name}.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Notifications ──────────────────────────────────────────────────────────────

@superadmin_bp.route('/notifications')
@require_super_admin
def notifications():
    """View all platform notifications sent to law firms."""
    page = request.args.get('page', 1, type=int)
    notifs = (PlatformNotification.query
              .order_by(PlatformNotification.sent_at.desc())
              .paginate(page=page, per_page=30, error_out=False))
    law_firms = LawFirm.query.order_by(LawFirm.name).all()
    return render_template('superadmin/notifications.html',
                           notifs=notifs, law_firms=law_firms)


@superadmin_bp.route('/notifications/send', methods=['POST'])
@require_super_admin
def send_notification():
    """Send a manual notification to one firm or broadcast to all."""
    data    = request.get_json()
    title   = (data.get('title') or '').strip()
    message = (data.get('message') or '').strip()
    firm_id = data.get('firm_id')          # None / '' = broadcast
    notif_type = data.get('notification_type', NOTIF_TYPE_GENERAL)

    if not title or not message:
        return jsonify({'success': False, 'message': 'Title and message are required.'}), 400

    try:
        if firm_id:
            notif = PlatformNotification(
                law_firm_id=int(firm_id),
                sent_by_id=current_user.id,
                title=title,
                message=message,
                notification_type=notif_type,
                is_auto=False,
            )
            db.session.add(notif)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Notification sent to the selected law firm.'})
        else:
            # Broadcast – one record per firm
            firms = LawFirm.query.all()
            for firm in firms:
                notif = PlatformNotification(
                    law_firm_id=firm.id,
                    sent_by_id=current_user.id,
                    title=title,
                    message=message,
                    notification_type=notif_type,
                    is_auto=False,
                )
                db.session.add(notif)
            db.session.commit()
            return jsonify({'success': True, 'message': f'Broadcast sent to {len(firms)} law firms.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@superadmin_bp.route('/notifications/auto-renewal', methods=['POST'])
@require_super_admin
def auto_renewal_notifications():
    """
    Check all active subscriptions and automatically send renewal-reminder
    notifications to firms that expire within 7 days or are already expired.
    """
    now      = datetime.now()
    warning  = now + timedelta(days=7)
    sent     = 0
    skipped  = 0

    firms = LawFirm.query.filter(LawFirm.admin_access_granted == True).all()
    for firm in firms:
        if not firm.admin_access_expires:
            continue

        days_left = (firm.admin_access_expires - now).days

        if firm.admin_access_expires < now:
            # Already expired
            notif_type = NOTIF_TYPE_SUSPENDED
            title = '⚠️ Subscription Expired'
            msg   = (f'Your LawColab subscription for {firm.name} expired on '
                     f'{firm.admin_access_expires.strftime("%B %d, %Y")}. '
                     f'Please renew to restore full access.')
        elif firm.admin_access_expires <= warning:
            # Expiring soon
            notif_type = NOTIF_TYPE_EXPIRY
            title = f'🔔 Subscription Expires in {days_left} Day{"s" if days_left != 1 else ""}'
            msg   = (f'Your LawColab subscription for {firm.name} will expire on '
                     f'{firm.admin_access_expires.strftime("%B %d, %Y")}. '
                     f'Contact us to renew and avoid service interruption.')
        else:
            skipped += 1
            continue

        # Avoid duplicate auto-notifications sent in the last 24 hours
        recent = PlatformNotification.query.filter(
            PlatformNotification.law_firm_id == firm.id,
            PlatformNotification.is_auto == True,
            PlatformNotification.notification_type == notif_type,
            PlatformNotification.sent_at >= now - timedelta(hours=24)
        ).first()
        if recent:
            skipped += 1
            continue

        notif = PlatformNotification(
            law_firm_id=firm.id,
            sent_by_id=current_user.id,
            title=title,
            message=msg,
            notification_type=notif_type,
            is_auto=True,
        )
        db.session.add(notif)
        sent += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Auto-renewal check complete. {sent} notification(s) sent, {skipped} skipped.'
    })


@superadmin_bp.route('/notifications/<int:notif_id>/delete', methods=['POST'])
@require_super_admin
def delete_notification(notif_id):
    notif = PlatformNotification.query.get_or_404(notif_id)
    db.session.delete(notif)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('superadmin.notifications'))


# ── Database Overview ──────────────────────────────────────────────────────────

@superadmin_bp.route('/database-overview')
@require_super_admin
def database_overview():
    """Show row counts and basic health stats for all tables."""
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(db.engine)
    table_names = sorted(insp.get_table_names())

    table_stats = []
    for tname in table_names:
        try:
            count = db.session.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar()
        except Exception:
            count = 'N/A'
        table_stats.append({'table': tname, 'rows': count})

    # Summary health stats
    now = datetime.now()
    active_subs    = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires > now
    ).count()
    expired_subs   = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires <= now
    ).count()
    expiring_soon  = LawFirm.query.filter(
        LawFirm.admin_access_granted == True,
        LawFirm.admin_access_expires > now,
        LawFirm.admin_access_expires <= now + timedelta(days=7)
    ).count()
    pending_access = LawFirm.query.filter_by(admin_access_granted=False).count()

    health = {
        'active_subscriptions': active_subs,
        'expired_subscriptions': expired_subs,
        'expiring_soon': expiring_soon,
        'pending_access': pending_access,
        'total_notifications': PlatformNotification.query.count(),
    }

    return render_template('superadmin/database_overview.html',
                           table_stats=table_stats, health=health)


# ─── Admin Notifications ──────────────────────────────────────────────────────

@superadmin_bp.route('/notifications')
@require_super_admin
def admin_notifications():
    """Super admin notifications: robot discoveries, claim requests, etc."""
    from models import AdminNotification
    notifications = AdminNotification.query.order_by(
        AdminNotification.is_read.asc(),
        AdminNotification.created_at.desc()
    ).limit(100).all()
    unread_count = AdminNotification.query.filter_by(is_read=False).count()
    return render_template('superadmin/admin_notifications.html',
                           notifications=notifications,
                           unread_count=unread_count)


@superadmin_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@require_super_admin
def mark_notification_read(notif_id):
    from models import AdminNotification
    notif = AdminNotification.query.get_or_404(notif_id)
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@superadmin_bp.route('/notifications/read-all', methods=['POST'])
@require_super_admin
def mark_all_notifications_read():
    from models import AdminNotification
    AdminNotification.query.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@superadmin_bp.route('/notifications/count')
@require_super_admin
def notifications_count():
    from models import AdminNotification
    count = AdminNotification.query.filter_by(is_read=False).count()
    return jsonify({'count': count})


# ── Google / SEO Settings helpers ────────────────────────────────────────────

def _get_site_setting(key: str, default: str = '') -> str:
    """Read one value from the site_settings table."""
    try:
        row = db.session.execute(
            text("SELECT value FROM site_settings WHERE key = :k"), {"k": key}
        ).fetchone()
        return row[0] if row and row[0] else default
    except Exception:
        return default


def _set_site_setting(key: str, value: str) -> None:
    """Upsert a value in site_settings (works with SQLite and PostgreSQL)."""
    try:
        now_ts = datetime.now()
        existing = db.session.execute(
            text("SELECT key FROM site_settings WHERE key = :k"), {"k": key}
        ).fetchone()
        if existing:
            db.session.execute(
                text("UPDATE site_settings SET value = :v, updated_at = :t WHERE key = :k"),
                {"k": key, "v": value, "t": now_ts}
            )
        else:
            db.session.execute(
                text("INSERT INTO site_settings (key, value, updated_at) VALUES (:k, :v, :t)"),
                {"k": key, "v": value, "t": now_ts}
            )
        db.session.commit()
    except Exception:
        db.session.rollback()


@superadmin_bp.route('/google-settings', methods=['POST'])
@require_super_admin
def save_google_settings():
    """Save GA4 / GSC / GTM settings to the database."""
    ga4_id      = request.form.get('ga4_measurement_id', '').strip()
    gsc_code    = request.form.get('gsc_verification', '').strip()
    gtm_id      = request.form.get('gtm_id', '').strip()
    site_domain = request.form.get('site_domain', '').strip()

    if ga4_id:
        _set_site_setting('ga4_measurement_id', ga4_id)
    if gsc_code:
        _set_site_setting('gsc_verification', gsc_code)
    if gtm_id:
        _set_site_setting('gtm_id', gtm_id)
    if site_domain:
        _set_site_setting('site_domain', site_domain)

    flash('Google settings saved successfully!', 'success')
    return redirect(url_for('superadmin.web_analytics', days=30, _anchor='google-settings'))


# ─────────────────────────────────────────────────────────────────────────────
# Contact Inquiries Inbox
# ─────────────────────────────────────────────────────────────────────────────

def _ci_row(row):
    """Convert a RowMapping to a plain dict."""
    return dict(row._mapping) if hasattr(row, '_mapping') else dict(row)


@superadmin_bp.route('/contact-inbox')
@require_super_admin
def contact_inbox():
    """Super admin contact inquiries inbox."""
    status_filter = request.args.get('status', 'all')
    search = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 20

    where_clauses = []
    params = {}

    if status_filter != 'all':
        where_clauses.append("status = :status")
        params['status'] = status_filter

    if search:
        where_clauses.append("""
            (lower(first_name) LIKE :q OR lower(last_name) LIKE :q
             OR lower(email) LIKE :q OR lower(company) LIKE :q
             OR lower(inquiry_type) LIKE :q OR lower(message) LIKE :q)
        """)
        params['q'] = f'%{search.lower()}%'

    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

    total = db.session.execute(
        text(f"SELECT COUNT(*) FROM contact_inquiries {where_sql}"), params
    ).scalar() or 0

    offset = (page - 1) * per_page
    rows = db.session.execute(
        text(f"""
            SELECT * FROM contact_inquiries {where_sql}
            ORDER BY created_at DESC LIMIT :lim OFFSET :off
        """), {**params, 'lim': per_page, 'off': offset}
    ).fetchall()

    inquiries = [_ci_row(r) for r in rows]

    # Counts per status
    counts = {}
    for s in ('new', 'in_progress', 'resolved'):
        counts[s] = db.session.execute(
            text("SELECT COUNT(*) FROM contact_inquiries WHERE status = :s"), {'s': s}
        ).scalar() or 0
    counts['all'] = total if status_filter == 'all' else (
        db.session.execute(text("SELECT COUNT(*) FROM contact_inquiries")).scalar() or 0
    )

    total_pages = max(1, (counts['all'] + per_page - 1) // per_page) if status_filter == 'all' else max(1, (total + per_page - 1) // per_page)

    return render_template(
        'superadmin/contact_inquiries.html',
        inquiries=inquiries,
        status_filter=status_filter,
        search=search,
        page=page,
        total_pages=total_pages,
        counts=counts,
    )


@superadmin_bp.route('/contact-inbox/<int:inquiry_id>')
@require_super_admin
def contact_inbox_detail(inquiry_id):
    """View a single contact inquiry with email thread."""
    row = db.session.execute(
        text("SELECT * FROM contact_inquiries WHERE id = :id"), {'id': inquiry_id}
    ).fetchone()
    if not row:
        flash('Inquiry not found.', 'error')
        return redirect(url_for('superadmin.contact_inbox'))

    inquiry = _ci_row(row)

    # Mark as in_progress if still new
    if inquiry['status'] == 'new':
        db.session.execute(
            text("UPDATE contact_inquiries SET status='in_progress', updated_at=NOW() WHERE id=:id"),
            {'id': inquiry_id}
        )
        db.session.commit()
        inquiry['status'] = 'in_progress'

    emails = [_ci_row(r) for r in db.session.execute(
        text("SELECT * FROM contact_inquiry_emails WHERE inquiry_id=:id ORDER BY sent_at ASC"),
        {'id': inquiry_id}
    ).fetchall()]

    return render_template(
        'superadmin/contact_inquiries.html',
        detail_inquiry=inquiry,
        detail_emails=emails,
        inquiries=[],
        status_filter='all',
        search='',
        page=1,
        total_pages=1,
        counts={'all': 0, 'new': 0, 'in_progress': 0, 'resolved': 0},
    )


@superadmin_bp.route('/contact-inbox/<int:inquiry_id>/send-email', methods=['POST'])
@require_super_admin
def contact_inbox_send_email(inquiry_id):
    """Send an email reply to a contact inquiry submitter."""
    from utils.email_sender import send_email

    row = db.session.execute(
        text("SELECT * FROM contact_inquiries WHERE id = :id"), {'id': inquiry_id}
    ).fetchone()
    if not row:
        return jsonify({'success': False, 'error': 'Inquiry not found'}), 404

    inquiry = _ci_row(row)
    subject = request.form.get('subject', '').strip()
    body_text = request.form.get('body_text', '').strip()

    if not subject or not body_text:
        flash('Subject and message body are required.', 'error')
        return redirect(url_for('superadmin.contact_inbox_detail', inquiry_id=inquiry_id))

    body_html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;">
      <div style="background:#0d1b4b;padding:24px 32px;border-radius:12px 12px 0 0;">
        <img src="https://lawcolab.com/static/img/logo-light.png" alt="LAWCOLAB" height="36"
             onerror="this.style.display='none'" style="margin-bottom:8px;">
        <p style="color:#FFD700;font-size:13px;margin:0;font-weight:700;">LAWCOLAB GLOBAL</p>
      </div>
      <div style="background:#ffffff;padding:32px;border:1px solid #e2e8f0;">
        <p style="color:#374151;font-size:15px;line-height:1.7;white-space:pre-line;">{body_text}</p>
      </div>
      <div style="background:#f8faff;padding:16px 32px;border:1px solid #e2e8f0;border-top:none;
                  border-radius:0 0 12px 12px;font-size:12px;color:#64748b;">
        This email was sent from <strong>LAWCOLAB</strong> in reply to your enquiry.<br>
        Contact us: <a href="mailto:info@lawcolab.com" style="color:#0d1b4b;">info@lawcolab.com</a>
      </div>
    </div>
    """

    result = send_email(
        to_email=inquiry['email'],
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        from_name='LAWCOLAB Team',
    )

    sent_by = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email

    db.session.execute(text("""
        INSERT INTO contact_inquiry_emails
            (inquiry_id, direction, subject, body_html, body_text,
             sent_by_name, provider, success, error_msg, sent_at)
        VALUES (:iid, 'out', :sub, :bh, :bt, :sb, :prov, :ok, :err, NOW())
    """), dict(
        iid=inquiry_id, sub=subject, bh=body_html, bt=body_text,
        sb=sent_by, prov=result.get('provider', 'unknown'),
        ok=result.get('success', False),
        err=result.get('error')
    ))

    # Update status + timestamp
    db.session.execute(
        text("UPDATE contact_inquiries SET updated_at=NOW() WHERE id=:id"),
        {'id': inquiry_id}
    )
    db.session.commit()

    if result.get('success'):
        flash(f'Email sent to {inquiry["email"]} successfully!', 'success')
    else:
        flash(f'Email queued (provider: {result.get("provider")}). Error: {result.get("error") or "none"}', 'warning')

    return redirect(url_for('superadmin.contact_inbox_detail', inquiry_id=inquiry_id))


@superadmin_bp.route('/contact-inbox/<int:inquiry_id>/update-status', methods=['POST'])
@require_super_admin
def contact_inbox_update_status(inquiry_id):
    """Update the status and/or notes of a contact inquiry."""
    new_status = request.form.get('status', '').strip()
    notes = request.form.get('notes', '').strip()

    updates = {}
    if new_status in ('new', 'in_progress', 'resolved'):
        updates['status'] = new_status
    if notes is not None:
        updates['notes'] = notes or None

    if updates:
        set_parts = ', '.join(f"{k}=:{k}" for k in updates)
        db.session.execute(
            text(f"UPDATE contact_inquiries SET {set_parts}, updated_at=NOW() WHERE id=:id"),
            {**updates, 'id': inquiry_id}
        )
        db.session.commit()
        flash('Inquiry updated.', 'success')

    return redirect(url_for('superadmin.contact_inbox_detail', inquiry_id=inquiry_id))


@superadmin_bp.route('/contact-inbox/<int:inquiry_id>/delete', methods=['POST'])
@require_super_admin
def contact_inbox_delete(inquiry_id):
    """Delete a contact inquiry."""
    db.session.execute(
        text("DELETE FROM contact_inquiries WHERE id=:id"), {'id': inquiry_id}
    )
    db.session.commit()
    flash('Inquiry deleted.', 'success')
    return redirect(url_for('superadmin.contact_inbox'))
