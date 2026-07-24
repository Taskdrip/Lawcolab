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

@superadmin_bp.route('/users/delete', methods=['POST'])
@require_super_admin
def delete_user():
    """Delete user account"""
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    if user.is_super_admin():
        flash('Cannot delete super admin account.', 'error')
        return redirect(request.referrer or url_for('superadmin.manage_users'))
    
    email = user.email
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {email} has been permanently deleted.', 'success')
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
        
        if period == '3days':
            expiry = now + timedelta(days=3)
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
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False)
    
    return render_template('superadmin/platform_users.html',
                         users=users,
                         search=search,
                         role_filter=role_filter)

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

@superadmin_bp.route('/law-firms/<int:firm_id>/extend-subscription', methods=['POST'])
@require_super_admin
def extend_subscription(firm_id):
    """Extend or change a law firm's subscription period."""
    firm   = LawFirm.query.get_or_404(firm_id)
    data   = request.get_json()
    period = data.get('period', '1year')
    action = data.get('action', 'extend')   # extend | set

    period_map = {
        '3days': 3, '1month': 30, '3months': 90,
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
