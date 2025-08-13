from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import and_, or_, func, extract
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.colors import HexColor, black, blue
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
import io

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

@invoices_bp.route('/analytics')
@login_required
@role_required(['admin', 'team_member'])
def analytics_dashboard():
    """Invoice dashboard with analytics"""
    # Currency breakdown for paid invoices
    currency_stats = db.session.query(
        Invoice.currency,
        func.count(Invoice.id).label('count'),
        func.sum(Invoice.total_amount).label('total')
    ).filter(
        Invoice.law_firm_id == current_user.law_firm_id,
        Invoice.status == 'paid'
    ).group_by(Invoice.currency).all()
    
    # Monthly payment analytics (last 12 months)
    current_date = datetime.now()
    monthly_stats = []
    for i in range(12):
        target_date = current_date - timedelta(days=30*i)
        month_start = target_date.replace(day=1)
        if i == 0:
            month_end = current_date
        else:
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        payments = db.session.query(
            func.count(PaymentRecord.id).label('count'),
            func.sum(PaymentRecord.amount_paid).label('total')
        ).join(Invoice).filter(
            Invoice.law_firm_id == current_user.law_firm_id,
            PaymentRecord.payment_date >= month_start,
            PaymentRecord.payment_date <= month_end
        ).first()
        
        monthly_stats.append({
            'month': target_date.strftime('%B %Y'),
            'count': payments.count if payments and payments.count else 0,
            'total': float(payments.total) if payments and payments.total else 0.0
        })
    
    monthly_stats.reverse()  # Show oldest to newest
    
    # Client payment breakdown
    client_stats = db.session.query(
        User.first_name,
        User.last_name,
        func.count(Invoice.id).label('invoice_count'),
        func.sum(Invoice.total_amount).label('total_billed'),
        func.sum(PaymentRecord.amount_paid).label('total_paid')
    ).outerjoin(PaymentRecord, Invoice.id == PaymentRecord.invoice_id)\
     .filter(
        Invoice.law_firm_id == current_user.law_firm_id,
        User.role == 'client'
    ).group_by(User.id, User.first_name, User.last_name).all()
    
    # Recent payments
    recent_payments = db.session.query(PaymentRecord, Invoice, User)\
        .join(Invoice, PaymentRecord.invoice_id == Invoice.id)\
        .join(User, Invoice.client_id == User.id)\
        .filter(Invoice.law_firm_id == current_user.law_firm_id)\
        .order_by(PaymentRecord.payment_date.desc())\
        .limit(10).all()
    
    return render_template('invoices/dashboard.html',
                         currency_stats=currency_stats,
                         monthly_stats=monthly_stats,
                         client_stats=client_stats,
                         recent_payments=recent_payments)

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
            currency = request.form.get('currency', 'USD')
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
            invoice.currency = currency
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
            
            # Determine action
            action = request.form.get('action', 'save_draft')
            if action == 'create_and_send':
                return redirect(url_for('invoices.send_invoice', id=invoice.id))
            else:
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

@invoices_bp.route('/api/client-projects/<client_id>')
@login_required
@role_required(['admin', 'team_member'])
def get_client_projects(client_id):
    """API endpoint to get projects for a specific client"""
    from models import ProjectAssignment
    
    try:
        # Get projects where the client is assigned, joining with projects to filter by law firm
        project_assignments = db.session.query(ProjectAssignment).join(
            Project, ProjectAssignment.project_id == Project.id
        ).filter(
            ProjectAssignment.user_id == client_id,
            Project.law_firm_id == current_user.law_firm_id
        ).all()
        
        # Format projects for JSON response
        project_data = []
        for assignment in project_assignments:
            if assignment.project:
                project_data.append({
                    'id': assignment.project.id,
                    'name': assignment.project.title,  # Use 'title' instead of 'name'
                    'status': assignment.project.status
                })
        
        return jsonify({
            'success': True,
            'projects': project_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'projects': []
        })

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

@invoices_bp.route('/<int:id>/pdf')
@login_required
def download_invoice_pdf(id):
    """Download invoice as PDF"""
    invoice = Invoice.query.get_or_404(id)
    
    # Security check
    if current_user.is_client() and invoice.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    if not current_user.is_client() and invoice.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    # Get law firm details
    law_firm = LawFirm.query.get(invoice.law_firm_id)
    client = User.query.get(invoice.client_id)
    
    if not law_firm or not client:
        flash('Invoice data not complete.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    # Generate PDF using ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        spaceAfter=30,
        textColor=HexColor('#667eea')
    )
    
    # Law firm header
    story.append(Paragraph(f"<b>{law_firm.name if law_firm and law_firm.name else 'Law Firm'}</b>", title_style))
    if law_firm and law_firm.address:
        story.append(Paragraph(law_firm.address, styles['Normal']))
    if law_firm and law_firm.phone:
        story.append(Paragraph(f"Phone: {law_firm.phone}", styles['Normal']))
    if law_firm and law_firm.email:
        story.append(Paragraph(f"Email: {law_firm.email}", styles['Normal']))
    
    story.append(Spacer(1, 30))
    
    # Invoice details
    story.append(Paragraph(f"<b>INVOICE #{invoice.invoice_number}</b>", styles['Heading2']))
    story.append(Paragraph(f"Date: {invoice.created_at.strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Paragraph(f"Due Date: {invoice.due_date.strftime('%B %d, %Y')}", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # Client details
    story.append(Paragraph("<b>Bill To:</b>", styles['Heading3']))
    client_name = f"{client.first_name if client and client.first_name else ''} {client.last_name if client and client.last_name else ''}".strip()
    story.append(Paragraph(client_name or "Client", styles['Normal']))
    if client and client.email:
        story.append(Paragraph(client.email, styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # Invoice items table
    data = [['Description', 'Quantity', 'Rate', 'Amount']]
    for item in invoice.line_items:
        currency_symbol = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': '$', 'NGN': '₦'}.get(invoice.currency, '$')
        data.append([
            item.description,
            f"{item.quantity:.2f}",
            f"{currency_symbol}{item.rate:.2f}",
            f"{currency_symbol}{item.amount:.2f}"
        ])
    
    # Add total row
    currency_symbol = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': '$', 'NGN': '₦'}.get(invoice.currency, '$')
    data.append(['', '', 'Total:', f"{currency_symbol}{invoice.total_amount:.2f}"])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#f8f9fc')),
        ('GRID', (0, 0), (-1, -1), 1, black)
    ]))
    
    story.append(table)
    story.append(Spacer(1, 30))
    
    # Footer
    story.append(Paragraph("<i>Generated by Taskdrip for legal professionals worldwide</i>", styles['Normal']))
    
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Invoice-{invoice.invoice_number}.pdf'
    
    return response

@invoices_bp.route('/payment/<int:payment_id>/pdf')
@login_required
def download_payment_pdf(payment_id):
    """Download payment receipt as PDF"""
    payment = PaymentRecord.query.get_or_404(payment_id)
    invoice = Invoice.query.get(payment.invoice_id)
    
    # Security check
    if current_user.is_client() and invoice.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    if not current_user.is_client() and invoice.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('invoices.list_invoices'))
    
    # Get law firm details
    law_firm = LawFirm.query.get(invoice.law_firm_id)
    client = User.query.get(invoice.client_id)
    
    # Generate PDF using ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        spaceAfter=30,
        textColor=HexColor('#28a745')
    )
    
    # Law firm header
    story.append(Paragraph(f"<b>{law_firm.name}</b>", title_style))
    if law_firm.address:
        story.append(Paragraph(law_firm.address, styles['Normal']))
    
    story.append(Spacer(1, 30))
    
    # Payment receipt details
    story.append(Paragraph("<b>PAYMENT RECEIPT</b>", styles['Heading2']))
    story.append(Paragraph(f"Receipt Date: {payment.payment_date.strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Paragraph(f"Invoice: #{invoice.invoice_number}", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # Client details
    story.append(Paragraph("<b>Received From:</b>", styles['Heading3']))
    story.append(Paragraph(f"{client.first_name} {client.last_name}", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # Payment details
    currency_symbol = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': '$', 'NGN': '₦'}.get(invoice.currency, '$')
    payment_data = [
        ['Payment Amount:', f"{currency_symbol}{payment.amount_paid:.2f}"],
        ['Payment Method:', payment.payment_method or 'Not specified'],
        ['Reference:', payment.payment_reference or 'N/A']
    ]
    
    payment_table = Table(payment_data)
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f8f9fc')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, black)
    ]))
    
    story.append(payment_table)
    story.append(Spacer(1, 30))
    
    # Footer
    story.append(Paragraph("<i>Payment receipt generated by Taskdrip</i>", styles['Normal']))
    
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Payment-Receipt-{invoice.invoice_number}.pdf'
    
    return response

@invoices_bp.route('/<int:id>/send', methods=['GET', 'POST'])
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
        invoice.sent_date = datetime.now()
        
        # Skip notification creation for now to avoid database errors
        # Will implement proper notification system later
        pass
        
        db.session.commit()
        
        flash(f'Invoice {invoice.invoice_number} sent successfully to {invoice.client.display_name}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error sending invoice: {str(e)}', 'error')
    
    return redirect(url_for('invoices.view_invoice', id=id))

@invoices_bp.route('/update-bank-details', methods=['POST'])
@login_required
@role_required(['admin', 'team_member'])
def update_bank_details():
    """Update law firm bank details"""
    try:
        law_firm = current_user.law_firm
        if not law_firm:
            return jsonify({'success': False, 'error': 'No law firm associated with user.'})
        
        # Update bank details
        law_firm.bank_name = request.form.get('bank_name', '').strip()
        law_firm.account_holder_name = request.form.get('account_holder_name', '').strip()
        law_firm.account_number = request.form.get('account_number', '').strip()
        law_firm.routing_number = request.form.get('routing_number', '').strip()
        law_firm.swift_code = request.form.get('swift_code', '').strip()
        law_firm.tax_id = request.form.get('tax_id', '').strip()
        
        # Validate required fields
        if not all([law_firm.bank_name, law_firm.account_holder_name, law_firm.account_number]):
            return jsonify({'success': False, 'error': 'Bank name, account holder name, and account number are required.'})
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Bank details updated successfully.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@invoices_bp.route('/<int:id>/mark-paid', methods=['POST'])
@login_required
def mark_paid(id):
    """Mark invoice as paid - available to law firm staff and clients"""
    # Get invoice with proper access control
    if current_user.is_client():
        # Clients can only mark their own invoices as paid
        invoice = Invoice.query.filter_by(
            id=id,
            client_id=current_user.id,
            law_firm_id=current_user.law_firm_id
        ).first_or_404()
    else:
        # Law firm staff can mark any invoice from their firm as paid
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
        
        # Create notification (simplified for now to avoid errors)
        try:
            create_invoice_notification(
                invoice=invoice,
                notification_type='payment_received',
                recipient_type='both',
                message=f'Payment received for invoice {invoice.invoice_number}. Amount: ${amount_paid}'
            )
        except Exception as notif_error:
            # Continue even if notification fails
            print(f"Notification error: {notif_error}")
        
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

@invoices_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required(['admin', 'team_member'])
def delete_invoice(id):
    """Delete an invoice (only drafts can be deleted)"""
    invoice = Invoice.query.filter_by(
        id=id,
        law_firm_id=current_user.law_firm_id
    ).first_or_404()
    
    if invoice.status != 'draft':
        flash('Only draft invoices can be deleted.', 'error')
        return redirect(url_for('invoices.view_invoice', id=id))
    
    try:
        invoice_number = invoice.invoice_number
        
        # Delete related line items (cascade should handle this, but being explicit)
        for line_item in invoice.line_items:
            db.session.delete(line_item)
        
        # Delete the invoice
        db.session.delete(invoice)
        db.session.commit()
        
        flash(f'Invoice {invoice_number} deleted successfully.', 'success')
        return redirect(url_for('invoices.list_invoices'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting invoice: {str(e)}', 'error')
        return redirect(url_for('invoices.view_invoice', id=id))

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