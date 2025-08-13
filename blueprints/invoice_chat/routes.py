import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid

from app import db
from models import Invoice, InvoiceChat, InvoiceChatMessage, InvoiceChatAttachment, User
from utils.decorators import simple_login_required

invoice_chat_bp = Blueprint('invoice_chat', __name__, url_prefix='/invoice-chat')

# File upload configuration
UPLOAD_FOLDER = 'uploads/invoice_chat'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'zip'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_upload_folder():
    """Ensure upload folder exists"""
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

@invoice_chat_bp.route('/<int:invoice_id>')
@simple_login_required
def chat_view(invoice_id):
    """View invoice chat"""
    # Get the invoice and verify access
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    # Check access permissions
    if current_user.is_client() and invoice.client_id != current_user.id:
        flash('You do not have permission to access this invoice.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    # Get or create chat
    chat = InvoiceChat.query.filter_by(invoice_id=invoice_id).first()
    if not chat:
        chat = InvoiceChat(
            invoice_id=invoice_id,
            law_firm_id=current_user.law_firm_id,
            client_id=invoice.client_id
        )
        db.session.add(chat)
        db.session.flush()  # Ensure chat.id is available
        
        # Create welcome system message
        welcome_msg = InvoiceChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            message=f"Invoice chat started for {invoice.invoice_number} - {invoice.title}",
            message_type='text',
            is_system=True
        )
        db.session.add(welcome_msg)
        db.session.commit()
    
    # Get chat messages
    messages = InvoiceChatMessage.query.filter_by(
        chat_id=chat.id
    ).order_by(InvoiceChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    for message in messages:
        if message.sender_id != current_user.id:
            message.mark_as_read(current_user)
    
    # Get participants
    participants = chat.get_participants()
    if current_user.is_client():
        participants = [p for p in participants if p.id != current_user.id]
    
    return render_template('invoice_chat/chat.html',
                         invoice=invoice,
                         chat=chat,
                         messages=messages,
                         participants=participants)

@invoice_chat_bp.route('/<int:invoice_id>/send', methods=['POST'])
@simple_login_required
def send_message(invoice_id):
    """Send a message in invoice chat"""
    # Get the invoice and verify access
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    # Check access permissions
    if current_user.is_client() and invoice.client_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get or create chat
    chat = InvoiceChat.query.filter_by(invoice_id=invoice_id).first()
    if not chat:
        chat = InvoiceChat(
            invoice_id=invoice_id,
            law_firm_id=current_user.law_firm_id,
            client_id=invoice.client_id
        )
        db.session.add(chat)
        db.session.flush()
    
    message_text = request.form.get('message', '').strip()
    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    try:
        # Create message
        message = InvoiceChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            message=message_text,
            message_type='text'
        )
        db.session.add(message)
        
        # Update chat last message time
        chat.last_message_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'sender_name': current_user.display_name,
                'message': message.message,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M'),
                'is_current_user': True
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to send message: {str(e)}'}), 500

@invoice_chat_bp.route('/<int:invoice_id>/upload', methods=['POST'])
@simple_login_required
def upload_file(invoice_id):
    """Upload file to invoice chat"""
    # Get the invoice and verify access
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    # Check access permissions
    if current_user.is_client() and invoice.client_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    try:
        ensure_upload_folder()
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save file
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            return jsonify({'error': 'File size exceeds 16MB limit'}), 400
        
        # Get or create chat
        chat = InvoiceChat.query.filter_by(invoice_id=invoice_id).first()
        if not chat:
            chat = InvoiceChat(
                invoice_id=invoice_id,
                law_firm_id=current_user.law_firm_id,
                client_id=invoice.client_id
            )
            db.session.add(chat)
            db.session.flush()
        
        # Create message with file attachment
        message = InvoiceChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            message=f"📎 Uploaded file: {original_filename}",
            message_type='file'
        )
        db.session.add(message)
        db.session.flush()
        
        # Create attachment record
        attachment = InvoiceChatAttachment(
            message_id=message.id,
            filename=unique_filename,
            original_filename=original_filename,
            file_size=file_size,
            content_type=file.content_type or 'application/octet-stream',
            file_path=file_path,
            uploaded_by_id=current_user.id
        )
        db.session.add(attachment)
        
        # Update chat last message time
        chat.last_message_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'sender_name': current_user.display_name,
                'message': message.message,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M'),
                'is_current_user': True,
                'attachment': {
                    'id': attachment.id,
                    'filename': attachment.original_filename,
                    'size': attachment.file_size_formatted
                }
            }
        })
        
    except Exception as e:
        db.session.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Failed to upload file: {str(e)}'}), 500

@invoice_chat_bp.route('/download/<int:attachment_id>')
@simple_login_required
def download_file(attachment_id):
    """Download chat attachment"""
    attachment = InvoiceChatAttachment.query.get_or_404(attachment_id)
    
    # Verify access through the chat
    chat = attachment.message.chat
    invoice = chat.invoice
    
    # Check access permissions
    if invoice.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    if current_user.is_client() and invoice.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    try:
        return send_file(
            attachment.file_path,
            as_attachment=True,
            download_name=attachment.original_filename,
            mimetype=attachment.content_type
        )
    except FileNotFoundError:
        flash('File not found.', 'error')
        return redirect(url_for('invoice_chat.chat_view', invoice_id=invoice.id))

@invoice_chat_bp.route('/<int:invoice_id>/messages', methods=['GET'])
@simple_login_required
def get_messages(invoice_id):
    """Get chat messages (for AJAX updates)"""
    # Get the invoice and verify access
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    # Check access permissions
    if current_user.is_client() and invoice.client_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    chat = InvoiceChat.query.filter_by(invoice_id=invoice_id).first()
    if not chat:
        return jsonify({'messages': []})
    
    # Get messages after a certain timestamp if provided
    since = request.args.get('since')
    query = InvoiceChatMessage.query.filter_by(chat_id=chat.id)
    
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.filter(InvoiceChatMessage.created_at > since_dt)
        except ValueError:
            pass
    
    messages = query.order_by(InvoiceChatMessage.created_at.asc()).all()
    
    # Mark new messages as read
    for message in messages:
        if message.sender_id != current_user.id:
            message.mark_as_read(current_user)
    
    message_data = []
    for message in messages:
        msg_data = {
            'id': message.id,
            'sender_name': message.sender.display_name,
            'message': message.message,
            'created_at': message.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_current_user': message.sender_id == current_user.id,
            'is_system': message.is_system,
            'message_type': message.message_type
        }
        
        if message.attachments:
            msg_data['attachments'] = [{
                'id': att.id,
                'filename': att.original_filename,
                'size': att.file_size_formatted
            } for att in message.attachments]
        
        message_data.append(msg_data)
    
    return jsonify({'messages': message_data})