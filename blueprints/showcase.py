from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, abort
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from app import db
from models import LawFirm, LawFirmShowcase, PublicLawFirmReview, PublicLawFirmMessage, User, ROLE_SUPER_ADMIN
from utils.decorators import role_required
from datetime import datetime
from sqlalchemy import desc, func
import re

showcase_bp = Blueprint('showcase', __name__)

@showcase_bp.route('/')
def featured_firms():
    """Display featured law firms on the homepage showcase"""
    showcases = LawFirmShowcase.query.filter_by(
        is_featured=True, 
        is_active=True
    ).order_by(LawFirmShowcase.showcase_order.asc()).limit(6).all()
    
    return render_template('showcase/featured_firms.html', showcases=showcases)

@showcase_bp.route('/firm/<int:showcase_id>')
def firm_profile(showcase_id):
    """Public law firm profile page with reviews and contact form"""
    showcase = LawFirmShowcase.query.filter_by(
        id=showcase_id, 
        is_active=True
    ).first_or_404()
    
    # Increment view count
    showcase.total_views += 1
    db.session.commit()
    
    # Get featured reviews
    featured_reviews = PublicLawFirmReview.query.filter_by(
        showcase_id=showcase_id,
        is_approved=True,
        is_visible=True,
        is_featured=True
    ).order_by(desc(PublicLawFirmReview.created_at)).limit(3).all()
    
    # Get all approved reviews
    all_reviews = PublicLawFirmReview.query.filter_by(
        showcase_id=showcase_id,
        is_approved=True,
        is_visible=True
    ).order_by(desc(PublicLawFirmReview.created_at)).all()
    
    # Calculate rating distribution
    rating_counts = db.session.query(
        PublicLawFirmReview.rating,
        func.count(PublicLawFirmReview.id)
    ).filter_by(
        showcase_id=showcase_id,
        is_approved=True,
        is_visible=True
    ).group_by(PublicLawFirmReview.rating).all()
    
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating, count in rating_counts:
        rating_distribution[rating] = count
    
    return render_template('showcase/firm_profile.html', 
                         showcase=showcase,
                         featured_reviews=featured_reviews,
                         all_reviews=all_reviews,
                         rating_distribution=rating_distribution)

@showcase_bp.route('/firm/<int:showcase_id>/review', methods=['POST'])
def submit_review(showcase_id):
    """Submit a public review for a law firm"""
    showcase = LawFirmShowcase.query.filter_by(
        id=showcase_id, 
        is_active=True
    ).first_or_404()
    
    try:
        # Validate CSRF token
        validate_csrf(request.form.get('csrf_token'))
        
        # Get form data
        reviewer_name = request.form.get('reviewer_name', '').strip()
        reviewer_email = request.form.get('reviewer_email', '').strip()
        reviewer_company = request.form.get('reviewer_company', '').strip()
        reviewer_location = request.form.get('reviewer_location', '').strip()
        rating = int(request.form.get('rating', 5))
        review_title = request.form.get('review_title', '').strip()
        review_text = request.form.get('review_text', '').strip()
        
        # Validate required fields
        if not reviewer_name or not review_text:
            flash('Name and review text are required.', 'error')
            return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))
        
        # Validate email format if provided
        if reviewer_email:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, reviewer_email):
                flash('Please enter a valid email address.', 'error')
                return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))
        
        # Validate rating
        if rating < 1 or rating > 5:
            rating = 5
        
        # Create review
        review = PublicLawFirmReview(
            showcase_id=showcase_id,
            reviewer_name=reviewer_name,
            reviewer_email=reviewer_email,
            reviewer_company=reviewer_company,
            reviewer_location=reviewer_location,
            rating=rating,
            review_title=review_title,
            review_text=review_text,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.add(review)
        
        # Update showcase stats
        update_showcase_stats(showcase_id)
        
        db.session.commit()
        flash('Thank you for your review! It has been submitted successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting your review. Please try again.', 'error')
    
    return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))

@showcase_bp.route('/firm/<int:showcase_id>/message', methods=['POST'])
def send_message(showcase_id):
    """Send a private message to a law firm"""
    showcase = LawFirmShowcase.query.filter_by(
        id=showcase_id, 
        is_active=True
    ).first_or_404()
    
    try:
        # Validate CSRF token
        validate_csrf(request.form.get('csrf_token'))
        
        # Get form data
        sender_name = request.form.get('sender_name', '').strip()
        sender_email = request.form.get('sender_email', '').strip()
        sender_phone = request.form.get('sender_phone', '').strip()
        sender_company = request.form.get('sender_company', '').strip()
        subject = request.form.get('subject', '').strip()
        message_text = request.form.get('message_text', '').strip()
        message_type = request.form.get('message_type', 'inquiry')
        
        # Validate required fields
        if not sender_name or not sender_email or not subject or not message_text:
            flash('Name, email, subject, and message are required.', 'error')
            return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, sender_email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))
        
        # Create message
        message = PublicLawFirmMessage(
            showcase_id=showcase_id,
            sender_name=sender_name,
            sender_email=sender_email,
            sender_phone=sender_phone,
            sender_company=sender_company,
            subject=subject,
            message_text=message_text,
            message_type=message_type,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.add(message)
        db.session.commit()
        
        flash('Your message has been sent successfully! The law firm will contact you soon.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while sending your message. Please try again.', 'error')
    
    return redirect(url_for('showcase.firm_profile', showcase_id=showcase_id))

@showcase_bp.route('/admin/manage')
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_manage():
    """Admin interface to manage law firm showcases"""
    showcases = LawFirmShowcase.query.join(LawFirm).order_by(
        LawFirmShowcase.is_featured.desc(),
        LawFirmShowcase.showcase_order.asc(),
        LawFirm.name.asc()
    ).all()
    
    # Get law firms without showcases
    firms_without_showcase = LawFirm.query.outerjoin(LawFirmShowcase).filter(
        LawFirmShowcase.id.is_(None)
    ).all()
    
    return render_template('showcase/admin_manage.html', 
                         showcases=showcases,
                         firms_without_showcase=firms_without_showcase)

@showcase_bp.route('/admin/create/<int:law_firm_id>')
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_create_showcase(law_firm_id):
    """Create a new showcase for a law firm"""
    law_firm = LawFirm.query.get_or_404(law_firm_id)
    
    # Check if showcase already exists
    if law_firm.showcase:
        flash('This law firm already has a showcase.', 'warning')
        return redirect(url_for('showcase.admin_manage'))
    
    # Create new showcase
    showcase = LawFirmShowcase(
        law_firm_id=law_firm_id,
        public_title=law_firm.name,
        public_description=law_firm.description or f"Professional legal services by {law_firm.name}",
        website_url=law_firm.website
    )
    
    db.session.add(showcase)
    db.session.commit()
    
    flash(f'Showcase created for {law_firm.name}!', 'success')
    return redirect(url_for('showcase.admin_edit', showcase_id=showcase.id))

@showcase_bp.route('/admin/edit/<int:showcase_id>')
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_edit(showcase_id):
    """Edit showcase details"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    return render_template('showcase/admin_edit.html', showcase=showcase)

@showcase_bp.route('/admin/update/<int:showcase_id>', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_update(showcase_id):
    """Update showcase details"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    
    try:
        validate_csrf(request.form.get('csrf_token'))
        
        # Update showcase fields
        showcase.public_title = request.form.get('public_title', '').strip()
        showcase.public_description = request.form.get('public_description', '').strip()
        showcase.hero_image_url = request.form.get('hero_image_url', '').strip()
        showcase.logo_image_url = request.form.get('logo_image_url', '').strip()
        showcase.website_url = request.form.get('website_url', '').strip()
        showcase.facebook_url = request.form.get('facebook_url', '').strip()
        showcase.linkedin_url = request.form.get('linkedin_url', '').strip()
        showcase.twitter_url = request.form.get('twitter_url', '').strip()
        showcase.instagram_url = request.form.get('instagram_url', '').strip()
        
        showcase.is_featured = 'is_featured' in request.form
        showcase.is_active = 'is_active' in request.form
        showcase.showcase_order = int(request.form.get('showcase_order', 0))
        
        db.session.commit()
        flash('Showcase updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating the showcase.', 'error')
    
    return redirect(url_for('showcase.admin_edit', showcase_id=showcase_id))

@showcase_bp.route('/admin/reviews/<int:showcase_id>')
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_reviews(showcase_id):
    """Manage reviews for a showcase"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    reviews = PublicLawFirmReview.query.filter_by(
        showcase_id=showcase_id
    ).order_by(desc(PublicLawFirmReview.created_at)).all()
    
    return render_template('showcase/admin_reviews.html', 
                         showcase=showcase, 
                         reviews=reviews)

@showcase_bp.route('/admin/messages/<int:showcase_id>')
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_messages(showcase_id):
    """Manage messages for a showcase"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    messages = PublicLawFirmMessage.query.filter_by(
        showcase_id=showcase_id
    ).order_by(desc(PublicLawFirmMessage.created_at)).all()
    
    return render_template('showcase/admin_messages.html', 
                         showcase=showcase, 
                         messages=messages)

@showcase_bp.route('/admin/review/<int:review_id>/<action>', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_review_action(review_id, action):
    """Handle review moderation actions"""
    review = PublicLawFirmReview.query.get_or_404(review_id)
    
    try:
        if action == 'approve':
            review.is_approved = True
            review.approved_at = datetime.now()
        elif action == 'feature':
            review.is_featured = True
        elif action == 'unfeature':
            review.is_featured = False
        elif action == 'hide':
            review.is_visible = False
        elif action == 'show':
            review.is_visible = True
        elif action == 'delete':
            db.session.delete(review)
            db.session.commit()
            update_showcase_stats(review.showcase_id)
            return jsonify({'success': True, 'message': 'Review deleted'})
        else:
            return jsonify({'success': False, 'message': 'Invalid action'})
        
        db.session.commit()
        update_showcase_stats(review.showcase_id)
        return jsonify({'success': True, 'message': f'Review {action}d successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@showcase_bp.route('/admin/message/<int:message_id>/read', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_mark_message_read(message_id):
    """Mark a message as read"""
    message = PublicLawFirmMessage.query.get_or_404(message_id)
    
    try:
        message.is_read = True
        message.read_at = datetime.now()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Message marked as read'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@showcase_bp.route('/admin/message/<int:message_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_delete_message(message_id):
    """Delete a message"""
    message = PublicLawFirmMessage.query.get_or_404(message_id)
    
    try:
        db.session.delete(message)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Message deleted'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@showcase_bp.route('/admin/grant-verification/<int:showcase_id>', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_grant_verification(showcase_id):
    """Grant verified badge to a law firm showcase"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        notes = data.get('notes', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Verification reason is required'})
        
        # Update showcase verification
        showcase.is_verified = True
        showcase.verified_date = datetime.now()
        showcase.verified_by_id = current_user.id
        showcase.verification_reason = reason
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Verified badge granted to {showcase.law_firm.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@showcase_bp.route('/admin/revoke-verification/<int:showcase_id>', methods=['POST'])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def admin_revoke_verification(showcase_id):
    """Revoke verified badge from a law firm showcase"""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    
    try:
        # Remove verification
        showcase.is_verified = False
        showcase.verified_date = None
        showcase.verified_by_id = None
        showcase.verification_reason = None
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Verified badge revoked from {showcase.law_firm.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

def update_showcase_stats(showcase_id):
    """Update showcase statistics (reviews count and average rating)"""
    showcase = LawFirmShowcase.query.get(showcase_id)
    if not showcase:
        return
    
    # Get review stats
    result = db.session.query(
        func.count(PublicLawFirmReview.id),
        func.avg(PublicLawFirmReview.rating)
    ).filter_by(
        showcase_id=showcase_id,
        is_approved=True,
        is_visible=True
    ).first()
    
    showcase.total_reviews = result[0] or 0
    showcase.average_rating = round(float(result[1] or 5.0), 2)
    
    db.session.commit()