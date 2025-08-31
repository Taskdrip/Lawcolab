from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from app import db
from models import LawFirm, User
from models_payment import PaymentGateway, EscrowTransaction, EscrowTransactionLog
from datetime import datetime, timedelta
import uuid

escrow_bp = Blueprint('escrow', __name__, url_prefix='/escrow')

@escrow_bp.route('/law-firm/<int:firm_id>/hire')
def hire_law_firm(firm_id):
    """Public page to hire a law firm with escrow payment"""
    law_firm = LawFirm.query.get_or_404(firm_id)
    
    # Get active payment gateways
    payment_gateways = PaymentGateway.query.filter_by(is_active=True).all()
    
    # Get lawyers from this firm
    lawyers = User.query.filter_by(
        law_firm_id=firm_id,
        role='team_member',
        active=True
    ).all()
    
    # Get firm's recent successful projects (for social proof)
    recent_projects = EscrowTransaction.query.filter_by(
        law_firm_id=firm_id,
        status='completed'
    ).order_by(EscrowTransaction.completed_at.desc()).limit(5).all()
    
    return render_template('escrow/hire_firm.html',
                         law_firm=law_firm,
                         payment_gateways=payment_gateways,
                         lawyers=lawyers,
                         recent_projects=recent_projects)

@escrow_bp.route('/law-firm/<int:firm_id>/create-escrow', methods=['POST'])
@login_required
def create_escrow_transaction(firm_id):
    """Create a new escrow transaction"""
    law_firm = LawFirm.query.get_or_404(firm_id)
    
    # Validate form data
    service_description = request.form.get('service_description', '').strip()
    amount = float(request.form.get('amount', 0))
    payment_gateway_id = int(request.form.get('payment_gateway_id'))
    assigned_lawyer_id = request.form.get('assigned_lawyer_id')
    deadline_str = request.form.get('deadline', '')
    
    if not service_description or amount <= 0:
        flash('Please provide a valid service description and amount.', 'error')
        return redirect(url_for('escrow.hire_law_firm', firm_id=firm_id))
    
    # Validate payment gateway
    gateway = PaymentGateway.query.filter_by(id=payment_gateway_id, is_active=True).first()
    if not gateway:
        flash('Invalid payment gateway selected.', 'error')
        return redirect(url_for('escrow.hire_law_firm', firm_id=firm_id))
    
    # Validate amount limits
    if amount < gateway.min_amount or amount > gateway.max_amount:
        flash(f'Amount must be between ${gateway.min_amount} and ${gateway.max_amount}.', 'error')
        return redirect(url_for('escrow.hire_law_firm', firm_id=firm_id))
    
    # Parse deadline
    deadline = None
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid deadline format.', 'error')
            return redirect(url_for('escrow.hire_law_firm', firm_id=firm_id))
    
    # Calculate total cost including fees
    total_amount, gateway_fee = gateway.calculate_total_cost(amount)
    platform_fee = amount * 0.05  # 5% platform fee
    
    # Create escrow transaction
    transaction = EscrowTransaction()
    transaction.client_id = current_user.id
    transaction.law_firm_id = firm_id
    transaction.assigned_lawyer_id = assigned_lawyer_id if assigned_lawyer_id else None
    transaction.service_description = service_description
    transaction.amount = amount
    transaction.total_amount = total_amount
    transaction.platform_fee = platform_fee
    transaction.gateway_fee = gateway_fee
    transaction.payment_gateway_id = payment_gateway_id
    transaction.deadline = deadline
    transaction.status = 'pending'
    transaction.payment_status = 'unpaid'
    
    db.session.add(transaction)
    db.session.flush()  # Get the ID
    
    # Create initial log entry
    log = EscrowTransactionLog(
        transaction_id=transaction.id,
        action='created',
        performed_by_id=current_user.id,
        notes=f"Escrow transaction created for {service_description}"
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'Escrow transaction created! Total amount: ${total_amount:.2f}', 'success')
    
    # Redirect to payment page based on gateway
    if gateway.name == 'stripe':
        return redirect(url_for('escrow.stripe_payment', transaction_id=transaction.id))
    elif gateway.name == 'paystack':
        return redirect(url_for('escrow.paystack_payment', transaction_id=transaction.id))
    elif gateway.name == 'crypto':
        return redirect(url_for('escrow.crypto_payment', transaction_id=transaction.id))
    elif gateway.name == 'bank_transfer':
        return redirect(url_for('escrow.bank_transfer_payment', transaction_id=transaction.id))
    else:
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction.id))

@escrow_bp.route('/transaction/<transaction_id>')
@login_required
def view_transaction(transaction_id):
    """View escrow transaction details"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    # Check access permissions
    if not (current_user.id == transaction.client_id or 
            current_user.law_firm_id == transaction.law_firm_id or
            current_user.is_super_admin()):
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    
    logs = transaction.transaction_logs.order_by('created_at').all()
    milestones = transaction.milestone_payments.order_by('order_index').all()
    
    return render_template('escrow/transaction_detail.html',
                         transaction=transaction,
                         logs=logs,
                         milestones=milestones)

@escrow_bp.route('/payment/stripe/<transaction_id>')
@login_required
def stripe_payment(transaction_id):
    """Stripe payment page"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    if transaction.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    
    if transaction.payment_status == 'paid':
        flash('Transaction already paid.', 'info')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    gateway = transaction.payment_gateway
    config = gateway.get_config()
    
    return render_template('escrow/payment/stripe.html',
                         transaction=transaction,
                         stripe_public_key=config.get('publishable_key'))

@escrow_bp.route('/payment/paystack/<transaction_id>')
@login_required
def paystack_payment(transaction_id):
    """Paystack payment page"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    if transaction.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    
    if transaction.payment_status == 'paid':
        flash('Transaction already paid.', 'info')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    gateway = transaction.payment_gateway
    config = gateway.get_config()
    
    return render_template('escrow/payment/paystack.html',
                         transaction=transaction,
                         paystack_public_key=config.get('public_key'))

@escrow_bp.route('/payment/crypto/<transaction_id>')
@login_required
def crypto_payment(transaction_id):
    """Cryptocurrency payment page"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    if transaction.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    
    if transaction.payment_status == 'paid':
        flash('Transaction already paid.', 'info')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    # Get available crypto wallets
    from models_payment import CryptoWallet
    crypto_wallets = CryptoWallet.query.filter_by(is_active=True).all()
    
    return render_template('escrow/payment/crypto.html',
                         transaction=transaction,
                         crypto_wallets=crypto_wallets)

@escrow_bp.route('/payment/bank-transfer/<transaction_id>')
@login_required
def bank_transfer_payment(transaction_id):
    """Bank transfer payment page"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    if transaction.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    
    if transaction.payment_status == 'paid':
        flash('Transaction already paid.', 'info')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    # Get bank accounts
    from models_payment import BankAccount
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    
    return render_template('escrow/payment/bank_transfer.html',
                         transaction=transaction,
                         bank_accounts=bank_accounts)

@escrow_bp.route('/my-transactions')
@login_required
def my_transactions():
    """View user's transactions (client or lawyer perspective)"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    if current_user.is_client():
        query = EscrowTransaction.query.filter_by(client_id=current_user.id)
    elif current_user.is_team_member() or current_user.is_admin():
        query = EscrowTransaction.query.filter(
            (EscrowTransaction.law_firm_id == current_user.law_firm_id) |
            (EscrowTransaction.assigned_lawyer_id == current_user.id)
        )
    else:
        query = EscrowTransaction.query.filter_by(client_id=current_user.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    transactions = query.order_by(EscrowTransaction.created_at.desc())\
                       .paginate(page=page, per_page=10, error_out=False)
    
    return render_template('escrow/my_transactions.html',
                         transactions=transactions,
                         status_filter=status_filter)

@escrow_bp.route('/transaction/<transaction_id>/start-work', methods=['POST'])
@login_required
def start_work(transaction_id):
    """Mark work as started (lawyer action)"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    # Check if user can start work
    if not (current_user.law_firm_id == transaction.law_firm_id and 
            (current_user.is_admin() or current_user.id == transaction.assigned_lawyer_id)):
        flash('Access denied.', 'error')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    if transaction.payment_status != 'paid':
        flash('Cannot start work until payment is confirmed.', 'error')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    if transaction.status != 'paid':
        transaction.status = 'in_progress'
        transaction.work_started_at = datetime.utcnow()
        
        # Log the action
        log = EscrowTransactionLog(
            transaction_id=transaction.id,
            action='work_started',
            performed_by_id=current_user.id,
            notes=f"Work started by {current_user.full_name}"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Work has been marked as started!', 'success')
    
    return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))

@escrow_bp.route('/transaction/<transaction_id>/complete-work', methods=['POST'])
@login_required
def complete_work(transaction_id):
    """Mark work as completed (lawyer action)"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    # Check if user can complete work
    if not (current_user.law_firm_id == transaction.law_firm_id and 
            (current_user.is_admin() or current_user.id == transaction.assigned_lawyer_id)):
        flash('Access denied.', 'error')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    if transaction.status == 'in_progress':
        transaction.status = 'completed'
        transaction.completed_at = datetime.utcnow()
        
        # Log the action
        log = EscrowTransactionLog(
            transaction_id=transaction.id,
            action='work_completed',
            performed_by_id=current_user.id,
            notes=f"Work completed by {current_user.full_name}"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Work has been marked as completed! Awaiting client approval for escrow release.', 'success')
    
    return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))

@escrow_bp.route('/transaction/<transaction_id>/approve-release', methods=['POST'])
@login_required
def approve_escrow_release(transaction_id):
    """Approve escrow release (client action)"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    
    if transaction.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))
    
    if transaction.status == 'completed':
        success, message = transaction.release_escrow(current_user, "Client approved work completion")
        
        if success:
            db.session.commit()
            flash(message, 'success')
        else:
            flash(message, 'error')
    
    return redirect(url_for('escrow.view_transaction', transaction_id=transaction_id))