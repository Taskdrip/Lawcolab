from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from replit_auth import require_login
from models import SupportRequest, User, LawFirm
from app import db
from utils.decorators import require_super_admin

support_bp = Blueprint('support', __name__)

@support_bp.route('/chat')
@require_login
def chat():
    """Support chat interface"""
    # Ensure user has a law firm
    if not current_user.law_firm_id:
        if current_user.is_admin():
            current_user.create_law_firm_if_admin()
        else:
            flash('You are not associated with a law firm.', 'error')
            return redirect(url_for('index'))
    
    # Get or create support chat room
    room = current_user.law_firm.get_support_chat_room()
    
    # Get recent messages for the support room
    try:
        from models_chat import ChatMessage
        recent_messages = ChatMessage.query.filter_by(room_id=room.id)\
                                         .order_by(ChatMessage.created_at.desc())\
                                         .limit(50).all()
        recent_messages.reverse()  # Show oldest first
    except ImportError:
        recent_messages = []
    
    return render_template('chat/support_chat.html', 
                         room=room, 
                         recent_messages=recent_messages,
                         current_user=current_user)

@support_bp.route('/support-requests')
@require_super_admin
def list_support_requests():
    """View all support requests for super admin"""
    requests = SupportRequest.query.order_by(SupportRequest.created_at.desc()).all()
    return render_template('superadmin/support_requests.html', requests=requests)

@support_bp.route('/support-request/<int:request_id>')
@require_super_admin
def view_support_request(request_id):
    """View individual support request details"""
    support_request = SupportRequest.query.get_or_404(request_id)
    return render_template('superadmin/support_request_detail.html', request=support_request)

@support_bp.route('/resolve-support-request', methods=['POST'])
@require_super_admin
def resolve_support_request():
    """Mark support request as resolved"""
    data = request.get_json()
    request_id = data.get('request_id')
    
    support_request = SupportRequest.query.get_or_404(request_id)
    support_request.status = 'resolved'
    support_request.resolved_at = db.func.now()
    support_request.resolved_by_id = current_user.id
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Support request marked as resolved.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error resolving request.'})