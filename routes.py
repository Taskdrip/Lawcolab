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
from blueprints.superadmin import superadmin_bp
from blueprints.enhanced_chat import enhanced_chat_bp
from blueprints.support_requests import support_bp

# Import invoice blueprints
from blueprints.invoices.routes import invoices_bp
from blueprints.invoice_chat.routes import invoice_chat_bp

# Import sales blueprint
from blueprints.sales import sales_bp

# Import showcase blueprint
from blueprints.showcase import showcase_bp

# Import payment management blueprints - temporarily disabled
# from blueprints.payment_management import payment_mgmt_bp
# from blueprints.escrow_public import escrow_bp

# Import payment models - temporarily disabled
# import models_payment  # noqa: F401

# Register blueprints
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(clients_bp, url_prefix="/clients")
app.register_blueprint(projects_bp, url_prefix="/projects")
app.register_blueprint(team_bp, url_prefix="/team")
app.register_blueprint(public_bp, url_prefix="/public")
app.register_blueprint(chat_bp, url_prefix="/chat")
app.register_blueprint(superadmin_bp, url_prefix="/superadmin")
app.register_blueprint(support_bp, url_prefix="/support")
app.register_blueprint(enhanced_chat_bp, url_prefix='/enhanced-chat')
app.register_blueprint(invoices_bp, url_prefix="/invoices")
app.register_blueprint(invoice_chat_bp, url_prefix="/invoice-chat")
app.register_blueprint(sales_bp, url_prefix="/sales")
app.register_blueprint(showcase_bp, url_prefix="/showcase")
# app.register_blueprint(payment_mgmt_bp)  # Temporarily disabled
# app.register_blueprint(escrow_bp)  # Temporarily disabled

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    """Main landing page - shows public landing if not authenticated, redirects to dashboard if authenticated"""
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on role
        if current_user.is_super_admin():
            return redirect(url_for('superadmin.dashboard'))
        elif current_user.is_admin():
            return redirect(url_for('admin.admin_dashboard'))
        elif current_user.is_team_member():
            return redirect(url_for('dashboard.team_member_dashboard'))
        else:
            return redirect(url_for('dashboard.client_dashboard'))
    
    # Show public landing page with popup settings
    from models import PopupSettings, CustomerReview, LawFirmShowcase
    from sqlalchemy import desc
    
    # Get popup settings for comprehensive popup
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
    
    # Get featured reviews
    reviews = CustomerReview.query.filter_by(is_active=True).order_by(desc(CustomerReview.is_featured), CustomerReview.id).limit(20).all()
    
    # Get featured law firm showcases
    featured_showcases = LawFirmShowcase.query.filter_by(
        is_featured=True, 
        is_active=True
    ).order_by(LawFirmShowcase.showcase_order.asc()).limit(6).all()
    
    return render_template('index.html', settings=settings, reviews=reviews, featured_showcases=featured_showcases)

@app.route('/landing')
def landing():
    """Comprehensive landing page"""
    return render_template('landing.html')

@app.route('/pricing')
def pricing():
    """Pricing plans page"""
    return render_template('pricing.html')

@app.route('/about')
def about():
    """About Taskdrip and LawColab page"""
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

@app.route('/registration-success')
def registration_success():
    """Thank you page after law firm registration"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return render_template('auth/registration_success.html')

@app.route('/chat-support', methods=['GET', 'POST'])
def chat_support():
    """Redirect to enhanced chat support system"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('enhanced_chat.support_chat'))

# Legal pages routes
@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('legal/privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('legal/terms_of_service.html')

@app.route('/cookie-policy')
def cookie_policy():
    """Cookie Policy page"""
    return render_template('legal/cookie_policy.html')

@app.route('/gdpr')
def gdpr():
    """GDPR page"""
    return render_template('legal/gdpr.html')

@app.route('/features')
def features():
    """Features page"""
    return render_template('features.html')

# Test route to verify pages are working
@app.route('/test-pages')
def test_pages():
    """Simple test page to verify About and Contact pages"""
    return send_from_directory('.', 'test_pages.html')

@app.route('/demo-invoice-create')
def demo_invoice_create():
    """Demo route to show invoice creation with bank details - bypasses auth for testing"""
    from models import User, Project
    
    # Get the first admin user and their law firm
    admin_user = User.query.filter_by(role='admin', active=True).first()
    if not admin_user or not admin_user.law_firm:
        return "No admin user or law firm found for demo", 404
    
    # Simulate login
    from flask_login import login_user
    login_user(admin_user)
    
    # Get clients and projects for the form
    clients = User.query.filter_by(
        law_firm_id=admin_user.law_firm_id,
        role='client',
        active=True
    ).all()
    
    projects = Project.query.filter_by(
        law_firm_id=admin_user.law_firm_id
    ).all()
    
    return render_template('invoices/create.html', clients=clients, projects=projects)

# Add route to serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Invoice blueprints already registered above

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('403.html'), 404  # Use same template for simplicity