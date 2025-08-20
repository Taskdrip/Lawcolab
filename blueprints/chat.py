from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app import db
from models import User, ROLE_SUPER_ADMIN

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/start-support-chat')
def start_support_chat():
    """Start a support chat session for new customers"""
    lead_data = session.get('lead_data')
    
    if not lead_data:
        flash('Please complete the signup process first.', 'warning')
        return redirect(url_for('sales.popup_page'))
    
    # Create a simple chat interface for now
    return render_template('chat/support_chat.html', lead_data=lead_data)

@chat_bp.route('/support-chat')
def support_chat():
    """Support chat interface"""
    return render_template('chat/support_chat.html')