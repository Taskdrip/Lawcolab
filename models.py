from datetime import datetime
from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

# User roles
ROLE_ADMIN = 'admin'
ROLE_TEAM_MEMBER = 'team_member'
ROLE_CLIENT = 'client'

# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=True)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    role = db.Column(db.String, default=ROLE_CLIENT, nullable=False)
    phone = db.Column(db.String, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True)
    password_hash = db.Column(db.String(256), nullable=True)  # For email/password login
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    assigned_projects = db.relationship('ProjectAssignment', back_populates='user', foreign_keys='ProjectAssignment.user_id', cascade='all, delete-orphan')
    client_notes = db.relationship('ClientNote', back_populates='client', foreign_keys='ClientNote.client_id')
    created_notes = db.relationship('ClientNote', back_populates='created_by_user', foreign_keys='ClientNote.created_by_id')
    
    # Chat relationships
    sent_messages = db.relationship('ChatMessage', back_populates='sender', foreign_keys='ChatMessage.sender_id')
    received_messages = db.relationship('ChatMessage', back_populates='receiver', foreign_keys='ChatMessage.receiver_id')

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email or "Unknown User"

    def has_role(self, role):
        return self.role == role

    def is_admin(self):
        return self.role == ROLE_ADMIN

    def is_team_member(self):
        return self.role == ROLE_TEAM_MEMBER

    def is_client(self):
        return self.role == ROLE_CLIENT
    
    def is_active(self):
        return self.active

    def set_password(self, password):
        """Hash and store password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.String, db.ForeignKey('users.id'))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)

class LawFirm(db.Model):
    __tablename__ = 'law_firms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    logo_url = db.Column(db.String(500))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    website = db.Column(db.String(200))
    practice_areas = db.Column(db.Text)  # JSON string of practice areas
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default='active')  # active, completed, on_hold
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    deadline = db.Column(db.Date)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    assignments = db.relationship('ProjectAssignment', back_populates='project', cascade='all, delete-orphan')
    files = db.relationship('ProjectFile', back_populates='project', cascade='all, delete-orphan')

    @property
    def assigned_users(self):
        return [assignment.user for assignment in self.assignments]

    @property
    def assigned_clients(self):
        return [assignment.user for assignment in self.assignments if assignment.user.is_client()]

    @property
    def assigned_team_members(self):
        return [assignment.user for assignment in self.assignments if assignment.user.is_team_member()]

class ProjectAssignment(db.Model):
    __tablename__ = 'project_assignments'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.now)
    assigned_by_id = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    project = db.relationship('Project', back_populates='assignments')
    user = db.relationship('User', back_populates='assigned_projects', foreign_keys=[user_id])
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])

    __table_args__ = (UniqueConstraint('project_id', 'user_id'),)

class ProjectFile(db.Model):
    __tablename__ = 'project_files'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(50))
    uploaded_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    project = db.relationship('Project', back_populates='files')
    uploaded_by = db.relationship('User')

class ClientNote(db.Model):
    __tablename__ = 'client_notes'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    client = db.relationship('User', back_populates='client_notes', foreign_keys=[client_id])
    created_by_user = db.relationship('User', back_populates='created_notes', foreign_keys=[created_by_id])



class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)
    
    # Relationships
    sender = db.relationship('User', back_populates='sent_messages', foreign_keys=[sender_id])
    receiver = db.relationship('User', back_populates='received_messages', foreign_keys=[receiver_id])
    
    def __repr__(self):
        return f'<ChatMessage from {self.sender_id} to {self.receiver_id}>'

class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    last_message_at = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])
    
    __table_args__ = (UniqueConstraint('user1_id', 'user2_id', name='unique_conversation'),)
    
    def get_other_user(self, current_user_id):
        """Get the other user in the conversation"""
        return self.user2 if self.user1_id == current_user_id else self.user1
    
    def __repr__(self):
        return f'<ChatConversation between {self.user1_id} and {self.user2_id}>'
