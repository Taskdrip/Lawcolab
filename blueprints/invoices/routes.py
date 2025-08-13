from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import and_, or_

from app import db
from models import Invoice, InvoiceLineItem, InvoiceNotification, PaymentRecord, User, Project, LawFirm
from utils.decorators import role_required
from utils.notifications import create_invoice_notification, send_invoice_reminder

invoices_bp = Blueprint('invoices', __name__, url_prefix='/invoices')

@invoices_bp.route('/')
@login_required
def list_invoices():
    """List all invoices for the current user's law firm"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    # Base query with law firm isolation
    query = Invoice.query.filter_by(law_firm_id=current_user.law_firm_id)
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Role-based filtering
    if current_user.is_client():
        query = query.filter_by(client_id=current_user.id)
    
    # Order by creation date (newest first)
    query = query.order_by(Invoice.created_at.desc())
    
    # Paginate results
    invoices = query.paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get summary statistics
    stats = {
        'total': Invoice.query.filter_by(law_firm_id=current_user.law_firm_id).count(),
        'draft': Invoice.query.filter_by(law_firm_id=current_user.law_firm_id, status='draft').count(),
        'sent': Invoice.query.filter_by(law_firm_id=current_user.law_firm_id, status='sent').count(),
        'paid': Invoice.query.filter_by(law_firm_id=current_user.law_firm_id, status='paid').count(),
        'overdue': Invoice.query.filter_by(law_firm_id=current_user.law_firm_id, status='sent').filter(Invoice.due_date < date.today()).count()
    }
    
    return render_template('invoices/list.html', 
                         invoices=invoices, 
                         status_filter=status_filter,
                         stats=stats)

@invoices_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'team_member'])
def create_invoice():
    """Create a new invoice"""
    if request.method == 'POST':
        try:
            # Get form data
            client_id = request.form.get('client_id')
            project_id = request.form.get('project_id') or None
            title = request.form.get('title')
            description = request.form.get('description', '')
            amount = Decimal(request.form.get('amount', '0'))
            invoice_type = request.form.get('invoice_type', 'service')
            billing_period = request.form.get('billing_period')
            due_days = int(request.form.get('due_days', 30))
            
            # Validate required fields
            if not all([client_id, title, amount]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('invoices.create_invoice'))
            
            # Validate client belongs to law firm
            client = User.query.filter_by(
                id=client_id, 
                law_firm_id=current_user.law_firm_id,
                role='client'
            ).first()
            
            if not client:
                flash('Invalid client selected.', 'error')
                return redirect(url_for('invoices.create_invoice'))
            
            # Create invoice
            invoice = Invoice()
            invoice.law_firm_id = current_user.law_firm_id
            invoice.client_id = client_id
            invoice.project_id = project_id
            invoice.created_by_id = current_user.id
            invoice.title = title
            invoice.description = description
            invoice.amount = amount
            invoice.invoice_type = invoice_type
            invoice.billing_period = billing_period
            invoice.issue_date = date.today()
            invoice.due_date = date.today() + timedelta(days=due_days)
            invoice.status = 'draft'
            
            # Generate invoice number
            invoice.generate_invoice_number()
            
            db.session.add(invoice)
            db.session.flush()
            
            # Add line items if provided
            line_items = request.form.getlist('line_description[]')
            quantities = request.form.getlist('line_quantity[]')
            rates = request.form.getlist('line_rate[]')
            
            for i, desc in enumerate(line_items):
                if desc.strip():
                    line_item = InvoiceLineItem()
                    line_item.invoice_id = invoice.id
                    line_item.description = desc
                    line_item.quantity = Decimal(quantities[i] if i < len(quantities) else '1')
                    line_item.rate = Decimal(rates[i] if i < len(rates) else '0')
                    line_item.amount = line_item.quantity * line_item.rate
                    db.session.add(line_item)
            
            db.session.commit()
            
            flash(f'Invoice {invoice.invoice_number} created successfully.', 'success')
            return redirect(url_for('invoices.view_invoice', id=invoice.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating invoice: {str(e)}', 'error')
            return redirect(url_for('invoices.create_invoice'))
    
    # GET request - show form
    clients = User.query.filter_by(
        law_firm_id=current_user.law_firm_id,
        role='client',
        active=True
    ).all()
    
    projects = Project.query.filter_by(
        law_firm_id=current_user.law_firm_id
    ).all()
    
    return render_template('invoices/create.html', clients=clients, projects=projects)

@invoices_bp.route('/<int:id>')
@login_required
def view_invoice(id):
    """View invoice details"""
    invoice = Invoice.query.filter_by(
        id=id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    # Check permissions
    if current_user.is_client() and invoice.client_id != current_user.id:
        flash('You do not have permission to view this invoice.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    return render_template('invoices/view.html', invoice=invoice)

@invoices_bp.route('/<int:id>/send', methods=['POST'])
@login_required
@role_required(['admin', 'team_member'])
def send_invoice(id):
    """Send invoice to client"""
    invoice = Invoice.query.filter_by(
        id=id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    if invoice.status != 'draft':
        flash('Only draft invoices can be sent.', 'error')
        return redirect(url_for('invoices.view_invoice', id=id))
    
    try:
        # Update status
        invoice.status = 'sent'
        
        # Create notification for client
        create_invoice_notification(
            invoice=invoice,
            notification_type='invoice_sent',
            recipient_type='client',
            message=f'New invoice {invoice.invoice_number} for {invoice.title} has been sent to you.'
        )
        
        # Schedule reminder notifications
        # 7 days before due date
        reminder_date = invoice.due_date - timedelta(days=7)
        if reminder_date > date.today():
            create_invoice_notification(
                invoice=invoice,
                notification_type='reminder',
                recipient_type='both',
                message=f'Reminder: Invoice {invoice.invoice_number} is due in 7 days.',
                scheduled_date=datetime.combine(reminder_date, datetime.min.time())
            )
        
        # On due date
        create_invoice_notification(
            invoice=invoice,
            notification_type='due_today',
            recipient_type='both',
            message=f'Invoice {invoice.invoice_number} is due today.',
            scheduled_date=datetime.combine(invoice.due_date, datetime.min.time())
        )
        
        # 3 days after due date (overdue)
        overdue_date = invoice.due_date + timedelta(days=3)
        create_invoice_notification(
            invoice=invoice,
            notification_type='overdue',
            recipient_type='both',
            message=f'Invoice {invoice.invoice_number} is now 3 days overdue.',
            scheduled_date=datetime.combine(overdue_date, datetime.min.time())
        )
        
        db.session.commit()
        
        flash(f'Invoice {invoice.invoice_number} sent successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error sending invoice: {str(e)}', 'error')
    
    return redirect(url_for('invoices.view_invoice', id=id))

@invoices_bp.route('/<int:id>/mark-paid', methods=['POST'])
@login_required
@role_required(['admin', 'team_member'])
def mark_paid(id):
    """Mark invoice as paid"""
    invoice = Invoice.query.filter_by(
        id=id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    if invoice.status not in ['sent', 'overdue']:
        flash('Only sent or overdue invoices can be marked as paid.', 'error')
        return redirect(url_for('invoices.view_invoice', id=id))
    
    try:
        # Get payment details from form
        payment_method = request.form.get('payment_method', 'bank_transfer')
        payment_reference = request.form.get('payment_reference', '')
        payment_date = request.form.get('payment_date')
        amount_paid = request.form.get('amount_paid')
        notes = request.form.get('notes', '')
        
        # Parse payment date
        if payment_date:
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
        else:
            payment_date = date.today()
        
        # Parse amount
        if amount_paid:
            amount_paid = Decimal(amount_paid)
        else:
            amount_paid = invoice.total_amount
        
        # Update invoice
        invoice.status = 'paid'
        invoice.paid_date = payment_date
        invoice.payment_method = payment_method
        invoice.payment_reference = payment_reference
        
        # Create payment record
        payment = PaymentRecord()
        payment.invoice_id = invoice.id
        payment.law_firm_id = current_user.law_firm_id
        payment.amount_paid = amount_paid
        payment.payment_date = payment_date
        payment.payment_method = payment_method
        payment.reference_number = payment_reference
        payment.notes = notes
        payment.recorded_by_id = current_user.id
        
        db.session.add(payment)
        
        # Create notification
        create_invoice_notification(
            invoice=invoice,
            notification_type='payment_received',
            recipient_type='both',
            message=f'Payment received for invoice {invoice.invoice_number}. Amount: ${amount_paid}'
        )
        
        db.session.commit()
        
        flash(f'Invoice {invoice.invoice_number} marked as paid.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error marking invoice as paid: {str(e)}', 'error')
    
    return redirect(url_for('invoices.view_invoice', id=id))

@invoices_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'team_member'])
def edit_invoice(id):
    """Edit invoice (only drafts can be edited)"""
    invoice = Invoice.query.filter_by(
        id=id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    if invoice.status != 'draft':
        flash('Only draft invoices can be edited.', 'error')
        return redirect(url_for('invoices.view_invoice', id=id))
    
    if request.method == 'POST':
        try:
            # Update invoice details
            invoice.title = request.form.get('title')
            invoice.description = request.form.get('description', '')
            invoice.amount = Decimal(request.form.get('amount', '0'))
            invoice.invoice_type = request.form.get('invoice_type', 'service')
            invoice.billing_period = request.form.get('billing_period')
            
            # Update due date if changed
            due_days = int(request.form.get('due_days', 30))
            invoice.due_date = invoice.issue_date + timedelta(days=due_days)
            
            db.session.commit()
            
            flash(f'Invoice {invoice.invoice_number} updated successfully.', 'success')
            return redirect(url_for('invoices.view_invoice', id=id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating invoice: {str(e)}', 'error')
    
    # GET request - show form
    clients = User.query.filter_by(
        law_firm_id=current_user.law_firm_id,
        role='client',
        active=True
    ).all()
    
    projects = Project.query.filter_by(
        law_firm_id=current_user.law_firm_id
    ).all()
    
    return render_template('invoices/edit.html', invoice=invoice, clients=clients, projects=projects)

@invoices_bp.route('/notifications')
@login_required
def notifications():
    """View invoice notifications"""
    page = request.args.get('page', 1, type=int)
    
    # Get notifications for current user's law firm
    query = InvoiceNotification.query.join(Invoice).filter(
        Invoice.law_firm_id == current_user.law_firm_id
    )
    
    # Role-based filtering
    if current_user.is_client():
        query = query.filter(
            or_(
                InvoiceNotification.recipient_type == 'client',
                InvoiceNotification.recipient_type == 'both'
            ),
            Invoice.client_id == current_user.id
        )
    else:
        query = query.filter(
            or_(
                InvoiceNotification.recipient_type == 'law_firm',
                InvoiceNotification.recipient_type == 'both'
            )
        )
    
    notifications = query.order_by(InvoiceNotification.scheduled_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('invoices/notifications.html', notifications=notifications)

@invoices_bp.route('/dashboard')
@login_required
def dashboard():
    """Invoice dashboard with key metrics"""
    # Get dashboard data based on user role
    if current_user.is_client():
        # Client dashboard
        total_invoices = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id,
            client_id=current_user.id
        ).count()
        
        outstanding_amount = db.session.query(
            db.func.sum(Invoice.amount)
        ).filter_by(
            law_firm_id=current_user.law_firm_id,
            client_id=current_user.id,
            status='sent'
        ).scalar() or 0
        
        overdue_count = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id,
            client_id=current_user.id,
            status='sent'
        ).filter(Invoice.due_date < date.today()).count()
        
        recent_invoices = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id,
            client_id=current_user.id
        ).order_by(Invoice.created_at.desc()).limit(5).all()
        
    else:
        # Law firm dashboard
        total_invoices = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id
        ).count()
        
        outstanding_amount = db.session.query(
            db.func.sum(Invoice.amount)
        ).filter_by(
            law_firm_id=current_user.law_firm_id,
            status='sent'
        ).scalar() or 0
        
        overdue_count = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id,
            status='sent'
        ).filter(Invoice.due_date < date.today()).count()
        
        recent_invoices = Invoice.query.filter_by(
            law_firm_id=current_user.law_firm_id
        ).order_by(Invoice.created_at.desc()).limit(5).all()
    
    return render_template('invoices/dashboard.html',
                         total_invoices=total_invoices,
                         outstanding_amount=outstanding_amount,
                         overdue_count=overdue_count,
                         recent_invoices=recent_invoices)