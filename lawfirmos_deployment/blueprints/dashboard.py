from flask import Blueprint, render_template
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_admin, require_team_member_or_admin
from app import db
from models import User, Project, LawFirm, ClientNote, ProjectFile

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/admin')
@require_admin
def admin_dashboard():
    """Admin dashboard with overview metrics"""
    # Get overview statistics
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='active').count()
    total_clients = User.query.filter_by(role='client').count()
    total_team_members = User.query.filter_by(role='team_member').count()
    
    # Recent activity
    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()
    recent_files = ProjectFile.query.order_by(ProjectFile.uploaded_at.desc()).limit(5).all()
    recent_notes = ClientNote.query.order_by(ClientNote.created_at.desc()).limit(5).all()
    
    return render_template('dashboard/admin.html',
                         total_projects=total_projects,
                         active_projects=active_projects,
                         total_clients=total_clients,
                         total_team_members=total_team_members,
                         recent_projects=recent_projects,
                         recent_files=recent_files,
                         recent_notes=recent_notes)

@dashboard_bp.route('/team-member')
@require_team_member_or_admin
def team_member_dashboard():
    """Team member dashboard"""
    # Get projects assigned to this team member
    assigned_projects = Project.query.join(Project.assignments).filter_by(user_id=current_user.id).all()
    
    # Get clients for assigned projects
    client_ids = set()
    for project in assigned_projects:
        for assignment in project.assignments:
            if assignment.user.is_client():
                client_ids.add(assignment.user.id)
    
    clients = User.query.filter(User.id.in_(client_ids)).all() if client_ids else []
    
    return render_template('dashboard/team_member.html',
                         assigned_projects=assigned_projects,
                         clients=clients)

@dashboard_bp.route('/client')
@require_login
def client_dashboard():
    """Client dashboard"""
    if not current_user.is_client():
        # Allow admins and team members to view this for testing
        if not (current_user.is_admin() or current_user.is_team_member()):
            return redirect(url_for('dashboard.admin_dashboard'))
    
    # Get projects assigned to this client
    assigned_projects = Project.query.join(Project.assignments).filter_by(user_id=current_user.id).all()
    
    # Get team members for assigned projects
    team_member_ids = set()
    for project in assigned_projects:
        for assignment in project.assignments:
            if assignment.user.is_team_member():
                team_member_ids.add(assignment.user.id)
    
    team_members = User.query.filter(User.id.in_(team_member_ids)).all() if team_member_ids else []
    
    return render_template('dashboard/client.html',
                         assigned_projects=assigned_projects,
                         team_members=team_members)
