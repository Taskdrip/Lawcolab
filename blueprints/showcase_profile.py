"""
Law Firm self-service showcase profile editor.
Law firm admins edit their own showcase and submit it for super admin approval.
Mounted at /showcase-profile
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from app import db
from models import LawFirm, LawFirmShowcase, ROLE_ADMIN, ROLE_SUPER_ADMIN
from utils.decorators import role_required
from datetime import datetime
import json
import os
import uuid
from werkzeug.utils import secure_filename

showcase_profile_bp = Blueprint('showcase_profile', __name__)

UPLOAD_FOLDER = 'static/uploads/showcase'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _save_image(file_field_name):
    """Save an uploaded image; return the URL path or None."""
    file = request.files.get(file_field_name)
    if file and file.filename and _allowed(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        file.save(os.path.join(UPLOAD_FOLDER, fname))
        return f"/static/uploads/showcase/{fname}"
    return None


@showcase_profile_bp.route('/')
@login_required
@role_required(ROLE_ADMIN)
def index():
    """Show current showcase status and link to editor."""
    firm = current_user.law_firm
    if not firm:
        flash('No law firm associated with your account.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    showcase = LawFirmShowcase.query.filter_by(law_firm_id=firm.id).first()
    return render_template('showcase_profile/index.html', firm=firm, showcase=showcase)


@showcase_profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit():
    """Edit the firm's showcase profile."""
    firm = current_user.law_firm
    if not firm:
        flash('No law firm associated with your account.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    # Get or create showcase
    showcase = LawFirmShowcase.query.filter_by(law_firm_id=firm.id).first()
    if not showcase:
        showcase = LawFirmShowcase(
            law_firm_id=firm.id,
            public_title=firm.name,
            submission_status='draft'
        )
        db.session.add(showcase)
        db.session.commit()

    # Block editing if already approved (must re-submit for changes)
    # We allow editing at any status except already under review — well actually let's allow editing anytime
    # but re-submitting resets to 'submitted'

    if request.method == 'POST':
        try:
            # Basic info
            showcase.public_title = request.form.get('public_title', '').strip() or firm.name
            showcase.tagline = request.form.get('tagline', '').strip()
            showcase.public_description = request.form.get('public_description', '').strip()
            showcase.founded_year = request.form.get('founded_year', type=int)
            showcase.firm_size = request.form.get('firm_size', '').strip()

            # Contact & social
            showcase.phone = request.form.get('phone', '').strip()
            showcase.whatsapp = request.form.get('whatsapp', '').strip()
            showcase.website_url = request.form.get('website_url', '').strip()
            showcase.facebook_url = request.form.get('facebook_url', '').strip()
            showcase.linkedin_url = request.form.get('linkedin_url', '').strip()
            showcase.twitter_url = request.form.get('twitter_url', '').strip()
            showcase.instagram_url = request.form.get('instagram_url', '').strip()
            showcase.youtube_url = request.form.get('youtube_url', '').strip()

            # Practice areas (multi-select checkboxes)
            areas = request.form.getlist('practice_areas')
            showcase.practice_areas_json = json.dumps(areas) if areas else None

            # Locations (dynamic rows submitted as JSON string)
            locations_raw = request.form.get('locations_json', '[]')
            try:
                locs = json.loads(locations_raw)
                showcase.locations_json = json.dumps(locs) if locs else None
            except Exception:
                pass

            # Team members
            team_raw = request.form.get('team_json', '[]')
            try:
                team = json.loads(team_raw)
                showcase.team_json = json.dumps(team) if team else None
            except Exception:
                pass

            # Image uploads
            hero_url = _save_image('hero_image')
            if hero_url:
                showcase.hero_image_url = hero_url
            elif request.form.get('hero_image_url_existing'):
                showcase.hero_image_url = request.form.get('hero_image_url_existing')

            logo_url = _save_image('logo_image')
            if logo_url:
                showcase.logo_image_url = logo_url
            elif request.form.get('logo_image_url_existing'):
                showcase.logo_image_url = request.form.get('logo_image_url_existing')

            showcase.updated_at = datetime.now()
            db.session.commit()

            action = request.form.get('action', 'save')
            if action == 'submit':
                if not showcase.public_description or len(showcase.public_description) < 30:
                    flash('Please add a detailed description (at least 30 characters) before submitting.', 'warning')
                    return redirect(url_for('showcase_profile.edit'))
                showcase.submission_status = 'submitted'
                showcase.submitted_at = datetime.now()
                db.session.commit()
                flash('🎉 Your firm profile has been submitted for review! Our team will approve it shortly.', 'success')
                return redirect(url_for('showcase_profile.index'))

            flash('Profile saved successfully.', 'success')
            return redirect(url_for('showcase_profile.edit'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error saving profile: {str(e)}', 'error')

    from blueprints.directory import PRACTICE_AREA_LIST, NIGERIAN_STATES
    return render_template(
        'showcase_profile/edit.html',
        firm=firm,
        showcase=showcase,
        practice_area_list=PRACTICE_AREA_LIST,
        nigerian_states=NIGERIAN_STATES,
    )


@showcase_profile_bp.route('/upload-image', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def upload_image():
    """AJAX image upload endpoint."""
    file = request.files.get('file')
    field = request.form.get('field', 'hero')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file provided'})
    if not _allowed(file.filename):
        return jsonify({'success': False, 'message': 'File type not allowed'})
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        file.save(os.path.join(UPLOAD_FOLDER, fname))
        url = f"/static/uploads/showcase/{fname}"
        return jsonify({'success': True, 'url': url})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
