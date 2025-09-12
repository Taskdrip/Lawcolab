from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from app import db
from models import SalesLead, PopupSettings, CustomerReview, User, ROLE_SUPER_ADMIN, PaymentMethod, PopupSuppression
from utils.decorators import role_required
from datetime import datetime
from sqlalchemy import desc
import re

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/popup')
def popup_page():
    """Display the fullscreen popup sales page - STANDALONE NO INHERITANCE"""
    from flask import Response
    with open('templates/sales/working_popup.html', 'r') as f:
        content = f.read()
    return Response(content, mimetype='text/html')

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
    valid_plans = ['starter', 'growth', 'scale', 'founder']
    
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
    
    lead_data = session.get('lead_data')
    if not lead_data:
        flash('Please complete the registration form first.', 'warning')
        return redirect(url_for('sales.popup_page'))
    
    # Get payment methods
    from models import PaymentMethod
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.display_order).all()
    
    settings = PopupSettings.query.first()
    if not settings:
        settings = PopupSettings()
    
    return render_template('sales/checkout.html', 
                         lead_data=lead_data, 
                         selected_plan=selected_plan,
                         payment_methods=payment_methods,
                         settings=settings)

@sales_bp.route('/checkout/complete', methods=['POST'])
def complete_checkout():
    """Complete the checkout process"""
    try:
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
        
        # Store payment method in session
        session['payment_method'] = payment_method
        
        return redirect(url_for('sales.preorder_thanks'))
        
    except Exception as e:
        flash(f'Error processing checkout: {str(e)}', 'error')
        return redirect(url_for('sales.checkout_page'))

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
        
        # Update pricing
        settings.starter_price = float(request.form.get('starter_price', 70.00))
        settings.growth_price = float(request.form.get('growth_price', 190.00))
        settings.scale_price = float(request.form.get('scale_price', 750.00))
        settings.founders_price = float(request.form.get('founders_price', 750.00))
        
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


@sales_bp.route('/checkout')
def checkout():
    """Display checkout page"""
    lead_data = session.get('lead_data')
    if not lead_data:
        flash('Please fill out the sales form first.', 'warning')
        return redirect(url_for('sales.popup_page'))
    
    # Get active payment methods
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.display_order, PaymentMethod.name).all()
    
    return render_template('sales/checkout.html', lead_data=lead_data, payment_methods=payment_methods)


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


@sales_bp.route('/preorder-thanks')
def preorder_thanks():
    """Pre-order thank you page"""
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
        settings.scale_price = float(request.form.get('scale_price', settings.scale_price))
        settings.founders_price = float(request.form.get('founders_price', settings.founders_price))
        
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

