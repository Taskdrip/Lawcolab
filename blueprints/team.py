from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_team_member_or_admin
from app import db
from models import User, Project, ProjectAssignment
from utils.profile_upload import save_profile_image

team_bp = Blueprint('team', __name__)

@team_bp.route('/')
@require_team_member_or_admin
def list_team():
    """List all team members"""
    # Only show team members from the same law firm
    team_members = User.query.filter(
        User.role.in_(['admin', 'team_member']),
        User.law_firm_id == current_user.law_firm_id,
        User.active == True
    ).all()
    return render_template('team/list.html', team_members=team_members)

@team_bp.route('/<member_id>')
@require_login
def team_member_profile(member_id):
    """View team member profile"""
    team_member = User.query.filter(
        User.id == member_id,
        User.role.in_(['admin', 'team_member'])
    ).first_or_404()
    
    # Get team member's projects
    projects = Project.query.join(Project.assignments).filter_by(user_id=member_id).all()
    
    # Count unique clients
    client_ids = set()
    for project in projects:
        for assignment in project.assignments:
            if assignment.user.is_client():
                client_ids.add(assignment.user_id)
    client_count = len(client_ids)
    
    return render_template('team/profile_enhanced.html',
                         team_member=team_member,
                         projects=projects,
                         client_count=client_count)

@team_bp.route('/<member_id>/upload_profile_image', methods=['POST'])
@require_login
def upload_profile_image(member_id):
    """Upload profile image for team member"""
    team_member = User.query.filter(
        User.id == member_id,
        User.role.in_(['admin', 'team_member'])
    ).first_or_404()
    
    # Check permissions - only admin or the team member themselves can upload
    if not (current_user.is_admin() or current_user.id == member_id):
        flash('You do not have permission to update this profile.', 'error')
        return redirect(url_for('team.team_member_profile', member_id=member_id))
    
    if 'profile_image' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('team.team_member_profile', member_id=member_id))
    
    file = request.files['profile_image']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('team.team_member_profile', member_id=member_id))
    
    filename = save_profile_image(file, member_id)
    if filename:
        team_member.profile_image_url = filename
        db.session.commit()
        flash('Profile image updated successfully!', 'success')
    else:
        flash('Invalid file type. Please upload a PNG, JPG, or GIF image.', 'error')
    
    return redirect(url_for('team.team_member_profile', member_id=member_id))
