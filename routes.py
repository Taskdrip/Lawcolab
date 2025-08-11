from flask import session, render_template, redirect, url_for
from flask_login import current_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
from models import User, LawFirm, Project, ProjectAssignment

# Register blueprints
app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")

# Import blueprint modules
from blueprints.dashboard import dashboard_bp
from blueprints.admin import admin_bp
from blueprints.clients import clients_bp
from blueprints.projects import projects_bp
from blueprints.team import team_bp
from blueprints.public import public_bp

app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(clients_bp, url_prefix="/clients")
app.register_blueprint(projects_bp, url_prefix="/projects")
app.register_blueprint(team_bp, url_prefix="/team")
app.register_blueprint(public_bp, url_prefix="/public")

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    """Main landing page - shows public landing if not authenticated, redirects to dashboard if authenticated"""
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on role
        if current_user.is_admin():
            return redirect(url_for('dashboard.admin_dashboard'))
        elif current_user.is_team_member():
            return redirect(url_for('dashboard.team_member_dashboard'))
        else:
            return redirect(url_for('dashboard.client_dashboard'))
    
    # Show public landing page
    firm = LawFirm.query.first()
    return render_template('index.html', firm=firm)

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('403.html'), 404  # Use same template for simplicity
