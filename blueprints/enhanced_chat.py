from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from replit_auth import require_login
from app import db
from models import User, LawFirm, Project, ProjectAssignment, ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from models_chat import ChatRoom, ChatParticipant, ChatMessage, SuperAdminBroadcast, BroadcastDelivery
from sqlalchemy import or_, and_, desc
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import uuid

enhanced_chat_bp = Blueprint('enhanced_chat', __name__, template_folder='../templates')

@enhanced_chat_bp.route('/support')
@require_login
def support_chat():
    """Law firm support chat with super admin"""
    if not current_user.law_firm_id:
        if current_user.is_admin():
            current_user.create_law_firm_if_admin()
        else:
            flash('You are not associated with a law firm.', 'error')
            return redirect(url_for('index'))
    
    # Check if this is a new law firm without admin access
    if not current_user.law_firm.admin_access_granted:
        return render_template('chat/subscription_request.html')
    
    # Get or create support chat room
    support_room = current_user.law_firm.get_support_chat_room()
    
    # Get chat messages
    messages = ChatMessage.query.filter_by(room_id=support_room.id)\
                               .order_by(ChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    participant = ChatParticipant.query.filter_by(
        room_id=support_room.id,
        user_id=current_user.id
    ).first()
    
    if participant:
        participant.last_read_at = datetime.now()
        db.session.commit()
    
    return render_template('chat/support_chat.html', 
                         room=support_room, 
                         messages=messages,
                         current_user=current_user)

@enhanced_chat_bp.route('/request-access', methods=['POST'])
@require_login
def request_access():
    """Handle subscription request and send to super admin chat"""
    if not current_user.law_firm_id:
        if current_user.is_admin():
            current_user.create_law_firm_if_admin()
        else:
            return jsonify({'success': False, 'message': 'No law firm associated'})
    
    # Get form data
    request_type = request.form.get('request_type')
    team_size = request.form.get('team_size', 'Not specified')
    additional_message = request.form.get('message', '')
    
    # Create pricing map
    pricing = {
        'trial': 'FREE 3-Day Trial',
        '1month': '$70 (1 Month)',
        '3months': '$190 (3 Months) - Save $20',
        '6months': '$400 (6 Months) - Save $70', 
        '1year': '$750 (1 Year) - Save $190'
    }
    
    # Create support request message
    plan_display = pricing.get(request_type, request_type)
    
    request_message = f"""🚀 NEW SUBSCRIPTION REQUEST

Law Firm: {current_user.law_firm.name}
Plan Requested: {plan_display}
Team Size: {team_size}
Admin Contact: {current_user.full_name} ({current_user.email})

{f'Additional Message: {additional_message}' if additional_message else ''}

Please review and activate admin access for this law firm."""
    
    # Get or create support room
    support_room = current_user.law_firm.get_support_chat_room()
    
    # Send message to support room
    message = ChatMessage(
        room_id=support_room.id,
        sender_id=current_user.id,
        message_content=request_message,
        message_type='text'
    )
    
    db.session.add(message)
    
    # Also create support request record
    from models import SupportRequest
    support_request = SupportRequest(
        user_id=current_user.id,
        law_firm_id=current_user.law_firm_id,
        request_type=request_type,
        message=additional_message,
        team_size=team_size
    )
    
    db.session.add(support_request)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Request sent to admin team'})

@enhanced_chat_bp.route('/project/<int:project_id>')
@require_login
def project_chat(project_id):
    """Project-based team chat - only assigned members can access"""
    project = Project.query.get_or_404(project_id)
    
    # Check if user is assigned to this project
    if not current_user.is_assigned_to_project(project_id):
        flash('You are not assigned to this project.', 'error')
        return redirect(url_for('projects.list_projects'))
    
    # Get or create project chat room
    project_room = ChatRoom.query.filter_by(
        project_id=project_id,
        room_type='project',
        is_active=True
    ).first()
    
    if not project_room:
        project_room = ChatRoom(
            name=f"Project: {project.title}",
            room_type='project',
            law_firm_id=project.law_firm_id,
            project_id=project_id,
            created_by_id=current_user.id
        )
        db.session.add(project_room)
        db.session.flush()
        
        # Add all assigned users as participants
        for assignment in project.assignments:
            participant = ChatParticipant(
                room_id=project_room.id,
                user_id=assignment.user_id
            )
            db.session.add(participant)
        
        db.session.commit()
    
    # Get chat messages
    messages = ChatMessage.query.filter_by(room_id=project_room.id)\
                               .order_by(ChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    participant = ChatParticipant.query.filter_by(
        room_id=project_room.id,
        user_id=current_user.id
    ).first()
    
    if participant:
        participant.last_read_at = datetime.now()
        db.session.commit()
    
    return render_template('chat/project_chat.html', 
                         room=project_room, 
                         project=project,
                         messages=messages,
                         current_user=current_user)

@enhanced_chat_bp.route('/send-message', methods=['POST'])
@require_login
def send_message():
    """Send a message to a chat room"""
    data = request.get_json()
    room_id = data.get('room_id')
    message_content = data.get('message', '').strip()
    
    if not message_content:
        return jsonify({'success': False, 'message': 'Message content is required'}), 400
    
    room = ChatRoom.query.get_or_404(room_id)
    
    # Check if user is participant in this room
    participant = ChatParticipant.query.filter_by(
        room_id=room_id,
        user_id=current_user.id,
        is_active=True
    ).first()
    
    if not participant:
        return jsonify({'success': False, 'message': 'Not authorized to send messages in this room'}), 403
    
    # Create message
    message = ChatMessage(
        room_id=room_id,
        sender_id=current_user.id,
        message_content=message_content,
        message_type='text'
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message_id': message.id,
        'sender_name': current_user.full_name,
        'sender_role': current_user.role,
        'is_super_admin': current_user.role == ROLE_SUPER_ADMIN,
        'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@enhanced_chat_bp.route('/upload-file', methods=['POST'])
@require_login
def upload_file():
    """Upload file to chat room"""
    room_id = request.form.get('room_id')
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    room = ChatRoom.query.get_or_404(room_id)
    
    # Check if user is participant in this room
    participant = ChatParticipant.query.filter_by(
        room_id=room_id,
        user_id=current_user.id,
        is_active=True
    ).first()
    
    if not participant:
        return jsonify({'success': False, 'message': 'Not authorized to upload files in this room'}), 403
    
    # Secure filename
    filename = secure_filename(file.filename)
    if filename == '':
        filename = f"file_{uuid.uuid4().hex[:8]}"
    
    # Create upload directory
    upload_dir = os.path.join('uploads', 'chat', str(room_id))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{filename}")
    file.save(file_path)
    
    # Create message
    message = ChatMessage(
        room_id=room_id,
        sender_id=current_user.id,
        message_content=f"Uploaded file: {filename}",
        message_type='file',
        file_path=file_path,
        file_name=filename
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message_id': message.id,
        'filename': filename,
        'sender_name': current_user.full_name,
        'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@enhanced_chat_bp.route('/superadmin/broadcast', methods=['GET', 'POST'])
@require_login
def superadmin_broadcast():
    """Super admin broadcast messages to law firms"""
    if current_user.role != ROLE_SUPER_ADMIN:
        flash('Access denied. Super admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message_content = request.form.get('message', '').strip()
        target_type = request.form.get('target_type', 'all')
        is_urgent = request.form.get('is_urgent') == 'on'
        
        if not title or not message_content:
            flash('Title and message are required.', 'error')
            return redirect(request.url)
        
        # Create broadcast
        broadcast = SuperAdminBroadcast(
            sender_id=current_user.id,
            title=title,
            message_content=message_content,
            target_type=target_type,
            is_urgent=is_urgent
        )
        
        db.session.add(broadcast)
        db.session.flush()
        
        # Get target law firms
        query = LawFirm.query
        if target_type == 'active':
            query = query.filter_by(admin_access_granted=True)
        elif target_type == 'expired':
            query = query.filter(LawFirm.admin_access_expires < datetime.now())
        elif target_type == 'pending':
            query = query.filter_by(admin_access_granted=False)
        
        target_firms = query.all()
        
        # Create deliveries and send to support chats
        for firm in target_firms:
            # Create delivery record
            delivery = BroadcastDelivery(
                broadcast_id=broadcast.id,
                law_firm_id=firm.id
            )
            db.session.add(delivery)
            
            # Send to support chat
            support_room = firm.get_support_chat_room()
            if support_room:
                message = ChatMessage(
                    room_id=support_room.id,
                    sender_id=current_user.id,
                    message_content=f"📢 **{title}**\n\n{message_content}",
                    message_type='broadcast',
                    is_broadcast=True
                )
                db.session.add(message)
        
        db.session.commit()
        flash(f'Broadcast sent to {len(target_firms)} law firms.', 'success')
        return redirect(request.url)
    
    # Get recent broadcasts
    recent_broadcasts = SuperAdminBroadcast.query\
                                         .order_by(SuperAdminBroadcast.created_at.desc())\
                                         .limit(10).all()
    
    return render_template('chat/superadmin_broadcast.html', 
                         broadcasts=recent_broadcasts)

@enhanced_chat_bp.route('/superadmin/support-rooms')
@require_login
def superadmin_support_rooms():
    """Super admin view of all support rooms"""
    if current_user.role != ROLE_SUPER_ADMIN:
        flash('Access denied. Super admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get all support rooms with unread messages count
    support_rooms = ChatRoom.query.filter_by(room_type='support', is_active=True)\
                                  .order_by(ChatRoom.updated_at.desc()).all()
    
    # Calculate unread counts for super admin
    room_data = []
    for room in support_rooms:
        # Get super admin participant or create one
        super_admin_participant = ChatParticipant.query.filter_by(
            room_id=room.id,
            user_id=current_user.id
        ).first()
        
        if not super_admin_participant:
            super_admin_participant = ChatParticipant(
                room_id=room.id,
                user_id=current_user.id,
                joined_at=datetime.now(),
                last_read_at=datetime.now() - timedelta(days=30)  # Show all messages as new
            )
            db.session.add(super_admin_participant)
        
        unread_count = super_admin_participant.unread_count
        last_message = ChatMessage.query.filter_by(room_id=room.id)\
                                       .order_by(ChatMessage.created_at.desc()).first()
        
        room_data.append({
            'room': room,
            'unread_count': unread_count,
            'last_message': last_message
        })
    
    db.session.commit()
    
    return render_template('chat/superadmin_support_rooms.html', 
                         room_data=room_data)

@enhanced_chat_bp.route('/superadmin/support/<int:room_id>')
@require_login
def superadmin_support_chat(room_id):
    """Super admin access to specific support room"""
    if current_user.role != ROLE_SUPER_ADMIN:
        flash('Access denied. Super admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    room = ChatRoom.query.get_or_404(room_id)
    
    if room.room_type != 'support':
        flash('Invalid room type.', 'error')
        return redirect(url_for('enhanced_chat.superadmin_support_rooms'))
    
    # Ensure super admin is participant
    participant = ChatParticipant.query.filter_by(
        room_id=room_id,
        user_id=current_user.id
    ).first()
    
    if not participant:
        participant = ChatParticipant(
            room_id=room_id,
            user_id=current_user.id
        )
        db.session.add(participant)
        db.session.commit()
    
    # Get messages
    messages = ChatMessage.query.filter_by(room_id=room_id)\
                               .order_by(ChatMessage.created_at.asc()).all()
    
    # Mark as read
    participant.last_read_at = datetime.now()
    db.session.commit()
    
    return render_template('chat/superadmin_support_chat.html', 
                         room=room, 
                         messages=messages,
                         current_user=current_user)