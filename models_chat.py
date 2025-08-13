from app import db
from datetime import datetime
from models import User

class ChatRoom(db.Model):
    """Chat rooms for different types of conversations"""
    __tablename__ = 'chat_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    room_type = db.Column(db.String(50), nullable=False)  # 'support', 'project', 'direct', 'broadcast'
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'))  # Multi-tenancy
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)  # For project chats
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    law_firm = db.relationship('LawFirm', backref='chat_rooms')
    project = db.relationship('Project', backref='chat_rooms')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    participants = db.relationship('ChatParticipant', back_populates='room', cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', back_populates='room', cascade='all, delete-orphan')

class ChatParticipant(db.Model):
    """Users participating in chat rooms"""
    __tablename__ = 'chat_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.now)
    last_read_at = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    room = db.relationship('ChatRoom', back_populates='participants')
    user = db.relationship('User', backref='chat_participations')
    
    @property
    def unread_count(self):
        """Get count of unread messages for this participant"""
        return ChatMessage.query.filter(
            ChatMessage.room_id == self.room_id,
            ChatMessage.created_at > self.last_read_at,
            ChatMessage.sender_id != self.user_id
        ).count()

class ChatMessage(db.Model):
    """Individual chat messages"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    sender_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # 'text', 'file', 'notification', 'broadcast'
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(200), nullable=True)
    is_broadcast = db.Column(db.Boolean, default=False)  # For super admin broadcasts
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    edited_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    room = db.relationship('ChatRoom', back_populates='messages')
    sender = db.relationship('User', foreign_keys=[sender_id])

class SuperAdminBroadcast(db.Model):
    """Super admin broadcast messages to all law firms"""
    __tablename__ = 'superadmin_broadcasts'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(20), default='all')  # 'all', 'active', 'expired', 'pending'
    is_urgent = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id])
    deliveries = db.relationship('BroadcastDelivery', back_populates='broadcast', cascade='all, delete-orphan')

class BroadcastDelivery(db.Model):
    """Track broadcast message deliveries to law firms"""
    __tablename__ = 'broadcast_deliveries'
    
    id = db.Column(db.Integer, primary_key=True)
    broadcast_id = db.Column(db.Integer, db.ForeignKey('superadmin_broadcasts.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    delivered_at = db.Column(db.DateTime, default=datetime.now)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    broadcast = db.relationship('SuperAdminBroadcast', back_populates='deliveries')
    law_firm = db.relationship('LawFirm', backref='broadcast_deliveries')