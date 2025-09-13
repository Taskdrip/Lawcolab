from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from app import db
from models import SalesLead, PopupSettings, CustomerReview, User, ROLE_SUPER_ADMIN, PaymentMethod, PopupSuppression
from utils.decorators import role_required
from datetime import datetime
from sqlalchemy import desc
import re
import time
import os
from werkzeug.utils import secure_filename

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/popup')
def popup_page():
    """Display the fullscreen popup sales page"""
    from models import PopupSettings, CustomerReview
    from sqlalchemy import desc
    
    # Get popup settings
    settings = PopupSettings.query.first()
    if not settings:
        # Create default settings
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    # Get featured reviews
    reviews = CustomerReview.query.filter_by(is_active=True).order_by(desc(CustomerReview.is_featured), CustomerReview.id).limit(20).all()
    
    return render_template('sales/working_popup.html', settings=settings, reviews=reviews)

@sales_bp.route('/popup-content')
def popup_content():
    """Returns just the popup content for dynamic loading"""
    from models import PopupSettings, CustomerReview
    from sqlalchemy import desc
    
    # Get popup settings
    settings = PopupSettings.query.first()
    if not settings:
        # Create default settings
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    # Get featured reviews
    reviews = CustomerReview.query.filter_by(is_active=True).order_by(desc(CustomerReview.is_featured), CustomerReview.id).limit(20).all()
    
    return render_template('sales/popup_content_only.html', settings=settings, reviews=reviews)

@sales_bp.route('/submit-lead', methods=['POST'])
def submit_lead():
    """Handle lead form submission"""
    try:
        # Validate CSRF token
        validate_csrf(request.form.get('csrf_token'))
        # Extract form data
        lead_data = {
            'name': request.form.get('name', '').strip(),
            'firm_name': request.form.get('firm', '').strip(),
            'email': request.form.get('email', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'country': request.form.get('country', '').strip(),
            'address': request.form.get('address', '').strip(),
            'team_size': request.form.get('team_size', '').strip(),
            'plan': request.form.get('plan', '').strip(),
            'payment_method': request.form.get('payment', '').strip()
        }
        
        # Validate required fields
        required_fields = ['name', 'firm_name', 'email', 'plan']
        for field in required_fields:
            if not lead_data[field]:
                flash(f'{field.replace("_", " ").title()} is required', 'error')
                return redirect(url_for('sales.popup_page'))
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, lead_data['email']):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('sales.popup_page'))
        
        # Create new lead
        new_lead = SalesLead()
        for key, value in lead_data.items():
            setattr(new_lead, key, value)
        
        # Add UTM tracking if available
        new_lead.utm_source = session.get('utm_source')
        new_lead.utm_medium = session.get('utm_medium')
        new_lead.utm_campaign = session.get('utm_campaign')
        
        db.session.add(new_lead)
        db.session.commit()
        
        # Store lead data in session for checkout
        session['lead_data'] = lead_data
        session['lead_id'] = new_lead.id
        session['selected_plan'] = lead_data['plan'].lower()  # Fix session management with normalization
        
        flash('Thank you! Your pre-order has been submitted successfully.', 'success')
        return redirect(url_for('sales.checkout_page'))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('sales.popup_page'))

@sales_bp.route('/checkout')
def checkout_page():
    """Checkout page with payment options"""
    # Get plan parameter from URL
    plan = request.args.get('plan', '').lower()
    valid_plans = ['trial', 'starter', 'growth', 'enterprise', 'founder', 'lifetime']
    
    # Validate plan parameter
    if plan and plan not in valid_plans:
        flash('Invalid plan selected. Please try again.', 'error')
        return redirect(url_for('sales.popup_page'))
    
    # Store plan in session if provided
    if plan:
        session['selected_plan'] = plan
    
    # Check if we have a plan either from URL or session
    selected_plan = session.get('selected_plan')
    if not selected_plan:
        flash('Please select a plan first.', 'warning')
        return redirect(url_for('sales.popup_page'))
    
    # Validate session plan against valid plans
    if selected_plan not in valid_plans:
        flash('Invalid plan selected. Please try again.', 'error')
        return redirect(url_for('sales.popup_page'))
    
    lead_data = session.get('lead_data')
    if not lead_data:
        flash('Please complete the registration form first.', 'warning')
        return redirect(url_for('sales.popup_page'))
    
    # Get active payment gateways from super admin settings
    from models_payment import PaymentGateway
    payment_gateways = PaymentGateway.query.filter_by(is_active=True).order_by(PaymentGateway.name).all()
    
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
    
    return render_template('sales/checkout_dynamic.html', 
                         lead_data=lead_data, 
                         selected_plan=selected_plan,
                         payment_gateways=payment_gateways,
                         settings=settings)

@sales_bp.route('/checkout/complete', methods=['POST'])
def complete_checkout():
    """Complete the checkout process - redirect to payment evidence upload or congratulations"""
    try:
        # Validate CSRF token
        validate_csrf(request.form.get('csrf_token'))
        
        lead_data = session.get('lead_data')
        if not lead_data:
            flash('Session expired. Please start over.', 'error')
            return redirect(url_for('sales.popup_page'))
        
        payment_method = request.form.get('payment_method')
        if not payment_method:
            flash('Please select a payment method.', 'error')
            return redirect(url_for('sales.checkout_page'))
        
        # Update lead with payment method choice and selected plan
        lead_id = session.get('lead_id')
        selected_plan = session.get('selected_plan')
        if lead_id:
            lead = SalesLead.query.get(lead_id)
            if lead:
                lead.payment_method = payment_method
                if selected_plan:
                    lead.plan = selected_plan
                lead.status = 'payment_pending'
                db.session.commit()
        
        # Generate payment reference and store details
        import time
        payment_reference = f"LAWCOLAB-{selected_plan.upper()}-{int(time.time())}"
        session['payment_method'] = payment_method
        session['payment_reference'] = payment_reference
        session['payment_start_time'] = int(time.time())
        session['payment_amount'] = get_plan_amount(selected_plan)
        
        # For crypto payments, redirect to evidence upload
        if payment_method != 'bank_transfer':
            return redirect(url_for('sales.payment_evidence'))
        else:
            # For bank transfers, redirect to congratulations
            flash('Payment instructions sent! Please complete your bank transfer and await verification.', 'success')
            return redirect(url_for('sales.congratulations'))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred processing your request. Please try again.', 'error')
        return redirect(url_for('sales.checkout_page'))

def get_plan_amount(plan):
    """Get the amount for a given plan"""
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
    
    if plan == 'starter':
        return settings.starter_price
    elif plan == 'growth':
        return settings.growth_price
    elif plan == 'enterprise':
        return settings.enterprise_price
    elif plan == 'founders' or plan == 'founder':
        return settings.founders_price or 1745
    else:
        return 0

@sales_bp.route('/payment-evidence')
def payment_evidence():
    """Show payment evidence upload page with countdown timer"""
    payment_method = session.get('payment_method')
    if not payment_method or payment_method == 'bank_transfer':
        flash('Invalid payment method for evidence upload.', 'error')
        return redirect(url_for('sales.checkout_page'))
    
    # Calculate time remaining (30 minutes from start)
    payment_start_time = session.get('payment_start_time', int(time.time()))
    current_time = int(time.time())
    elapsed_seconds = current_time - payment_start_time
    time_remaining_seconds = max(0, 1800 - elapsed_seconds)  # 30 minutes = 1800 seconds
    
    if time_remaining_seconds <= 0:
        flash('Payment window has expired. Please start a new payment process.', 'error')
        return redirect(url_for('sales.popup_page'))
    
    lead_data = session.get('lead_data')
    selected_plan = session.get('selected_plan')
    payment_reference = session.get('payment_reference')
    payment_amount = session.get('payment_amount')
    
    # Get payment gateway info
    from models_payment import PaymentGateway
    gateway = PaymentGateway.query.filter_by(name=payment_method, is_active=True).first()
    payment_method_name = gateway.display_name if gateway else 'Crypto Payment'
    
    minutes = time_remaining_seconds // 60
    seconds = time_remaining_seconds % 60
    time_remaining_display = f"{minutes:02d}:{seconds:02d}"
    
    return render_template('sales/payment_evidence.html',
                         lead_data=lead_data,
                         plan_name=selected_plan.title() if selected_plan else 'Plan',
                         payment_method_name=payment_method_name,
                         payment_reference=payment_reference,
                         amount=payment_amount,
                         time_remaining=time_remaining_display,
                         time_remaining_seconds=time_remaining_seconds)

@sales_bp.route('/submit-payment-evidence', methods=['POST'])
def submit_payment_evidence():
    """Handle payment evidence submission"""
    try:
        # Validate CSRF token
        validate_csrf(request.form.get('csrf_token'))
        
        # Check if payment window is still valid
        payment_start_time = session.get('payment_start_time')
        if not payment_start_time:
            flash('Payment session expired. Please start a new payment process.', 'error')
            return redirect(url_for('sales.popup_page'))
        
        elapsed_seconds = int(time.time()) - payment_start_time
        if elapsed_seconds > 1800:  # 30 minutes
            flash('Payment window has expired. Please start a new payment process.', 'error')
            return redirect(url_for('sales.popup_page'))
        
        # Get form data
        transaction_hash = request.form.get('transaction_hash', '').strip()
        additional_notes = request.form.get('additional_notes', '').strip()
        payment_reference = request.form.get('payment_reference')
        
        if not transaction_hash:
            flash('Transaction hash is required.', 'error')
            return redirect(url_for('sales.payment_evidence'))
        
        # Handle file upload
        receipt_file = request.files.get('receipt_file')
        if not receipt_file or not receipt_file.filename:
            flash('Payment receipt file is required.', 'error')
            return redirect(url_for('sales.payment_evidence'))
        
        # Validate file
        allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
        file_extension = receipt_file.filename.rsplit('.', 1)[1].lower() if '.' in receipt_file.filename else ''
        
        if file_extension not in allowed_extensions:
            flash('Invalid file type. Please upload PNG, JPG, or PDF files only.', 'error')
            return redirect(url_for('sales.payment_evidence'))
        
        # Check file size (10MB limit)
        receipt_file.seek(0, 2)  # Seek to end
        file_size = receipt_file.tell()
        receipt_file.seek(0)  # Reset to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            flash('File size too large. Please upload files smaller than 10MB.', 'error')
            return redirect(url_for('sales.payment_evidence'))
        
        # Save file
        upload_folder = 'uploads/payment_evidence'
        os.makedirs(upload_folder, exist_ok=True)
        
        filename = secure_filename(f"{payment_reference}_{receipt_file.filename}")
        file_path = os.path.join(upload_folder, filename)
        receipt_file.save(file_path)
        
        # Update lead record with evidence
        lead_id = session.get('lead_id')
        if lead_id:
            lead = SalesLead.query.get(lead_id)
            if lead:
                lead.status = 'payment_evidence_submitted'
                # Store evidence details in a note or separate field
                evidence_note = f"Transaction Hash: {transaction_hash}\nFile: {filename}"
                if additional_notes:
                    evidence_note += f"\nNotes: {additional_notes}"
                lead.notes = evidence_note
                db.session.commit()
        
        # Clear payment session data
        session.pop('payment_start_time', None)
        
        flash('Payment evidence submitted successfully! We will verify your payment within 1-24 hours.', 'success')
        return redirect(url_for('sales.congratulations'))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred submitting your payment evidence. Please try again.', 'error')
        return redirect(url_for('sales.payment_evidence'))

@sales_bp.route('/congratulations')
def congratulations():
    """Show congratulations page after successful payment submission"""
    lead_data = session.get('lead_data')
    if not lead_data:
        flash('Session expired. Please start over.', 'error')
        return redirect(url_for('sales.popup_page'))
    
    selected_plan = session.get('selected_plan')
    payment_amount = session.get('payment_amount')
    payment_reference = session.get('payment_reference')
    
    return render_template('sales/congratulations.html',
                         customer_name=lead_data.get('name'),
                         customer_email=lead_data.get('email'),
                         plan_name=selected_plan.title() if selected_plan else 'Plan',
                         amount=payment_amount,
                         payment_reference=payment_reference)

@sales_bp.route('/thankyou')
def thankyou():
    """Thank you page with video"""
    settings = PopupSettings.query.first()
    lead_id = session.get('lead_id')
    
    # Clear the lead ID from session
    if lead_id:
        session.pop('lead_id', None)
    
    return render_template('sales/thankyou.html', settings=settings, lead_id=lead_id)

@sales_bp.route('/admin')
@login_required
@role_required([ROLE_SUPER_ADMIN])
def admin_dashboard():
    """Admin dashboard for managing leads and popup settings"""
    # Get leads with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    leads = SalesLead.query.order_by(desc(SalesLead.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get analytics
    total_leads = SalesLead.query.count()
    new_leads = SalesLead.query.filter_by(status='new').count()
    converted_leads = SalesLead.query.filter_by(status='converted').count()
    
    # Plan breakdown
    from sqlalchemy import func
    plan_stats = db.session.query(
        SalesLead.plan, 
        func.count(SalesLead.id).label('count')
    ).group_by(SalesLead.plan).all()
    
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    return render_template('sales/admin.html', 
                         leads=leads, 
                         total_leads=total_leads,
                         new_leads=new_leads,
                         converted_leads=converted_leads,
                         plan_stats=plan_stats,
                         settings=settings)

@sales_bp.route('/admin/settings', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def update_settings():
    """Update popup settings"""
    try:
        settings = PopupSettings.query.first()
        if not settings:
            settings = PopupSettings()
            db.session.add(settings)
        
        # Update settings
        settings.popup_delay_seconds = int(request.form.get('popup_delay_seconds', 15))
        settings.popup_enabled = request.form.get('popup_enabled') == 'on'
        settings.welcome_video_url = request.form.get('welcome_video_url', '').strip()
        settings.thankyou_video_url = request.form.get('thankyou_video_url', '').strip()
        
        # Update 5-plan pricing structure
        settings.trial_duration_days = int(request.form.get('trial_duration_days', 3))
        settings.starter_price = float(request.form.get('starter_price', 39.00))
        settings.growth_price = float(request.form.get('growth_price', 90.00))
        settings.enterprise_price = float(request.form.get('enterprise_price', 350.00))
        settings.founders_price = float(request.form.get('founders_price', 750.00))
        settings.lifetime_price = float(request.form.get('lifetime_price', 999.00))
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error updating settings. Please try again.', 'error')
    
    return redirect(url_for('sales.admin_dashboard'))

@sales_bp.route('/admin/lead/<int:lead_id>/status', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def update_lead_status():
    """Update lead status"""
    try:
        if not request.json:
            return jsonify({'success': False, 'message': 'No JSON data provided'}), 400
        
        lead_id = request.json.get('lead_id')
        new_status = request.json.get('status')
        
        lead = SalesLead.query.get_or_404(lead_id)
        lead.status = new_status
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Status updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating status'}), 500

@sales_bp.route('/admin/reviews')
@login_required
@role_required([ROLE_SUPER_ADMIN])
def manage_reviews():
    """Manage customer reviews"""
    reviews = CustomerReview.query.order_by(desc(CustomerReview.is_featured), CustomerReview.id).all()
    return render_template('sales/reviews.html', reviews=reviews)

@sales_bp.route('/admin/reviews', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def add_review():
    """Add a new customer review"""
    try:
        review = CustomerReview()
        review.name = request.form.get('name', '').strip()
        review.firm_name = request.form.get('firm_name', '').strip()
        review.review_text = request.form.get('review_text', '').strip()
        review.rating = int(request.form.get('rating', 5))
        review.location = request.form.get('location', '').strip()
        review.is_featured = request.form.get('is_featured') == 'on'
        
        db.session.add(review)
        db.session.commit()
        flash('Review added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error adding review. Please try again.', 'error')
    
    return redirect(url_for('sales.manage_reviews'))

@sales_bp.route('/admin/reviews/<int:review_id>', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def update_review(review_id):
    """Update an existing customer review"""
    try:
        review = CustomerReview.query.get_or_404(review_id)
        
        review.name = request.form.get('name', '').strip()
        review.firm_name = request.form.get('firm_name', '').strip()
        review.review_text = request.form.get('review_text', '').strip()
        review.rating = int(request.form.get('rating', 5))
        review.location = request.form.get('location', '').strip()
        review.is_featured = request.form.get('is_featured') == 'on'
        review.is_active = request.form.get('is_active') == 'on'
        
        db.session.commit()
        flash('Review updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error updating review. Please try again.', 'error')
    
    return redirect(url_for('sales.manage_reviews'))

@sales_bp.route('/admin/reviews/<int:review_id>/delete', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def delete_review(review_id):
    """Delete a customer review"""
    try:
        review = CustomerReview.query.get_or_404(review_id)
        db.session.delete(review)
        db.session.commit()
        flash('Review deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error deleting review. Please try again.', 'error')
    
    return redirect(url_for('sales.manage_reviews'))

@sales_bp.route('/api/popup-settings')
def popup_settings_api():
    """API endpoint for popup settings"""
    settings = PopupSettings.query.first()
    if not settings:
        return jsonify({
            'enabled': True,
            'delay': 15
        })
    
    return jsonify({
        'enabled': settings.popup_enabled,
        'delay': settings.popup_delay_seconds
    })


# Duplicate route removed - keeping the enhanced checkout_page function above


@sales_bp.route('/payment-admin')
@login_required
@role_required([ROLE_SUPER_ADMIN])
def payment_admin():
    """Payment method administration page"""
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.display_order, PaymentMethod.name).all()
    return render_template('sales/payment_admin.html', payment_methods=payment_methods)


@sales_bp.route('/payment-admin', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def add_payment_method():
    """Add new payment method"""
    try:
        validate_csrf(request.form.get('csrf_token'))
        
        payment_method = PaymentMethod()
        payment_method.name = request.form.get('name', '').strip()
        payment_method.type = request.form.get('type', '').strip()
        payment_method.details = request.form.get('details', '').strip()
        payment_method.is_active = bool(int(request.form.get('is_active', 1)))
        payment_method.display_order = int(request.form.get('display_order', 0))
        
        db.session.add(payment_method)
        db.session.commit()
        
        flash(f'Payment method "{payment_method.name}" added successfully!', 'success')
        
    except Exception as e:
        flash(f'Error adding payment method: {str(e)}', 'error')
    
    return redirect(url_for('sales.payment_admin'))


@sales_bp.route('/payment-admin/delete/<int:method_id>', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def delete_payment_method(method_id):
    """Delete payment method"""
    try:
        validate_csrf(request.form.get('csrf_token'))
        
        method = PaymentMethod.query.get_or_404(method_id)
        method_name = method.name
        
        db.session.delete(method)
        db.session.commit()
        
        flash(f'Payment method "{method_name}" deleted successfully!', 'success')
        
    except Exception as e:
        flash(f'Error deleting payment method: {str(e)}', 'error')
    
    return redirect(url_for('sales.payment_admin'))


@sales_bp.route('/payment-method/<int:method_id>')
def get_payment_method(method_id):
    """Get payment method details via AJAX"""
    method = PaymentMethod.query.get_or_404(method_id)
    return jsonify({
        'name': method.name,
        'type': method.type,
        'details': method.details
    })


@sales_bp.route('/payment-pending')
def payment_pending():
    """Payment pending page with countdown and confirmation options"""
    lead_data = session.get('lead_data')
    if not lead_data:
        flash('Session expired. Please start over.', 'error')
        return redirect(url_for('sales.popup_page'))
    
    selected_plan = session.get('selected_plan')
    payment_method = session.get('payment_method')
    
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
    
    return render_template('sales/payment_pending.html', 
                         lead_data=lead_data, 
                         selected_plan=selected_plan,
                         payment_method=payment_method,
                         settings=settings)

@sales_bp.route('/preorder-thanks')
def preorder_thanks():
    """Pre-order thank you page - now only shown after payment confirmation"""
    lead_data = session.get('lead_data')
    
    # Mark this IP as having ordered to suppress future popups
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    
    # Check if suppression record exists
    suppression = PopupSuppression.query.filter_by(ip_address=client_ip).first()
    if not suppression:
        suppression = PopupSuppression()
        suppression.ip_address = client_ip
        suppression.user_agent = user_agent
        suppression.has_ordered = True
        db.session.add(suppression)
    else:
        suppression.has_ordered = True
    
    db.session.commit()
    
    # Update lead status to paid (assuming payment confirmed)
    lead_id = session.get('lead_id')
    if lead_id:
        lead = SalesLead.query.get(lead_id)
        if lead:
            lead.status = 'paid'
            db.session.commit()
    
    return render_template('sales/preorder_thanks.html', lead_data=lead_data)


@sales_bp.route('/api/should-show-popup')
def should_show_popup():
    """Check if popup should be shown for this user"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    
    # Check if this IP has ordered or been suppressed
    suppression = PopupSuppression.query.filter_by(ip_address=client_ip).first()
    
    # Don't show if user has ordered
    if suppression and suppression.has_ordered:
        return jsonify({'show': False, 'reason': 'has_ordered'})
    
    # Don't show if temporarily suppressed (they closed it recently)
    if suppression and suppression.suppressed_until and suppression.suppressed_until > datetime.now():
        return jsonify({'show': False, 'reason': 'temporarily_suppressed'})
    
    return jsonify({'show': True})


@sales_bp.route('/api/suppress-popup', methods=['POST'])
def suppress_popup():
    """Temporarily suppress popup when user closes it"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    
    # Suppress for 24 hours when closed
    from datetime import timedelta
    suppress_until = datetime.now() + timedelta(hours=24)
    
    suppression = PopupSuppression.query.filter_by(ip_address=client_ip).first()
    if not suppression:
        suppression = PopupSuppression()
        suppression.ip_address = client_ip
        suppression.user_agent = user_agent
        suppression.suppressed_until = suppress_until
        db.session.add(suppression)
    else:
        suppression.suppressed_until = suppress_until
    
    db.session.commit()
    
    return jsonify({'success': True})


@sales_bp.route('/api/reset-popup-debug', methods=['POST'])
def reset_popup_debug():
    """Reset popup suppression for testing (debug only)"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    
    # Delete suppression record for this IP
    PopupSuppression.query.filter_by(ip_address=client_ip).delete()
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Popup suppression reset'})


@sales_bp.route('/admin/sales-admin')
@login_required
@role_required([ROLE_SUPER_ADMIN])
def sales_admin():
    """Main sales administration interface"""
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    # Get payment methods
    from models import PaymentMethod
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.display_order, PaymentMethod.name).all()
    
    # Get recent leads
    leads = SalesLead.query.order_by(desc(SalesLead.created_at)).limit(20).all()
    
    return render_template('admin/sales_admin.html', 
                         settings=settings, 
                         payment_methods=payment_methods,
                         leads=leads)

@sales_bp.route('/admin/update-popup-settings', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def update_popup_settings():
    """Update popup behavior settings"""
    try:
        validate_csrf(request.form.get('csrf_token'))
        
        settings = PopupSettings.query.first()
        if not settings:
            settings = PopupSettings()
            db.session.add(settings)
        
        settings.popup_enabled = 'popup_enabled' in request.form
        settings.popup_delay_seconds = int(request.form.get('popup_delay_seconds', 7))
        settings.founders_price = float(request.form.get('founders_price', 579))
        settings.starter_price = float(request.form.get('starter_price', 39))
        settings.growth_price = float(request.form.get('growth_price', 190))
        settings.enterprise_price = float(request.form.get('enterprise_price', 350))
        settings.lifetime_price = float(request.form.get('lifetime_price', 999))
        
        db.session.commit()
        flash('Popup settings updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating settings: {str(e)}', 'error')
    
    return redirect(url_for('sales.sales_admin'))

@sales_bp.route('/admin/update-page-content', methods=['POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def update_page_content():
    """Update sales page content"""
    try:
        validate_csrf(request.form.get('csrf_token'))
        
        settings = PopupSettings.query.first()
        if not settings:
            settings = PopupSettings()
            db.session.add(settings)
        
        # Only update fields that exist in PopupSettings model
        settings.welcome_video_url = request.form.get('welcome_video_url', '').strip()
        settings.thankyou_video_url = request.form.get('thankyou_video_url', '').strip()
        
        db.session.commit()
        flash('Page content updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating content: {str(e)}', 'error')
    
    return redirect(url_for('sales.sales_admin'))

@sales_bp.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_SUPER_ADMIN])
def admin_sales_settings():
    """Admin interface to edit sales page content"""
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    if request.method == 'POST':
        # Update settings from form
        # Update existing fields only
        settings.welcome_video_url = request.form.get('welcome_video_url', settings.welcome_video_url)
        settings.thankyou_video_url = request.form.get('thankyou_video_url', settings.thankyou_video_url)
        
        # Update pricing
        settings.starter_price = float(request.form.get('starter_price', settings.starter_price))
        settings.growth_price = float(request.form.get('growth_price', settings.growth_price))
        settings.enterprise_price = float(request.form.get('enterprise_price', settings.enterprise_price or 350.00))
        settings.founders_price = float(request.form.get('founders_price', settings.founders_price))
        settings.lifetime_price = float(request.form.get('lifetime_price', settings.lifetime_price))
        
        # Update popup behavior
        settings.popup_enabled = 'popup_enabled' in request.form
        settings.popup_delay_seconds = int(request.form.get('popup_delay_seconds', settings.popup_delay_seconds))
        
        settings.updated_at = datetime.now()
        db.session.commit()
        
        flash('Sales page settings updated successfully!', 'success')
        return redirect(url_for('sales.admin_sales_settings'))
    
    return render_template('sales/admin_settings.html', settings=settings)


@sales_bp.route('/submit-review', methods=['POST'])
def submit_review():
    """Handle customer review submission"""
    try:
        # Create new review
        review = CustomerReview()
        review.name = request.form.get('reviewer_name')
        review.firm_name = request.form.get('firm_name')
        review.rating = int(request.form.get('rating', 5))
        review.review_text = request.form.get('review_text')
        review.location = request.form.get('location')
        review.is_active = True  # Auto-approve reviews from paying customers
        review.is_featured = False
        
        db.session.add(review)
        db.session.commit()
        
        flash('Thank you for your review! It helps other law firms discover LawColab.', 'success')
        return redirect(url_for('sales.preorder_thanks'))
        
    except Exception as e:
        db.session.rollback()
        flash('Could not submit review. Please try again.', 'error')
        return redirect(url_for('sales.preorder_thanks'))

@sales_bp.route('/admin/setup-demo-payments')
@login_required  
@role_required([ROLE_SUPER_ADMIN])
def setup_demo_payments():
    """Setup demo payment methods"""
    try:
        from models import PaymentMethod
        
        # Clear existing demo payments
        PaymentMethod.query.delete()
        
        demo_payments = [
            {
                'name': 'Bank Transfer (Wire)',
                'type': 'bank_transfer',
                'details': 'Bank Name: Zenith Bank\nAccount Name: Lawcolab Global\nAccount Number: 1310505179\nCurrency: NGN\nReference: LAWCOLAB-FOUNDER - Abraham',
                'display_order': 1,
                'is_active': True
            },
            {
                'name': 'Bitcoin (BTC)',
                'type': 'crypto',
                'details': 'Network: Bitcoin\nAddress: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\nNote: Email transaction hash to payments@lawcolab.com',
                'display_order': 2,
                'is_active': True
            },
            {
                'name': 'Ethereum (ETH)',
                'type': 'crypto',
                'details': 'Network: Ethereum\nAddress: 0x742d35Cc6634C0532925a3b8D2c82E8B1b1C8B4F\nNote: Email transaction hash to payments@lawcolab.com',
                'display_order': 3,
                'is_active': True
            },
            {
                'name': 'USDT (TRC20)',
                'type': 'crypto',
                'details': 'Network: Tron (TRC-20)\nAddress: TRX9Ym4pJKvhCVJzBJQjGT6A8cYYf8Qz9X\nNote: Email transaction hash to payments@lawcolab.com',
                'display_order': 4,
                'is_active': True
            }
        ]
        
        for payment_data in demo_payments:
            method = PaymentMethod()
            method.name = payment_data['name']
            method.type = payment_data['type']
            method.details = payment_data['details']
            method.display_order = payment_data['display_order']
            method.is_active = payment_data['is_active']
            db.session.add(method)
        
        db.session.commit()
        flash('Demo payment methods created successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error setting up demo payments: {str(e)}', 'error')
    
    return redirect(url_for('sales.sales_admin'))

