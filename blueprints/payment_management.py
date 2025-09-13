from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from utils.decorators import require_super_admin
from app import db
from models_payment import PaymentGateway, EscrowTransaction, CryptoWallet, BankAccount
from datetime import datetime
import json

payment_mgmt_bp = Blueprint('payment_management', __name__, url_prefix='/superadmin/payments')

@payment_mgmt_bp.route('/')
@require_super_admin
def payment_dashboard():
    """Payment management dashboard"""
    # Gateway stats
    gateways = PaymentGateway.query.all()
    active_gateways = PaymentGateway.query.filter_by(is_active=True).count()
    
    # Transaction stats
    total_transactions = EscrowTransaction.query.count()
    pending_transactions = EscrowTransaction.query.filter_by(status='pending').count()
    completed_transactions = EscrowTransaction.query.filter_by(status='completed').count()
    
    # Revenue stats
    from sqlalchemy import func
    total_revenue = db.session.query(func.sum(EscrowTransaction.platform_fee))\
                             .filter_by(payment_status='paid').scalar() or 0
    
    recent_transactions = EscrowTransaction.query.order_by(EscrowTransaction.created_at.desc()).limit(10).all()
    
    stats = {
        'active_gateways': active_gateways,
        'total_gateways': len(gateways),
        'total_transactions': total_transactions,
        'pending_transactions': pending_transactions,
        'completed_transactions': completed_transactions,
        'total_revenue': float(total_revenue),
    }
    
    return render_template('payment_management/dashboard.html',
                         stats=stats,
                         gateways=gateways,
                         recent_transactions=recent_transactions)

@payment_mgmt_bp.route('/gateways')
@require_super_admin
def manage_gateways():
    """Manage payment gateways"""
    gateways = PaymentGateway.query.order_by(PaymentGateway.name).all()
    return render_template('payment_management/gateways.html', gateways=gateways)

@payment_mgmt_bp.route('/gateways/create', methods=['GET', 'POST'])
@require_super_admin
def create_gateway():
    """Create or edit payment gateway"""
    if request.method == 'POST':
        gateway_id = request.form.get('gateway_id')
        
        if gateway_id:
            gateway = PaymentGateway.query.get_or_404(gateway_id)
        else:
            gateway = PaymentGateway()
            gateway.created_by_id = current_user.id
        
        # Basic info
        gateway.name = request.form.get('name', '').lower()
        gateway.display_name = request.form.get('display_name', '')
        gateway.is_active = request.form.get('is_active') == 'on'
        gateway.test_mode = request.form.get('test_mode') == 'on'
        
        # Fees
        gateway.transaction_fee_percent = float(request.form.get('transaction_fee_percent', 0)) / 100
        gateway.fixed_fee = float(request.form.get('fixed_fee', 0))
        gateway.min_amount = float(request.form.get('min_amount', 0))
        gateway.max_amount = float(request.form.get('max_amount', 999999))
        
        # Configuration based on gateway type
        config = {}
        if gateway.name == 'stripe':
            config = {
                'publishable_key': request.form.get('stripe_publishable_key', ''),
                'secret_key': request.form.get('stripe_secret_key', ''),
                'webhook_secret': request.form.get('stripe_webhook_secret', ''),
            }
        elif gateway.name == 'paystack':
            config = {
                'public_key': request.form.get('paystack_public_key', ''),
                'secret_key': request.form.get('paystack_secret_key', ''),
            }
        elif gateway.name == 'crypto':
            config = {
                'api_key': request.form.get('crypto_api_key', ''),
                'merchant_id': request.form.get('crypto_merchant_id', ''),
                'webhook_secret': request.form.get('crypto_webhook_secret', ''),
            }
        elif gateway.name == 'bank_transfer':
            config = {
                'account_verification_required': request.form.get('account_verification') == 'on',
                'manual_approval': request.form.get('manual_approval') == 'on',
            }
        
        gateway.set_config(config)
        gateway.updated_at = datetime.utcnow()
        
        if not gateway_id:
            db.session.add(gateway)
        
        db.session.commit()
        
        flash(f'Payment gateway {gateway.display_name} saved successfully!', 'success')
        return redirect(url_for('payment_management.manage_gateways'))
    
    gateway_id = request.args.get('id')
    gateway = PaymentGateway.query.get(gateway_id) if gateway_id else None
    
    return render_template('payment_management/gateway_form.html', gateway=gateway)

@payment_mgmt_bp.route('/gateways/<int:gateway_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_gateway(gateway_id):
    """Toggle gateway active status"""
    gateway = PaymentGateway.query.get_or_404(gateway_id)
    gateway.is_active = not gateway.is_active
    gateway.updated_at = datetime.utcnow()
    db.session.commit()
    
    status = "activated" if gateway.is_active else "deactivated"
    flash(f'Payment gateway {gateway.display_name} has been {status}.', 'success')
    return redirect(url_for('payment_management.manage_gateways'))

@payment_mgmt_bp.route('/transactions')
@require_super_admin
def manage_transactions():
    """Manage escrow transactions"""
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    
    query = EscrowTransaction.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    transactions = query.order_by(EscrowTransaction.created_at.desc())\
                        .paginate(page=page, per_page=20, error_out=False)
    
    # Get status counts for filters
    status_counts = {
        'all': EscrowTransaction.query.count(),
        'pending': EscrowTransaction.query.filter_by(status='pending').count(),
        'paid': EscrowTransaction.query.filter_by(payment_status='paid').count(),
        'in_progress': EscrowTransaction.query.filter_by(status='in_progress').count(),
        'completed': EscrowTransaction.query.filter_by(status='completed').count(),
        'disputed': EscrowTransaction.query.filter_by(status='disputed').count(),
    }
    
    return render_template('payment_management/transactions.html',
                         transactions=transactions,
                         status_filter=status_filter,
                         status_counts=status_counts)

@payment_mgmt_bp.route('/transactions/<transaction_id>')
@require_super_admin
def view_transaction(transaction_id):
    """View transaction details"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    logs = transaction.transaction_logs.order_by('created_at').all()
    milestones = transaction.milestone_payments.order_by('order_index').all()
    
    return render_template('payment_management/transaction_detail.html',
                         transaction=transaction,
                         logs=logs,
                         milestones=milestones)

@payment_mgmt_bp.route('/transactions/<transaction_id>/release-escrow', methods=['POST'])
@require_super_admin
def release_escrow(transaction_id):
    """Release escrow funds"""
    transaction = EscrowTransaction.query.get_or_404(transaction_id)
    notes = request.form.get('notes', '')
    
    success, message = transaction.release_escrow(current_user, notes)
    
    if success:
        db.session.commit()
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('payment_management.view_transaction', transaction_id=transaction_id))

@payment_mgmt_bp.route('/crypto-wallets')
@require_super_admin
def manage_crypto_wallets():
    """Manage cryptocurrency wallets"""
    wallets = CryptoWallet.query.order_by(CryptoWallet.currency).all()
    return render_template('payment_management/crypto_wallets.html', wallets=wallets)

@payment_mgmt_bp.route('/crypto-wallets/create', methods=['GET', 'POST'])
@require_super_admin
def create_crypto_wallet():
    """Create cryptocurrency wallet"""
    if request.method == 'POST':
        wallet = CryptoWallet()
        wallet.currency = request.form.get('currency', '').upper()
        wallet.wallet_address = request.form.get('wallet_address', '')
        wallet.network = request.form.get('network', '')
        wallet.minimum_confirmations = int(request.form.get('minimum_confirmations', 6))
        wallet.is_active = request.form.get('is_active') == 'on'
        wallet.created_by_id = current_user.id
        
        db.session.add(wallet)
        db.session.commit()
        
        flash(f'{wallet.currency} wallet added successfully!', 'success')
        return redirect(url_for('payment_management.manage_crypto_wallets'))
    
    return render_template('payment_management/crypto_wallet_form.html')

@payment_mgmt_bp.route('/bank-accounts')
@require_super_admin
def manage_bank_accounts():
    """Manage bank accounts for wire transfers"""
    accounts = BankAccount.query.order_by(BankAccount.bank_name).all()
    return render_template('payment_management/bank_accounts.html', accounts=accounts)

@payment_mgmt_bp.route('/bank-accounts/create', methods=['GET', 'POST'])
@require_super_admin
def create_bank_account():
    """Create bank account"""
    if request.method == 'POST':
        account = BankAccount()
        account.account_name = request.form.get('account_name', '')
        account.bank_name = request.form.get('bank_name', '')
        account.account_number = request.form.get('account_number', '')
        account.routing_number = request.form.get('routing_number', '')
        account.iban = request.form.get('iban', '')
        account.swift_code = request.form.get('swift_code', '')
        account.currency = request.form.get('currency', 'USD')
        account.country = request.form.get('country', '')
        account.is_active = request.form.get('is_active') == 'on'
        account.is_primary = request.form.get('is_primary') == 'on'
        account.created_by_id = current_user.id
        
        # If this is set as primary, unset others
        if account.is_primary:
            BankAccount.query.update({'is_primary': False})
        
        db.session.add(account)
        db.session.commit()
        
        flash(f'Bank account for {account.bank_name} added successfully!', 'success')
        return redirect(url_for('payment_management.manage_bank_accounts'))
    
    return render_template('payment_management/bank_account_form.html')

@payment_mgmt_bp.route('/crypto-wallets/<int:wallet_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_crypto_wallet(wallet_id):
    """Toggle crypto wallet active status"""
    wallet = CryptoWallet.query.get_or_404(wallet_id)
    wallet.is_active = not wallet.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'status': 'active' if wallet.is_active else 'inactive'})

@payment_mgmt_bp.route('/crypto-wallets/edit/<int:wallet_id>', methods=['GET', 'POST'])
@require_super_admin
def edit_crypto_wallet(wallet_id):
    """Edit crypto wallet"""
    wallet = CryptoWallet.query.get_or_404(wallet_id)
    
    if request.method == 'POST':
        wallet.currency = request.form.get('currency', '').upper()
        wallet.wallet_address = request.form.get('wallet_address', '')
        wallet.network = request.form.get('network', '')
        wallet.minimum_confirmations = int(request.form.get('minimum_confirmations', 6))
        wallet.is_active = request.form.get('is_active') == 'on'
        
        db.session.commit()
        
        flash(f'{wallet.currency} wallet updated successfully!', 'success')
        return redirect(url_for('payment_management.manage_crypto_wallets'))
    
    return render_template('payment_management/crypto_wallet_form.html', wallet=wallet, is_edit=True)

@payment_mgmt_bp.route('/bank-accounts/<int:account_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_bank_account(account_id):
    """Toggle bank account active status"""
    account = BankAccount.query.get_or_404(account_id)
    account.is_active = not account.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'status': 'active' if account.is_active else 'inactive'})

@payment_mgmt_bp.route('/bank-accounts/edit/<int:account_id>', methods=['GET', 'POST'])
@require_super_admin
def edit_bank_account(account_id):
    """Edit bank account"""
    account = BankAccount.query.get_or_404(account_id)
    
    if request.method == 'POST':
        account.account_name = request.form.get('account_name', '')
        account.bank_name = request.form.get('bank_name', '')
        account.account_number = request.form.get('account_number', '')
        account.routing_number = request.form.get('routing_number', '')
        account.iban = request.form.get('iban', '')
        account.swift_code = request.form.get('swift_code', '')
        account.currency = request.form.get('currency', 'USD')
        account.country = request.form.get('country', '')
        account.is_active = request.form.get('is_active') == 'on'
        
        # Handle primary account logic
        is_primary = request.form.get('is_primary') == 'on'
        if is_primary and not account.is_primary:
            BankAccount.query.update({'is_primary': False})
            account.is_primary = True
        elif not is_primary:
            account.is_primary = False
        
        db.session.commit()
        flash(f'Bank account for {account.bank_name} updated successfully!', 'success')
        return redirect(url_for('payment_management.manage_bank_accounts'))
    
    return render_template('payment_management/bank_account_form.html', account=account, edit_mode=True)

@payment_mgmt_bp.route('/bank-accounts/<int:account_id>/set-primary', methods=['POST'])
@require_super_admin
def set_primary_bank_account(account_id):
    """Set bank account as primary"""
    # First, unset all primary accounts
    BankAccount.query.update({'is_primary': False})
    
    # Set this account as primary
    account = BankAccount.query.get_or_404(account_id)
    account.is_primary = True
    db.session.commit()
    
    return jsonify({'success': True})

@payment_mgmt_bp.route('/analytics')
@require_super_admin
def payment_analytics():
    """Payment analytics and reporting"""
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta
    
    # Revenue by month
    monthly_revenue = db.session.query(
        extract('year', EscrowTransaction.created_at).label('year'),
        extract('month', EscrowTransaction.created_at).label('month'),
        func.sum(EscrowTransaction.platform_fee).label('revenue')
    ).filter_by(payment_status='paid')\
     .group_by('year', 'month')\
     .order_by('year', 'month').all()
    
    # Revenue by gateway
    gateway_revenue = db.session.query(
        PaymentGateway.display_name,
        func.sum(EscrowTransaction.platform_fee).label('revenue'),
        func.count(EscrowTransaction.id).label('transaction_count')
    ).join(EscrowTransaction)\
     .filter_by(payment_status='paid')\
     .group_by(PaymentGateway.id).all()
    
    # Transaction status distribution
    status_distribution = db.session.query(
        EscrowTransaction.status,
        func.count(EscrowTransaction.id).label('count')
    ).group_by(EscrowTransaction.status).all()
    
    analytics_data = {
        'monthly_revenue': [
            {
                'year': int(row.year),
                'month': int(row.month),
                'revenue': float(row.revenue or 0)
            } for row in monthly_revenue
        ],
        'gateway_revenue': [
            {
                'gateway': row.display_name,
                'revenue': float(row.revenue or 0),
                'transactions': row.transaction_count
            } for row in gateway_revenue
        ],
        'status_distribution': [
            {
                'status': row.status,
                'count': row.count
            } for row in status_distribution
        ]
    }
    
    return render_template('payment_management/analytics.html', analytics=analytics_data)