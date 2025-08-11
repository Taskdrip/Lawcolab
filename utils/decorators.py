from functools import wraps
from flask import abort
from flask_login import current_user
from replit_auth import require_login

def require_role(role):
    """Decorator to require a specific role"""
    def decorator(f):
        @wraps(f)
        @require_login
        def decorated_function(*args, **kwargs):
            if not current_user.has_role(role):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_admin(f):
    """Decorator to require admin role"""
    return require_role('admin')(f)

def require_team_member_or_admin(f):
    """Decorator to require team member or admin role"""
    @wraps(f)
    @require_login
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_team_member()):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
