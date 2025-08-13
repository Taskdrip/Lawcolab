from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import current_user
from models import LawFirm, User, Project, ProjectAssignment
from datetime import datetime
from sqlalchemy import func

public_bp = Blueprint('public', __name__)

@public_bp.route('/landing')
def landing():
    """Public landing page for the law firm"""
    firm = LawFirm.query.first()
    team_members = User.query.filter(User.role.in_(['admin', 'team_member'])).all()
    
    return render_template('public/landing.html', firm=firm, team_members=team_members)

@public_bp.route('/firm/<firm_id>')
def law_firm_profile(firm_id):
    """Public law firm profile page"""
    law_firm = LawFirm.query.get_or_404(firm_id)
    
    # Get firm statistics
    team_count = User.query.filter(
        User.law_firm_id == firm_id,
        User.role.in_(['admin', 'team_member'])
    ).count()
    
    client_count = User.query.filter(
        User.law_firm_id == firm_id,
        User.role == 'client'
    ).count()
    
    project_count = Project.query.filter_by(law_firm_id=firm_id).count()
    
    # Get team members for display
    team_members = User.query.filter(
        User.law_firm_id == firm_id,
        User.role.in_(['admin', 'team_member'])
    ).limit(4).all()
    
    return render_template('public/law_firm_profile.html',
                         law_firm=law_firm,
                         team_count=team_count,
                         client_count=client_count,
                         project_count=project_count,
                         team_members=team_members,
                         current_year=datetime.now().year)

@public_bp.route('/profile/<user_id>')
def user_profile(user_id):
    """Public user profile page"""
    profile_user = User.query.get_or_404(user_id)
    
    # Get user statistics
    active_projects = ProjectAssignment.query.join(Project).filter(
        ProjectAssignment.user_id == user_id,
        Project.status == 'active'
    ).count()
    
    total_collaborations = ProjectAssignment.query.filter_by(user_id=user_id).count()
    
    # Calculate years of experience (since account creation)
    years_experience = max(1, (datetime.now() - profile_user.created_at).days // 365)
    
    # Recent projects for display
    recent_projects = []
    if profile_user.role in ['admin', 'team_member']:
        recent_projects = Project.query.join(ProjectAssignment).filter(
            ProjectAssignment.user_id == user_id
        ).order_by(Project.created_at.desc()).limit(6).all()
    elif profile_user.role == 'client':
        recent_projects = Project.query.join(ProjectAssignment).filter(
            ProjectAssignment.user_id == user_id
        ).order_by(Project.created_at.desc()).limit(3).all()
    
    return render_template('public/user_profile.html',
                         profile_user=profile_user,
                         active_projects_count=active_projects,
                         collaborations_count=total_collaborations,
                         years_experience=years_experience,
                         rating="4.9★",
                         recent_projects=recent_projects,
                         current_cases=recent_projects if profile_user.role == 'client' else [])
