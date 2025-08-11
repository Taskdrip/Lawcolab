from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from utils.decorators import require_admin
from utils.forms import LawFirmProfileForm, UserRoleForm, UserProfileForm
from app import db
from models import LawFirm, User

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/firm-profile', methods=['GET', 'POST'])
@require_admin
def firm_profile():
    """Manage law firm profile"""
    firm = LawFirm.query.first()
    form = LawFirmProfileForm()
    
    if form.validate_on_submit():
        if not firm:
            firm = LawFirm()
            db.session.add(firm)
        
        firm.name = form.name.data
        firm.description = form.description.data
        firm.logo_url = form.logo_url.data
        firm.phone = form.phone.data
        firm.email = form.email.data
        firm.address = form.address.data
        firm.website = form.website.data
        firm.practice_areas = form.practice_areas.data
        
        db.session.commit()
        flash('Firm profile updated successfully!', 'success')
        return redirect(url_for('admin.firm_profile'))
    
    # Pre-populate form if firm exists
    if firm:
        form.name.data = firm.name
        form.description.data = firm.description
        form.logo_url.data = firm.logo_url
        form.phone.data = firm.phone
        form.email.data = firm.email
        form.address.data = firm.address
        form.website.data = firm.website
        form.practice_areas.data = firm.practice_areas
    
    return render_template('admin/firm_profile.html', form=form, firm=firm)

@admin_bp.route('/team-management')
@require_admin
def team_management():
    """Manage team members"""
    team_members = User.query.filter(User.role.in_(['admin', 'team_member'])).all()
    clients = User.query.filter_by(role='client').all()
    return render_template('admin/team_management.html', 
                         team_members=team_members, 
                         clients=clients)

@admin_bp.route('/user/<user_id>/role', methods=['POST'])
@require_admin
def update_user_role():
    """Update user role"""
    user_id = request.form.get('user_id')
    new_role = request.form.get('role')
    
    user = User.query.get_or_404(user_id)
    
    if new_role in ['admin', 'team_member', 'client']:
        user.role = new_role
        db.session.commit()
        flash(f'User role updated to {new_role}!', 'success')
    else:
        flash('Invalid role specified!', 'error')
    
    return redirect(url_for('admin.team_management'))

@admin_bp.route('/user/<user_id>/profile', methods=['GET', 'POST'])
@require_admin
def edit_user_profile(user_id):
    """Edit user profile"""
    user = User.query.get_or_404(user_id)
    form = UserProfileForm()
    
    if form.validate_on_submit():
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.phone = form.phone.data
        user.bio = form.bio.data
        
        db.session.commit()
        flash('User profile updated successfully!', 'success')
        return redirect(url_for('admin.team_management'))
    
    # Pre-populate form
    form.first_name.data = user.first_name
    form.last_name.data = user.last_name
    form.phone.data = user.phone
    form.bio.data = user.bio
    
    return render_template('admin/edit_user_profile.html', form=form, user=user)
