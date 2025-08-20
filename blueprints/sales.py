from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from app import db
from models import SalesLead, PopupSettings, CustomerReview, User, ROLE_SUPER_ADMIN, PaymentMethod
from utils.decorators import role_required
from datetime import datetime
from sqlalchemy import desc
import re

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/popup')
def popup_page():
    """Display the fullscreen popup sales page"""
    # Get popup settings
    settings = PopupSettings.query.first()
    if not settings:
        # Create default settings
        settings = PopupSettings()
        db.session.add(settings)
        db.session.commit()
    
    # Get featured reviews
    reviews = CustomerReview.query.filter_by(is_active=True).order_by(desc(CustomerReview.is_featured), CustomerReview.id).limit(20).all()
    
    return render_template('sales/popup.html', settings=settings, reviews=reviews)

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
        return redirect(url_for('sales.preorder_thanks'))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('sales.popup_page'))

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
        settings.starter_price = float(request.form.get('starter_price', 29.00))
        settings.growth_price = float(request.form.get('growth_price', 79.00))
        settings.scale_price = float(request.form.get('scale_price', 199.00))
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
        
        payment_method = PaymentMethod(
            name=request.form.get('name', '').strip(),
            type=request.form.get('type', '').strip(),
            details=request.form.get('details', '').strip(),
            is_active=bool(int(request.form.get('is_active', 1))),
            display_order=int(request.form.get('display_order', 0))
        )
        
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
    return render_template('sales/preorder_thanks.html', lead_data=lead_data)