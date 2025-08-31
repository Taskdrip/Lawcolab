from app import db
from datetime import datetime
from decimal import Decimal
import json
from cryptography.fernet import Fernet
import os

class PaymentGateway(db.Model):
    """Payment gateway configuration for super admin management"""
    __tablename__ = 'payment_gateways'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # stripe, paystack, crypto, bank_transfer
    display_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    test_mode = db.Column(db.Boolean, default=True)
    
    # Encrypted configuration
    encrypted_config = db.Column(db.Text)  # Encrypted JSON of API keys/config
    
    # Fees and limits
    transaction_fee_percent = db.Column(db.Numeric(5, 4), default=0.0)  # e.g., 2.9% = 0.029
    fixed_fee = db.Column(db.Numeric(10, 2), default=0.0)  # Fixed fee per transaction
    min_amount = db.Column(db.Numeric(15, 2), default=0.0)
    max_amount = db.Column(db.Numeric(15, 2), default=999999.99)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    escrow_transactions = db.relationship('EscrowTransaction', backref='payment_gateway', lazy='dynamic')
    
    def get_encryption_key(self):
        """Get or create encryption key for this gateway"""
        key = os.environ.get(f'PAYMENT_KEY_{self.name.upper()}')
        if not key:
            key = Fernet.generate_key().decode()
            # In production, store this securely
        return key.encode() if isinstance(key, str) else key
    
    def set_config(self, config_dict):
        """Encrypt and store configuration"""
        fernet = Fernet(self.get_encryption_key())
        config_json = json.dumps(config_dict)
        self.encrypted_config = fernet.encrypt(config_json.encode()).decode()
    
    def get_config(self):
        """Decrypt and return configuration"""
        if not self.encrypted_config:
            return {}
        fernet = Fernet(self.get_encryption_key())
        try:
            decrypted = fernet.decrypt(self.encrypted_config.encode())
            return json.loads(decrypted.decode())
        except:
            return {}
    
    def calculate_total_cost(self, amount):
        """Calculate total cost including fees"""
        fee = (amount * self.transaction_fee_percent) + self.fixed_fee
        return amount + fee, fee

class EscrowTransaction(db.Model):
    """Escrow transactions for law firm services"""
    __tablename__ = 'escrow_transactions'
    
    id = db.Column(db.String(32), primary_key=True)  # UUID
    
    # Parties
    client_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    law_firm_id = db.Column(db.Integer, db.ForeignKey('law_firms.id'), nullable=False)
    assigned_lawyer_id = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Transaction details
    service_description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD')
    
    # Payment details
    payment_gateway_id = db.Column(db.Integer, db.ForeignKey('payment_gateways.id'), nullable=False)
    payment_method = db.Column(db.String(50))  # card, bank_transfer, crypto, etc.
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, paid, in_progress, completed, disputed, refunded
    payment_status = db.Column(db.String(20), default='unpaid')  # unpaid, paid, failed, refunded
    
    # Timeline
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    work_started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    deadline = db.Column(db.DateTime)
    
    # External payment references
    external_payment_id = db.Column(db.String(200))  # Stripe payment intent, Paystack ref, etc.
    external_transaction_ref = db.Column(db.String(200))
    
    # Escrow specific
    escrow_released = db.Column(db.Boolean, default=False)
    escrow_released_at = db.Column(db.DateTime)
    escrow_released_by_id = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Fee calculation
    platform_fee = db.Column(db.Numeric(10, 2), default=0.0)
    gateway_fee = db.Column(db.Numeric(10, 2), default=0.0)
    total_amount = db.Column(db.Numeric(15, 2), nullable=False)  # amount + fees
    
    # Dispute handling
    dispute_reason = db.Column(db.Text)
    dispute_opened_at = db.Column(db.DateTime)
    dispute_resolved_at = db.Column(db.DateTime)
    
    # Relationships - simplified without back_populates for now
    client = db.relationship('User', foreign_keys=[client_id])
    assigned_lawyer = db.relationship('User', foreign_keys=[assigned_lawyer_id])
    escrow_released_by = db.relationship('User', foreign_keys=[escrow_released_by_id])
    law_firm = db.relationship('LawFirm')
    
    # Additional relationships
    milestone_payments = db.relationship('EscrowMilestone', backref='transaction', lazy='dynamic')
    transaction_logs = db.relationship('EscrowTransactionLog', backref='transaction', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4()).replace('-', '')
    
    def can_release_escrow(self, user):
        """Check if user can release escrow funds"""
        return (user.is_super_admin() or 
                users.id == self.client_id or 
                (user.law_firm_id == self.law_firm_id and user.is_admin()))
    
    def release_escrow(self, released_by_user, notes=None):
        """Release escrow funds to law firm"""
        if self.escrow_released:
            return False, "Escrow already released"
        
        if not self.can_release_escrow(released_by_user):
            return False, "Unauthorized to release escrow"
        
        if self.payment_status != 'paid':
            return False, "Payment not confirmed"
        
        self.escrow_released = True
        self.escrow_released_at = datetime.utcnow()
        self.escrow_released_by_id = released_by_users.id
        self.status = 'completed'
        
        # Log the release
        log = EscrowTransactionLog(
            transaction_id=self.id,
            action='escrow_released',
            performed_by_id=released_by_users.id,
            notes=notes or f"Escrow released by {released_by_user.full_name}"
        )
        db.session.add(log)
        
        return True, "Escrow funds released successfully"

class EscrowMilestone(db.Model):
    """Milestone-based payments for large contracts"""
    __tablename__ = 'escrow_milestones'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(32), db.ForeignKey('escrow_transactions.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    order_index = db.Column(db.Integer, default=0)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, approved
    due_date = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Files and evidence
    deliverable_files = db.Column(db.Text)  # JSON array of file paths
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EscrowTransactionLog(db.Model):
    """Audit log for escrow transactions"""
    __tablename__ = 'escrow_transaction_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(32), db.ForeignKey('escrow_transactions.id'), nullable=False)
    
    action = db.Column(db.String(50), nullable=False)  # created, paid, started, completed, disputed, etc.
    performed_by_id = db.Column(db.String, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    
    # Additional data
    additional_data = db.Column(db.Text)  # JSON for additional data
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    performed_by = db.relationship('User', backref='escrow_logs')

class CryptoWallet(db.Model):
    """Cryptocurrency wallet configuration"""
    __tablename__ = 'crypto_wallets'
    
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), nullable=False)  # BTC, ETH, USDT, etc.
    wallet_address = db.Column(db.String(200), nullable=False)
    network = db.Column(db.String(50))  # mainnet, testnet, BSC, Polygon, etc.
    
    is_active = db.Column(db.Boolean, default=True)
    minimum_confirmations = db.Column(db.Integer, default=6)
    
    # Encrypted private data (if needed for automated processing)
    encrypted_private_key = db.Column(db.Text)  # Only if automated processing needed
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class BankAccount(db.Model):
    """Bank account configuration for wire transfers"""
    __tablename__ = 'bank_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(200), nullable=False)
    bank_name = db.Column(db.String(200), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    routing_number = db.Column(db.String(50))
    iban = db.Column(db.String(50))
    swift_code = db.Column(db.String(20))
    
    currency = db.Column(db.String(3), default='USD')
    country = db.Column(db.String(3))  # ISO country code
    
    is_active = db.Column(db.Boolean, default=True)
    is_primary = db.Column(db.Boolean, default=False)
    
    # For verification
    verification_status = db.Column(db.String(20), default='pending')  # pending, verified, rejected
    verification_notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))