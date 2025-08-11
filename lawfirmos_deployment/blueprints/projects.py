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
    """List projects based on user role"""
    if current_user.is_admin():
        # Admins see all projects
        projects = Project.query.order_by(Project.created_at.desc()).all()
    elif current_user.is_team_member():
        # Team members see assigned projects
        projects = Project.query.join(Project.assignments).filter_by(user_id=current_user.id).all()
    else:
        # Clients see their assigned projects
        projects = Project.query.join(Project.assignments).filter_by(user_id=current_user.id).all()
    
    return render_template('projects/list.html', projects=projects)

@projects_bp.route('/create', methods=['GET', 'POST'])
@require_team_member_or_admin
def create_project():
    """Create a new project"""
    form = ProjectForm()
    
    if form.validate_on_submit():
        project = Project(
            title=form.title.data,
            description=form.description.data,
            status=form.status.data,
            priority=form.priority.data,
            deadline=form.deadline.data,
            created_by_id=current_user.id
        )
        
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
    
    # Get all users for assignment (admin/team member only)
    all_users = []
    if current_user.is_admin() or current_user.is_team_member():
        all_users = User.query.filter_by(active=True).order_by(User.role, User.first_name, User.last_name).all()
    
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
        assignment = ProjectAssignment(
            project_id=project_id,
            user_id=user_id,
            assigned_by_id=current_user.id
        )
        db.session.add(assignment)
        
        # Implement seamless tagging for lawyer-client connections
        try:
            db.session.flush()
            
            # Get current project assignments to check for automatic connections
            project_assignments = ProjectAssignment.query.filter_by(project_id=project_id).all()
            clients = [a.user for a in project_assignments if a.user.role == 'client']
            lawyers = [a.user for a in project_assignments if a.user.role in ['admin', 'team_member']]
            
            # Create automatic chat connections between clients and lawyers
            if user.role == 'client':
                # New client assigned, connect to all existing lawyers
                for lawyer in lawyers:
                    if lawyer.id != user.id:
                        # Check if conversation already exists
                        from models import ChatConversation
                        from sqlalchemy import or_, and_
                        existing_conversation = ChatConversation.query.filter(
                            or_(
                                and_(ChatConversation.user1_id == user.id, ChatConversation.user2_id == lawyer.id),
                                and_(ChatConversation.user1_id == lawyer.id, ChatConversation.user2_id == user.id)
                            )
                        ).first()
                        
                        if not existing_conversation:
                            conversation = ChatConversation(
                                user1_id=min(user.id, lawyer.id),
                                user2_id=max(user.id, lawyer.id)
                            )
                            db.session.add(conversation)
            elif user.role in ['admin', 'team_member']:
                # New lawyer assigned, connect to all existing clients
                for client in clients:
                    if client.id != user.id:
                        # Check if conversation already exists
                        from models import ChatConversation
                        from sqlalchemy import or_, and_
                        existing_conversation = ChatConversation.query.filter(
                            or_(
                                and_(ChatConversation.user1_id == user.id, ChatConversation.user2_id == client.id),
                                and_(ChatConversation.user1_id == client.id, ChatConversation.user2_id == user.id)
                            )
                        ).first()
                        
                        if not existing_conversation:
                            conversation = ChatConversation(
                                user1_id=min(user.id, client.id),
                                user2_id=max(user.id, client.id)
                            )
                            db.session.add(conversation)
            
            db.session.commit()
            
            # Success message with seamless tagging info
            connection_count = len(clients) if user.role in ['admin', 'team_member'] else len(lawyers)
            if connection_count > 0:
                flash(f'{user.full_name} has been assigned to the project with automatic chat connections established!', 'success')
            else:
                flash(f'{user.full_name} has been assigned to the project.', 'success')
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
        original_filename = secure_filename(file.filename)
        file_extension = os.path.splitext(original_filename)[1]
        unique_filename = str(uuid.uuid4()) + file_extension
        
        # Save file
        file_path = os.path.join('uploads', unique_filename)
        file.save(file_path)
        
        # Create database record
        project_file = ProjectFile(
            project_id=project_id,
            filename=unique_filename,
            original_filename=original_filename,
            file_size=os.path.getsize(file_path),
            file_type=file_extension,
            uploaded_by_id=current_user.id
        )
        
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
    message = ProjectMessage(
        project_id=project_id,
        user_id=current_user.id,
        message=message_text
    )
    
    db.session.add(message)
    db.session.commit()
    
    flash('Message sent successfully!', 'success')
    return redirect(url_for('projects.project_chat', project_id=project_id))
