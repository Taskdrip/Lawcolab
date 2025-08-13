from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from replit_auth import require_login
from utils.decorators import require_team_member_or_admin
from utils.forms import ProjectForm
from app import db
from models import Project, ProjectAssignment, User, ProjectFile, ProjectMessage
import os
from werkzeug.utils import secure_filename
import uuid

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/')
@require_login
def list_projects():
    """List projects based on user role - only from same law firm"""
    if current_user.is_admin():
        # Admins see all projects from their law firm
        projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(Project.created_at.desc()).all()
    elif current_user.is_team_member():
        # Team members see assigned projects from their law firm
        projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).join(ProjectAssignment).filter_by(user_id=current_user.id).all()
    else:
        # Clients see their assigned projects from their law firm
        projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).join(ProjectAssignment).filter_by(user_id=current_user.id).all()
    
    return render_template('projects/list.html', projects=projects)

@projects_bp.route('/create', methods=['GET', 'POST'])
@require_team_member_or_admin
def create_project():
    """Create a new project"""
    form = ProjectForm()
    
    if form.validate_on_submit():
        project = Project()
        project.title = form.title.data
        project.description = form.description.data
        project.status = form.status.data
        project.priority = form.priority.data
        project.deadline = form.deadline.data
        project.created_by_id = current_user.id
        project.law_firm_id = current_user.law_firm_id
        
        db.session.add(project)
        db.session.commit()
        
        flash('Project created successfully!', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))
    
    return render_template('projects/create.html', form=form)

@projects_bp.route('/<int:project_id>')
@require_login
def project_detail(project_id):
    """View project details"""
    project = Project.query.get_or_404(project_id)
    
    # Check if user has access to this project
    if current_user.is_client():
        # Clients can only see projects they're assigned to
        assignment = ProjectAssignment.query.filter_by(
            project_id=project_id, 
            user_id=current_user.id
        ).first()
        if not assignment:
            flash('You do not have access to this project.', 'error')
            return redirect(url_for('projects.list_projects'))
    elif current_user.is_team_member():
        # Team members can see projects they're assigned to or created
        if project.created_by_id != current_user.id:
            assignment = ProjectAssignment.query.filter_by(
                project_id=project_id, 
                user_id=current_user.id
            ).first()
            if not assignment:
                flash('You do not have access to this project.', 'error')
                return redirect(url_for('projects.list_projects'))
    
    # Get users from same law firm for assignment (admin/team member only)
    all_users = []
    if current_user.is_admin() or current_user.is_team_member():
        # Only show users from the same law firm, excluding already assigned users
        assigned_user_ids = [assignment.user_id for assignment in project.assignments]
        all_users = User.query.filter(
            User.law_firm_id == current_user.law_firm_id,
            User.active == True,
            ~User.id.in_(assigned_user_ids) if assigned_user_ids else True
        ).order_by(User.role, User.first_name, User.last_name).all()
    
    from datetime import date
    return render_template('projects/detail.html', 
                         project=project, 
                         all_users=all_users,
                         today=date.today())

@projects_bp.route('/<int:project_id>/assign', methods=['POST'])
@require_team_member_or_admin
def assign_user(project_id):
    """Assign a user to a project"""
    project = Project.query.get_or_404(project_id)
    user_id = request.form.get('user_id')
    
    if not user_id:
        flash('Please select a user to assign.', 'error')
        return redirect(url_for('projects.project_detail', project_id=project_id))
    
    user = User.query.get_or_404(user_id)
    
    # Check if assignment already exists
    existing = ProjectAssignment.query.filter_by(
        project_id=project_id, 
        user_id=user_id
    ).first()
    
    if existing:
        flash(f'{user.full_name} is already assigned to this project.', 'warning')
    else:
        assignment = ProjectAssignment()
        assignment.project_id = project_id
        assignment.user_id = user_id
        assignment.assigned_by_id = current_user.id
        db.session.add(assignment)
        
        # Create or update project chat room with all participants
        try:
            db.session.flush()
            
            # Import chat models
            from models_chat import ChatRoom, ChatParticipant, ChatMessage
            
            # Get or create project chat room
            project_room = ChatRoom.query.filter_by(
                project_id=project_id,
                room_type='project',
                is_active=True
            ).first()
            
            if not project_room:
                # Create new project chat room
                project_room = ChatRoom(
                    name=f"Project: {project.title}",
                    room_type='project',
                    law_firm_id=project.law_firm_id,
                    project_id=project_id,
                    created_by_id=current_user.id
                )
                db.session.add(project_room)
                db.session.flush()
                
                # Send welcome message to the chat room
                welcome_message = ChatMessage(
                    room_id=project_room.id,
                    sender_id=current_user.id,
                    message_content=f"Welcome to the project chat for '{project.title}'! All team members and clients assigned to this project can collaborate here.",
                    message_type='notification'
                )
                db.session.add(welcome_message)
            
            # Add the newly assigned user as a participant if not already added
            existing_participant = ChatParticipant.query.filter_by(
                room_id=project_room.id,
                user_id=user_id
            ).first()
            
            if not existing_participant:
                new_participant = ChatParticipant(
                    room_id=project_room.id,
                    user_id=user_id
                )
                db.session.add(new_participant)
                
                # Send notification about new member
                notification_message = ChatMessage(
                    room_id=project_room.id,
                    sender_id=current_user.id,
                    message_content=f"{user.full_name} has been added to the project team.",
                    message_type='notification'
                )
                db.session.add(notification_message)
            
            # Ensure all project participants are in the chat room
            project_assignments = ProjectAssignment.query.filter_by(project_id=project_id).all()
            for assignment in project_assignments:
                participant_exists = ChatParticipant.query.filter_by(
                    room_id=project_room.id,
                    user_id=assignment.user_id
                ).first()
                
                if not participant_exists:
                    participant = ChatParticipant(
                        room_id=project_room.id,
                        user_id=assignment.user_id
                    )
                    db.session.add(participant)
            
            db.session.commit()
            
            # Success message with chat room info
            participant_count = len(project_assignments)
            flash(f'{user.full_name} has been assigned to the project! A project chat room with {participant_count} participants is now available.', 'success')
        except Exception as e:
            db.session.rollback()
            db.session.add(assignment)
            db.session.commit()
            flash(f'{user.full_name} has been assigned to the project.', 'success')
            print(f"Seamless tagging error: {e}")
    
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/<int:project_id>/unassign/<user_id>', methods=['POST'])
@require_team_member_or_admin
def unassign_user(project_id, user_id):
    """Remove a user from a project"""
    assignment = ProjectAssignment.query.filter_by(
        project_id=project_id, 
        user_id=user_id
    ).first_or_404()
    
    user_name = assignment.user.full_name
    db.session.delete(assignment)
    db.session.commit()
    
    flash(f'{user_name} has been removed from the project.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/<int:project_id>/upload', methods=['POST'])
@require_login
def upload_file(project_id):
    """Upload a file to a project"""
    project = Project.query.get_or_404(project_id)
    
    # Check if user has access to this project
    if current_user.is_client():
        assignment = ProjectAssignment.query.filter_by(
            project_id=project_id, 
            user_id=current_user.id
        ).first()
        if not assignment:
            flash('You do not have access to this project.', 'error')
            return redirect(url_for('projects.list_projects'))
    
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('projects.project_detail', project_id=project_id))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('projects.project_detail', project_id=project_id))
    
    if file:
        # Generate unique filename
        if file.filename:
            original_filename = secure_filename(file.filename)
            file_extension = os.path.splitext(original_filename)[1]
        else:
            flash('Invalid filename.', 'error')
            return redirect(url_for('projects.project_detail', project_id=project_id))
        unique_filename = str(uuid.uuid4()) + file_extension
        
        # Save file
        file_path = os.path.join('uploads', unique_filename)
        file.save(file_path)
        
        # Create database record
        project_file = ProjectFile()
        project_file.project_id = project_id
        project_file.filename = unique_filename
        project_file.original_filename = original_filename
        project_file.file_size = os.path.getsize(file_path)
        project_file.file_type = file_extension
        project_file.uploaded_by_id = current_user.id
        
        db.session.add(project_file)
        db.session.commit()
        
        flash('File uploaded successfully!', 'success')
    
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/<int:project_id>/chat')
@require_login
def project_chat(project_id):
    """Project chat page for collaboration"""
    project = Project.query.get_or_404(project_id)
    
    # Check if user has access to this project
    if current_user.is_client():
        assignment = ProjectAssignment.query.filter_by(
            project_id=project_id, 
            user_id=current_user.id
        ).first()
        if not assignment:
            flash('You do not have access to this project.', 'error')
            return redirect(url_for('projects.list_projects'))
    elif current_user.is_team_member():
        if project.created_by_id != current_user.id:
            assignment = ProjectAssignment.query.filter_by(
                project_id=project_id, 
                user_id=current_user.id
            ).first()
            if not assignment:
                flash('You do not have access to this project.', 'error')
                return redirect(url_for('projects.list_projects'))
    
    # Get chat messages
    messages = ProjectMessage.query.filter_by(project_id=project_id).order_by(ProjectMessage.created_at.asc()).all()
    
    return render_template('projects/chat.html', 
                         project=project, 
                         messages=messages)

@projects_bp.route('/<int:project_id>/chat/send', methods=['POST'])
@require_login
def send_message(project_id):
    """Send a message to project chat"""
    project = Project.query.get_or_404(project_id)
    message_text = request.form.get('message', '').strip()
    
    if not message_text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('projects.project_chat', project_id=project_id))
    
    # Check access
    if current_user.is_client():
        assignment = ProjectAssignment.query.filter_by(
            project_id=project_id, 
            user_id=current_user.id
        ).first()
        if not assignment:
            flash('You do not have access to this project.', 'error')
            return redirect(url_for('projects.list_projects'))
    elif current_user.is_team_member():
        if project.created_by_id != current_user.id:
            assignment = ProjectAssignment.query.filter_by(
                project_id=project_id, 
                user_id=current_user.id
            ).first()
            if not assignment:
                flash('You do not have access to this project.', 'error')
                return redirect(url_for('projects.list_projects'))
    
    # Create message
    message = ProjectMessage()
    message.project_id = project_id
    message.user_id = current_user.id
    message.message = message_text
    
    db.session.add(message)
    db.session.commit()
    
    flash('Message sent successfully!', 'success')
    return redirect(url_for('projects.project_chat', project_id=project_id))
