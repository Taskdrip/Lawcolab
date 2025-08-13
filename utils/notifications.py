"""
Invoice notification utilities for LawFirmOS
Handles automatic reminders, due date notifications, and payment confirmations
"""

from datetime import datetime, timedelta
from app import db
from models import InvoiceNotification

def create_invoice_notification(invoice, notification_type, recipient_type, message, scheduled_date=None):
    """
    Create a new invoice notification
    
    Args:
        invoice: Invoice object
        notification_type: Type of notification (reminder, overdue, renewal, payment_received, etc.)
        recipient_type: Who receives it (client, law_firm, both)
        message: Notification message
        scheduled_date: When to send (defaults to now)
    """
    if scheduled_date is None:
        scheduled_date = datetime.now()
    
    notification = InvoiceNotification()
    notification.invoice_id = invoice.id
    notification.notification_type = notification_type
    notification.recipient_type = recipient_type
    notification.message = message
    notification.scheduled_date = scheduled_date
    notification.status = 'pending' if scheduled_date > datetime.now() else 'sent'
    notification.is_automatic = True
    
    # If sending immediately, mark as sent
    if scheduled_date <= datetime.now():
        notification.sent_date = datetime.now()
        notification.status = 'sent'
    
    db.session.add(notification)
    return notification

def send_invoice_reminder(invoice):
    """
    Send reminder notification for an invoice
    Used by background tasks to process scheduled reminders
    """
    try:
        # Mark invoice reminder as sent
        invoice.reminder_sent = True
        
        # Create immediate notification
        create_invoice_notification(
            invoice=invoice,
            notification_type='reminder_sent',
            recipient_type='both',
            message=f'Reminder sent for invoice {invoice.invoice_number}. Due date: {invoice.due_date}',
            scheduled_date=datetime.now()
        )
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sending reminder for invoice {invoice.id}: {str(e)}")
        return False

def process_overdue_invoices():
    """
    Process overdue invoices and send notifications
    This function should be called by a background task/cron job
    """
    from models import Invoice
    from datetime import date
    
    # Find overdue invoices that haven't been marked as overdue yet
    overdue_invoices = Invoice.query.filter(
        Invoice.status == 'sent',
        Invoice.due_date < date.today()
    ).all()
    
    for invoice in overdue_invoices:
        try:
            # Update invoice status
            invoice.status = 'overdue'
            
            # Send overdue notification
            days_overdue = (date.today() - invoice.due_date).days
            create_invoice_notification(
                invoice=invoice,
                notification_type='overdue',
                recipient_type='both',
                message=f'Invoice {invoice.invoice_number} is now {days_overdue} days overdue. Amount: ${invoice.total_amount}',
                scheduled_date=datetime.now()
            )
            
            invoice.overdue_notifications_sent += 1
            
        except Exception as e:
            print(f"Error processing overdue invoice {invoice.id}: {str(e)}")
            continue
    
    db.session.commit()

def schedule_renewal_reminders(invoice):
    """
    Schedule renewal reminders for retainer/subscription invoices
    """
    if invoice.invoice_type not in ['retainer', 'renewal']:
        return
    
    if not invoice.billing_period:
        return
    
    # Calculate next renewal date based on billing period
    next_renewal_date = None
    if invoice.billing_period == 'monthly':
        next_renewal_date = invoice.due_date + timedelta(days=30)
    elif invoice.billing_period == 'quarterly':
        next_renewal_date = invoice.due_date + timedelta(days=90)
    elif invoice.billing_period == 'yearly':
        next_renewal_date = invoice.due_date + timedelta(days=365)
    
    if next_renewal_date:
        # Schedule renewal reminder 30 days before
        reminder_date = next_renewal_date - timedelta(days=30)
        if reminder_date > datetime.now().date():
            create_invoice_notification(
                invoice=invoice,
                notification_type='renewal_reminder',
                recipient_type='both',
                message=f'Your {invoice.billing_period} service for {invoice.title} will renew on {next_renewal_date}. Amount: ${invoice.total_amount}',
                scheduled_date=datetime.combine(reminder_date, datetime.min.time())
            )

def get_user_notifications(user, limit=10):
    """
    Get recent notifications for a user
    """
    from models import Invoice
    from sqlalchemy import or_
    
    # Get notifications based on user role
    query = InvoiceNotification.query.join(Invoice).filter(
        Invoice.law_firm_id == user.law_firm_id
    )
    
    if user.is_client():
        # Client sees notifications for their invoices
        query = query.filter(
            or_(
                InvoiceNotification.recipient_type == 'client',
                InvoiceNotification.recipient_type == 'both'
            ),
            Invoice.client_id == user.id
        )
    else:
        # Law firm users see all notifications
        query = query.filter(
            or_(
                InvoiceNotification.recipient_type == 'law_firm',
                InvoiceNotification.recipient_type == 'both'
            )
        )
    
    return query.filter(
        InvoiceNotification.status == 'sent'
    ).order_by(
        InvoiceNotification.sent_date.desc()
    ).limit(limit).all()

def mark_notification_as_read(notification_id, user):
    """
    Mark a notification as read (future feature)
    """
    # This can be implemented later with a read status table
    pass

def get_pending_notifications():
    """
    Get all pending notifications that should be sent
    Used by background tasks
    """
    return InvoiceNotification.query.filter(
        InvoiceNotification.status == 'pending',
        InvoiceNotification.scheduled_date <= datetime.now()
    ).all()

def send_pending_notifications():
    """
    Process and send all pending notifications
    Should be called by a background task every few minutes
    """
    pending = get_pending_notifications()
    
    for notification in pending:
        try:
            # Mark as sent
            notification.status = 'sent'
            notification.sent_date = datetime.now()
            
            # Here you could integrate with email service, SMS, etc.
            # For now, we just mark as sent in the database
            
        except Exception as e:
            notification.status = 'failed'
            print(f"Failed to send notification {notification.id}: {str(e)}")
    
    db.session.commit()