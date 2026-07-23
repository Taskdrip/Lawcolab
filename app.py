import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Session secret — must be set via SESSION_SECRET env var in production
_secret = os.environ.get("SESSION_SECRET", "")
if not _secret:
    logger.warning(
        "SESSION_SECRET is not set. Using an insecure default. "
        "Set SESSION_SECRET in your environment before deploying."
    )
    _secret = "change-me-before-deploying-this-app"
app.secret_key = _secret

# Trust Railway's reverse-proxy headers (X-Forwarded-For / X-Forwarded-Proto)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

# ── Session security ──────────────────────────────────────────────────────────
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Use Secure cookies when running under HTTPS (Railway terminates TLS at proxy)
_is_production = os.environ.get("FLASK_ENV", "development") == "production"
app.config["SESSION_COOKIE_SECURE"] = _is_production
app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 7  # 7 days

# ── CSRF ──────────────────────────────────────────────────────────────────────
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["WTF_CSRF_SSL_STRICT"] = False

# ── Database ──────────────────────────────────────────────────────────────────
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url or None
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 10,
    "connect_args": {"connect_timeout": 10},
    "echo": False,
}

# ── Uploads ───────────────────────────────────────────────────────────────────
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

# ── Extensions ────────────────────────────────────────────────────────────────
db = SQLAlchemy(model_class=Base)
db.init_app(app)

csrf = CSRFProtect(app)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Flask-Login ───────────────────────────────────────────────────────────────
from flask_login import LoginManager  # noqa: E402

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"  # type: ignore
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(user_id)


# ── Rate limiter ──────────────────────────────────────────────────────────────
from utils.security import limiter, apply_security_headers  # noqa: E402

limiter.init_app(app)


# ── Security headers on every response ───────────────────────────────────────
@app.after_request
def set_security_headers(response):
    return apply_security_headers(response)


# ── Template filters ──────────────────────────────────────────────────────────
@app.template_filter("nl2br")
def nl2br_filter(text):
    if text is None:
        return ""
    return text.replace("\n", "<br>")


@app.template_filter("currency_symbol")
def currency_symbol_filter(currency_code):
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$", "NGN": "₦"}
    return symbols.get(currency_code, "$")


# ── DB setup + super admin seed ───────────────────────────────────────────────
with app.app_context():
    import models        # noqa: F401
    import models_chat   # noqa: F401
    import models_audit  # noqa: F401
    db.create_all()
    logger.info("Database tables created / verified")

    _sa_email = os.environ.get("SUPER_ADMIN_EMAIL", "").strip().lower()
    _sa_password = os.environ.get("SUPER_ADMIN_PASSWORD", "").strip()
    _sa_first = os.environ.get("SUPER_ADMIN_FIRST_NAME", "Super").strip()
    _sa_last = os.environ.get("SUPER_ADMIN_LAST_NAME", "Admin").strip()

    if _sa_email and _sa_password:
        from models import User, ROLE_SUPER_ADMIN
        import uuid as _uuid

        existing = User.query.filter_by(email=_sa_email).first()
        if not existing:
            sa = User()
            sa.id = str(_uuid.uuid4())
            sa.email = _sa_email
            sa.first_name = _sa_first
            sa.last_name = _sa_last
            sa.role = ROLE_SUPER_ADMIN
            sa.active = True
            sa.law_firm_id = None
            sa.set_password(_sa_password)
            db.session.add(sa)
            db.session.commit()
            logger.info("Super admin created: %s", _sa_email)
        else:
            logger.info("Super admin already exists: %s", _sa_email)
    else:
        logger.warning(
            "SUPER_ADMIN_EMAIL / SUPER_ADMIN_PASSWORD not set — "
            "super admin will not be auto-created on first deploy."
        )
