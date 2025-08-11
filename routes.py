from flask import session, render_template, redirect, url_for, send_from_directory, make_response
from flask_login import current_user
from app import app, db
from models import User, LawFirm, Project, ProjectAssignment
import os

# Import blueprint modules
from auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.admin import admin_bp
from blueprints.clients import clients_bp
from blueprints.projects import projects_bp
from blueprints.team import team_bp
from blueprints.public import public_bp
from blueprints.chat import chat_bp

# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(clients_bp, url_prefix="/clients")
app.register_blueprint(projects_bp, url_prefix="/projects")
app.register_blueprint(team_bp, url_prefix="/team")
app.register_blueprint(public_bp, url_prefix="/public")
app.register_blueprint(chat_bp, url_prefix="/chat")

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
            return redirect(url_for('admin.admin_dashboard'))
        elif current_user.is_team_member():
            return redirect(url_for('dashboard.team_member_dashboard'))
        else:
            return redirect(url_for('dashboard.client_dashboard'))
    
    # Show public landing page
    firm = LawFirm.query.first()
    return render_template('index.html', firm=firm)

@app.route('/landing')
def landing():
    """Comprehensive landing page"""
    return render_template('landing.html')

@app.route('/about')
def about():
    """About Taskdrip and LawFirmOS page"""
    response = render_template('about.html')
    # Add cache control headers to prevent caching issues
    from flask import make_response
    resp = make_response(response)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/contact')
def contact():
    """Contact Taskdrip page"""
    response = render_template('contact.html')
    # Add cache control headers to prevent caching issues
    from flask import make_response
    resp = make_response(response)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

# Test route to verify pages are working
@app.route('/test-pages')
def test_pages():
    """Simple test page to verify About and Contact pages"""
    return send_from_directory('.', 'test_pages.html')

# Add route to serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('403.html'), 404  # Use same template for simplicity