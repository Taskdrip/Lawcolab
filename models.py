from datetime import datetime, timedelta
from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

# Import payment models to ensure tables are created - use primary payment system only
from models_payment import PaymentGateway, EscrowTransaction, EscrowMilestone, EscrowTransactionLog, CryptoWallet, BankAccount

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
    
    # Enhanced address fields for professional invoices
    address_line_1 = db.Column(db.String(200))
    address_line_2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state_province = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(100))
    
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
    
    # Payment relationships will be added after models are properly configured

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
            new_firm = LawFirm()
            new_firm.name = firm_name
            new_firm.description = f"Legal practice managed by {self.full_name}"
            new_firm.email = self.email
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
    showcase = db.relationship('LawFirmShowcase', back_populates='law_firm', uselist=False)
    # escrow_transactions relationship will be added after models are properly configured
    
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
            admin_users = [u for u in self.users if u.role == 'admin']
            admin_user = admin_users[0] if admin_users else None
            if admin_user:
                support_room = ChatRoom()
                support_room.name = f"Support - {self.name}"
                support_room.room_type = 'support'
                support_room.law_firm_id = self.id
                support_room.created_by_id = admin_user.id
                db.session.add(support_room)
                db.session.flush()
                
                # Add admin as participant
                participant = ChatParticipant()
                participant.room_id = support_room.id
                participant.user_id = admin_user.id
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
        return [assignment.user for assignment in self.assignments if assignment.user and assignment.user.is_client()]

    @property
    def assigned_team_members(self):
        return [assignment.user for assignment in self.assignments if assignment.user and assignment.user.is_team_member()]

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
        line_items_list = list(self.line_items) if self.line_items else []
        if line_items_list:
            return sum(float(item.amount) for item in line_items_list)
        return float(self.amount)
    
    def generate_invoice_number(self):
        """Generate unique invoice number"""
        from datetime import date
        today = date.today()
        prefix = f"INV-{today.year}-{today.month:02d}"
        
        # Find the next sequential number for this month
        from sqlalchemy import func
        existing = db.session.query(func.count(Invoice.id)).filter(
            Invoice.law_firm_id == self.law_firm_id,
            Invoice.invoice_number.like(f"{prefix}-%")
        ).scalar() or 0
        
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


# Sales Lead Models for Popup Sales Page
class SalesLead(db.Model):
    __tablename__ = 'sales_leads'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    firm_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    team_size = db.Column(db.String(50), nullable=True)
    plan = db.Column(db.String(100), nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='new')  # new, contacted, converted, lost
    
    # UTM tracking
    utm_source = db.Column(db.String(100), nullable=True)
    utm_medium = db.Column(db.String(100), nullable=True)
    utm_campaign = db.Column(db.String(100), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class PopupSettings(db.Model):
    __tablename__ = 'popup_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    popup_delay_seconds = db.Column(db.Integer, default=7)
    popup_enabled = db.Column(db.Boolean, default=True)
    welcome_video_url = db.Column(db.String(500), nullable=True)
    thankyou_video_url = db.Column(db.String(500), nullable=True)
    
    # 5-Plan Pricing Structure
    trial_duration_days = db.Column(db.Integer, default=3)  # Free trial duration
    starter_price = db.Column(db.Numeric(10, 2), default=39.00)  # 1-month Starter Plan
    growth_price = db.Column(db.Numeric(10, 2), default=90.00)  # 3-month Growth Plan
    enterprise_price = db.Column(db.Numeric(10, 2), default=350.00)  # 1-year Enterprise Plan
    founders_price = db.Column(db.Numeric(10, 2), default=750.00)  # Founders Pack - $750 for 6-month setup & support
    lifetime_price = db.Column(db.Numeric(10, 2), default=999.00)  # Legacy Lifetime Plan (kept for compatibility)
    
    # Regular pricing (what they would pay later)
    starter_regular_price = db.Column(db.Numeric(10, 2), default=70.00)
    growth_regular_price = db.Column(db.Numeric(10, 2), default=210.00)
    enterprise_regular_price = db.Column(db.Numeric(10, 2), default=840.00)
    founders_regular_price = db.Column(db.Numeric(10, 2), default=840.00)
    
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class CustomerReview(db.Model):
    __tablename__ = 'customer_reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    firm_name = db.Column(db.String(200), nullable=False)
    review_text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)
    location = db.Column(db.String(200), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)


class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Bank Transfer", "USDT Tron"
    type = db.Column(db.String(50), nullable=False)  # "bank", "crypto"
    details = db.Column(db.Text, nullable=False)  # Account details or wallet address
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)


class PopupSuppression(db.Model):
    __tablename__ = 'popup_suppressions'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)
    suppressed_until = db.Column(db.DateTime, nullable=True)
    has_ordered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


# Law Firm Showcase Models
class LawFirmShowcase(db.Model):
    __tablename__ = 'law_firm_showcases'
    
    id = db.Column(db.Integer, primary_key=True)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    showcase_order = db.Column(db.Integer, default=0)
    
    # Public display fields
    public_title = db.Column(db.String(200), nullable=True)
    public_description = db.Column(db.Text, nullable=True)
    hero_image_url = db.Column(db.String(500), nullable=True)
    logo_image_url = db.Column(db.String(500), nullable=True)
    
    # Social media and contact
    website_url = db.Column(db.String(300), nullable=True)
    facebook_url = db.Column(db.String(300), nullable=True)
    linkedin_url = db.Column(db.String(300), nullable=True)
    twitter_url = db.Column(db.String(300), nullable=True)
    instagram_url = db.Column(db.String(300), nullable=True)
    
    # Showcase stats
    total_reviews = db.Column(db.Integer, default=0)
    average_rating = db.Column(db.Numeric(3, 2), default=5.0)
    total_views = db.Column(db.Integer, default=0)
    
    # Verification system
    is_verified = db.Column(db.Boolean, default=False)
    verified_date = db.Column(db.DateTime, nullable=True)
    verified_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    verification_reason = db.Column(db.String(200), nullable=True)  # e.g., "1-year premium subscription"
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    law_firm = db.relationship('LawFirm', back_populates='showcase')
    public_reviews = db.relationship('PublicLawFirmReview', back_populates='showcase', cascade='all, delete-orphan')
    public_messages = db.relationship('PublicLawFirmMessage', back_populates='showcase', cascade='all, delete-orphan')
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])


class PublicLawFirmReview(db.Model):
    __tablename__ = 'public_law_firm_reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    showcase_id = db.Column(db.Integer, db.ForeignKey('law_firm_showcases.id'), nullable=False)
    
    # Reviewer information
    reviewer_name = db.Column(db.String(200), nullable=False)
    reviewer_email = db.Column(db.String(300), nullable=True)
    reviewer_company = db.Column(db.String(200), nullable=True)
    reviewer_location = db.Column(db.String(200), nullable=True)
    
    # Review content
    rating = db.Column(db.Integer, nullable=False, default=5)  # 1-5 stars
    review_title = db.Column(db.String(300), nullable=True)
    review_text = db.Column(db.Text, nullable=False)
    
    # Moderation
    is_approved = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_visible = db.Column(db.Boolean, default=True)
    
    # Metadata
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    showcase = db.relationship('LawFirmShowcase', back_populates='public_reviews')


# ─── Calendar / Scheduling ───────────────────────────────────────────────────

EVENT_TYPE_COURT = 'court_date'
EVENT_TYPE_MEETING = 'meeting'
EVENT_TYPE_APPOINTMENT = 'appointment'
EVENT_TYPE_DEADLINE = 'deadline'
EVENT_TYPE_OTHER = 'other'

EVENT_STATUS_UPCOMING = 'upcoming'
EVENT_STATUS_COMPLETED = 'completed'
EVENT_STATUS_CANCELLED = 'cancelled'


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)

    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    event_type = db.Column(db.String(50), default=EVENT_TYPE_MEETING, nullable=False)
    status = db.Column(db.String(50), default=EVENT_STATUS_UPCOMING, nullable=False)

    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=True)
    all_day = db.Column(db.Boolean, default=False)

    location = db.Column(db.String(300), nullable=True)
    virtual_link = db.Column(db.String(500), nullable=True)

    # Reminder: minutes before the event
    reminder_minutes = db.Column(db.Integer, default=60, nullable=True)
    reminder_sent = db.Column(db.Boolean, default=False)

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    law_firm = db.relationship('LawFirm', backref='calendar_events')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_events')
    project = db.relationship('Project', backref='calendar_events')
    attendees = db.relationship('CalendarEventAttendee', back_populates='event', cascade='all, delete-orphan')

    @property
    def type_label(self):
        labels = {
            EVENT_TYPE_COURT: 'Court Date',
            EVENT_TYPE_MEETING: 'Meeting',
            EVENT_TYPE_APPOINTMENT: 'Appointment',
            EVENT_TYPE_DEADLINE: 'Deadline',
            EVENT_TYPE_OTHER: 'Other',
        }
        return labels.get(self.event_type, self.event_type.title())

    @property
    def type_color(self):
        colors = {
            EVENT_TYPE_COURT: 'danger',
            EVENT_TYPE_MEETING: 'primary',
            EVENT_TYPE_APPOINTMENT: 'success',
            EVENT_TYPE_DEADLINE: 'warning',
            EVENT_TYPE_OTHER: 'secondary',
        }
        return colors.get(self.event_type, 'secondary')

    @property
    def type_icon(self):
        icons = {
            EVENT_TYPE_COURT: 'fa-gavel',
            EVENT_TYPE_MEETING: 'fa-handshake',
            EVENT_TYPE_APPOINTMENT: 'fa-calendar-check',
            EVENT_TYPE_DEADLINE: 'fa-clock',
            EVENT_TYPE_OTHER: 'fa-calendar',
        }
        return icons.get(self.event_type, 'fa-calendar')


class CalendarEventAttendee(db.Model):
    __tablename__ = 'calendar_event_attendees'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('calendar_events.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    rsvp_status = db.Column(db.String(20), default='invited')  # invited, accepted, declined

    event = db.relationship('CalendarEvent', back_populates='attendees')
    user = db.relationship('User', backref='event_attendances')


# ─────────────────────────────────────────────────────────────────────────────

class DashboardSlider(db.Model):
    """Feature ad sliders shown on user dashboards, editable by admins."""
    __tablename__ = 'dashboard_sliders'

    id          = db.Column(db.Integer, primary_key=True)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=True)  # None = platform default

    title       = db.Column(db.String(200), nullable=False)
    subtitle    = db.Column(db.String(300), nullable=True)
    description = db.Column(db.Text,        nullable=True)
    cta_text    = db.Column(db.String(100), nullable=True,  default='Learn More')
    cta_link    = db.Column(db.String(500), nullable=True,  default='#')
    bg_image    = db.Column(db.String(500), nullable=True)   # path under static/
    bg_color    = db.Column(db.String(20),  nullable=False,  default='#0d1b4b')
    icon        = db.Column(db.String(80),  nullable=True,   default='fas fa-star')
    sort_order  = db.Column(db.Integer,     nullable=False,  default=0)
    is_active   = db.Column(db.Boolean,     nullable=False,  default=True)

    created_at  = db.Column(db.DateTime, default=datetime.now)
    updated_at  = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    law_firm    = db.relationship('LawFirm', backref='sliders')


class PublicLawFirmMessage(db.Model):
    __tablename__ = 'public_law_firm_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    showcase_id = db.Column(db.Integer, db.ForeignKey('law_firm_showcases.id'), nullable=False)
    
    # Sender information
    sender_name = db.Column(db.String(200), nullable=False)
    sender_email = db.Column(db.String(300), nullable=False)
    sender_phone = db.Column(db.String(50), nullable=True)
    sender_company = db.Column(db.String(200), nullable=True)
    
    # Message content
    subject = db.Column(db.String(300), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), default='inquiry')  # inquiry, consultation, quote
    
    # Status tracking
    is_read = db.Column(db.Boolean, default=False)
    is_replied = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='normal')  # urgent, high, normal, low
    
    # Metadata
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    read_at = db.Column(db.DateTime, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    showcase = db.relationship('LawFirmShowcase', back_populates='public_messages')
