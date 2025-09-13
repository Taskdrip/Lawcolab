from functools import wraps
from flask import flash, redirect, url_for, request, session, jsonify
from flask_login import current_user
from datetime import datetime, timedelta
import logging

def require_active_subscription(f):
    """Decorator to check if user has an active subscription or trial"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this feature.', 'error')
            return redirect(url_for('auth.login', next=request.url))
        
        # Super admins always have access
        if current_user.is_super_admin():
            return f(*args, **kwargs)
        
        # Handle new admins who don't have a law firm yet - let them access onboarding
        if not current_user.law_firm:
            if current_user.is_admin():
                # Allow admin to create law firm first - they'll get trial access
                return f(*args, **kwargs)
            else:
                flash('No law firm associated with your account.', 'error')
                return redirect(url_for('index'))
        
        law_firm = current_user.law_firm
        
        # Check subscription status
        if not law_firm.admin_access_granted:
            flash('Your account is pending activation. Please complete payment verification.', 'warning')
            return redirect(url_for('subscription_expired'))
        
        if law_firm.is_subscription_expired:
            flash('Your subscription has expired. Please upgrade to continue using LawColab.', 'error')
            return redirect(url_for('subscription_expired'))
        
        # Add trial expiration warning to session for display
        if law_firm.days_until_expiry is not None and law_firm.days_until_expiry <= 1:
            session['trial_expiring'] = True
            session['days_remaining'] = law_firm.days_until_expiry
        
        return f(*args, **kwargs)
    return decorated_function

def trial_warning_context():
    """Add trial warning context to templates"""
    context = {}
    if current_user.is_authenticated and current_user.law_firm:
        law_firm = current_user.law_firm
        if law_firm.admin_access_granted and not law_firm.is_subscription_expired:
            context['subscription_status'] = law_firm.subscription_status
            context['days_until_expiry'] = law_firm.days_until_expiry
            context['is_trial'] = law_firm.subscription_period == '3days'
            
            # Calculate hours remaining for trials
            if law_firm.admin_access_expires and law_firm.subscription_period == '3days':
                time_remaining = law_firm.admin_access_expires - datetime.now()
                context['hours_remaining'] = max(0, int(time_remaining.total_seconds() / 3600))
                context['minutes_remaining'] = max(0, int((time_remaining.total_seconds() % 3600) / 60))
    
    return context

def check_feature_access(feature_name):
    """Check if current user can access a specific feature"""
    if not current_user.is_authenticated:
        return False
    
    # Super admins have access to everything
    if current_user.is_super_admin():
        return True
    
    # Check law firm subscription
    if not current_user.law_firm or not current_user.law_firm.admin_access_granted:
        return False
    
    if current_user.law_firm.is_subscription_expired:
        return False
    
    # Feature-specific restrictions for trial users
    if current_user.law_firm.subscription_period == '3days':
        trial_restricted_features = [
            'advanced_reports',
            'bulk_operations',
            'api_access',
            'white_label'
        ]
        if feature_name in trial_restricted_features:
            return False
    
    return True

def get_trial_notification():
    """Get trial expiration notification message"""
    if not current_user.is_authenticated or not current_user.law_firm:
        return None
    
    law_firm = current_user.law_firm
    
    if not law_firm.admin_access_granted or law_firm.is_subscription_expired:
        return None
    
    days_remaining = law_firm.days_until_expiry
    
    if law_firm.subscription_period == '3days':
        if days_remaining == 0:
            time_remaining = law_firm.admin_access_expires - datetime.now()
            hours_remaining = max(0, int(time_remaining.total_seconds() / 3600))
            return {
                'type': 'urgent',
                'title': 'Trial Expiring Today!',
                'message': f'Your free trial expires in {hours_remaining} hours. Upgrade now to keep your data and continue using LawColab.',
                'action_url': url_for('sales.popup_page'),
                'action_text': 'Upgrade Now'
            }
        elif days_remaining == 1:
            return {
                'type': 'warning',
                'title': 'Trial Expires Tomorrow',
                'message': 'Your 3-day free trial ends tomorrow. Upgrade to continue accessing all features.',
                'action_url': url_for('sales.popup_page'),
                'action_text': 'View Plans'
            }
    
    return None

def require_paid_plan(f):
    """Decorator for features that require a paid subscription (not trial)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this feature.', 'error')
            return redirect(url_for('auth.login', next=request.url))
        
        # Super admins always have access
        if current_user.is_super_admin():
            return f(*args, **kwargs)
        
        if not current_user.law_firm or not current_user.law_firm.admin_access_granted:
            flash('Please activate your subscription to access this feature.', 'error')
            return redirect(url_for('subscription_expired'))
        
        # Block trial users from premium features
        if current_user.law_firm.subscription_period == '3days':
            flash('This feature requires a paid subscription. Upgrade to access premium features.', 'error')
            return redirect(url_for('subscription_expired'))
        
        if current_user.law_firm.is_subscription_expired:
            flash('Your subscription has expired. Please renew to access this feature.', 'error')
            return redirect(url_for('subscription_expired'))
        
        return f(*args, **kwargs)
    return decorated_function