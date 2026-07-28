"""
Super Admin — Directory CRM
Mounted at /superadmin/directory
Approve/reject showcase submissions, manage external (Google Maps) firms,
add CRM notes, run the discovery robot.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app import db
from models import (
    LawFirm, LawFirmShowcase, DirectoryLawFirm, DirectoryNote, User,
    ROLE_SUPER_ADMIN
)
from utils.decorators import require_super_admin
from datetime import datetime
from sqlalchemy import or_, func, desc
import json

dir_admin_bp = Blueprint('dir_admin', __name__)


# ─── Showcase Approval Queue ──────────────────────────────────────────────────

@dir_admin_bp.route('/')
@require_super_admin
def index():
    """Directory CRM overview."""
    pending = LawFirmShowcase.query.filter_by(submission_status='submitted').count()
    approved = LawFirmShowcase.query.filter_by(submission_status='approved').count()
    total_ext = DirectoryLawFirm.query.count()
    no_website = DirectoryLawFirm.query.filter_by(has_website=False, is_active=True).count()
    new_leads = DirectoryLawFirm.query.filter_by(crm_status='new', is_active=True).count()

    recent_submissions = LawFirmShowcase.query.filter(
        LawFirmShowcase.submission_status.in_(['submitted', 'approved', 'rejected'])
    ).order_by(desc(LawFirmShowcase.submitted_at)).limit(10).all()

    stats = dict(
        pending=pending, approved=approved, total_ext=total_ext,
        no_website=no_website, new_leads=new_leads
    )
    return render_template('directory_admin/index.html',
                           stats=stats,
                           recent_submissions=recent_submissions)


@dir_admin_bp.route('/submissions')
@require_super_admin
def submissions():
    """Approve / reject law firm showcase submissions."""
    status_filter = request.args.get('status', 'submitted')
    page = request.args.get('page', 1, type=int)

    q = LawFirmShowcase.query.join(LawFirm)
    if status_filter and status_filter != 'all':
        q = q.filter(LawFirmShowcase.submission_status == status_filter)
    else:
        q = q.filter(LawFirmShowcase.submission_status.in_(
            ['submitted', 'approved', 'rejected', 'draft']
        ))

    showcases = q.order_by(desc(LawFirmShowcase.submitted_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('directory_admin/submissions.html',
                           showcases=showcases,
                           status_filter=status_filter)


@dir_admin_bp.route('/submissions/<int:showcase_id>/review')
@require_super_admin
def review_submission(showcase_id):
    """Detailed review of a single showcase submission."""
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    return render_template('directory_admin/review_submission.html', showcase=showcase)


@dir_admin_bp.route('/submissions/<int:showcase_id>/approve', methods=['POST'])
@require_super_admin
def approve_submission(showcase_id):
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    try:
        showcase.submission_status = 'approved'
        showcase.is_active = True
        showcase.approved_at = datetime.now()
        showcase.approved_by_id = current_user.id
        showcase.rejection_reason = None
        db.session.commit()
        flash(f'✅ {showcase.public_title or showcase.law_firm.name} has been approved and is now live in the directory.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving: {str(e)}', 'error')
    return redirect(request.referrer or url_for('dir_admin.submissions'))


@dir_admin_bp.route('/submissions/<int:showcase_id>/reject', methods=['POST'])
@require_super_admin
def reject_submission(showcase_id):
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    try:
        reason = request.form.get('reason', '').strip()
        showcase.submission_status = 'rejected'
        showcase.rejection_reason = reason
        db.session.commit()
        flash(f'❌ {showcase.law_firm.name} submission rejected.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting: {str(e)}', 'error')
    return redirect(request.referrer or url_for('dir_admin.submissions'))


@dir_admin_bp.route('/submissions/<int:showcase_id>/feature', methods=['POST'])
@require_super_admin
def toggle_feature(showcase_id):
    showcase = LawFirmShowcase.query.get_or_404(showcase_id)
    showcase.is_featured = not showcase.is_featured
    db.session.commit()
    state = 'featured' if showcase.is_featured else 'unfeatured'
    return jsonify({'success': True, 'is_featured': showcase.is_featured,
                    'message': f'Firm {state} in spotlight.'})


# ─── External (Google Maps) Directory ─────────────────────────────────────────

@dir_admin_bp.route('/external')
@require_super_admin
def external_firms():
    """CRM view of all external / scraped firms — HubSpot-style."""
    search = request.args.get('q', '').strip()
    state_f = request.args.get('state', '').strip()
    country_f = request.args.get('country', '').strip()
    status_f = request.args.get('crm_status', '').strip()
    no_website = request.args.get('no_website', '') == '1'
    page = request.args.get('page', 1, type=int)

    q = DirectoryLawFirm.query
    if search:
        q = q.filter(or_(
            DirectoryLawFirm.name.ilike(f'%{search}%'),
            DirectoryLawFirm.city.ilike(f'%{search}%'),
            DirectoryLawFirm.address.ilike(f'%{search}%'),
        ))
    if state_f:
        q = q.filter(DirectoryLawFirm.state.ilike(f'%{state_f}%'))
    if country_f:
        q = q.filter(DirectoryLawFirm.country.ilike(f'%{country_f}%'))
    if status_f:
        q = q.filter_by(crm_status=status_f)
    if no_website:
        q = q.filter_by(has_website=False)

    firms = q.order_by(DirectoryLawFirm.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    # Quick counts for sidebar chips
    counts = {
        'total': DirectoryLawFirm.query.count(),
        'new': DirectoryLawFirm.query.filter_by(crm_status='new').count(),
        'contacted': DirectoryLawFirm.query.filter_by(crm_status='contacted').count(),
        'converted': DirectoryLawFirm.query.filter_by(crm_status='converted').count(),
        'no_website': DirectoryLawFirm.query.filter_by(has_website=False).count(),
    }

    from blueprints.directory import NIGERIAN_STATES
    return render_template('directory_admin/external_firms.html',
                           firms=firms, counts=counts,
                           states=NIGERIAN_STATES,
                           filters=dict(q=search, state=state_f, country=country_f,
                                        crm_status=status_f, no_website=no_website))


@dir_admin_bp.route('/external/add', methods=['GET', 'POST'])
@require_super_admin
def add_external():
    """Manually add a law firm to the directory."""
    if request.method == 'POST':
        try:
            areas_raw = request.form.getlist('practice_areas')
            firm = DirectoryLawFirm(
                name=request.form.get('name', '').strip(),
                phone=request.form.get('phone', '').strip(),
                email=request.form.get('email', '').strip(),
                website=request.form.get('website', '').strip(),
                address=request.form.get('address', '').strip(),
                city=request.form.get('city', '').strip(),
                state=request.form.get('state', '').strip(),
                country=request.form.get('country', 'Nigeria').strip(),
                description=request.form.get('description', '').strip(),
                practice_areas_json=json.dumps(areas_raw) if areas_raw else None,
                source='manual',
                has_website=bool(request.form.get('website', '').strip()),
                crm_status='new',
            )
            if not firm.name:
                flash('Firm name is required.', 'error')
                return redirect(url_for('dir_admin.add_external'))
            db.session.add(firm)
            db.session.commit()
            flash(f'✅ {firm.name} added to directory.', 'success')
            return redirect(url_for('dir_admin.external_firms'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')

    from blueprints.directory import PRACTICE_AREA_LIST, NIGERIAN_STATES
    return render_template('directory_admin/add_external.html',
                           practice_areas=PRACTICE_AREA_LIST,
                           states=NIGERIAN_STATES)


@dir_admin_bp.route('/external/<int:firm_id>')
@require_super_admin
def external_detail(firm_id):
    """CRM detail view for a single external firm."""
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    return render_template('directory_admin/external_detail.html', firm=firm)


@dir_admin_bp.route('/external/<int:firm_id>/update-status', methods=['POST'])
@require_super_admin
def update_crm_status(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    new_status = request.form.get('crm_status', 'new')
    firm.crm_status = new_status
    db.session.commit()
    return jsonify({'success': True, 'crm_status': new_status})


@dir_admin_bp.route('/external/<int:firm_id>/add-note', methods=['POST'])
@require_super_admin
def add_note(firm_id):
    """Add a CRM note to an external firm."""
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    text = request.form.get('note_text', '').strip()
    note_type = request.form.get('note_type', 'general')
    if not text:
        return jsonify({'success': False, 'message': 'Note text is required.'})
    try:
        note = DirectoryNote(
            firm_id=firm.id,
            created_by_id=current_user.id,
            note_text=text,
            note_type=note_type,
        )
        db.session.add(note)
        db.session.commit()
        return jsonify({
            'success': True,
            'note': {
                'id': note.id,
                'text': note.note_text,
                'type': note.note_type,
                'author': current_user.full_name,
                'created_at': note.created_at.strftime('%b %d, %Y %H:%M'),
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@dir_admin_bp.route('/external/<int:firm_id>/delete', methods=['POST'])
@require_super_admin
def delete_external(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    name = firm.name
    db.session.delete(firm)
    db.session.commit()
    flash(f'Firm "{name}" removed from directory.', 'info')
    return redirect(url_for('dir_admin.external_firms'))


# ─── Google Maps Robot ─────────────────────────────────────────────────────────

# Nigerian law firm seed data (representative sample the robot would discover)
_SEED_FIRMS = [
    {"name": "Templars", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "The Octagon, 13A A.J Marinho Drive, Victoria Island, Lagos",
     "phone": "+234 1 700 2337", "website": "https://www.templars-law.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Mergers & Acquisitions"],
     "google_rating": 4.7, "google_reviews_count": 42, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Templars+Lagos"},
    {"name": "AELEX", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "1 Hospital Road, Onikan, Lagos Island, Lagos",
     "phone": "+234 1 270 1420", "website": "https://www.aelex.com",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Litigation"],
     "google_rating": 4.6, "google_reviews_count": 28, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=AELEX+Lagos"},
    {"name": "Aluko & Oyebode", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "Marina Nominees House, 27 Marina, Lagos Island",
     "phone": "+234 1 270 1400", "website": "https://www.aluko-oyebode.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Tax Law"],
     "google_rating": 4.8, "google_reviews_count": 55, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aluko+Oyebode+Lagos"},
    {"name": "Olaniwun Ajayi LP", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "The Adunola, Plot L2, 401 Close, Banana Island",
     "phone": "+234 1 270 1434", "website": "https://www.olaniwunajayi.net",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Employment & Labour"],
     "google_rating": 4.5, "google_reviews_count": 33, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Olaniwun+Ajayi+Lagos"},
    {"name": "Streamsowers & Köhn", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "4th Floor, Union Marble House, 1 Alfred Rewane Road, Ikoyi",
     "phone": "+234 1 270 1456", "website": "https://www.sk-law.com.ng",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Litigation"],
     "google_rating": 4.4, "google_reviews_count": 19, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Streamsowers+Kohn+Lagos"},
    {"name": "Udo Udoma & Belo-Osagie", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "St. Nicholas House (10th–12th Floors), Catholic Mission Street, Lagos",
     "phone": "+234 1 4622 460", "website": "https://www.uubo.org",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Oil & Gas"],
     "google_rating": 4.7, "google_reviews_count": 61, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Udo+Udoma+Belo-Osagie+Lagos"},
    {"name": "Perchstone & Graeys", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "2nd Floor, 20 Gerrard Road, Ikoyi, Lagos",
     "phone": "+234 1 270 1502", "website": "https://perchstone.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Employment & Labour"],
     "google_rating": 4.3, "google_reviews_count": 14, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Perchstone+Graeys+Lagos"},
    {"name": "Ajumogobia & Okeke", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 590, Aminu Kano Crescent, Wuse II, Abuja",
     "phone": "+234 9 461 0001", "website": "https://www.ajumogobia.com",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Tax Law"],
     "google_rating": 4.5, "google_reviews_count": 22, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ajumogobia+Okeke+Abuja"},
    {"name": "Chris Ogunbanjo LP", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "63A Ademola Street, South-West Ikoyi, Lagos",
     "phone": "+234 1 270 1521", "website": "https://www.chrisogunbanjo.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Litigation"],
     "google_rating": 4.2, "google_reviews_count": 9, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Chris+Ogunbanjo+Lagos"},
    {"name": "Paul Usoro & Co", "city": "Uyo", "state": "Akwa Ibom", "country": "Nigeria",
     "address": "No. 16 Abak Road, Uyo, Akwa Ibom State",
     "phone": "+234 85 204 100", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Criminal Law"],
     "google_rating": 4.1, "google_reviews_count": 7, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Paul+Usoro+Uyo"},
    {"name": "Banwo & Ighodalo", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "98 Awolowo Road, Ikoyi, Lagos",
     "phone": "+234 1 270 1530", "website": "https://www.banwo-ighodalo.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Mergers & Acquisitions"],
     "google_rating": 4.9, "google_reviews_count": 74, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Banwo+Ighodalo+Lagos"},
    {"name": "G. Elias & Co", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "22 Moloney Street, Lagos Island, Lagos",
     "phone": "+234 1 263 5941", "website": "https://www.gelias.com",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Litigation"],
     "google_rating": 4.6, "google_reviews_count": 38, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=G+Elias+Lagos"},
    {"name": "SimmonsCooper Partners", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "12 Catholic Mission Street, Lagos Island",
     "phone": "+234 1 460 0450", "website": "https://www.simmonscooperpartners.com",
     "practice_areas": ["Corporate & Commercial", "Aviation Law", "Maritime Law"],
     "google_rating": 4.4, "google_reviews_count": 17, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=SimmonsCooper+Partners+Lagos"},
    {"name": "Jackson Etti & Edu", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "5 Ibiyinka Olorunbe Close, Victoria Island, Lagos",
     "phone": "+234 1 4617 000", "website": "https://www.jee.com.ng",
     "practice_areas": ["Corporate & Commercial", "Intellectual Property", "Real Estate"],
     "google_rating": 4.5, "google_reviews_count": 29, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Jackson+Etti+Edu+Lagos"},
    {"name": "Dikko & Mahmoud", "city": "Kano", "state": "Kano", "country": "Nigeria",
     "address": "23 Lamido Street, Nassarawa G.R.A, Kano",
     "phone": "+234 64 319 220", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Criminal Law"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Dikko+Mahmoud+Kano"},
    {"name": "Muyiwa Afolabi & Associates", "city": "Ibadan", "state": "Oyo", "country": "Nigeria",
     "address": "4 Awolowo Avenue, Ibadan, Oyo State",
     "phone": "+234 2 241 5678", "website": "",
     "practice_areas": ["Family Law", "Litigation", "Real Estate"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Muyiwa+Afolabi+Ibadan"},
    {"name": "Odujinrin & Adefulu", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "Plot 29 Oju-Elegba Road, Surulere, Lagos",
     "phone": "+234 1 774 1800", "website": "https://www.odujinrin-adefulu.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Litigation"],
     "google_rating": 4.3, "google_reviews_count": 12, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Odujinrin+Adefulu+Lagos"},
    {"name": "Fidelis Oditah & Co", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1102 Jos Street, Garki Area II, Abuja",
     "phone": "+234 9 413 6550", "website": "https://www.oditahlaw.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Arbitration"],
     "google_rating": 4.6, "google_reviews_count": 25, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Fidelis+Oditah+Abuja"},
    {"name": "Olisa Agbakoba Legal", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "27 Oba Akran Avenue, Ikeja, Lagos",
     "phone": "+234 1 495 1310", "website": "https://www.oal.com.ng",
     "practice_areas": ["Human Rights", "Maritime Law", "Litigation", "Oil & Gas"],
     "google_rating": 4.7, "google_reviews_count": 46, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Olisa+Agbakoba+Lagos"},
    {"name": "Chukwuma & Associates", "city": "Enugu", "state": "Enugu", "country": "Nigeria",
     "address": "43 Ogui Road, Enugu, Enugu State",
     "phone": "+234 42 256 789", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Chukwuma+Associates+Enugu"},
]


@dir_admin_bp.route('/robot')
@require_super_admin
def robot_dashboard():
    """Google Maps discovery robot dashboard."""
    already_added = DirectoryLawFirm.query.count()
    return render_template('directory_admin/robot.html',
                           already_added=already_added,
                           seed_count=len(_SEED_FIRMS))


@dir_admin_bp.route('/robot/run', methods=['POST'])
@require_super_admin
def robot_run():
    """Import seed Nigerian law firm data (simulates Google Maps scrape)."""
    added = 0
    skipped = 0
    errors = 0

    for data in _SEED_FIRMS:
        try:
            # Skip if name already exists
            existing = DirectoryLawFirm.query.filter(
                DirectoryLawFirm.name.ilike(data['name'])
            ).first()
            if existing:
                skipped += 1
                continue

            firm = DirectoryLawFirm(
                name=data['name'],
                city=data.get('city'),
                state=data.get('state'),
                country=data.get('country', 'Nigeria'),
                address=data.get('address'),
                phone=data.get('phone'),
                website=data.get('website'),
                practice_areas_json=json.dumps(data.get('practice_areas', [])),
                google_rating=data.get('google_rating'),
                google_reviews_count=data.get('google_reviews_count', 0),
                google_maps_url=data.get('google_maps_url'),
                source=data.get('source', 'google_maps'),
                has_website=bool(data.get('website', '').strip()),
                crm_status='new',
                is_active=True,
            )
            db.session.add(firm)
            added += 1
        except Exception:
            errors += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

    return jsonify({
        'success': True,
        'added': added,
        'skipped': skipped,
        'errors': errors,
        'message': f'Robot completed: {added} firms added, {skipped} already existed.'
    })
