from flask import Blueprint, render_template
from models import LawFirm, User

public_bp = Blueprint('public', __name__)

@public_bp.route('/landing')
def landing():
    """Public landing page for the law firm"""
    firm = LawFirm.query.first()
    team_members = User.query.filter(User.role.in_(['admin', 'team_member'])).all()
    
    return render_template('public/landing.html', firm=firm, team_members=team_members)
