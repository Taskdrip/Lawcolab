from app import db
from datetime import datetime

class AuditLog(db.Model):
    """Security audit log for tracking important system events"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Event details
    event_type = db.Column(db.String(50), nullable=False)  # 'support_message', 'super_admin_access', etc.
    event_description = db.Column(db.Text, nullable=False)
    
    # User and context
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=True)
    target_resource = db.Column(db.String(100), nullable=True)  # room_id, invoice_id, etc.
    
    # Metadata
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    user = db.relationship('User', backref='audit_logs')
    law_firm = db.relationship('LawFirm', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.event_type}: {self.event_description}>'

def log_audit_event(event_type, description, user_id=None, law_firm_id=None, 
                   target_resource=None, success=True, error_message=None,
                   ip_address=None, user_agent=None):
    """
    Create an audit log entry for security and compliance tracking
    """
    try:
        audit_entry = AuditLog(
            event_type=event_type,
            event_description=description,
            user_id=user_id,
            law_firm_id=law_firm_id,
            target_resource=target_resource,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.session.add(audit_entry)
        db.session.commit()
        
        return audit_entry
        
    except Exception as e:
        db.session.rollback()
        print(f"Failed to create audit log: {str(e)}")
        return None