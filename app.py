from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_wtf.csrf import CSRFProtect
import os
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

# Configure logging for production performance
logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or "fallback-secret-key-for-development"
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# CSRF Configuration
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit for CSRF tokens
app.config['WTF_CSRF_SSL_STRICT'] = False  # Allow HTTP for development

# Database configuration optimized for performance
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 10,
    'max_overflow': 20,
    'echo': False  # Disable SQL logging for performance
}

# Upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize database
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Exempt login route from CSRF protection
@csrf.exempt
def csrf_exempt_login():
    pass

# Create uploads directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Set up Flask-Login
from flask_login import LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # type: ignore
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(user_id)

# Custom template filter for line breaks
@app.template_filter('nl2br')
def nl2br_filter(text):
    """Convert newlines to <br> tags"""
    if text is None:
        return ''
    return text.replace('\n', '<br>')

# Custom template filter for currency symbols
@app.template_filter('currency_symbol')
def currency_symbol_filter(currency_code):
    """Convert currency code to symbol"""
    symbols = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'CAD': '$',
        'NGN': '₦'
    }
    return symbols.get(currency_code, '$')

# Create tables
with app.app_context():
    import models  # noqa: F401
    import models_chat  # noqa: F401
    db.create_all()
    logging.info("Database tables created")
