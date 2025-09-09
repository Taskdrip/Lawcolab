from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
import uuid
import random
import string

simple_checkout_bp = Blueprint('simple_checkout', __name__, template_folder='templates')

@simple_checkout_bp.route('/checkout')
def checkout():
    """Simple checkout page for Lawcolab payments"""
    # Get order details from parameters
    amount = request.args.get('amount', type=float, default=100.00)
    description = request.args.get('description', 'LawColab Service Payment')
    customer_email = request.args.get('email', '')
    customer_name = request.args.get('name', '')
    
    return render_template('simple_checkout.html', 
                         amount=amount,
                         description=description,
                         customer_email=customer_email,
                         customer_name=customer_name)

@simple_checkout_bp.route('/create-order', methods=['POST'])
def create_order():
    """Create a payment order and show payment instructions"""
    try:
        # Get form data
        amount = float(request.form.get('amount', 0))
        customer_email = request.form.get('customer_email', '').strip()
        customer_name = request.form.get('customer_name', '').strip()
        description = request.form.get('description', 'LawColab Service Payment')
        payment_method = request.form.get('payment_method', 'bank_transfer')
        
        # Validation
        if not amount or amount <= 0:
            flash('Invalid payment amount', 'error')
            return redirect(url_for('simple_checkout.checkout'))
        
        if not customer_email or not customer_name:
            flash('Customer email and name are required', 'error')
            return redirect(url_for('simple_checkout.checkout'))
        
        # Generate order reference
        order_ref = generate_order_reference()
        
        # Redirect based on payment method
        if payment_method == 'bank_transfer':
            return redirect(url_for('simple_checkout.bank_instructions', 
                                  order_ref=order_ref,
                                  amount=amount,
                                  name=customer_name,
                                  email=customer_email,
                                  description=description))
        else:
            return redirect(url_for('simple_checkout.crypto_instructions',
                                  order_ref=order_ref,
                                  amount=amount,
                                  name=customer_name,
                                  email=customer_email,
                                  description=description))
            
    except Exception as e:
        flash('Failed to create payment order. Please try again.', 'error')
        return redirect(url_for('simple_checkout.checkout'))

@simple_checkout_bp.route('/bank-instructions')
def bank_instructions():
    """Show bank transfer instructions"""
    order_ref = request.args.get('order_ref', '')
    amount = request.args.get('amount', type=float, default=0)
    name = request.args.get('name', '')
    email = request.args.get('email', '')
    description = request.args.get('description', '')
    
    # Lawcolab Global bank details
    bank_details = {
        'account_name': 'Lawcolab Global',
        'account_number': '1310505179',
        'bank_name': 'Zenith Bank',
        'instructions': 'Include your order reference in the transaction description for faster verification.'
    }
    
    return render_template('bank_instructions.html',
                         order_ref=order_ref,
                         amount=amount,
                         customer_name=name,
                         customer_email=email,
                         description=description,
                         bank_details=bank_details)

@simple_checkout_bp.route('/crypto-instructions')
def crypto_instructions():
    """Show crypto payment instructions"""
    order_ref = request.args.get('order_ref', '')
    amount = request.args.get('amount', type=float, default=0)
    name = request.args.get('name', '')
    email = request.args.get('email', '')
    description = request.args.get('description', '')
    
    # Sample crypto wallets
    crypto_wallets = [
        {
            'name': 'Bitcoin (BTC)',
            'address': '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',
            'network': 'Bitcoin Network'
        },
        {
            'name': 'Ethereum (ETH)',
            'address': '0x742d35Cc6634C0532925a3b8D2c82E8B1b1C8B4F',
            'network': 'Ethereum Network'
        },
        {
            'name': 'USDT (TRC20)',
            'address': 'TRX9Ym4pJKvhCVJzBJQjGT6A8cYYf8Qz9X',
            'network': 'Tron Network'
        }
    ]
    
    return render_template('crypto_instructions.html',
                         order_ref=order_ref,
                         amount=amount,
                         customer_name=name,
                         customer_email=email,
                         description=description,
                         crypto_wallets=crypto_wallets)

@simple_checkout_bp.route('/payment-success')
def payment_success():
    """Payment success page"""
    order_ref = request.args.get('order_ref', '')
    return render_template('payment_success.html', order_ref=order_ref)

def generate_order_reference():
    """Generate unique order reference"""
    prefix = 'LWC'
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{suffix}"