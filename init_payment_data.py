#!/usr/bin/env python3
"""
Initialize default payment methods for LawColab
"""

from app import app, db
from models import PaymentMethod

def init_payment_methods():
    """Initialize default payment methods"""
    
    with app.app_context():
        # Check if payment methods already exist
        existing_count = PaymentMethod.query.count()
        if existing_count > 0:
            print(f"Payment methods already exist ({existing_count} found). Skipping initialization.")
            return
        
        # Default payment methods
        payment_methods = [
            {
                'name': 'USDT Tron (TRC20)',
                'type': 'crypto',
                'details': '''USDT Tron (TRC20) Wallet Address:
TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t

Instructions:
1. Send the exact amount in USDT on Tron network
2. Use the TRC20 network (lowest fees)
3. Copy the transaction hash after payment
4. Send confirmation to support@lawcolab.com with:
   - Transaction hash
   - Your order reference number
   - Your registered email address

Processing time: Usually within 1-2 hours''',
                'display_order': 1,
                'is_active': True
            },
            {
                'name': 'USDT BNB Smart Chain (BEP20)',
                'type': 'crypto',
                'details': '''USDT BNB Smart Chain (BEP20) Wallet Address:
0x8894E0a0c962CB723c1976a4421c95949bE2D4E6

Instructions:
1. Send the exact amount in USDT on BNB Smart Chain
2. Use the BEP20 network for lower fees
3. Copy the transaction hash after payment
4. Send confirmation to support@lawcolab.com with:
   - Transaction hash
   - Your order reference number
   - Your registered email address

Processing time: Usually within 1-2 hours''',
                'display_order': 2,
                'is_active': True
            },
            {
                'name': 'Bank Transfer (International)',
                'type': 'bank',
                'details': '''International Bank Transfer Details:

Bank Name: Guaranty Trust Bank (GTB)
Account Name: Taskdrip Technology Solutions
Account Number: 0123456789
SWIFT Code: GTBINGLA
Bank Address: Lagos, Nigeria

Local Bank Details (Nigeria):
Account Name: Taskdrip Technology Solutions  
Account Number: 0123456789
Bank: GTB

Instructions:
1. Use your order reference as payment reference
2. Send payment confirmation to support@lawcolab.com
3. Include bank transfer receipt/confirmation
4. Processing time: 1-3 business days''',
                'display_order': 3,
                'is_active': True
            },
            {
                'name': 'USDT Polygon (MATIC)',
                'type': 'crypto',
                'details': '''USDT Polygon (MATIC) Wallet Address:
0x8894E0a0c962CB723c1976a4421c95949bE2D4E6

Instructions:
1. Send the exact amount in USDT on Polygon network
2. Very low transaction fees on Polygon
3. Copy the transaction hash after payment
4. Send confirmation to support@lawcolab.com

Processing time: Usually within 1-2 hours''',
                'display_order': 4,
                'is_active': True
            },
            {
                'name': 'USDT Solana',
                'type': 'crypto',
                'details': '''USDT Solana Wallet Address:
5Q4CyQSwJr7dWGKWWq6hHLWoMpX1qXnFWhtKXrWjqZwJ

Instructions:
1. Send the exact amount in USDT on Solana network
2. Fast and low-cost transactions
3. Copy the transaction hash after payment
4. Send confirmation to support@lawcolab.com

Processing time: Usually within 1 hour''',
                'display_order': 5,
                'is_active': True
            }
        ]
        
        # Create payment methods
        for method_data in payment_methods:
            method = PaymentMethod(**method_data)
            db.session.add(method)
        
        db.session.commit()
        print(f"Successfully initialized {len(payment_methods)} payment methods!")

if __name__ == '__main__':
    init_payment_methods()