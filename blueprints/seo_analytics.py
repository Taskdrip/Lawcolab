"""
LAWCOLAB SEO & Analytics Dashboard — /superadmin/analytics
Tracks page views, devices, countries (via IP), referrers, bounce.
AI robot analyses the data and produces recommendations.
"""
from flask import Blueprint, render_template, request, jsonify
from app import db
from sqlalchemy import text
from utils.decorators import require_super_admin
from datetime import datetime, timedelta
import json, logging

logger = logging.getLogger(__name__)
seo_analytics_bp = Blueprint('seo_analytics', __name__)

GTM_ID = 'GTM-TVF3MJPP'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _q(sql, params=None):
    try:
        rows = db.session.execute(text(sql), params or {}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _scalar(sql, params=None):
    try:
        return db.session.execute(text(sql), params or {}).scalar() or 0
    except Exception:
        return 0


def _date_range(days):
    end   = datetime.now()
    start = end - timedelta(days=days)
    return start, end


# ── Main Dashboard ─────────────────────────────────────────────────────────────

@seo_analytics_bp.route('/')
@require_super_admin
def dashboard():
    period = request.args.get('period', '30', type=str)
    days   = int(period) if period.isdigit() else 30
    start, end = _date_range(days)

    # ── Totals ──
    total_views   = _scalar("SELECT COUNT(*) FROM page_analytics WHERE created_at >= :s", {"s": start})
    unique_sess   = _scalar("SELECT COUNT(DISTINCT session_id) FROM page_analytics WHERE created_at >= :s", {"s": start})
    total_prev    = _scalar("SELECT COUNT(*) FROM page_analytics WHERE created_at >= :s AND created_at < :e",
                            {"s": start - timedelta(days=days), "e": start})
    unique_prev   = _scalar("SELECT COUNT(DISTINCT session_id) FROM page_analytics WHERE created_at >= :s AND created_at < :e",
                            {"s": start - timedelta(days=days), "e": start})

    views_change  = round(((total_views - total_prev) / max(total_prev, 1)) * 100, 1)
    unique_change = round(((unique_sess - unique_prev) / max(unique_prev, 1)) * 100, 1)

    # ── Bounce rate (sessions with only 1 page view) ──
    bounce_sessions = _scalar("""
        SELECT COUNT(*) FROM (
            SELECT session_id FROM page_analytics
            WHERE created_at >= :s GROUP BY session_id HAVING COUNT(*) = 1
        ) x
    """, {"s": start})
    bounce_rate = round((bounce_sessions / max(unique_sess, 1)) * 100, 1)

    # ── Avg pages per session ──
    avg_pages = round(total_views / max(unique_sess, 1), 2)

    # ── Daily trend (last `days`) ──
    daily_trend = []
    for i in range(days - 1, -1, -1):
        d = datetime.now() - timedelta(days=i)
        ds = d.replace(hour=0, minute=0, second=0, microsecond=0)
        de = ds + timedelta(days=1)
        v = _scalar("SELECT COUNT(*) FROM page_analytics WHERE created_at>=:s AND created_at<:e",
                    {"s": ds, "e": de})
        u = _scalar("SELECT COUNT(DISTINCT session_id) FROM page_analytics WHERE created_at>=:s AND created_at<:e",
                    {"s": ds, "e": de})
        daily_trend.append({"date": ds.strftime("%b %d"), "views": v, "unique": u})

    # ── Top pages ──
    top_pages = _q("""
        SELECT page_path AS path, COUNT(*) as views, COUNT(DISTINCT session_id) as unique_v
        FROM page_analytics WHERE created_at >= :s
        GROUP BY page_path ORDER BY views DESC LIMIT 15
    """, {"s": start})

    # ── Device breakdown ──
    devices = _q("""
        SELECT device_type, COUNT(*) as cnt
        FROM page_analytics WHERE created_at >= :s
        GROUP BY device_type ORDER BY cnt DESC
    """, {"s": start})

    # ── Top referrers (extract domain from referrer URL) ──
    referrers = _q("""
        SELECT COALESCE(NULLIF(
            CASE WHEN referrer ~ '^https?://'
                 THEN regexp_replace(regexp_replace(referrer, '^https?://([^/?#]*).*', '\\1'), '^www\\.', '')
                 ELSE '' END
        , ''), 'Direct') as src, COUNT(*) as cnt
        FROM page_analytics WHERE created_at >= :s
        GROUP BY src ORDER BY cnt DESC LIMIT 10
    """, {"s": start})

    # ── Top countries ──
    countries = _q("""
        SELECT COALESCE(NULLIF(country,''),'Unknown') as country, COUNT(*) as cnt
        FROM page_analytics WHERE created_at >= :s
        GROUP BY country ORDER BY cnt DESC LIMIT 10
    """, {"s": start})

    # ── Browser ──
    browsers = _q("""
        SELECT COALESCE(NULLIF(browser,''),'Other') as browser, COUNT(*) as cnt
        FROM page_analytics WHERE created_at >= :s
        GROUP BY browser ORDER BY cnt DESC LIMIT 8
    """, {"s": start})

    # ── Blog stats ──
    blog_views  = _scalar("SELECT COALESCE(SUM(view_count),0) FROM blog_posts WHERE published=TRUE")
    blog_posts  = _scalar("SELECT COUNT(*) FROM blog_posts WHERE published=TRUE")
    blog_comments = _scalar("SELECT COUNT(*) FROM blog_comments WHERE approved=TRUE")

    # ── AI Recommendations ──
    ai_recs = _generate_ai_recommendations(
        total_views=total_views, unique_sess=unique_sess,
        bounce_rate=bounce_rate, avg_pages=avg_pages,
        devices=devices, top_pages=top_pages,
        referrers=referrers, days=days
    )

    return render_template('seo_analytics/dashboard.html',
        gtm_id=GTM_ID, period=str(days),
        total_views=total_views, unique_sess=unique_sess,
        views_change=views_change, unique_change=unique_change,
        bounce_rate=bounce_rate, avg_pages=avg_pages,
        daily_trend=json.dumps(daily_trend),
        top_pages=top_pages, devices=devices,
        referrers=referrers, countries=countries,
        browsers=browsers,
        blog_views=blog_views, blog_posts=blog_posts, blog_comments=blog_comments,
        ai_recs=ai_recs,
    )


@seo_analytics_bp.route('/track', methods=['POST'])
def track():
    """Called client-side to log a page view event."""
    data = request.json or {}
    path    = (data.get('path') or request.referrer or '/')[:500]
    ref     = (data.get('referrer') or '')[:500]
    sid     = (data.get('session_id') or request.cookies.get('_lc_sid', ''))[:64]
    ua      = request.headers.get('User-Agent', '')[:500]
    ip      = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()[:45]

    device  = _detect_device(ua)
    browser = _detect_browser(ua)
    import hashlib
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:64] if ip else ''

    try:
        db.session.execute(text("""
            INSERT INTO page_analytics
            (page_path, session_id, referrer, ip_hash,
             device_type, browser, country, created_at)
            VALUES (:page_path,:sid,:ref,:ip_hash,:device,:browser,:country,NOW())
        """), dict(page_path=path, sid=sid, ref=ref, ip_hash=ip_hash,
                   device=device, browser=browser, country=''))
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@seo_analytics_bp.route('/ai-refresh', methods=['POST'])
@require_super_admin
def ai_refresh():
    """Re-run AI analysis on demand."""
    days = request.json.get('days', 30)
    start = datetime.now() - timedelta(days=days)

    total_views   = _scalar("SELECT COUNT(*) FROM page_analytics WHERE created_at >= :s", {"s": start})
    unique_sess   = _scalar("SELECT COUNT(DISTINCT session_id) FROM page_analytics WHERE created_at >= :s", {"s": start})
    bounce_s      = _scalar("SELECT COUNT(*) FROM (SELECT session_id FROM page_analytics WHERE created_at>=:s GROUP BY session_id HAVING COUNT(*)=1) x", {"s": start})
    bounce_rate   = round((bounce_s / max(unique_sess, 1)) * 100, 1)
    avg_pages     = round(total_views / max(unique_sess, 1), 2)
    devices       = _q("SELECT device_type, COUNT(*) as cnt FROM page_analytics WHERE created_at>=:s GROUP BY device_type ORDER BY cnt DESC", {"s": start})
    top_pages     = _q("SELECT page_path AS path, COUNT(*) as views FROM page_analytics WHERE created_at>=:s GROUP BY page_path ORDER BY views DESC LIMIT 10", {"s": start})
    referrers     = _q("""SELECT COALESCE(NULLIF(
            CASE WHEN referrer ~ '^https?://'
                 THEN regexp_replace(regexp_replace(referrer, '^https?://([^/?#]*).*', '\\1'), '^www\\.', '')
                 ELSE '' END
        , ''), 'Direct') as src, COUNT(*) as cnt FROM page_analytics WHERE created_at>=:s GROUP BY src ORDER BY cnt DESC LIMIT 5""", {"s": start})

    recs = _generate_ai_recommendations(
        total_views=total_views, unique_sess=unique_sess,
        bounce_rate=bounce_rate, avg_pages=avg_pages,
        devices=devices, top_pages=top_pages, referrers=referrers, days=days
    )
    return jsonify({'recommendations': recs})


# ── AI Recommendation Engine ───────────────────────────────────────────────────

def _generate_ai_recommendations(total_views, unique_sess, bounce_rate, avg_pages,
                                   devices, top_pages, referrers, days):
    recs = []

    # Bounce rate analysis
    if bounce_rate > 70:
        recs.append({
            "type": "warning",
            "icon": "fas fa-exclamation-triangle",
            "title": f"High Bounce Rate ({bounce_rate}%)",
            "detail": "Over 70% of visitors leave after viewing only one page. Improve internal linking, add a clear CTA above the fold, and ensure page load time is under 3 seconds.",
            "priority": "high",
            "actions": ["Add related content links", "Improve page load speed", "Add prominent CTA buttons"]
        })
    elif bounce_rate > 50:
        recs.append({
            "type": "info",
            "icon": "fas fa-info-circle",
            "title": f"Moderate Bounce Rate ({bounce_rate}%)",
            "detail": "Bounce rate is acceptable but improvable. Consider adding an email capture popup or a featured content sidebar.",
            "priority": "medium",
            "actions": ["Add newsletter signup", "Feature related blog posts", "Improve page descriptions"]
        })
    else:
        recs.append({
            "type": "success",
            "icon": "fas fa-check-circle",
            "title": f"Good Bounce Rate ({bounce_rate}%)",
            "detail": "Visitors are engaging with multiple pages. Keep creating valuable internal links.",
            "priority": "low",
            "actions": ["Continue publishing blog content", "Maintain internal linking"]
        })

    # Mobile vs Desktop
    mobile_cnt = sum(d['cnt'] for d in devices if d.get('device_type') == 'mobile')
    total_dev  = sum(d['cnt'] for d in devices) or 1
    mobile_pct = round(mobile_cnt / total_dev * 100, 1)
    if mobile_pct > 60:
        recs.append({
            "type": "info",
            "icon": "fas fa-mobile-alt",
            "title": f"Mobile-First Audience ({mobile_pct}% mobile)",
            "detail": "The majority of your visitors are on mobile. Prioritise mobile page speed (Core Web Vitals), ensure all forms and CTAs are thumb-friendly, and test on small screens regularly.",
            "priority": "high",
            "actions": ["Run Google PageSpeed Insights on mobile", "Check tap target sizes", "Compress hero images for mobile"]
        })

    # Traffic volume
    if total_views == 0:
        recs.append({
            "type": "warning",
            "icon": "fas fa-chart-line",
            "title": "No Traffic Data Yet",
            "detail": "The internal tracker has just been installed. Data will start appearing as visitors arrive. Make sure GTM-TVF3MJPP is firing on all pages.",
            "priority": "high",
            "actions": ["Verify GTM container is published", "Submit sitemap to Google Search Console", "Share your URL on LinkedIn and WhatsApp"]
        })
    elif total_views < 100:
        recs.append({
            "type": "warning",
            "icon": "fas fa-seedling",
            "title": f"Low Traffic Volume ({total_views} views in {days} days)",
            "detail": "Your site needs more organic visibility. Focus on publishing blog posts targeting legal keywords in Nigeria and Africa.",
            "priority": "high",
            "actions": [
                "Publish 2 blog posts per week on legal tech topics",
                "Submit sitemap.xml to Google Search Console",
                f"Share every new post on LinkedIn, WhatsApp, and Twitter",
                "Add lawcolab.com to Nigerian law directories"
            ]
        })
    elif total_views > 5000:
        recs.append({
            "type": "success",
            "icon": "fas fa-rocket",
            "title": f"Strong Traffic ({total_views:,} views in {days} days)",
            "detail": "Great traction! Focus on conversion — ensure CTAs are prominent on high-traffic pages.",
            "priority": "low",
            "actions": ["Add retargeting pixels via GTM", "A/B test CTAs on top pages", "Set up conversion goals in GA4"]
        })

    # Top pages quality
    if top_pages:
        top = top_pages[0]
        recs.append({
            "type": "info",
            "icon": "fas fa-star",
            "title": f"Top Page: {top.get('path', '/')}",
            "detail": f"This page drives the most traffic ({top.get('views',0)} views). Ensure it has a strong CTA, fast load time, and links to your signup/trial page.",
            "priority": "medium",
            "actions": [f"Add a CTA on {top.get('path','/')}", "Improve meta description for this page", "Add internal links to related pages"]
        })

    # Referrer analysis
    direct_sources = [r for r in referrers if r.get('src') == 'Direct']
    direct_pct = round((direct_sources[0]['cnt'] / max(total_views, 1)) * 100, 1) if direct_sources else 0
    if direct_pct > 60:
        recs.append({
            "type": "info",
            "icon": "fas fa-share-alt",
            "title": f"Heavy Direct Traffic ({direct_pct}%)",
            "detail": "Most visitors type your URL directly or arrive with no referrer — great for brand recall! To diversify, focus on SEO and social sharing.",
            "priority": "medium",
            "actions": ["Publish on LinkedIn", "Guest post on legal blogs", "Optimise for 'law firm software Nigeria' keyword"]
        })

    # SEO recommendations (always-on)
    recs.append({
        "type": "seo",
        "icon": "fas fa-search",
        "title": "SEO Quick Wins",
        "detail": "Core SEO actions that increase Google rankings for Nigerian law firm searches.",
        "priority": "medium",
        "actions": [
            "Submit https://lawcolab.com/sitemap.xml in Google Search Console",
            "Ensure every page has a unique <title> and meta description",
            "Target long-tail keywords: 'law firm case management software Nigeria'",
            "Add alt text to all images",
            "Build backlinks from Nigerian Bar Association and legal blogs"
        ]
    })

    # GTM / GA4 integration tip
    recs.append({
        "type": "gtm",
        "icon": "fas fa-tag",
        "title": "GTM Container Active (GTM-TVF3MJPP)",
        "detail": "Google Tag Manager is installed. Add a GA4 Configuration tag inside GTM to unlock full Google Analytics reporting, goals, and audience tracking.",
        "priority": "medium",
        "actions": [
            "In GTM: New Tag → GA4 Configuration → enter your G-XXXXXXXX Measurement ID",
            "Set trigger: All Pages",
            "Publish the container",
            "Verify in GA4 → Real-time reports"
        ]
    })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r.get("priority", "medium"), 1))
    return recs


# ── UA parsing helpers ─────────────────────────────────────────────────────────

def _detect_device(ua: str) -> str:
    ua = ua.lower()
    if any(x in ua for x in ('ipad', 'tablet', 'kindle')):
        return 'tablet'
    if any(x in ua for x in ('mobile', 'android', 'iphone', 'ipod', 'blackberry', 'windows phone')):
        return 'mobile'
    return 'desktop'


def _detect_browser(ua: str) -> str:
    ua_l = ua.lower()
    if 'edg' in ua_l:    return 'Edge'
    if 'opr' in ua_l or 'opera' in ua_l: return 'Opera'
    if 'chrome' in ua_l: return 'Chrome'
    if 'firefox' in ua_l: return 'Firefox'
    if 'safari' in ua_l: return 'Safari'
    if 'msie' in ua_l or 'trident' in ua_l: return 'IE'
    return 'Other'


def _extract_domain(url: str) -> str:
    if not url:
        return ''
    try:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return d.replace('www.', '')[:100]
    except Exception:
        return ''
