from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user

def simple_login_required(f):
    """Simple login check without OAuth token verification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_super_admin(f):
    @wraps(f)
    @simple_login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_super_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    @wraps(f)
    @simple_login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_super_admin()):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def require_team_member_or_admin(f):
    @wraps(f)
    @simple_login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_team_member() or current_user.is_super_admin()):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def require_client_or_admin(f):
    @wraps(f)
    @simple_login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_client()):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    """
    Decorator to require specific roles for access
    Args:
        roles: List of allowed roles or single role string
    """
    if isinstance(roles, str):
        roles = [roles]
    
    def decorator(f):
        @wraps(f)
        @simple_login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
