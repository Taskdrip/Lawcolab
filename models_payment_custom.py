from datetime import datetime
from app import db
from sqlalchemy import UniqueConstraint
import uuid

# Payment status constants
PAYMENT_STATUS_PENDING = 'pending'
PAYMENT_STATUS_CONFIRMED = 'confirmed'
PAYMENT_STATUS_FAILED = 'failed'
PAYMENT_STATUS_EXPIRED = 'expired'

# Payment method constants
PAYMENT_METHOD_BANK_TRANSFER = 'bank_transfer'
PAYMENT_METHOD_CRYPTO = 'crypto'

class PaymentOrder(db.Model):
    """Main payment order model for checkout"""
    __tablename__ = 'payment_orders'
    
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_reference = db.Column(db.String(50), unique=True, nullable=False)
    
    # Customer details
    customer_email = db.Column(db.String(255), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    
    # Order details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='NGN', nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Payment method selection
    payment_method = db.Column(db.String(20), nullable=False)  # bank_transfer, crypto
    
    # Order status
    status = db.Column(db.String(20), default=PAYMENT_STATUS_PENDING, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)  # Payment expiry time
    confirmed_at = db.Column(db.DateTime, nullable=True)
    
    # Callback URLs
    success_url = db.Column(db.Text, nullable=True)
    cancel_url = db.Column(db.Text, nullable=True)
    
    # Additional order metadata
    order_metadata = db.Column(db.JSON, nullable=True)
    
    # Relationships
    transactions = db.relationship('PaymentTransaction', back_populates='order', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PaymentOrder {self.order_reference}>'
    
    def is_expired(self):
        """Check if payment order has expired"""
        if not self.expires_at:
            return False
        return datetime.now() > self.expires_at
    
    def generate_reference(self):
        """Generate unique order reference"""
        import random
        import string
        prefix = 'LWC'
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"{prefix}-{suffix}"

class PaymentTransaction(db.Model):
    """Payment transaction records"""
    __tablename__ = 'payment_transactions'
    
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_reference = db.Column(db.String(100), unique=True, nullable=False)
    
    # Order relationship
    order_id = db.Column(db.String, db.ForeignKey('payment_orders.id'), nullable=False)
    order = db.relationship('PaymentOrder', back_populates='transactions')
    
    # Transaction details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='NGN', nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    
    # Transaction status
    status = db.Column(db.String(20), default=PAYMENT_STATUS_PENDING, nullable=False)
    
    # Payment proof (for bank transfer)
    payment_proof_url = db.Column(db.Text, nullable=True)
    bank_reference = db.Column(db.String(100), nullable=True)  # Customer's bank reference
    
    # Crypto details
    crypto_address = db.Column(db.String(255), nullable=True)  # Our crypto wallet address
    crypto_currency = db.Column(db.String(10), nullable=True)  # BTC, ETH, USDT, etc.
    crypto_amount = db.Column(db.String(50), nullable=True)  # Exact crypto amount
    crypto_tx_hash = db.Column(db.String(255), nullable=True)  # Blockchain transaction hash
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # Admin verification
    verified_by = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    verification_notes = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<PaymentTransaction {self.transaction_reference}>'

class PaymentBankAccount(db.Model):
    """Bank account details for receiving payments"""
    __tablename__ = 'payment_bank_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(255), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    bank_name = db.Column(db.String(255), nullable=False)
    bank_code = db.Column(db.String(10), nullable=True)  # Bank sort code
    
    # Additional details
    account_type = db.Column(db.String(50), default='current', nullable=False)
    currency = db.Column(db.String(3), default='NGN', nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    
    # Display settings
    display_order = db.Column(db.Integer, default=0, nullable=False)
    instructions = db.Column(db.Text, nullable=True)  # Special instructions for customers
    
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    
    def __repr__(self):
        return f'<BankAccount {self.bank_name} - {self.account_number}>'

class CryptoWallet(db.Model):
    """Crypto wallet addresses for receiving payments"""
    __tablename__ = 'crypto_wallets'
    
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), nullable=False)  # BTC, ETH, USDT, etc.
    network = db.Column(db.String(50), nullable=True)  # Ethereum, Bitcoin, Tron, etc.
    wallet_address = db.Column(db.String(255), nullable=False)
    
    # Display settings
    display_name = db.Column(db.String(100), nullable=False)  # "Bitcoin (BTC)"
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    
    # Rate settings
    current_rate_usd = db.Column(db.Numeric(15, 8), nullable=True)  # Current exchange rate
    rate_updated_at = db.Column(db.DateTime, nullable=True)
    
    # QR code for easy payments
    qr_code_url = db.Column(db.Text, nullable=True)
    
    # Instructions
    payment_instructions = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    
    def __repr__(self):
        return f'<CryptoWallet {self.currency} - {self.wallet_address[:10]}...>'

class PaymentSettings(db.Model):
    """Global payment system settings"""
    __tablename__ = 'payment_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=True)
    setting_type = db.Column(db.String(20), default='text', nullable=False)  # text, number, boolean, json
    
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f'<PaymentSettings {self.setting_key}>'
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value"""
        setting = cls.query.filter_by(setting_key=key).first()
        if not setting:
            return default
        
        if setting.setting_type == 'boolean':
            return setting.setting_value.lower() in ('true', '1', 'yes')
        elif setting.setting_type == 'number':
            try:
                return float(setting.setting_value)
            except (ValueError, TypeError):
                return default
        elif setting.setting_type == 'json':
            import json
            try:
                return json.loads(setting.setting_value)
            except (ValueError, TypeError):
                return default
        else:
            return setting.setting_value
    
    @classmethod
    def set_setting(cls, key, value, setting_type='text', description=None):
        """Set a setting value"""
        setting = cls.query.filter_by(setting_key=key).first()
        if not setting:
            setting = cls(setting_key=key)
            db.session.add(setting)
        
        if setting_type == 'json':
            import json
            setting.setting_value = json.dumps(value)
        else:
            setting.setting_value = str(value)
            
        setting.setting_type = setting_type
        if description:
            setting.description = description
        
        db.session.commit()
        return setting