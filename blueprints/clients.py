from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_team_member_or_admin
from utils.trial_access import require_active_subscription
from utils.forms import ClientNoteForm
from app import db
from models import User, ClientNote, Project, ProjectAssignment
from utils.profile_upload import save_profile_image

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/')
@require_login
@require_active_subscription
def list_clients():
    """List clients from the same law firm with search functionality"""
    
    # Check if user has required permissions first
    if not (current_user.is_admin() or current_user.is_team_member() or current_user.is_super_admin()):
        flash(f'Access denied. You need admin or team member role to view clients. Your current role: {current_user.role}', 'error')
        return redirect(url_for('index'))
    
    search = request.args.get('search', '')
    
    # Only show clients from the current user's law firm (ensure current user has law_firm_id)
    if not current_user.law_firm_id:
        # If admin doesn't have law firm, create one
        if current_user.is_admin():
            current_user.create_law_firm_if_admin()
        else:
            flash('You are not associated with a law firm.', 'error')
            return redirect(url_for('index'))
    
    query = User.query.filter(
        User.role == 'client',
        User.law_firm_id == current_user.law_firm_id,
        User.law_firm_id.is_not(None)  # Ensure law_firm_id is not null
    )
    
    if search:
        query = query.filter(
            db.or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search),
                User.company_name.contains(search)
            )
        )
    
    clients = query.all()
    return render_template('clients/list.html', clients=clients, search=search)

@clients_bp.route('/<client_id>')
@require_login
def client_profile(client_id):
    """View client profile and notes"""
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    
    # Check permissions - clients can only view their own profile
    if current_user.is_client() and current_user.id != client_id:
        flash('You can only view your own profile.', 'error')
        return redirect(url_for('dashboard.client_dashboard'))
    
    # Get client's projects (from same law firm)
    projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).join(ProjectAssignment).filter_by(user_id=client_id).all()
    
    # Get client notes (only for team members and admins)
    notes = []
    if current_user.is_admin() or current_user.is_team_member():
        notes = ClientNote.query.filter_by(client_id=client_id).order_by(ClientNote.created_at.desc()).all()
    
    form = ClientNoteForm()
    
    # Always use the public profile template for now to avoid errors
    return render_template('clients/public_profile.html', 
                         client=client, 
                         projects=projects)

@clients_bp.route('/<client_id>/notes', methods=['POST'])
@require_team_member_or_admin
def add_client_note(client_id):
    """Add a note for a client"""
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    form = ClientNoteForm()
    
    if form.validate_on_submit():
        note = ClientNote()
        note.client_id = client_id
        note.note = form.note.data
        note.created_by_id = current_user.id
        db.session.add(note)
        db.session.commit()
        flash('Note added successfully!', 'success')
    else:
        flash('Error adding note. Please check your input.', 'error')
    
    return redirect(url_for('clients.client_profile', client_id=client_id))

@clients_bp.route('/<client_id>/upload_profile_image', methods=['POST'])
@require_login
def upload_profile_image(client_id):
    """Upload profile image for client"""
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    
    # Check permissions - only admin or the client themselves can upload
    if not (current_user.is_admin() or current_user.id == client_id):
        flash('You do not have permission to update this profile.', 'error')
        return redirect(url_for('clients.client_profile', client_id=client_id))
    
    if 'profile_image' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('clients.client_profile', client_id=client_id))
    
    file = request.files['profile_image']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('clients.client_profile', client_id=client_id))
    
    filename = save_profile_image(file, client_id)
    if filename:
        client.profile_image_url = filename
        db.session.commit()
        flash('Profile image updated successfully!', 'success')
    else:
        flash('Invalid file type. Please upload a PNG, JPG, or GIF image.', 'error')
    
    return redirect(url_for('clients.client_profile', client_id=client_id))
