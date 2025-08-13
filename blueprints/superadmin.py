from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from utils.decorators import require_super_admin
from app import db
from models import User, LawFirm, Project, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_CLIENT, ROLE_TEAM_MEMBER
# from utils.forms import LawFirmForm  # Not needed for super admin functions
import uuid
from datetime import datetime

superadmin_bp = Blueprint('superadmin', __name__)

@superadmin_bp.route('/dashboard')
@require_super_admin
def dashboard():
    """Super admin dashboard showing all law firms and platform statistics"""
    # Get platform-wide statistics
    total_law_firms = LawFirm.query.count()
    total_users = User.query.count()
    total_admins = User.query.filter_by(role=ROLE_ADMIN).count()
    total_team_members = User.query.filter_by(role=ROLE_TEAM_MEMBER).count()
    total_clients = User.query.filter_by(role=ROLE_CLIENT).count()
    total_projects = Project.query.count()
    
    # Get recent law firms
    recent_law_firms = LawFirm.query.order_by(LawFirm.created_at.desc()).limit(10).all()
    
    # Get recent admin signups
    recent_admins = User.query.filter_by(role=ROLE_ADMIN).order_by(User.created_at.desc()).limit(10).all()
    
    stats = {
        'total_law_firms': total_law_firms,
        'total_users': total_users,
        'total_admins': total_admins,
        'total_team_members': total_team_members,
        'total_clients': total_clients,
        'total_projects': total_projects
    }
    
    return render_template('superadmin/dashboard.html', 
                         stats=stats,
                         recent_law_firms=recent_law_firms,
                         recent_admins=recent_admins)

@superadmin_bp.route('/law-firms')
@require_super_admin
def manage_law_firms():
    """Manage all law firms on the platform"""
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    
    query = LawFirm.query
    if search:
        query = query.filter(
            db.or_(
                LawFirm.name.contains(search),
                LawFirm.email.contains(search),
                LawFirm.description.contains(search)
            )
        )
    
    law_firms = query.order_by(LawFirm.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    return render_template('superadmin/law_firms.html', 
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
        law_firm = LawFirm.query.get_or_404(firm_id)
        
        # Find the owner/first user of the law firm
        owner = law_firm.users[0] if law_firm.users else None
        
        if not owner:
            return jsonify({
                'success': False,
                'message': 'No users found in this law firm.'
            }), 400
        
        # Grant admin privileges
        owner.role = ROLE_ADMIN
        
        try:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Admin access granted to {owner.full_name} for {law_firm.name}.'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'Error granting admin access.'
            }), 500
    
    return jsonify({
        'success': False,
        'message': 'Invalid action.'
    }), 400

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
            db.or_(
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