#!/usr/bin/env python3
"""
Initialize payment gateway data for the super admin payment management system
"""
from app import app, db
from models_payment import PaymentGateway
from models import User

def init_payment_gateways():
    """Initialize default payment gateways"""
    with app.app_context():
        # Check if gateways already exist
        existing_gateways = PaymentGateway.query.count()
        if existing_gateways > 0:
            print(f"✓ Payment gateways already exist ({existing_gateways} gateways)")
            return

        # Get super admin user for created_by
        super_admin = User.query.filter_by(role='super_admin').first()
        if not super_admin:
            print("✗ No super admin found. Please create super admin first.")
            return

        # Create Stripe gateway
        stripe_gateway = PaymentGateway(
            name='stripe',
            display_name='Stripe',
            is_active=False,  # Inactive by default, super admin must configure
            test_mode=True,
            transaction_fee_percent=0.029,  # 2.9%
            fixed_fee=0.30,  # $0.30 per transaction
            min_amount=1.00,
            max_amount=999999.99,
            created_by_id=super_admin.id
        )
        
        # Create Paystack gateway
        paystack_gateway = PaymentGateway(
            name='paystack',
            display_name='Paystack',
            is_active=False,
            test_mode=True,
            transaction_fee_percent=0.015,  # 1.5%
            fixed_fee=0.0,
            min_amount=1.00,
            max_amount=999999.99,
            created_by_id=super_admin.id
        )
        
        # Create Crypto gateway
        crypto_gateway = PaymentGateway(
            name='crypto',
            display_name='Cryptocurrency',
            is_active=False,
            test_mode=True,
            transaction_fee_percent=0.01,  # 1%
            fixed_fee=0.0,
            min_amount=10.00,
            max_amount=999999.99,
            created_by_id=super_admin.id
        )
        
        # Create Bank Transfer gateway
        bank_gateway = PaymentGateway(
            name='bank_transfer',
            display_name='Bank Transfer',
            is_active=False,
            test_mode=True,
            transaction_fee_percent=0.005,  # 0.5%
            fixed_fee=5.00,  # $5 wire fee
            min_amount=100.00,
            max_amount=999999.99,
            created_by_id=super_admin.id
        )

        # Add all gateways
        db.session.add_all([stripe_gateway, paystack_gateway, crypto_gateway, bank_gateway])
        db.session.commit()

        print("✓ Payment gateways initialized successfully!")
        print("  - Stripe (2.9% + $0.30)")
        print("  - Paystack (1.5%)")
        print("  - Cryptocurrency (1%)")
        print("  - Bank Transfer (0.5% + $5)")
        print("\nAll gateways are inactive by default.")
        print("Super admin can configure API keys and activate them.")

if __name__ == "__main__":
    init_payment_gateways()