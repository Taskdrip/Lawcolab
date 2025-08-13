from datetime import datetime, timedelta
from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

# User roles
ROLE_SUPER_ADMIN = 'super_admin'  # Platform-wide admin
ROLE_ADMIN = 'admin'              # Law firm admin
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
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=True)  # Multi-tenancy
    
    # Company-specific fields for client organizations
    company_name = db.Column(db.String(200), nullable=True)
    company_description = db.Column(db.Text, nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    website_url = db.Column(db.String(255), nullable=True)
    company_size = db.Column(db.String(50), nullable=True)  # Small, Medium, Large, Enterprise
    headquarters = db.Column(db.String(200), nullable=True)
    founded_year = db.Column(db.Integer, nullable=True)
    
    # Professional fields for lawyers/team members
    specialization = db.Column(db.String(200), nullable=True)
    years_experience = db.Column(db.Integer, nullable=True)
    education = db.Column(db.Text, nullable=True)
    certifications = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    law_firm = db.relationship('LawFirm', back_populates='users')
    assigned_projects = db.relationship('ProjectAssignment', back_populates='user', foreign_keys='ProjectAssignment.user_id', cascade='all, delete-orphan')
    client_notes = db.relationship('ClientNote', back_populates='client', foreign_keys='ClientNote.client_id')
    created_notes = db.relationship('ClientNote', back_populates='created_by_user', foreign_keys='ClientNote.created_by_id')
    
    # Chat relationships
    sent_messages = db.relationship('DirectMessage', back_populates='sender', foreign_keys='DirectMessage.sender_id')
    received_messages = db.relationship('DirectMessage', back_populates='receiver', foreign_keys='DirectMessage.receiver_id')

    @property
    def full_name(self):
        # For clients with company names, prefer company name
        if self.is_client() and self.company_name:
            return self.company_name
        elif self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email or "Unknown User"
    
    @property
    def display_name(self):
        """Display name for UI - shows company or personal name"""
        if self.is_client() and self.company_name:
            return self.company_name
        return self.full_name

    def has_role(self, role):
        return self.role == role

    def is_super_admin(self):
        return self.role == ROLE_SUPER_ADMIN
        
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def is_team_member(self):
        return self.role == ROLE_TEAM_MEMBER

    def is_client(self):
        return self.role == ROLE_CLIENT
    
    def can_manage_law_firms(self):
        """Super admins can manage all law firms"""
        return self.is_super_admin()
    
    # Note: is_active property inherited from UserMixin, using self.active field

    def set_password(self, password):
        """Hash and store password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def create_law_firm_if_admin(self):
        """Create a law firm if this user is an admin and doesn't have one"""
        if self.is_admin() and not self.law_firm_id:
            # Create a new law firm for this admin
            firm_name = f"{self.full_name}'s Law Firm"
            new_firm = LawFirm(
                name=firm_name,
                description=f"Legal practice managed by {self.full_name}",
                email=self.email
            )
            db.session.add(new_firm)
            db.session.flush()  # Get the ID
            
            # Associate the admin with this firm
            self.law_firm_id = new_firm.id
            db.session.commit()
            return new_firm
        return self.law_firm
    
    def get_firm_users(self, role=None):
        """Get all users from the same law firm, optionally filtered by role"""
        if not self.law_firm_id:
            return []
        
        query = User.query.filter_by(law_firm_id=self.law_firm_id)
        if role:
            query = query.filter_by(role=role)
        return query.all()
    
    def get_firm_clients(self):
        """Get all clients from the same law firm"""
        return self.get_firm_users(ROLE_CLIENT)
    
    def get_firm_team_members(self):
        """Get all team members from the same law firm"""
        return self.get_firm_users(ROLE_TEAM_MEMBER)
    
    def get_firm_projects(self):
        """Get all projects from the same law firm"""
        if not self.law_firm_id:
            return []
        return Project.query.filter_by(law_firm_id=self.law_firm_id).all()
    
    def is_assigned_to_project(self, project_id):
        """Check if user is assigned to a specific project"""
        if self.is_admin():
            # Admins have access to all projects in their law firm
            project = Project.query.get(project_id)
            return project and project.law_firm_id == self.law_firm_id
        else:
            # Team members and clients need explicit assignment
            assignment = ProjectAssignment.query.filter_by(
                project_id=project_id,
                user_id=self.id
            ).first()
            return assignment is not None

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
    
    # Banking details for receiving payments
    bank_name = db.Column(db.String(100), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    routing_number = db.Column(db.String(20), nullable=True)
    swift_code = db.Column(db.String(20), nullable=True)
    account_holder_name = db.Column(db.String(100), nullable=True)
    tax_id = db.Column(db.String(50), nullable=True)
    
    # Admin access and subscription management
    admin_access_granted = db.Column(db.Boolean, default=False, nullable=False)
    admin_access_expires = db.Column(db.DateTime)
    subscription_period = db.Column(db.String(20))  # 3days, 1month, 3months, 6months, 1year
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    @property
    def is_subscription_expired(self):
        """Check if the law firm's subscription has expired"""
        if not self.admin_access_expires:
            return False
        from datetime import datetime
        return datetime.now() > self.admin_access_expires
    
    @property
    def days_until_expiry(self):
        """Get days until subscription expires"""
        if not self.admin_access_expires:
            return None
        from datetime import datetime
        delta = self.admin_access_expires - datetime.now()
        return max(0, delta.days)
    
    @property
    def subscription_status(self):
        """Get current subscription status"""
        if not self.admin_access_granted:
            return "Pending Payment Verification"
        elif self.is_subscription_expired:
            return "Expired"
        elif self.days_until_expiry is not None and self.days_until_expiry <= 7:
            return f"Expires in {self.days_until_expiry} days"
        else:
            return "Active"
    
    # Multi-tenancy relationships
    users = db.relationship('User', back_populates='law_firm')
    projects = db.relationship('Project', back_populates='law_firm')
    
    def get_support_chat_room(self):
        """Get or create support chat room with super admin"""
        from models_chat import ChatRoom, ChatParticipant
        
        # Look for existing support room
        support_room = ChatRoom.query.filter_by(
            law_firm_id=self.id,
            room_type='support',
            is_active=True
        ).first()
        
        if not support_room:
            # Create new support chat room
            admin_user = next((u for u in self.users if u.role == 'admin'), None)
            if admin_user:
                support_room = ChatRoom(
                    name=f"Support - {self.name}",
                    room_type='support',
                    law_firm_id=self.id,
                    created_by_id=admin_user.id
                )
                db.session.add(support_room)
                db.session.flush()
                
                # Add admin as participant
                participant = ChatParticipant(
                    room_id=support_room.id,
                    user_id=admin_user.id
                )
                db.session.add(participant)
                db.session.commit()
        
        return support_room

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default='active')  # active, completed, on_hold
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    deadline = db.Column(db.Date)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)  # Multi-tenancy
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    law_firm = db.relationship('LawFirm', back_populates='projects')
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



class SupportRequest(db.Model):
    __tablename__ = 'support_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    request_type = db.Column(db.String(50), nullable=False)  # trial, 1month, 3months, etc.
    message = db.Column(db.Text, nullable=False)
    team_size = db.Column(db.String(20))  # Optional: 1-5, 6-15, etc.
    status = db.Column(db.String(20), default='pending')  # pending, processing, resolved
    created_at = db.Column(db.DateTime, default=datetime.now)
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.String, db.ForeignKey('users.id'))  # Super admin who resolved
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    law_firm = db.relationship('LawFirm', foreign_keys=[law_firm_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])

class DirectMessage(db.Model):
    __tablename__ = 'direct_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)
    
    @property
    def created_at(self):
        """Alias for timestamp to maintain template compatibility"""
        return self.timestamp
    
    # Relationships
    sender = db.relationship('User', back_populates='sent_messages', foreign_keys=[sender_id])
    receiver = db.relationship('User', back_populates='received_messages', foreign_keys=[receiver_id])
    
    def __repr__(self):
        return f'<DirectMessage from {self.sender_id} to {self.receiver_id}>'

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

class ProjectMessage(db.Model):
    __tablename__ = 'project_messages'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    project = db.relationship('Project', backref='project_messages')
    user = db.relationship('User', backref='sent_project_messages')


# Invoice System Models
class Invoice(db.Model):
    __tablename__ = 'invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    client_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    # Invoice details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    
    # Invoice type and billing information
    invoice_type = db.Column(db.String(20), default='service')  # service, retainer, renewal, expense
    billing_period = db.Column(db.String(20), nullable=True)  # monthly, quarterly, yearly, one-time
    
    # Status and dates
    status = db.Column(db.String(20), default='draft')  # draft, sent, paid, overdue, cancelled
    issue_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    paid_date = db.Column(db.Date, nullable=True)
    
    # Notification settings
    reminder_sent = db.Column(db.Boolean, default=False)
    overdue_notifications_sent = db.Column(db.Integer, default=0)
    
    # Payment information
    payment_method = db.Column(db.String(50), nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    law_firm = db.relationship('LawFirm', backref='invoices')
    client = db.relationship('User', foreign_keys=[client_id], backref='client_invoices')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_invoices')
    project = db.relationship('Project', backref='invoices')
    line_items = db.relationship('InvoiceLineItem', back_populates='invoice', cascade='all, delete-orphan')
    notifications = db.relationship('InvoiceNotification', back_populates='invoice', cascade='all, delete-orphan')
    
    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        from datetime import date
        return self.status in ['sent'] and self.due_date < date.today()
    
    @property
    def days_until_due(self):
        """Calculate days until due date"""
        from datetime import date
        if self.status == 'paid':
            return None
        delta = self.due_date - date.today()
        return delta.days
    
    @property
    def total_amount(self):
        """Calculate total amount including line items"""
        if self.line_items:
            return sum(item.total_amount for item in self.line_items)
        return float(self.amount)
    
    def generate_invoice_number(self):
        """Generate unique invoice number"""
        from datetime import date
        today = date.today()
        prefix = f"INV-{today.year}-{today.month:02d}"
        
        # Find the next sequential number for this month
        existing = db.session.query(Invoice).filter(
            Invoice.law_firm_id == self.law_firm_id,
            Invoice.invoice_number.like(f"{prefix}-%")
        ).count()
        
        self.invoice_number = f"{prefix}-{existing + 1:04d}"


class InvoiceLineItem(db.Model):
    __tablename__ = 'invoice_line_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)
    rate = db.Column(db.Numeric(10, 2), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Time tracking for legal services
    hours_worked = db.Column(db.Numeric(5, 2), nullable=True)
    work_date = db.Column(db.Date, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    invoice = db.relationship('Invoice', back_populates='line_items')
    
    @property
    def total_amount(self):
        """Calculate total amount for this line item"""
        return float(self.quantity) * float(self.rate)


class InvoiceNotification(db.Model):
    __tablename__ = 'invoice_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    
    notification_type = db.Column(db.String(30), nullable=False)  # reminder, overdue, renewal, payment_received
    recipient_type = db.Column(db.String(20), nullable=False)  # client, law_firm, both
    message = db.Column(db.Text, nullable=False)
    
    scheduled_date = db.Column(db.DateTime, nullable=False)
    sent_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    
    # Auto-generated or manual
    is_automatic = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    invoice = db.relationship('Invoice', back_populates='notifications')
    
    @property
    def is_due(self):
        """Check if notification should be sent"""
        return self.status == 'pending' and self.scheduled_date <= datetime.now()


class PaymentRecord(db.Model):
    __tablename__ = 'payment_records'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # cash, check, bank_transfer, credit_card, etc.
    reference_number = db.Column(db.String(100), nullable=True)
    
    notes = db.Column(db.Text, nullable=True)
    recorded_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    invoice = db.relationship('Invoice', backref='payments')
    law_firm = db.relationship('LawFirm', backref='payment_records')
    recorded_by = db.relationship('User', backref='recorded_payments')


# Invoice Chat System Models
class InvoiceChat(db.Model):
    __tablename__ = 'invoice_chats'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    client_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    # Chat metadata
    is_active = db.Column(db.Boolean, default=True)
    last_message_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    invoice = db.relationship('Invoice', backref='chat')
    law_firm = db.relationship('LawFirm', backref='invoice_chats')
    client = db.relationship('User', backref='invoice_chats')
    messages = db.relationship('InvoiceChatMessage', back_populates='chat', cascade='all, delete-orphan')
    
    def get_participants(self):
        """Get all law firm team members who can participate in this chat"""
        return User.query.filter_by(
            law_firm_id=self.law_firm_id,
            active=True
        ).filter(
            User.role.in_(['admin', 'team_member'])
        ).all()


class InvoiceChatMessage(db.Model):
    __tablename__ = 'invoice_chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('invoice_chats.id'), nullable=False)
    sender_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, file, invoice, payment_update
    
    # Message metadata
    is_system = db.Column(db.Boolean, default=False)  # System-generated messages
    read_by_client = db.Column(db.Boolean, default=False)
    read_by_law_firm = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    chat = db.relationship('InvoiceChat', back_populates='messages')
    sender = db.relationship('User', backref='invoice_chat_messages')
    attachments = db.relationship('InvoiceChatAttachment', back_populates='message', cascade='all, delete-orphan')
    
    def mark_as_read(self, user):
        """Mark message as read by user"""
        if user.is_client():
            self.read_by_client = True
        else:
            self.read_by_law_firm = True
        db.session.commit()


class InvoiceChatAttachment(db.Model):
    __tablename__ = 'invoice_chat_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('invoice_chat_messages.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    content_type = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    
    uploaded_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    message = db.relationship('InvoiceChatMessage', back_populates='attachments')
    uploaded_by = db.relationship('User', backref='uploaded_attachments')
    
    @property
    def file_size_formatted(self):
        """Return human-readable file size"""
        bytes_size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
