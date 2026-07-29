"""
LawColab — Research Robot / CRM Grabber Browser
Mounted at /superadmin/research-robot

Features:
  • Keyword search across Google GMB, Facebook, LinkedIn, Reddit, Quora, YouTube, Web
  • Scrape and stage results (GrabbedResult) for review
  • One-click push to DirectoryLawFirm (CRM) or SocialCommunity
  • In-app social engagement tracker (comments / posts / shares)
  • Session history with stats
"""
from flask import (Blueprint, render_template, request, jsonify, redirect,
                   url_for, flash, Response)
from flask_login import current_user
from app import db
from models import DirectoryLawFirm, SocialCommunity
from models_grabber import ResearchSession, GrabbedResult, SocialEngagement, PostTemplate
from utils.decorators import require_super_admin
from utils.scraper_engine import (
    search_communities, search_gmb_listings, search_quora, search_web,
    search_twitter_x, search_ask_the_public, search_reddit_threads,
    extract_page_contacts,
)
from datetime import datetime
from sqlalchemy import desc, func
import json
import csv
import io
import logging
import requests

logger = logging.getLogger(__name__)

research_robot_bp = Blueprint("research_robot", __name__)

PLATFORM_META = {
    "facebook":   {"label": "Facebook",   "icon": "facebook",    "color": "#1877F2"},
    "linkedin":   {"label": "LinkedIn",   "icon": "linkedin",    "color": "#0A66C2"},
    "reddit":     {"label": "Reddit",     "icon": "reddit",      "color": "#FF4500"},
    "quora":      {"label": "Quora",      "icon": "quora",       "color": "#A82400"},
    "youtube":    {"label": "YouTube",    "icon": "youtube",     "color": "#FF0000"},
    "telegram":   {"label": "Telegram",   "icon": "telegram",    "color": "#229ED9"},
    "twitter":    {"label": "Twitter/X",  "icon": "twitter-x",   "color": "#000000"},
    "google_gmb": {"label": "Google GMB", "icon": "google",      "color": "#4285F4"},
    "web":        {"label": "Web",        "icon": "globe",       "color": "#6c757d"},
    "meetup":     {"label": "Meetup",     "icon": "people-fill", "color": "#f64060"},
    "whatsapp":   {"label": "WhatsApp",   "icon": "whatsapp",    "color": "#25D366"},
}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@research_robot_bp.route("/")
@require_super_admin
def dashboard():
    total_sessions   = ResearchSession.query.count()
    total_grabbed    = GrabbedResult.query.count()
    total_added      = GrabbedResult.query.filter(
        GrabbedResult.status.in_(["added_crm", "added_directory", "added_community"])
    ).count()
    total_engagement = SocialEngagement.query.count()

    recent_sessions = (ResearchSession.query
                       .order_by(desc(ResearchSession.created_at))
                       .limit(8).all())

    # Platform breakdown
    platform_stats = (
        db.session.query(GrabbedResult.platform, func.count(GrabbedResult.id))
        .group_by(GrabbedResult.platform)
        .all()
    )

    engagement_stats = (
        db.session.query(SocialEngagement.platform, func.count(SocialEngagement.id))
        .group_by(SocialEngagement.platform)
        .all()
    )

    return render_template(
        "research_robot/dashboard.html",
        total_sessions=total_sessions,
        total_grabbed=total_grabbed,
        total_added=total_added,
        total_engagement=total_engagement,
        recent_sessions=recent_sessions,
        platform_stats=platform_stats,
        engagement_stats=engagement_stats,
        platform_meta=PLATFORM_META,
    )


# ── Search ─────────────────────────────────────────────────────────────────────

@research_robot_bp.route("/search")
@require_super_admin
def search():
    """Search page — shows the keyword form and optional results."""
    sessions = (ResearchSession.query
                .order_by(desc(ResearchSession.created_at))
                .limit(10).all())
    return render_template(
        "research_robot/search.html",
        sessions=sessions,
        platform_meta=PLATFORM_META,
    )


@research_robot_bp.route("/scan", methods=["POST"])
@require_super_admin
def scan():
    """
    AJAX endpoint — runs the scraper and returns JSON results.
    Also creates a ResearchSession + GrabbedResult rows.
    """
    data        = request.get_json(force=True) or {}
    keyword     = (data.get("keyword") or "").strip()
    platform    = (data.get("platform") or "all").strip()
    search_type = (data.get("search_type") or "community").strip()
    country     = (data.get("country") or "Global").strip()
    location    = (data.get("location") or "").strip()

    if not keyword:
        return jsonify({"error": "keyword required"}), 400

    # Create session record
    session = ResearchSession(
        keyword=keyword,
        platform=platform,
        search_type=search_type,
        country=country,
        status="running",
        run_by_id=current_user.id if current_user.is_authenticated else None,
    )
    db.session.add(session)
    db.session.commit()

    try:
        # Run appropriate scraper
        if search_type == "gmb_listing":
            raw = search_gmb_listings(keyword, location=location or country, max_results=25)
        elif search_type == "quora":
            raw = search_quora(keyword, max_results=20)
        elif search_type == "twitter":
            raw = search_twitter_x(keyword, max_results=20)
        elif search_type == "ask_public":
            raw = search_ask_the_public(keyword, max_results=20)
        elif search_type == "reddit":
            raw = search_reddit_threads(keyword, max_results=20)
        elif platform == "twitter":
            raw = search_twitter_x(keyword, max_results=20)
        elif platform == "all" or search_type == "web":
            raw = search_communities(keyword, platform="all", country=country, max_results=30)
        else:
            raw = search_communities(keyword, platform=platform, country=country, max_results=25)

        # Persist GrabbedResult rows
        added = []
        for item in raw:
            gr = GrabbedResult(
                session_id=session.id,
                result_type=item.get("result_type", "community"),
                platform=item.get("platform", platform),
                name=item.get("name", "")[:300],
                url=(item.get("url") or "")[:1000],
                description=item.get("description", ""),
                snippet=item.get("snippet", ""),
                thumbnail=item.get("thumbnail", ""),
                member_count=item.get("member_count"),
                member_count_text=item.get("member_count_text", ""),
                category=item.get("category", "Legal General"),
                country_focus=item.get("country_focus", country),
                join_link=(item.get("join_link") or "")[:1000],
                phone=item.get("phone", ""),
                email=item.get("email", ""),
                address=item.get("address", ""),
                city=item.get("city", location or country),
                state=item.get("state", ""),
                country=item.get("country", country),
                rating=item.get("rating"),
                reviews=item.get("reviews"),
                website=(item.get("website") or "")[:500],
                place_id=item.get("place_id", ""),
                raw_json=json.dumps(item),
            )
            db.session.add(gr)
            added.append(gr)

        session.results_found = len(added)
        session.status = "done"
        session.completed_at = datetime.utcnow()
        db.session.commit()

        # Serialize for response
        results_out = []
        for gr in added:
            results_out.append({
                "id":               gr.id,
                "result_type":      gr.result_type,
                "platform":         gr.platform,
                "name":             gr.name,
                "url":              gr.url,
                "description":      gr.description,
                "member_count":     gr.member_count,
                "member_count_text":gr.member_count_text,
                "category":         gr.category,
                "country_focus":    gr.country_focus,
                "phone":            gr.phone,
                "address":          gr.address,
                "city":             gr.city,
                "rating":           gr.rating,
                "reviews":          gr.reviews,
                "website":          gr.website,
                "status":           gr.status,
            })

        return jsonify({
            "session_id": session.id,
            "found":      len(results_out),
            "results":    results_out,
        })

    except Exception as exc:
        logger.exception("Scan error for keyword=%s", keyword)
        session.status = "error"
        session.error_message = str(exc)
        db.session.commit()
        return jsonify({"error": str(exc)}), 500


# ── Grab (push to CRM / Directory / Community) ─────────────────────────────────

@research_robot_bp.route("/grab/<int:result_id>", methods=["POST"])
@require_super_admin
def grab_result(result_id):
    """Push a staged GrabbedResult into the CRM or SocialCommunity table."""
    gr      = GrabbedResult.query.get_or_404(result_id)
    target  = request.form.get("target", "")   # 'crm' | 'community' | 'skip'
    notes   = request.form.get("notes", "")

    if target == "skip":
        gr.status = "skipped"
        db.session.commit()
        return jsonify({"ok": True, "status": "skipped"})

    if gr.is_added:
        return jsonify({"ok": False, "error": "Already added"}), 400

    if target in ("crm", "directory"):
        # Check duplicate
        exists = DirectoryLawFirm.query.filter(
            DirectoryLawFirm.name.ilike(f"%{gr.name}%")
        ).first()
        if exists:
            gr.status = "duplicate"
            gr.crm_id = exists.id
            db.session.commit()
            return jsonify({"ok": True, "status": "duplicate", "existing_id": exists.id})

        firm = DirectoryLawFirm(
            name=gr.name or "Unknown",
            description=gr.description or gr.snippet,
            phone=gr.phone or "",
            email=gr.email or "",
            website=gr.website or gr.url,
            address=gr.address or "",
            city=gr.city or "",
            state=gr.state or "",
            country=gr.country or "Global",
            google_place_id=gr.place_id or "",
            google_rating=gr.rating,
            google_reviews_count=gr.reviews,
            source="research_robot",
            is_active=True,
            pipeline_stage="discovered",
            crm_status="active",
        )
        db.session.add(firm)
        db.session.flush()
        gr.status  = "added_crm"
        gr.crm_id  = firm.id
        gr.notes   = notes

        # Update session counter
        if gr.session:
            gr.session.results_added = (gr.session.results_added or 0) + 1

        db.session.commit()
        return jsonify({"ok": True, "status": "added_crm", "firm_id": firm.id})

    if target == "community":
        exists = SocialCommunity.query.filter(
            SocialCommunity.community_name.ilike(f"%{gr.name}%")
        ).first()
        if exists:
            gr.status = "duplicate"
            gr.crm_id = exists.id
            db.session.commit()
            return jsonify({"ok": True, "status": "duplicate", "existing_id": exists.id})

        sc = SocialCommunity(
            platform=gr.platform or "web",
            community_name=gr.name or "Unknown",
            url=gr.url or "",
            join_link=gr.join_link or gr.url,
            member_count=gr.member_count,
            member_count_display=gr.member_count_text or (
                f"{gr.member_count:,}" if gr.member_count else ""
            ),
            description=gr.description or gr.snippet,
            category=gr.category or "Legal General",
            country_focus=gr.country_focus or "Global",
            language="English",
            source="research_robot",
            is_active=True,
            outreach_status="not_contacted",
        )
        db.session.add(sc)
        db.session.flush()
        gr.status = "added_community"
        gr.crm_id = sc.id
        gr.notes  = notes

        if gr.session:
            gr.session.results_added = (gr.session.results_added or 0) + 1

        db.session.commit()
        return jsonify({"ok": True, "status": "added_community", "community_id": sc.id})

    return jsonify({"ok": False, "error": "unknown target"}), 400


@research_robot_bp.route("/grab-bulk", methods=["POST"])
@require_super_admin
def grab_bulk():
    """Bulk-push all pending results from a session."""
    data       = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    target     = data.get("target", "community")

    session_obj = ResearchSession.query.get_or_404(session_id)
    pending = GrabbedResult.query.filter_by(
        session_id=session_id, status="pending"
    ).all()

    added = 0
    dupes = 0
    for gr in pending:
        if target in ("crm", "directory"):
            exists = DirectoryLawFirm.query.filter(
                DirectoryLawFirm.name.ilike(f"%{gr.name}%")
            ).first()
            if exists:
                gr.status = "duplicate"
                dupes += 1
                continue
            firm = DirectoryLawFirm(
                name=gr.name or "Unknown",
                description=gr.description or gr.snippet,
                phone=gr.phone or "",
                email=gr.email or "",
                website=gr.website or gr.url,
                address=gr.address or "",
                city=gr.city or "",
                country=gr.country or "Global",
                source="research_robot",
                is_active=True,
                pipeline_stage="discovered",
                crm_status="active",
            )
            db.session.add(firm)
            db.session.flush()
            gr.status = "added_crm"
            gr.crm_id = firm.id
        else:
            exists = SocialCommunity.query.filter(
                SocialCommunity.community_name.ilike(f"%{gr.name}%")
            ).first()
            if exists:
                gr.status = "duplicate"
                dupes += 1
                continue
            sc = SocialCommunity(
                platform=gr.platform or "web",
                community_name=gr.name or "Unknown",
                url=gr.url or "",
                join_link=gr.join_link or gr.url,
                member_count=gr.member_count,
                member_count_display=gr.member_count_text or "",
                description=gr.description or gr.snippet,
                category=gr.category or "Legal General",
                country_focus=gr.country_focus or "Global",
                language="English",
                source="research_robot",
                is_active=True,
                outreach_status="not_contacted",
            )
            db.session.add(sc)
            db.session.flush()
            gr.status = "added_community"
            gr.crm_id = sc.id
        added += 1

    session_obj.results_added = (session_obj.results_added or 0) + added
    db.session.commit()

    return jsonify({"ok": True, "added": added, "duplicates": dupes})


# ── Session History ────────────────────────────────────────────────────────────

@research_robot_bp.route("/sessions")
@require_super_admin
def sessions():
    page = request.args.get("page", 1, type=int)
    pag  = (ResearchSession.query
            .order_by(desc(ResearchSession.created_at))
            .paginate(page=page, per_page=20))
    return render_template(
        "research_robot/sessions.html",
        pag=pag,
        platform_meta=PLATFORM_META,
    )


@research_robot_bp.route("/sessions/<int:session_id>")
@require_super_admin
def session_detail(session_id):
    sess    = ResearchSession.query.get_or_404(session_id)
    results = (GrabbedResult.query
               .filter_by(session_id=session_id)
               .order_by(GrabbedResult.id)
               .all())
    return render_template(
        "research_robot/session_detail.html",
        sess=sess,
        results=results,
        platform_meta=PLATFORM_META,
    )


@research_robot_bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@require_super_admin
def delete_session(session_id):
    sess = ResearchSession.query.get_or_404(session_id)
    db.session.delete(sess)
    db.session.commit()
    flash("Session deleted.", "success")
    return redirect(url_for("research_robot.sessions"))


# ── Social Engagement Tracker ─────────────────────────────────────────────────

@research_robot_bp.route("/engagement")
@require_super_admin
def engagement():
    platform = request.args.get("platform", "")
    etype    = request.args.get("type", "")
    page     = request.args.get("page", 1, type=int)

    q = SocialEngagement.query
    if platform:
        q = q.filter_by(platform=platform)
    if etype:
        q = q.filter_by(engagement_type=etype)

    pag = q.order_by(desc(SocialEngagement.posted_at)).paginate(page=page, per_page=25)

    # Stats
    total_likes   = db.session.query(func.sum(SocialEngagement.likes)).scalar()   or 0
    total_shares  = db.session.query(func.sum(SocialEngagement.shares)).scalar()  or 0
    total_comments= db.session.query(func.sum(SocialEngagement.comments)).scalar()or 0
    total_views   = db.session.query(func.sum(SocialEngagement.views)).scalar()   or 0

    platform_counts = (
        db.session.query(SocialEngagement.platform, func.count(SocialEngagement.id))
        .group_by(SocialEngagement.platform).all()
    )
    type_counts = (
        db.session.query(SocialEngagement.engagement_type, func.count(SocialEngagement.id))
        .group_by(SocialEngagement.engagement_type).all()
    )

    communities = SocialCommunity.query.filter_by(is_active=True).order_by(SocialCommunity.community_name).all()
    firms       = (DirectoryLawFirm.query.filter_by(is_active=True)
                   .order_by(DirectoryLawFirm.name).limit(200).all())

    return render_template(
        "research_robot/engagement.html",
        pag=pag,
        platform_meta=PLATFORM_META,
        total_likes=total_likes,
        total_shares=total_shares,
        total_comments=total_comments,
        total_views=total_views,
        platform_counts=platform_counts,
        type_counts=type_counts,
        communities=communities,
        firms=firms,
        filter_platform=platform,
        filter_type=etype,
    )


@research_robot_bp.route("/engagement/add", methods=["POST"])
@require_super_admin
def add_engagement():
    d = request.form
    eng = SocialEngagement(
        platform         = d.get("platform", "facebook"),
        engagement_type  = d.get("engagement_type", "comment"),
        target_url       = d.get("target_url", "")[:1000],
        target_name      = d.get("target_name", "")[:300],
        post_content     = d.get("post_content", ""),
        post_url         = d.get("post_url", "")[:1000],
        hashtags         = d.get("hashtags", "")[:500],
        status           = d.get("status", "posted"),
        campaign_tag     = d.get("campaign_tag", "")[:200],
        notes            = d.get("notes", ""),
        posted_by_id     = current_user.id if current_user.is_authenticated else None,
        linked_community_id = int(d["linked_community_id"]) if d.get("linked_community_id") else None,
        linked_firm_id      = int(d["linked_firm_id"])      if d.get("linked_firm_id")      else None,
    )
    db.session.add(eng)
    db.session.commit()
    flash("Engagement recorded successfully.", "success")
    return redirect(url_for("research_robot.engagement"))


@research_robot_bp.route("/engagement/<int:eng_id>/update-metrics", methods=["POST"])
@require_super_admin
def update_metrics(eng_id):
    eng = SocialEngagement.query.get_or_404(eng_id)
    d   = request.get_json(force=True) or {}
    eng.views    = d.get("views",    eng.views)
    eng.likes    = d.get("likes",    eng.likes)
    eng.comments = d.get("comments", eng.comments)
    eng.shares   = d.get("shares",   eng.shares)
    eng.clicks   = d.get("clicks",   eng.clicks)
    eng.last_checked_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "score": eng.engagement_score})


@research_robot_bp.route("/engagement/<int:eng_id>/delete", methods=["POST"])
@require_super_admin
def delete_engagement(eng_id):
    eng = SocialEngagement.query.get_or_404(eng_id)
    db.session.delete(eng)
    db.session.commit()
    return jsonify({"ok": True})


# ── In-app browser proxy ───────────────────────────────────────────────────────

@research_robot_bp.route("/browser")
@require_super_admin
def browser():
    """
    In-app research browser — fetches URLs server-side for content extraction.
    Hardened against SSRF: only http/https, no private/loopback ranges.
    """
    import socket
    import ipaddress

    url     = request.args.get("url", "").strip()
    content = ""
    error   = ""

    if url:
        # ── SSRF validation ────────────────────────────────────────────────────
        from urllib.parse import urlparse as _parse
        _BLOCKED_SCHEMES = {"file", "ftp", "gopher", "dict", "ldap", "ldaps", "data", "javascript"}
        _PRIVATE_NETS = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
            ipaddress.ip_network("169.254.0.0/16"),
            ipaddress.ip_network("::1/128"),
            ipaddress.ip_network("fc00::/7"),
        ]

        def _is_safe_url(raw):
            try:
                parsed = _parse(raw)
                if parsed.scheme not in ("http", "https"):
                    return False, f"Scheme '{parsed.scheme}' not allowed."
                host = parsed.hostname
                if not host:
                    return False, "No hostname."
                # Resolve and check all IPs
                infos = socket.getaddrinfo(host, None)
                for info in infos:
                    ip_str = info[4][0]
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        for net in _PRIVATE_NETS:
                            if ip in net:
                                return False, f"Host resolves to private/internal address ({ip_str})."
                    except ValueError:
                        pass
                return True, ""
            except Exception as exc:
                return False, str(exc)

        safe, reason = _is_safe_url(url)
        if not safe:
            error = f"URL blocked: {reason}"
        else:
            try:
                r = requests.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                        )
                    },
                    timeout=10,
                    allow_redirects=True,
                    stream=False,
                )
                # Limit response size to 512 KB
                content = r.text[:524288]
            except Exception as exc:
                error = str(exc)

    communities = (SocialCommunity.query
                   .filter_by(is_active=True)
                   .order_by(SocialCommunity.community_name)
                   .limit(100).all())

    # Smart extraction from fetched HTML
    extracted = {}
    if content and not error:
        try:
            extracted = extract_page_contacts(content)
        except Exception:
            pass

    return render_template(
        "research_robot/browser.html",
        url=url,
        content=content,
        error=error,
        communities=communities,
        platform_meta=PLATFORM_META,
        extracted=extracted,
    )


# ── Smart URL Scrape (AJAX) ────────────────────────────────────────────────────

@research_robot_bp.route("/scrape-url", methods=["POST"])
@require_super_admin
def scrape_url():
    """Fetch a URL server-side and return extracted contacts/metadata as JSON."""
    import socket, ipaddress
    from urllib.parse import urlparse as _parse

    data = request.get_json(force=True) or {}
    url  = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400

    _PRIVATE_NETS = [
        ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
    ]
    try:
        parsed = _parse(url)
        if parsed.scheme not in ("http", "https"):
            return jsonify({"error": "Only http/https URLs allowed"}), 400
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if any(ip in net for net in _PRIVATE_NETS):
                return jsonify({"error": "Private/internal address blocked"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        import requests as _req
        r = _req.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        }, timeout=12, allow_redirects=True)
        html = r.text[:400000]
        extracted = extract_page_contacts(html)
        return jsonify({"ok": True, "url": url, **extracted})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Manual Quick-Add (AJAX) ────────────────────────────────────────────────────

@research_robot_bp.route("/quick-add", methods=["POST"])
@require_super_admin
def quick_add():
    """Directly add a community or law firm record without running a full scan."""
    d      = request.get_json(force=True) or {}
    target = d.get("target", "community")  # 'community' | 'crm'
    name   = (d.get("name") or "").strip()
    url_   = (d.get("url") or "").strip()

    if not name:
        return jsonify({"error": "name required"}), 400

    if target == "community":
        exists = SocialCommunity.query.filter(
            SocialCommunity.community_name.ilike(f"%{name}%")
        ).first()
        if exists:
            return jsonify({"ok": True, "status": "duplicate", "id": exists.id})
        sc = SocialCommunity(
            platform=d.get("platform", "web"),
            community_name=name,
            url=url_,
            join_link=url_,
            description=d.get("description", ""),
            category=d.get("category", "Legal General"),
            country_focus=d.get("country", "Global"),
            member_count=d.get("member_count"),
            member_count_display=d.get("member_count_text", ""),
            language="English",
            source="manual_browser",
            is_active=True,
            outreach_status="not_contacted",
        )
        db.session.add(sc)
        db.session.commit()
        return jsonify({"ok": True, "status": "added_community", "id": sc.id})

    # CRM / Law Firm Directory
    exists = DirectoryLawFirm.query.filter(
        DirectoryLawFirm.name.ilike(f"%{name}%")
    ).first()
    if exists:
        return jsonify({"ok": True, "status": "duplicate", "id": exists.id})
    firm = DirectoryLawFirm(
        name=name,
        description=d.get("description", ""),
        phone=d.get("phone", ""),
        email=d.get("email", ""),
        website=url_,
        address=d.get("address", ""),
        city=d.get("city", ""),
        country=d.get("country", "Global"),
        source="manual_browser",
        is_active=True,
        pipeline_stage="discovered",
        crm_status="active",
    )
    db.session.add(firm)
    db.session.commit()
    return jsonify({"ok": True, "status": "added_crm", "id": firm.id})


# ── Post Templates ─────────────────────────────────────────────────────────────

@research_robot_bp.route("/post-templates")
@require_super_admin
def post_templates():
    platform = request.args.get("platform", "")
    etype    = request.args.get("type", "")
    q = PostTemplate.query.filter_by(is_active=True)
    if platform:
        q = q.filter(PostTemplate.platform.in_([platform, "all"]))
    if etype:
        q = q.filter_by(engagement_type=etype)
    templates = q.order_by(PostTemplate.use_count.desc()).all()
    return render_template(
        "research_robot/post_templates.html",
        templates=templates,
        platform_meta=PLATFORM_META,
        filter_platform=platform,
        filter_type=etype,
    )


@research_robot_bp.route("/post-templates/add", methods=["POST"])
@require_super_admin
def add_post_template():
    d = request.form
    tpl = PostTemplate(
        title=d.get("title", "")[:200],
        platform=d.get("platform", "all"),
        category=d.get("category", "Legal General"),
        content=d.get("content", ""),
        hashtags=d.get("hashtags", "")[:500],
        engagement_type=d.get("engagement_type", "comment"),
        created_by_id=current_user.id if current_user.is_authenticated else None,
    )
    db.session.add(tpl)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "id": tpl.id})
    flash("Template saved.", "success")
    return redirect(url_for("research_robot.post_templates"))


@research_robot_bp.route("/post-templates/<int:tpl_id>/delete", methods=["POST"])
@require_super_admin
def delete_post_template(tpl_id):
    tpl = PostTemplate.query.get_or_404(tpl_id)
    db.session.delete(tpl)
    db.session.commit()
    return jsonify({"ok": True})


@research_robot_bp.route("/post-templates/<int:tpl_id>/use", methods=["POST"])
@require_super_admin
def use_post_template(tpl_id):
    """Return template content and increment use count."""
    tpl = PostTemplate.query.get_or_404(tpl_id)
    tpl.use_count = (tpl.use_count or 0) + 1
    db.session.commit()
    return jsonify({
        "ok": True,
        "content":  tpl.content,
        "hashtags": tpl.hashtags or "",
        "platform": tpl.platform,
        "type":     tpl.engagement_type,
    })


# ── CSV Export ─────────────────────────────────────────────────────────────────

@research_robot_bp.route("/export")
@require_super_admin
def export_results():
    """Export grabbed results (all or by session) as CSV."""
    session_id = request.args.get("session_id", type=int)
    export_type = request.args.get("type", "results")  # results | engagements

    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == "engagements":
        writer.writerow(["ID", "Platform", "Type", "Target", "URL", "Content",
                         "Status", "Views", "Likes", "Comments", "Shares",
                         "Score", "Campaign", "Posted At"])
        rows = SocialEngagement.query.order_by(desc(SocialEngagement.posted_at)).all()
        for e in rows:
            writer.writerow([
                e.id, e.platform, e.engagement_type, e.target_name or "",
                e.target_url or "", (e.post_content or "")[:500],
                e.status, e.views or 0, e.likes or 0, e.comments or 0,
                e.shares or 0, e.engagement_score, e.campaign_tag or "",
                e.posted_at.strftime("%Y-%m-%d %H:%M") if e.posted_at else "",
            ])
        filename = "social_engagements.csv"
    else:
        writer.writerow(["ID", "Session ID", "Type", "Platform", "Name", "URL",
                         "Phone", "Email", "Address", "City", "Rating",
                         "Members", "Category", "Status", "Created"])
        q = GrabbedResult.query
        if session_id:
            q = q.filter_by(session_id=session_id)
        for gr in q.order_by(GrabbedResult.id).all():
            writer.writerow([
                gr.id, gr.session_id, gr.result_type, gr.platform,
                gr.name or "", gr.url or "", gr.phone or "", gr.email or "",
                gr.address or "", gr.city or "", gr.rating or "",
                gr.member_count or "", gr.category or "", gr.status,
                gr.created_at.strftime("%Y-%m-%d") if gr.created_at else "",
            ])
        filename = f"grabbed_results{'_session_'+str(session_id) if session_id else ''}.csv"

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
