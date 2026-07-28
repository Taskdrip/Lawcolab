from flask import Blueprint, render_template
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_admin, require_team_member_or_admin
from app import db
from models import User, Project, LawFirm, ClientNote, ProjectFile, DashboardSlider, LegalNews

dashboard_bp = Blueprint('dashboard', __name__)


def _get_sliders(law_firm_id):
    """Return active slides for a law firm, or platform-default slides."""
    slides = (DashboardSlider.query
              .filter_by(law_firm_id=law_firm_id, is_active=True)
              .order_by(DashboardSlider.sort_order)
              .all())
    if not slides:
        slides = (DashboardSlider.query
                  .filter_by(law_firm_id=None, is_active=True)
                  .order_by(DashboardSlider.sort_order)
                  .all())
    return slides


def _get_legal_news():
    """Return active legal news posts for the news banner."""
    return (LegalNews.query
            .filter_by(is_active=True)
            .order_by(LegalNews.sort_order, LegalNews.created_at.desc())
            .limit(8)
            .all())


@dashboard_bp.route('/admin')
@require_admin
def admin_dashboard():
    """Admin dashboard — redirects to the canonical admin dashboard (law-firm-scoped)."""
    from flask import redirect, url_for
    return redirect(url_for('admin.admin_dashboard'))

@dashboard_bp.route('/team-member')
@require_team_member_or_admin
def team_member_dashboard():
    """Team member dashboard — scope varies based on is_full_access flag."""
    from datetime import datetime as _dt, timedelta as _td
    law_firm_id = current_user.law_firm_id

    if current_user.is_full_access:
        # Full-access members see all firm projects and clients
        assigned_projects = (Project.query
                             .filter_by(law_firm_id=law_firm_id)
                             .order_by(Project.created_at.desc())
                             .all())
        clients = (User.query
                   .filter_by(law_firm_id=law_firm_id, role='client')
                   .order_by(User.created_at.desc())
                   .limit(20)
                   .all())
    else:
        # Limited — only directly assigned projects
        assigned_projects = (Project.query
                             .join(Project.assignments)
                             .filter_by(user_id=current_user.id)
                             .order_by(Project.created_at.desc())
                             .all())
        client_ids = set()
        for project in assigned_projects:
            for assignment in project.assignments:
                if assignment.user and assignment.user.is_client():
                    client_ids.add(assignment.user.id)
        clients = (User.query
                   .filter(User.id.in_(client_ids))
                   .all()) if client_ids else []

    sliders = _get_sliders(law_firm_id)
    legal_news = _get_legal_news()

    return render_template('dashboard/team_member.html',
                           assigned_projects=assigned_projects,
                           clients=clients,
                           sliders=sliders,
                           legal_news=legal_news)


@dashboard_bp.route('/client')
@require_login
def client_dashboard():
    """Client dashboard"""
    if not current_user.is_client():
        if not (current_user.is_admin() or current_user.is_team_member()):
            return redirect(url_for('dashboard.admin_dashboard'))

    assigned_projects = Project.query.join(Project.assignments).filter_by(user_id=current_user.id).all()

    team_member_ids = set()
    for project in assigned_projects:
        for assignment in project.assignments:
            if assignment.user.is_team_member():
                team_member_ids.add(assignment.user.id)

    team_members = User.query.filter(User.id.in_(team_member_ids)).all() if team_member_ids else []
    sliders = _get_sliders(current_user.law_firm_id)
    legal_news = _get_legal_news()

    return render_template('dashboard/client.html',
                         assigned_projects=assigned_projects,
                         team_members=team_members,
                         sliders=sliders,
                         legal_news=legal_news)
