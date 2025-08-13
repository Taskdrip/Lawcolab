from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app import db
from models import User, Project, LawFirm, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from utils.decorators import require_admin
from forms import ClientForm, TeamMemberForm
import uuid

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@require_admin
def admin_dashboard():
    """Admin dashboard showing law firm statistics"""
    # Ensure admin has a law firm
    if not current_user.law_firm_id:
        current_user.create_law_firm_if_admin()
    
    # Get law firm statistics
    total_clients = User.query.filter_by(law_firm_id=current_user.law_firm_id, role=ROLE_CLIENT).count()
    total_team_members = User.query.filter_by(law_firm_id=current_user.law_firm_id, role=ROLE_TEAM_MEMBER).count()
    total_projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).count()
    
    # Recent activity
    recent_clients = User.query.filter_by(law_firm_id=current_user.law_firm_id, role=ROLE_CLIENT).order_by(User.created_at.desc()).limit(5).all()
    recent_projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(Project.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_clients=total_clients,
                         total_team_members=total_team_members,
                         total_projects=total_projects,
                         recent_clients=recent_clients,
                         recent_projects=recent_projects)

@admin_bp.route('/add-client', methods=['GET', 'POST'])
@require_admin
def add_client():
    """Admin can add new clients to their law firm"""
    form = ClientForm()
    
    if form.validate_on_submit():
        # Create new client user
        client = User()
        client.id = str(uuid.uuid4())
        client.first_name = form.first_name.data
        client.last_name = form.last_name.data
        client.email = form.email.data.lower() if form.email.data else None
        client.phone = form.phone.data
        client.company_name = form.company_name.data
        client.company_description = form.company_description.data
        client.industry = form.industry.data
        client.website_url = form.website_url.data
        client.role = ROLE_CLIENT
        client.law_firm_id = current_user.law_firm_id  # Associate with admin's law firm
        client.active = True
        
        # Set a default password (clients should change this)
        if form.password.data:
            client.set_password(form.password.data)
        else:
            client.set_password('ClientPassword123!')  # Default password
        
        try:
            db.session.add(client)
            db.session.commit()
            flash(f'Client {client.full_name} has been added to your law firm successfully!', 'success')
            return redirect(url_for('clients.list_clients'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding client. Please try again.', 'error')
    
    return render_template('admin/add_client.html', form=form)

@admin_bp.route('/add-team-member', methods=['GET', 'POST'])
@require_admin  
def add_team_member():
    """Admin can add new team members to their law firm"""
    # Ensure admin has a law firm
    if not current_user.law_firm_id:
        current_user.create_law_firm_if_admin()
        db.session.commit()
    
    form = TeamMemberForm()
    
    if form.validate_on_submit():
        # Create new team member user
        team_member = User()
        team_member.id = str(uuid.uuid4())
        team_member.first_name = form.first_name.data
        team_member.last_name = form.last_name.data
        team_member.email = form.email.data.lower() if form.email.data else None
        team_member.phone = form.phone.data
        team_member.bio = form.bio.data
        team_member.specialization = form.specialization.data
        # Convert years_experience to int if provided
        if form.years_experience.data and form.years_experience.data.strip():
            try:
                team_member.years_experience = int(form.years_experience.data)
            except ValueError:
                team_member.years_experience = None
        else:
            team_member.years_experience = None
        team_member.education = form.education.data
        team_member.certifications = form.certifications.data
        team_member.role = ROLE_TEAM_MEMBER
        team_member.law_firm_id = current_user.law_firm_id  # Associate with admin's law firm
        team_member.active = True
        
        # Set password
        team_member.set_password(form.password.data)
        
        try:
            db.session.add(team_member)
            db.session.commit()
            flash(f'Team member {team_member.full_name} has been added to your law firm successfully!', 'success')
            return redirect(url_for('team.list_team'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding team member: {str(e)}")  # Debug logging
            flash(f'Error adding team member: {str(e)}', 'error')
    
    return render_template('admin/add_team_member.html', form=form)

@admin_bp.route('/manage-projects')
@require_admin
def manage_projects():
    """Admin project management page"""
    projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(Project.created_at.desc()).all()
    return render_template('admin/manage_projects.html', projects=projects)

@admin_bp.route('/manage-users')
@require_admin
def manage_users():
    """Admin user management page with beautiful interface"""
    # Get all users in the admin's law firm
    users = User.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(User.created_at.desc()).all()
    
    # Get statistics
    total_users = len(users)
    active_users = len([u for u in users if u.active])
    inactive_users = total_users - active_users
    
    # Separate by role
    admins = [u for u in users if u.role == ROLE_ADMIN]
    team_members = [u for u in users if u.role == ROLE_TEAM_MEMBER]
    clients = [u for u in users if u.role == ROLE_CLIENT]
    
    return render_template('admin/manage_users.html', 
                         users=users,
                         total_users=total_users,
                         active_users=active_users,
                         inactive_users=inactive_users,
                         admins=admins,
                         team_members=team_members,
                         clients=clients)

@admin_bp.route('/delete-user/<user_id>', methods=['POST'])
@require_admin
def delete_user(user_id):
    """Delete a user from the database"""
    user = User.query.get_or_404(user_id)
    
    # Security check: ensure user belongs to admin's law firm
    if user.law_firm_id != current_user.law_firm_id:
        flash('You can only delete users from your own law firm.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        # Store name for confirmation message
        user_name = user.full_name
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {user_name} has been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete user. Please try again.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/toggle-user-status/<user_id>', methods=['POST'])
@require_admin
def toggle_user_status(user_id):
    """Toggle user active/inactive status"""
    user = User.query.get_or_404(user_id)
    
    # Security check: ensure user belongs to admin's law firm
    if user.law_firm_id != current_user.law_firm_id:
        flash('You can only manage users from your own law firm.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Prevent admin from deactivating themselves
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        user.active = not user.active
        status = 'activated' if user.active else 'deactivated'
        db.session.commit()
        
        flash(f'User {user.full_name} has been {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status. Please try again.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/firm-profile', methods=['GET', 'POST'])
@require_admin
def firm_profile():
    """Admin can manage law firm profile"""
    firm = LawFirm.query.get(current_user.law_firm_id)
    
    if request.method == 'POST' and firm:
        firm.name = request.form.get('name')
        firm.description = request.form.get('description')
        firm.phone = request.form.get('phone')
        firm.email = request.form.get('email')
        firm.address = request.form.get('address')
        firm.website = request.form.get('website')
        firm.practice_areas = request.form.get('practice_areas')
        
        try:
            db.session.commit()
            flash('Law firm profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'error')
    
    return render_template('admin/firm_profile.html', firm=firm)

@admin_bp.route('/banking-settings', methods=['GET', 'POST'])
@require_admin
def banking_settings():
    """Admin can manage banking details for receiving payments"""
    firm = LawFirm.query.get(current_user.law_firm_id)
    
    if request.method == 'POST' and firm:
        # Update banking details
        firm.bank_name = request.form.get('bank_name', '').strip()
        firm.account_holder_name = request.form.get('account_holder_name', '').strip()
        firm.account_number = request.form.get('account_number', '').strip()
        firm.routing_number = request.form.get('routing_number', '').strip()
        firm.swift_code = request.form.get('swift_code', '').strip()
        firm.tax_id = request.form.get('tax_id', '').strip()
        
        try:
            db.session.commit()
            flash('Banking details updated successfully! Your clients will now see these payment details on invoices.', 'success')
            return redirect(url_for('admin.banking_settings'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating banking details. Please try again.', 'error')
    
    return render_template('admin/banking_settings.html', firm=firm)