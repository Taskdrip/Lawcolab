from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import db
from models_payment_custom import (
    PaymentOrder, PaymentTransaction, PaymentBankAccount, CryptoWallet, PaymentSettings,
    PAYMENT_STATUS_PENDING, PAYMENT_STATUS_CONFIRMED, PAYMENT_STATUS_FAILED,
    PAYMENT_METHOD_BANK_TRANSFER, PAYMENT_METHOD_CRYPTO
)
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import uuid
import random
import string

payment_checkout_bp = Blueprint('payment_checkout', __name__, template_folder='../templates')

@payment_checkout_bp.route('/checkout')
def checkout():
    """Main checkout page - select payment method"""
    # Get order details from session or parameters
    amount = request.args.get('amount', type=float)
    description = request.args.get('description', 'LawColab Service Payment')
    customer_email = request.args.get('email', '')
    customer_name = request.args.get('name', '')
    
    if not amount:
        flash('Invalid payment amount', 'error')
        return redirect(url_for('index'))
    
    # Get available payment methods
    bank_accounts = PaymentBankAccount.query.filter_by(is_active=True).order_by(PaymentBankAccount.display_order).all()
    crypto_wallets = CryptoWallet.query.filter_by(is_active=True).order_by(CryptoWallet.display_order).all()
    
    return render_template('payment/checkout.html', 
                         amount=amount,
                         description=description,
                         customer_email=customer_email,
                         customer_name=customer_name,
                         bank_accounts=bank_accounts,
                         crypto_wallets=crypto_wallets)

@payment_checkout_bp.route('/create-payment-order', methods=['POST'])
def create_payment_order():
    """Create a new payment order"""
    try:
        # Get form data
        amount = float(request.form.get('amount', 0))
        customer_email = request.form.get('customer_email', '').strip()
        customer_name = request.form.get('customer_name', '').strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        description = request.form.get('description', 'LawColab Service Payment')
        payment_method = request.form.get('payment_method', '')
        
        # Validation
        if not amount or amount <= 0:
            flash('Invalid payment amount', 'error')
            return redirect(url_for('payment_checkout.checkout'))
        
        if not customer_email or not customer_name:
            flash('Customer email and name are required', 'error')
            return redirect(url_for('payment_checkout.checkout'))
        
        if payment_method not in [PAYMENT_METHOD_BANK_TRANSFER, PAYMENT_METHOD_CRYPTO]:
            flash('Invalid payment method selected', 'error')
            return redirect(url_for('payment_checkout.checkout'))
        
        # Generate order reference
        order_reference = generate_order_reference()
        
        # Create payment order
        order = PaymentOrder(
            order_reference=order_reference,
            customer_email=customer_email.lower(),
            customer_name=customer_name,
            customer_phone=customer_phone,
            amount=amount,
            description=description,
            payment_method=payment_method,
            expires_at=datetime.now() + timedelta(hours=24),  # 24 hour expiry
            success_url=request.form.get('success_url'),
            cancel_url=request.form.get('cancel_url')
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Redirect to payment instructions based on method
        if payment_method == PAYMENT_METHOD_BANK_TRANSFER:
            return redirect(url_for('payment_checkout.bank_transfer_instructions', order_id=order.id))
        else:
            return redirect(url_for('payment_checkout.crypto_instructions', order_id=order.id))
            
    except Exception as e:
        db.session.rollback()
        flash('Failed to create payment order. Please try again.', 'error')
        return redirect(url_for('payment_checkout.checkout'))

@payment_checkout_bp.route('/bank-transfer/<order_id>')
def bank_transfer_instructions(order_id):
    """Show bank transfer payment instructions"""
    order = PaymentOrder.query.get_or_404(order_id)
    
    if order.is_expired():
        flash('This payment order has expired', 'error')
        return redirect(url_for('payment_checkout.checkout'))
    
    # Get primary bank account
    bank_account = PaymentBankAccount.query.filter_by(is_active=True, is_primary=True).first()
    if not bank_account:
        bank_account = PaymentBankAccount.query.filter_by(is_active=True).first()
    
    if not bank_account:
        flash('Bank transfer is currently unavailable', 'error')
        return redirect(url_for('payment_checkout.checkout'))
    
    return render_template('payment/bank_transfer.html', order=order, bank_account=bank_account)

@payment_checkout_bp.route('/crypto/<order_id>')
def crypto_instructions(order_id):
    """Show crypto payment instructions"""
    order = PaymentOrder.query.get_or_404(order_id)
    
    if order.is_expired():
        flash('This payment order has expired', 'error')
        return redirect(url_for('payment_checkout.checkout'))
    
    # Get available crypto wallets
    crypto_wallets = CryptoWallet.query.filter_by(is_active=True).order_by(CryptoWallet.display_order).all()
    
    if not crypto_wallets:
        flash('Crypto payment is currently unavailable', 'error')
        return redirect(url_for('payment_checkout.checkout'))
    
    return render_template('payment/crypto_payment.html', order=order, crypto_wallets=crypto_wallets)

@payment_checkout_bp.route('/upload-proof/<order_id>', methods=['POST'])
def upload_payment_proof(order_id):
    """Upload payment proof for bank transfer"""
    order = PaymentOrder.query.get_or_404(order_id)
    
    if order.is_expired():
        flash('This payment order has expired', 'error')
        return redirect(url_for('payment_checkout.bank_transfer_instructions', order_id=order_id))
    
    # Handle file upload
    if 'payment_proof' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('payment_checkout.bank_transfer_instructions', order_id=order_id))
    
    file = request.files['payment_proof']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('payment_checkout.bank_transfer_instructions', order_id=order_id))
    
    if file and allowed_file(file.filename):
        # Save file
        filename = secure_filename(f"{order.order_reference}_{file.filename}")
        upload_folder = os.path.join('static', 'payment_proofs')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # Create transaction record
        transaction = PaymentTransaction(
            transaction_reference=generate_transaction_reference(),
            order_id=order.id,
            amount=order.amount,
            currency=order.currency,
            payment_method=PAYMENT_METHOD_BANK_TRANSFER,
            payment_proof_url=f"/static/payment_proofs/{filename}",
            bank_reference=request.form.get('bank_reference', '').strip(),
            expires_at=datetime.now() + timedelta(hours=24)
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        flash('Payment proof uploaded successfully! Your payment is being verified.', 'success')
        return redirect(url_for('payment_checkout.payment_status', order_id=order.id))
    else:
        flash('Invalid file type. Please upload JPG, PNG, or PDF files only.', 'error')
        return redirect(url_for('payment_checkout.bank_transfer_instructions', order_id=order_id))

@payment_checkout_bp.route('/submit-crypto/<order_id>', methods=['POST'])
def submit_crypto_payment(order_id):
    """Submit crypto payment details"""
    order = PaymentOrder.query.get_or_404(order_id)
    
    if order.is_expired():
        flash('This payment order has expired', 'error')
        return redirect(url_for('payment_checkout.crypto_instructions', order_id=order_id))
    
    # Get form data
    crypto_currency = request.form.get('crypto_currency', '').strip()
    crypto_amount = request.form.get('crypto_amount', '').strip()
    crypto_tx_hash = request.form.get('crypto_tx_hash', '').strip()
    wallet_id = request.form.get('wallet_id', type=int)
    
    # Validation
    if not crypto_currency or not crypto_amount or not crypto_tx_hash:
        flash('All crypto payment details are required', 'error')
        return redirect(url_for('payment_checkout.crypto_instructions', order_id=order_id))
    
    # Get wallet details
    wallet = CryptoWallet.query.get(wallet_id)
    if not wallet or not wallet.is_active:
        flash('Invalid crypto wallet selected', 'error')
        return redirect(url_for('payment_checkout.crypto_instructions', order_id=order_id))
    
    # Create transaction record
    transaction = PaymentTransaction(
        transaction_reference=generate_transaction_reference(),
        order_id=order.id,
        amount=order.amount,
        currency=order.currency,
        payment_method=PAYMENT_METHOD_CRYPTO,
        crypto_address=wallet.wallet_address,
        crypto_currency=crypto_currency,
        crypto_amount=crypto_amount,
        crypto_tx_hash=crypto_tx_hash,
        expires_at=datetime.now() + timedelta(hours=24)
    )
    
    db.session.add(transaction)
    db.session.commit()
    
    flash('Crypto payment details submitted! Your payment is being verified.', 'success')
    return redirect(url_for('payment_checkout.payment_status', order_id=order.id))

@payment_checkout_bp.route('/status/<order_id>')
def payment_status(order_id):
    """Check payment status"""
    order = PaymentOrder.query.get_or_404(order_id)
    transactions = PaymentTransaction.query.filter_by(order_id=order.id).order_by(PaymentTransaction.created_at.desc()).all()
    
    return render_template('payment/status.html', order=order, transactions=transactions)

@payment_checkout_bp.route('/verify-payment/<transaction_id>', methods=['POST'])
@login_required
def verify_payment(transaction_id):
    """Admin endpoint to verify payment"""
    if not current_user.is_admin() and not current_user.is_super_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    transaction = PaymentTransaction.query.get_or_404(transaction_id)
    action = request.form.get('action')  # 'confirm' or 'reject'
    notes = request.form.get('verification_notes', '').strip()
    
    if action == 'confirm':
        transaction.status = PAYMENT_STATUS_CONFIRMED
        transaction.confirmed_at = datetime.now()
        transaction.order.status = PAYMENT_STATUS_CONFIRMED
        transaction.order.confirmed_at = datetime.now()
        flash('Payment confirmed successfully', 'success')
    elif action == 'reject':
        transaction.status = PAYMENT_STATUS_FAILED
        transaction.order.status = PAYMENT_STATUS_FAILED
        flash('Payment rejected', 'info')
    
    transaction.verified_by = current_user.id
    transaction.verification_notes = notes
    
    db.session.commit()
    
    return redirect(url_for('payment_checkout.admin_payments'))

@payment_checkout_bp.route('/admin/payments')
@login_required
def admin_payments():
    """Admin page to manage payments"""
    if not current_user.is_admin() and not current_user.is_super_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get all pending transactions
    pending_transactions = PaymentTransaction.query.filter_by(status=PAYMENT_STATUS_PENDING).order_by(PaymentTransaction.created_at.desc()).all()
    
    # Get recent confirmed transactions
    confirmed_transactions = PaymentTransaction.query.filter_by(status=PAYMENT_STATUS_CONFIRMED).order_by(PaymentTransaction.confirmed_at.desc()).limit(20).all()
    
    return render_template('payment/admin_payments.html', 
                         pending_transactions=pending_transactions,
                         confirmed_transactions=confirmed_transactions)

# Helper functions
def generate_order_reference():
    """Generate unique order reference"""
    prefix = 'LWC'
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    reference = f"{prefix}-{suffix}"
    
    # Ensure uniqueness
    while PaymentOrder.query.filter_by(order_reference=reference).first():
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        reference = f"{prefix}-{suffix}"
    
    return reference

def generate_transaction_reference():
    """Generate unique transaction reference"""
    prefix = 'TXN'
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    reference = f"{prefix}-{suffix}"
    
    # Ensure uniqueness
    while PaymentTransaction.query.filter_by(transaction_reference=reference).first():
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        reference = f"{prefix}-{suffix}"
    
    return reference

def allowed_file(filename):
    """Check if file type is allowed for payment proof"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS