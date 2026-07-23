"""
Security utilities for LawColab — rate limiting, brute-force protection,
secure headers, and login attempt tracking.
"""
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, flash, redirect, url_for, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Uses in-memory storage (single process). Cross-process protection is handled
# by DB-backed account lockout below.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # No global default — apply per-route
    storage_uri="memory://",
)

# ── Account-lockout constants ─────────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 10       # lock after this many failures
LOCKOUT_DURATION_MINUTES = 30  # lockout duration

def record_failed_login(user, db):
    """Increment failed attempts and lock account if threshold reached."""
    if user is None:
        return
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        logger.warning(
            "Account locked for %s after %d failed attempts",
            user.email, user.failed_login_attempts
        )
    db.session.commit()


def record_successful_login(user, db, ip_address=None):
    """Reset failed attempts on successful login."""
    if user is None:
        return
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip_address
    db.session.commit()


def is_account_locked(user):
    """Return True if the account is currently locked out."""
    if user is None:
        return False
    if user.locked_until and user.locked_until > datetime.utcnow():
        return True
    # Auto-clear expired lock
    if user.locked_until and user.locked_until <= datetime.utcnow():
        user.locked_until = None
        user.failed_login_attempts = 0
    return False


def get_lockout_remaining(user):
    """Return minutes remaining in lockout, or 0."""
    if not user or not user.locked_until:
        return 0
    remaining = (user.locked_until - datetime.utcnow()).total_seconds() / 60
    return max(0, round(remaining))


# ── Security Headers ──────────────────────────────────────────────────────────
def apply_security_headers(response):
    """Add hardened HTTP security headers to every response."""
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # Stop MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # XSS filter for older browsers
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Referrer policy — don't leak full URL to third parties
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Permissions policy — disable sensitive browser APIs
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=()"
    )
    # HSTS — enforce HTTPS for 1 year (Railway terminates TLS at the proxy)
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    # Basic CSP — allows CDN resources used by the templates
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://code.jquery.com https://stackpath.bootstrapcdn.com; "
        "style-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com https://stackpath.bootstrapcdn.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )
    return response
