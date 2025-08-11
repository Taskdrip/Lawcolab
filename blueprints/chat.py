from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from utils.decorators import simple_login_required
from app import db
from models import User, ChatMessage, ChatConversation
from sqlalchemy import or_, and_, desc
from datetime import datetime
import json

chat_bp = Blueprint('chat', __name__, template_folder='../templates')

@chat_bp.route('/')
@simple_login_required
def chat_home():
    """Main chat interface showing conversations list"""
    # Get all conversations for current user
    conversations = db.session.query(ChatConversation).filter(
        or_(
            ChatConversation.user1_id == current_user.id,
            ChatConversation.user2_id == current_user.id
        )
    ).order_by(desc(ChatConversation.last_message_at)).all()
    
    # Get all users except current user for starting new conversations
    all_users = User.query.filter(
        and_(User.id != current_user.id, User.active == True)
    ).order_by(User.first_name, User.last_name).all()
    
    # Get unread message counts
    unread_counts = {}
    for conversation in conversations:
        other_user = conversation.get_other_user(current_user.id)
        unread_count = ChatMessage.query.filter(
            and_(
                ChatMessage.sender_id == other_user.id,
                ChatMessage.receiver_id == current_user.id,
                ChatMessage.is_read == False
            )
        ).count()
        unread_counts[other_user.id] = unread_count
    
    return render_template('chat/home.html', 
                         conversations=conversations, 
                         all_users=all_users,
                         unread_counts=unread_counts)

@chat_bp.route('/conversation/<user_id>')
@simple_login_required
def conversation(user_id):
    """View conversation with a specific user"""
    other_user = User.query.get_or_404(user_id)
    
    if other_user.id == current_user.id:
        flash("You can't chat with yourself!", 'warning')
        return redirect(url_for('chat.chat_home'))
    
    # Get or create conversation
    conversation = ChatConversation.query.filter(
        or_(
            and_(ChatConversation.user1_id == current_user.id, ChatConversation.user2_id == user_id),
            and_(ChatConversation.user1_id == user_id, ChatConversation.user2_id == current_user.id)
        )
    ).first()
    
    if not conversation:
        # Create new conversation
        conversation = ChatConversation(
            user1_id=min(current_user.id, user_id),
            user2_id=max(current_user.id, user_id)
        )
        db.session.add(conversation)
        db.session.commit()
    
    # Get messages for this conversation
    messages = ChatMessage.query.filter(
        or_(
            and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == user_id),
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == current_user.id)
        )
    ).order_by(ChatMessage.timestamp.asc()).all()
    
    # Mark messages from other user as read
    ChatMessage.query.filter(
        and_(
            ChatMessage.sender_id == user_id,
            ChatMessage.receiver_id == current_user.id,
            ChatMessage.is_read == False
        )
    ).update({'is_read': True})
    db.session.commit()
    
    return render_template('chat/conversation.html', 
                         other_user=other_user, 
                         messages=messages,
                         conversation=conversation)

@chat_bp.route('/send_message', methods=['POST'])
@simple_login_required
def send_message():
    """Send a message to another user"""
    try:
        data = request.get_json()
        receiver_id = data.get('receiver_id')
        message_text = data.get('message', '').strip()
        
        if not receiver_id or not message_text:
            return jsonify({'error': 'Missing receiver or message'}), 400
        
        receiver = User.query.get(receiver_id)
        if not receiver or not receiver.active:
            return jsonify({'error': 'Invalid recipient'}), 400
        
        if receiver.id == current_user.id:
            return jsonify({'error': 'Cannot send message to yourself'}), 400
        
        # Create new message
        message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            message=message_text
        )
        db.session.add(message)
        
        # Update or create conversation
        conversation = ChatConversation.query.filter(
            or_(
                and_(ChatConversation.user1_id == current_user.id, ChatConversation.user2_id == receiver_id),
                and_(ChatConversation.user1_id == receiver_id, ChatConversation.user2_id == current_user.id)
            )
        ).first()
        
        if conversation:
            conversation.last_message_at = datetime.now()
        else:
            conversation = ChatConversation(
                user1_id=min(current_user.id, receiver_id),
                user2_id=max(current_user.id, receiver_id),
                last_message_at=datetime.now()
            )
            db.session.add(conversation)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message_id': message.id,
            'timestamp': message.timestamp.strftime('%H:%M')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to send message'}), 500

@chat_bp.route('/api/messages/<user_id>')
@simple_login_required
def get_messages(user_id):
    """Get messages with a specific user (API endpoint)"""
    try:
        messages = ChatMessage.query.filter(
            or_(
                and_(ChatMessage.sender_id == current_user.id, ChatMessage.receiver_id == user_id),
                and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == current_user.id)
            )
        ).order_by(ChatMessage.timestamp.asc()).all()
        
        message_list = []
        for msg in messages:
            message_list.append({
                'id': msg.id,
                'sender_id': msg.sender_id,
                'receiver_id': msg.receiver_id,
                'message': msg.message,
                'timestamp': msg.timestamp.strftime('%H:%M'),
                'is_own': msg.sender_id == current_user.id,
                'sender_name': msg.sender.full_name
            })
        
        return jsonify({'messages': message_list})
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch messages'}), 500

@chat_bp.route('/api/unread_count')
@simple_login_required
def get_unread_count():
    """Get total unread message count for current user"""
    try:
        unread_count = ChatMessage.query.filter(
            and_(
                ChatMessage.receiver_id == current_user.id,
                ChatMessage.is_read == False
            )
        ).count()
        
        return jsonify({'unread_count': unread_count})
        
    except Exception as e:
        return jsonify({'error': 'Failed to get unread count'}), 500