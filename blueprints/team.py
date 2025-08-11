from flask import Blueprint, render_template
from utils.decorators import require_team_member_or_admin
from models import User

team_bp = Blueprint('team', __name__)

@team_bp.route('/')
@require_team_member_or_admin
def list_team():
    """List all team members"""
    team_members = User.query.filter(User.role.in_(['admin', 'team_member'])).all()
    return render_template('team/list.html', team_members=team_members)
