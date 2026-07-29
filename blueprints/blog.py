"""
LAWCOLAB Blog Blueprint — /blog
Full-featured blog with share tracking, unique-view analytics, reading time,
glowing inline CTAs, and analytics dashboard.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, abort, make_response)
from flask_login import current_user
from app import db
from sqlalchemy import text
from datetime import datetime
import re, logging, math, secrets as _sec

logger = logging.getLogger(__name__)
blog_bp = Blueprint('blog', __name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug).strip('-')
    return slug[:80]


def _calc_read_time(content: str) -> int:
    """Estimate reading time in minutes at 200 wpm."""
    words = len(re.sub(r'<[^>]+>', ' ', content or '').split())
    return max(1, math.ceil(words / 200))


def _get_sid():
    return request.cookies.get('blog_sid') or _sec.token_hex(16)


def _device_type():
    ua = request.headers.get('User-Agent', '').lower()
    if any(x in ua for x in ('mobile', 'android', 'iphone')):
        return 'mobile'
    if any(x in ua for x in ('tablet', 'ipad')):
        return 'tablet'
    return 'desktop'


def _referrer_domain():
    ref = request.referrer or ''
    m = re.match(r'https?://([^/?#]+)', ref)
    return m.group(1) if m else ''


def _track_view(post_id, sid):
    """Record a unique page view — one per (post, session)."""
    try:
        db.session.execute(text("""
            INSERT INTO blog_post_views
                (post_id, session_id, referrer_domain, device_type, created_at)
            VALUES (:pid, :sid, :ref, :dev, NOW())
            ON CONFLICT (post_id, session_id) DO NOTHING
        """), {"pid": post_id, "sid": sid,
               "ref": _referrer_domain(), "dev": _device_type()})
        db.session.commit()
    except Exception:
        db.session.rollback()


def _share_counts(post_id):
    """Return {platform: count, total: n} for a post."""
    try:
        rows = db.session.execute(text("""
            SELECT platform, COUNT(*) as cnt FROM blog_shares
            WHERE post_id=:pid GROUP BY platform
        """), {"pid": post_id}).fetchall()
        result = {r[0]: r[1] for r in rows}
        result['total'] = sum(result.values())
        return result
    except Exception:
        return {'total': 0}


def _get_posts(limit=12, offset=0, category=None, tag=None,
               search=None, sort='newest'):
    sql = "SELECT * FROM blog_posts WHERE published=TRUE"
    params: dict = {}
    if category:
        sql += " AND category=:cat"
        params['cat'] = category
    if tag:
        sql += " AND tags LIKE :tag"
        params['tag'] = f'%{tag}%'
    if search:
        sql += " AND (title ILIKE :s OR excerpt ILIKE :s OR content ILIKE :s)"
        params['s'] = f'%{search}%'

    order_map = {
        'newest':    'published_at DESC',
        'oldest':    'published_at ASC',
        'popular':   'view_count DESC, published_at DESC',
        'liked':     'share_count DESC, view_count DESC',
        'commented': 'comment_count DESC, published_at DESC',
    }
    sql += f" ORDER BY {order_map.get(sort, 'published_at DESC')} LIMIT :lim OFFSET :off"
    params['lim'] = limit
    params['off'] = offset
    try:
        rows = db.session.execute(text(sql), params).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _get_post(slug):
    try:
        row = db.session.execute(
            text("SELECT * FROM blog_posts WHERE slug=:slug AND published=TRUE"),
            {"slug": slug}
        ).fetchone()
        return dict(row._mapping) if row else None
    except Exception:
        return None


def _get_comments(post_id):
    try:
        rows = db.session.execute(
            text("SELECT * FROM blog_comments WHERE post_id=:pid AND approved=TRUE "
                 "ORDER BY created_at ASC"),
            {"pid": post_id}
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _post_count(category=None, tag=None, search=None):
    sql = "SELECT COUNT(*) FROM blog_posts WHERE published=TRUE"
    params: dict = {}
    if category:
        sql += " AND category=:cat"
        params['cat'] = category
    if tag:
        sql += " AND tags LIKE :tag"
        params['tag'] = f'%{tag}%'
    if search:
        sql += " AND (title ILIKE :s OR excerpt ILIKE :s OR content ILIKE :s)"
        params['s'] = f'%{search}%'
    try:
        return db.session.execute(text(sql), params).scalar() or 0
    except Exception:
        return 0


def _categories():
    try:
        rows = db.session.execute(text(
            "SELECT category, COUNT(*) as cnt FROM blog_posts "
            "WHERE published=TRUE GROUP BY category ORDER BY cnt DESC"
        )).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _popular_posts(limit=5):
    try:
        rows = db.session.execute(
            text("SELECT id, title, slug, hero_image, view_count, comment_count, "
                 "share_count, read_time_minutes, published_at "
                 "FROM blog_posts WHERE published=TRUE "
                 "ORDER BY view_count DESC LIMIT :lim"),
            {"lim": limit}
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


# ─── Public routes ─────────────────────────────────────────────────────────────

@blog_bp.route('/')
def index():
    page     = request.args.get('page', 1, type=int)
    per_page = 9
    category = request.args.get('category', '').strip() or None
    tag      = request.args.get('tag', '').strip() or None
    search   = request.args.get('q', '').strip() or None
    sort     = request.args.get('sort', 'newest').strip()
    if sort not in ('newest', 'oldest', 'popular', 'liked', 'commented'):
        sort = 'newest'

    posts      = _get_posts(limit=per_page, offset=(page - 1) * per_page,
                            category=category, tag=tag, search=search, sort=sort)
    total      = _post_count(category=category, tag=tag, search=search)
    total_pages = max(1, (total + per_page - 1) // per_page)

    featured = None
    if page == 1 and not category and not tag and not search:
        try:
            row = db.session.execute(text(
                "SELECT * FROM blog_posts WHERE published=TRUE AND featured=TRUE "
                "ORDER BY published_at DESC LIMIT 1"
            )).fetchone()
            if row:
                featured = dict(row._mapping)
                posts = [p for p in posts if p['id'] != featured['id']]
        except Exception:
            pass

    cats    = _categories()
    popular = _popular_posts()

    return render_template('blog/index.html',
                           posts=posts, featured=featured,
                           page=page, total_pages=total_pages, total=total,
                           category=category, tag=tag, search=search, sort=sort,
                           cats=cats, popular=popular)


@blog_bp.route('/<slug>')
def post(slug):
    p = _get_post(slug)
    if not p:
        abort(404)

    sid = _get_sid()

    # Increment total view counter
    try:
        db.session.execute(
            text("UPDATE blog_posts SET view_count=view_count+1 WHERE id=:id"),
            {"id": p['id']}
        )
        db.session.commit()
        p['view_count'] = (p.get('view_count') or 0) + 1
    except Exception:
        db.session.rollback()

    # Unique session view
    _track_view(p['id'], sid)

    # Unique view count
    unique_views = 0
    try:
        unique_views = db.session.execute(
            text("SELECT COUNT(DISTINCT session_id) FROM blog_post_views WHERE post_id=:pid"),
            {"pid": p['id']}
        ).scalar() or 0
    except Exception:
        pass

    comments      = _get_comments(p['id'])
    comment_count = len(comments)

    # Related posts (same category, excluding current)
    related = []
    try:
        rows = db.session.execute(
            text("SELECT id,title,slug,hero_image,excerpt,published_at,view_count,"
                 "category,read_time_minutes FROM blog_posts "
                 "WHERE published=TRUE AND category=:cat AND id!=:id "
                 "ORDER BY published_at DESC LIMIT 3"),
            {"cat": p.get('category', ''), "id": p['id']}
        ).fetchall()
        related = [dict(r._mapping) for r in rows]
    except Exception:
        pass

    # Likes
    like_count = 0
    user_liked = False
    try:
        like_count = db.session.execute(
            text("SELECT COUNT(*) FROM blog_likes WHERE post_id=:pid"), {"pid": p['id']}
        ).scalar() or 0
        if sid:
            user_liked = bool(db.session.execute(
                text("SELECT 1 FROM blog_likes WHERE post_id=:pid AND session_id=:sid"),
                {"pid": p['id'], "sid": sid}
            ).fetchone())
    except Exception:
        pass

    # Share counts by platform
    shares = _share_counts(p['id'])

    cats    = _categories()
    popular = _popular_posts()
    og_desc = p.get('excerpt') or re.sub(r'<[^>]+>', '', p.get('content', ''))[:160]
    read_time = p.get('read_time_minutes') or _calc_read_time(p.get('content', ''))

    resp = make_response(render_template('blog/post.html',
                                         post=p,
                                         comments=comments,
                                         comment_count=comment_count,
                                         related=related,
                                         like_count=like_count,
                                         user_liked=user_liked,
                                         cats=cats,
                                         popular=popular,
                                         og_desc=og_desc,
                                         shares=shares,
                                         unique_views=unique_views,
                                         read_time=read_time))
    resp.set_cookie('blog_sid', sid, max_age=365 * 86400, samesite='Lax')
    return resp


@blog_bp.route('/<slug>/share', methods=['POST'])
def track_share(slug):
    """AJAX — record a share-button click before the social window opens."""
    p = _get_post(slug)
    if not p:
        return jsonify({'error': 'not found'}), 404

    data     = request.get_json(silent=True) or {}
    platform = (data.get('platform') or request.form.get('platform', 'unknown'))[:50]
    sid      = _get_sid()

    try:
        db.session.execute(text("""
            INSERT INTO blog_shares (post_id, platform, session_id, created_at)
            VALUES (:pid, :plat, :sid, NOW())
        """), {"pid": p['id'], "plat": platform, "sid": sid})
        db.session.execute(
            text("UPDATE blog_posts SET share_count=share_count+1 WHERE id=:id"),
            {"id": p['id']}
        )
        db.session.commit()
    except Exception:
        db.session.rollback()

    total = _share_counts(p['id'])
    resp  = make_response(jsonify({'ok': True, 'total': total.get('total', 0)}))
    resp.set_cookie('blog_sid', sid, max_age=365 * 86400, samesite='Lax')
    return resp


@blog_bp.route('/<slug>/comment', methods=['POST'])
def add_comment(slug):
    p = _get_post(slug)
    if not p:
        abort(404)

    name    = request.form.get('name', '').strip()[:100]
    email   = request.form.get('email', '').strip()[:200]
    content = request.form.get('content', '').strip()[:2000]

    if not name or not content:
        flash('Name and comment are required.', 'error')
        return redirect(url_for('blog.post', slug=slug) + '#comments')

    try:
        db.session.execute(text("""
            INSERT INTO blog_comments
                (post_id, name, email, content, approved, created_at)
            VALUES (:pid, :name, :email, :content, TRUE, NOW())
        """), dict(pid=p['id'], name=name, email=email, content=content))
        db.session.execute(
            text("UPDATE blog_posts SET comment_count=comment_count+1 WHERE id=:id"),
            {"id": p['id']}
        )
        db.session.commit()
        flash('Your comment has been posted!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.warning("Comment error: %s", e)
        flash('Could not post comment. Please try again.', 'error')

    return redirect(url_for('blog.post', slug=slug) + '#comments')


@blog_bp.route('/<slug>/like', methods=['POST'])
def like_post(slug):
    p = _get_post(slug)
    if not p:
        return jsonify({'error': 'Not found'}), 404

    sid     = _get_sid()
    already = False
    try:
        already = bool(db.session.execute(
            text("SELECT 1 FROM blog_likes WHERE post_id=:pid AND session_id=:sid"),
            {"pid": p['id'], "sid": sid}
        ).fetchone())
        if not already:
            db.session.execute(
                text("INSERT INTO blog_likes (post_id, session_id, created_at) "
                     "VALUES (:pid,:sid,NOW())"),
                {"pid": p['id'], "sid": sid}
            )
            db.session.commit()
        count = db.session.execute(
            text("SELECT COUNT(*) FROM blog_likes WHERE post_id=:pid"), {"pid": p['id']}
        ).scalar() or 0
    except Exception:
        db.session.rollback()
        count = 0

    resp = make_response(jsonify({'likes': count, 'liked': not already}))
    resp.set_cookie('blog_sid', sid, max_age=365 * 86400, samesite='Lax')
    return resp


# ─── Super-admin CRUD ──────────────────────────────────────────────────────────

from utils.decorators import require_super_admin


@blog_bp.route('/admin/')
@require_super_admin
def admin_list():
    try:
        rows = db.session.execute(text(
            "SELECT id,title,slug,category,published,featured,view_count,"
            "comment_count,share_count,read_time_minutes,published_at "
            "FROM blog_posts ORDER BY created_at DESC"
        )).fetchall()
        posts = [dict(r._mapping) for r in rows]
    except Exception:
        posts = []
    return render_template('blog/admin_list.html', posts=posts)


@blog_bp.route('/admin/analytics')
@require_super_admin
def admin_analytics():
    """Blog analytics dashboard."""
    try:
        top_posts = db.session.execute(text("""
            SELECT id, title, slug, view_count, comment_count,
                   COALESCE(share_count,0) as share_count,
                   (view_count + comment_count*5 + COALESCE(share_count,0)*3) as engagement_score
            FROM blog_posts WHERE published=TRUE
            ORDER BY engagement_score DESC LIMIT 10
        """)).fetchall()
        top_posts = [dict(r._mapping) for r in top_posts]
    except Exception:
        top_posts = []

    try:
        share_by_platform = db.session.execute(text(
            "SELECT platform, COUNT(*) as cnt FROM blog_shares "
            "GROUP BY platform ORDER BY cnt DESC"
        )).fetchall()
        share_by_platform = [dict(r._mapping) for r in share_by_platform]
    except Exception:
        share_by_platform = []

    try:
        referrers = db.session.execute(text("""
            SELECT referrer_domain, COUNT(*) as cnt
            FROM blog_post_views
            WHERE referrer_domain IS NOT NULL AND referrer_domain != ''
            GROUP BY referrer_domain ORDER BY cnt DESC LIMIT 10
        """)).fetchall()
        referrers = [dict(r._mapping) for r in referrers]
    except Exception:
        referrers = []

    try:
        device_breakdown = db.session.execute(text(
            "SELECT device_type, COUNT(*) as cnt FROM blog_post_views "
            "GROUP BY device_type ORDER BY cnt DESC"
        )).fetchall()
        device_breakdown = [dict(r._mapping) for r in device_breakdown]
    except Exception:
        device_breakdown = []

    try:
        totals = db.session.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM blog_posts WHERE published=TRUE)         AS total_posts,
                (SELECT COALESCE(SUM(view_count),0) FROM blog_posts)           AS total_views,
                (SELECT COUNT(*) FROM blog_likes)                              AS total_likes,
                (SELECT COUNT(*) FROM blog_shares)                             AS total_shares,
                (SELECT COUNT(*) FROM blog_comments WHERE approved=TRUE)       AS total_comments,
                (SELECT COUNT(DISTINCT session_id) FROM blog_post_views)       AS unique_visitors
        """)).fetchone()
        totals = dict(totals._mapping) if totals else {}
    except Exception:
        totals = {}

    # Shares per platform icon mapping
    platform_icons = {
        'twitter': 'fab fa-twitter', 'x': 'fab fa-x-twitter',
        'linkedin': 'fab fa-linkedin-in', 'whatsapp': 'fab fa-whatsapp',
        'facebook': 'fab fa-facebook-f', 'telegram': 'fab fa-telegram-plane',
        'reddit': 'fab fa-reddit-alien', 'email': 'fas fa-envelope',
        'copy': 'fas fa-link', 'pinterest': 'fab fa-pinterest-p',
        'instagram': 'fab fa-instagram',
    }
    platform_colors = {
        'twitter': '#1da1f2', 'x': '#000',
        'linkedin': '#0077b5', 'whatsapp': '#25d366',
        'facebook': '#1877f2', 'telegram': '#229ed9',
        'reddit': '#ff4500', 'email': '#6c757d',
        'copy': '#495057', 'pinterest': '#bd081c',
        'instagram': '#e1306c',
    }

    return render_template('blog/analytics.html',
                           top_posts=top_posts,
                           share_by_platform=share_by_platform,
                           referrers=referrers,
                           device_breakdown=device_breakdown,
                           totals=totals,
                           platform_icons=platform_icons,
                           platform_colors=platform_colors)


@blog_bp.route('/admin/new', methods=['GET', 'POST'])
@require_super_admin
def admin_new():
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        content  = request.form.get('content', '').strip()
        excerpt  = request.form.get('excerpt', '').strip()[:300]
        category = request.form.get('category', 'Legal Tech').strip()
        tags     = request.form.get('tags', '').strip()
        hero     = request.form.get('hero_image', '').strip()
        author   = request.form.get('author', 'LAWCOLAB Team').strip()
        published = bool(request.form.get('published'))
        featured  = bool(request.form.get('featured'))
        slug = _slugify(title)
        rt   = _calc_read_time(content)

        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('blog/admin_edit.html', post=request.form, action='new')

        base_slug = slug
        i = 2
        while True:
            existing = db.session.execute(
                text("SELECT id FROM blog_posts WHERE slug=:slug"), {"slug": slug}
            ).fetchone()
            if not existing:
                break
            slug = f"{base_slug}-{i}"
            i += 1

        try:
            db.session.execute(text("""
                INSERT INTO blog_posts
                (title, slug, content, excerpt, category, tags, hero_image, author,
                 published, featured, view_count, comment_count, share_count,
                 read_time_minutes, created_at, updated_at, published_at)
                VALUES (:title,:slug,:content,:excerpt,:cat,:tags,:hero,:author,
                        :pub,:feat,0,0,0,:rt,NOW(),NOW(),:pub_at)
            """), dict(title=title, slug=slug, content=content, excerpt=excerpt,
                       cat=category, tags=tags, hero=hero, author=author,
                       pub=published, feat=featured, rt=rt,
                       pub_at=datetime.now() if published else None))
            db.session.commit()
            flash(f'Post "{title}" created.', 'success')
            return redirect(url_for('blog.admin_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'error')

    return render_template('blog/admin_edit.html', post={}, action='new')


@blog_bp.route('/admin/<int:post_id>/edit', methods=['GET', 'POST'])
@require_super_admin
def admin_edit(post_id):
    try:
        row = db.session.execute(
            text("SELECT * FROM blog_posts WHERE id=:id"), {"id": post_id}
        ).fetchone()
        p = dict(row._mapping) if row else None
    except Exception:
        p = None
    if not p:
        abort(404)

    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        content  = request.form.get('content', '').strip()
        excerpt  = request.form.get('excerpt', '').strip()[:300]
        category = request.form.get('category', '').strip()
        tags     = request.form.get('tags', '').strip()
        hero     = request.form.get('hero_image', '').strip()
        author   = request.form.get('author', '').strip()
        published = bool(request.form.get('published'))
        featured  = bool(request.form.get('featured'))
        rt = _calc_read_time(content)

        try:
            db.session.execute(text("""
                UPDATE blog_posts SET title=:title, content=:content, excerpt=:excerpt,
                category=:cat, tags=:tags, hero_image=:hero, author=:author,
                published=:pub, featured=:feat, read_time_minutes=:rt, updated_at=NOW(),
                published_at=COALESCE(published_at, CASE WHEN :pub THEN NOW() ELSE NULL END)
                WHERE id=:id
            """), dict(title=title, content=content, excerpt=excerpt, cat=category,
                       tags=tags, hero=hero, author=author, pub=published,
                       feat=featured, rt=rt, id=post_id))
            db.session.commit()
            flash('Post updated.', 'success')
            return redirect(url_for('blog.admin_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'error')

    return render_template('blog/admin_edit.html', post=p, action='edit')


@blog_bp.route('/admin/<int:post_id>/delete', methods=['POST'])
@require_super_admin
def admin_delete(post_id):
    try:
        for tbl in ('blog_shares', 'blog_post_views', 'blog_comments', 'blog_likes'):
            try:
                db.session.execute(text(f"DELETE FROM {tbl} WHERE post_id=:id"),
                                   {"id": post_id})
            except Exception:
                db.session.rollback()
        db.session.execute(text("DELETE FROM blog_posts WHERE id=:id"), {"id": post_id})
        db.session.commit()
        flash('Post deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')
    return redirect(url_for('blog.admin_list'))


@blog_bp.route('/admin/comment/<int:cid>/delete', methods=['POST'])
@require_super_admin
def admin_delete_comment(cid):
    try:
        db.session.execute(text("DELETE FROM blog_comments WHERE id=:id"), {"id": cid})
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'success': True})
