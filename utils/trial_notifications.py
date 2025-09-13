"""
Trial notification system for LawColab
Handles trial expiration warnings and reminders
"""

from datetime import datetime, timedelta
from flask import current_app
from models import User, LawFirm
import logging

def check_trial_expirations():
    """Check for trials expiring soon and send notifications"""
    try:
        # Find trials expiring in 24 hours
        tomorrow = datetime.now() + timedelta(hours=24)
        expiring_tomorrow = LawFirm.query.filter(
            LawFirm.subscription_period == '3days',
            LawFirm.admin_access_granted == True,
            LawFirm.admin_access_expires <= tomorrow,
            LawFirm.admin_access_expires > datetime.now()
        ).all()
        
        # Find trials expiring in 1 hour
        one_hour = datetime.now() + timedelta(hours=1)
        expiring_soon = LawFirm.query.filter(
            LawFirm.subscription_period == '3days',
            LawFirm.admin_access_granted == True,
            LawFirm.admin_access_expires <= one_hour,
            LawFirm.admin_access_expires > datetime.now()
        ).all()
        
        # Send notifications
        for firm in expiring_tomorrow:
            send_trial_expiration_notification(firm, '24_hours')
            
        for firm in expiring_soon:
            send_trial_expiration_notification(firm, '1_hour')
            
        return len(expiring_tomorrow) + len(expiring_soon)
        
    except Exception as e:
        logging.error(f"Error checking trial expirations: {e}")
        return 0

def send_trial_expiration_notification(law_firm, timing):
    """Send trial expiration notification"""
    try:
        # Get the admin user for this law firm
        admin_user = User.query.filter_by(
            law_firm_id=law_firm.id,
            role='admin',
            active=True
        ).first()
        
        if not admin_user:
            return False
        
        # Determine message content based on timing
        if timing == '24_hours':
            subject = "Your LawColab trial expires tomorrow!"
            message = f"Hi {admin_user.full_name}, your 3-day trial expires tomorrow. Upgrade now to keep access!"
        else:  # 1_hour
            subject = "URGENT: Your LawColab trial expires in 1 hour!"
            message = f"Hi {admin_user.full_name}, your trial expires in 1 hour! Upgrade immediately to avoid losing access."
        
        # Log notification (in production, this would send actual email/SMS)
        logging.info(f"TRIAL NOTIFICATION ({timing}): {admin_user.email} - {subject}")
        logging.info(f"MESSAGE: {message}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error sending trial notification for firm {law_firm.id}: {e}")
        return False

def get_trial_flash_messages():
    """Get trial-related flash messages for current user"""
    from flask_login import current_user
    
    if not current_user.is_authenticated or not current_user.law_firm:
        return []
    
    law_firm = current_user.law_firm
    messages = []
    
    if law_firm.subscription_period == '3days' and law_firm.admin_access_granted:
        days_remaining = law_firm.days_until_expiry
        
        if days_remaining == 0:
            time_remaining = law_firm.admin_access_expires - datetime.now()
            hours_remaining = max(0, int(time_remaining.total_seconds() / 3600))
            
            if hours_remaining <= 1:
                messages.append({
                    'type': 'danger',
                    'message': f'⚠️ URGENT: Your trial expires in {hours_remaining} hour{"s" if hours_remaining != 1 else ""}! <a href="/sales/popup" class="alert-link">Upgrade now</a> to keep your data.'
                })
            else:
                messages.append({
                    'type': 'warning',
                    'message': f'Your trial expires today in {hours_remaining} hours. <a href="/sales/popup" class="alert-link">Upgrade now</a> to continue.'
                })
        elif days_remaining == 1:
            messages.append({
                'type': 'info',
                'message': f'Your 3-day trial ends tomorrow. <a href="/sales/popup" class="alert-link">View pricing plans</a> to continue using LawColab.'
            })
    
    return messages