from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_team_member_or_admin
from utils.forms import ClientNoteForm
from app import db
from models import User, ClientNote, Project

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/')
@require_team_member_or_admin
def list_clients():
    """List all clients with search functionality"""
    search = request.args.get('search', '')
    
    query = User.query.filter_by(role='client')
    
    if search:
        query = query.filter(
            db.or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search)
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
    
    # Get client's projects
    projects = Project.query.join(Project.assignments).filter_by(user_id=client_id).all()
    
    # Get client notes (only for team members and admins)
    notes = []
    if current_user.is_admin() or current_user.is_team_member():
        notes = ClientNote.query.filter_by(client_id=client_id).order_by(ClientNote.created_at.desc()).all()
    
    form = ClientNoteForm()
    
    return render_template('clients/profile.html', 
                         client=client, 
                         projects=projects, 
                         notes=notes, 
                         form=form)

@clients_bp.route('/<client_id>/notes', methods=['POST'])
@require_team_member_or_admin
def add_client_note(client_id):
    """Add a note for a client"""
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    form = ClientNoteForm()
    
    if form.validate_on_submit():
        note = ClientNote(
            client_id=client_id,
            note=form.note.data,
            created_by_id=current_user.id
        )
        db.session.add(note)
        db.session.commit()
        flash('Note added successfully!', 'success')
    else:
        flash('Error adding note. Please check your input.', 'error')
    
    return redirect(url_for('clients.client_profile', client_id=client_id))
