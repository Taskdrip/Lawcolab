"""
LAWCOLAB Blog Blueprint — /blog
Public blog with posts, comments, view counts, likes, tags, categories.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import current_user
from app import db
from sqlalchemy import text, desc
from datetime import datetime
import re, logging

logger = logging.getLogger(__name__)
blog_bp = Blueprint('blog', __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug).strip('-')
    return slug[:80]


def _get_posts(limit=12, offset=0, category=None, tag=None, search=None):
    sql = "SELECT * FROM blog_posts WHERE published=TRUE"
    params = {}
    if category:
        sql += " AND category=:cat"
        params['cat'] = category
    if tag:
        sql += " AND tags LIKE :tag"
        params['tag'] = f'%{tag}%'
    if search:
        sql += " AND (title ILIKE :s OR excerpt ILIKE :s OR content ILIKE :s)"
        params['s'] = f'%{search}%'
    sql += " ORDER BY published_at DESC LIMIT :lim OFFSET :off"
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
            text("SELECT * FROM blog_posts WHERE slug=:slug AND published=TRUE"), {"slug": slug}
        ).fetchone()
        return dict(row._mapping) if row else None
    except Exception:
        return None


def _get_comments(post_id):
    try:
        rows = db.session.execute(
            text("SELECT * FROM blog_comments WHERE post_id=:pid AND approved=TRUE ORDER BY created_at ASC"),
            {"pid": post_id}
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _post_count(category=None, tag=None, search=None):
    sql = "SELECT COUNT(*) FROM blog_posts WHERE published=TRUE"
    params = {}
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
        rows = db.session.execute(
            text("SELECT category, COUNT(*) as cnt FROM blog_posts WHERE published=TRUE GROUP BY category ORDER BY cnt DESC")
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def _popular_posts(limit=5):
    try:
        rows = db.session.execute(
            text("SELECT id, title, slug, hero_image, view_count, published_at FROM blog_posts WHERE published=TRUE ORDER BY view_count DESC LIMIT :lim"),
            {"lim": limit}
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


# ── Public routes ──────────────────────────────────────────────────────────────

@blog_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 9
    category = request.args.get('category', '').strip() or None
    tag = request.args.get('tag', '').strip() or None
    search = request.args.get('q', '').strip() or None

    posts = _get_posts(limit=per_page, offset=(page - 1) * per_page,
                       category=category, tag=tag, search=search)
    total = _post_count(category=category, tag=tag, search=search)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Featured post (first on page 1, no filters)
    featured = None
    if page == 1 and not category and not tag and not search:
        try:
            row = db.session.execute(
                text("SELECT * FROM blog_posts WHERE published=TRUE AND featured=TRUE ORDER BY published_at DESC LIMIT 1")
            ).fetchone()
            if row:
                featured = dict(row._mapping)
                posts = [p for p in posts if p['id'] != featured['id']]
        except Exception:
            pass

    cats = _categories()
    popular = _popular_posts()

    return render_template('blog/index.html',
                           posts=posts, featured=featured,
                           page=page, total_pages=total_pages, total=total,
                           category=category, tag=tag, search=search,
                           cats=cats, popular=popular)


@blog_bp.route('/<slug>')
def post(slug):
    post = _get_post(slug)
    if not post:
        abort(404)

    # Increment view count (fire-and-forget)
    try:
        db.session.execute(
            text("UPDATE blog_posts SET view_count=view_count+1 WHERE id=:id"),
            {"id": post['id']}
        )
        db.session.commit()
        post['view_count'] = (post.get('view_count') or 0) + 1
    except Exception:
        db.session.rollback()

    comments = _get_comments(post['id'])
    comment_count = len(comments)

    # Related posts (same category, excluding current)
    related = []
    try:
        rows = db.session.execute(
            text("SELECT id,title,slug,hero_image,excerpt,published_at,view_count,category FROM blog_posts WHERE published=TRUE AND category=:cat AND id!=:id ORDER BY published_at DESC LIMIT 3"),
            {"cat": post.get('category', ''), "id": post['id']}
        ).fetchall()
        related = [dict(r._mapping) for r in rows]
    except Exception:
        pass

    # Like count
    like_count = 0
    user_liked = False
    try:
        like_count = db.session.execute(
            text("SELECT COUNT(*) FROM blog_likes WHERE post_id=:pid"), {"pid": post['id']}
        ).scalar() or 0
        session_id = request.cookies.get('blog_sid', '')
        if session_id:
            user_liked = bool(db.session.execute(
                text("SELECT 1 FROM blog_likes WHERE post_id=:pid AND session_id=:sid"),
                {"pid": post['id'], "sid": session_id}
            ).fetchone())
    except Exception:
        pass

    cats = _categories()
    popular = _popular_posts()

    # SEO
    og_desc = post.get('excerpt') or post.get('content', '')[:160]

    return render_template('blog/post.html',
                           post=post, comments=comments, comment_count=comment_count,
                           related=related, like_count=like_count, user_liked=user_liked,
                           cats=cats, popular=popular, og_desc=og_desc)


@blog_bp.route('/<slug>/comment', methods=['POST'])
def add_comment(slug):
    post = _get_post(slug)
    if not post:
        abort(404)

    name    = request.form.get('name', '').strip()[:100]
    email   = request.form.get('email', '').strip()[:200]
    content = request.form.get('content', '').strip()[:2000]

    if not name or not content:
        flash('Name and comment are required.', 'error')
        return redirect(url_for('blog.post', slug=slug) + '#comments')

    try:
        db.session.execute(text("""
            INSERT INTO blog_comments (post_id, name, email, content, approved, created_at)
            VALUES (:pid, :name, :email, :content, TRUE, NOW())
        """), dict(pid=post['id'], name=name, email=email, content=content))
        db.session.execute(
            text("UPDATE blog_posts SET comment_count=comment_count+1 WHERE id=:id"),
            {"id": post['id']}
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
    post = _get_post(slug)
    if not post:
        return jsonify({'error': 'Not found'}), 404

    from flask import make_response
    import secrets as _sec
    sid = request.cookies.get('blog_sid') or _sec.token_hex(16)

    already = False
    try:
        already = bool(db.session.execute(
            text("SELECT 1 FROM blog_likes WHERE post_id=:pid AND session_id=:sid"),
            {"pid": post['id'], "sid": sid}
        ).fetchone())
        if not already:
            db.session.execute(
                text("INSERT INTO blog_likes (post_id, session_id, created_at) VALUES (:pid,:sid,NOW())"),
                {"pid": post['id'], "sid": sid}
            )
            db.session.commit()
        count = db.session.execute(
            text("SELECT COUNT(*) FROM blog_likes WHERE post_id=:pid"), {"pid": post['id']}
        ).scalar() or 0
    except Exception:
        db.session.rollback()
        count = 0

    resp = make_response(jsonify({'likes': count, 'liked': not already}))
    resp.set_cookie('blog_sid', sid, max_age=365 * 86400, samesite='Lax')
    return resp


# ── Super admin CRUD ────────────────────────────────────────────────────────────

from utils.decorators import require_super_admin

@blog_bp.route('/admin/')
@require_super_admin
def admin_list():
    try:
        rows = db.session.execute(
            text("SELECT id,title,slug,category,published,featured,view_count,comment_count,published_at FROM blog_posts ORDER BY created_at DESC")
        ).fetchall()
        posts = [dict(r._mapping) for r in rows]
    except Exception:
        posts = []
    return render_template('blog/admin_list.html', posts=posts)


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

        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('blog/admin_edit.html', post=request.form, action='new')

        # Ensure slug uniqueness
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
                 published, featured, view_count, comment_count, created_at, updated_at,
                 published_at)
                VALUES (:title,:slug,:content,:excerpt,:cat,:tags,:hero,:author,
                        :pub,:feat,0,0,NOW(),NOW(),:pub_at)
            """), dict(title=title, slug=slug, content=content, excerpt=excerpt,
                       cat=category, tags=tags, hero=hero, author=author,
                       pub=published, feat=featured,
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
        post = dict(row._mapping) if row else None
    except Exception:
        post = None
    if not post:
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

        try:
            db.session.execute(text("""
                UPDATE blog_posts SET title=:title, content=:content, excerpt=:excerpt,
                category=:cat, tags=:tags, hero_image=:hero, author=:author,
                published=:pub, featured=:feat, updated_at=NOW(),
                published_at=COALESCE(published_at, CASE WHEN :pub THEN NOW() ELSE NULL END)
                WHERE id=:id
            """), dict(title=title, content=content, excerpt=excerpt, cat=category,
                       tags=tags, hero=hero, author=author, pub=published,
                       feat=featured, id=post_id))
            db.session.commit()
            flash('Post updated.', 'success')
            return redirect(url_for('blog.admin_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'error')

    return render_template('blog/admin_edit.html', post=post, action='edit')


@blog_bp.route('/admin/<int:post_id>/delete', methods=['POST'])
@require_super_admin
def admin_delete(post_id):
    try:
        db.session.execute(text("DELETE FROM blog_comments WHERE post_id=:id"), {"id": post_id})
        db.session.execute(text("DELETE FROM blog_likes WHERE post_id=:id"), {"id": post_id})
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
