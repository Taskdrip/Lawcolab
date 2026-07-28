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


@dir_admin_bp.route('/external/<int:firm_id>/update-social', methods=['POST'])
@require_super_admin
def update_social(firm_id):
    """Save social media links for a firm."""
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    raw = request.form.get('social_links_json', '{}')
    try:
        links = json.loads(raw)
        # Only keep non-empty values
        links = {k: v for k, v in links.items() if v and str(v).strip()}
        firm.social_links_json = json.dumps(links) if links else None
        db.session.commit()
        return jsonify({'success': True})
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

# Nigerian law firm seed data — 100+ firms across all 36 states + FCT Abuja
# Simulates what the Google Maps discovery robot would find and import
_SEED_FIRMS = [
    # ── Lagos (Nigeria's commercial capital) ──────────────────────────────────
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

    # ── More Lagos firms ──────────────────────────────────────────────────────
    {"name": "Aelex Legal Practitioners", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1387 Cadastral Zone, Wuse II, Abuja",
     "phone": "+234 9 291 0001", "website": "https://www.aelex.com",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Litigation"],
     "google_rating": 4.5, "google_reviews_count": 18, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aelex+Abuja"},
    {"name": "Kenna Partners", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "16 Murtala Muhammed Drive, Ikoyi, Lagos",
     "phone": "+234 1 270 1548", "website": "https://www.kennapartners.com",
     "practice_areas": ["Corporate & Commercial", "Technology Law", "Intellectual Property"],
     "google_rating": 4.4, "google_reviews_count": 21, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Kenna+Partners+Lagos"},
    {"name": "Adepetun Caxton-Martins Agbor & Segun", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "5th Floor, UBA House, 57 Marina, Lagos Island",
     "phone": "+234 1 460 2940", "website": "https://www.acas-law.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Real Estate"],
     "google_rating": 4.6, "google_reviews_count": 31, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=ACAS+Law+Lagos"},
    {"name": "Sofunde Osakwe Ogundipe & Belgore", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "17A Keffi Street, South-West Ikoyi, Lagos",
     "phone": "+234 1 270 1560", "website": "https://www.soob.com.ng",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Tax Law"],
     "google_rating": 4.5, "google_reviews_count": 27, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=SOOB+Law+Lagos"},
    {"name": "Famsville Solicitors", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "204 Igbosere Road, Lagos Island",
     "phone": "+234 1 342 9571", "website": "https://www.famsvillelaw.com",
     "practice_areas": ["Real Estate", "Corporate & Commercial", "Family Law"],
     "google_rating": 4.2, "google_reviews_count": 11, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Famsville+Solicitors+Lagos"},
    {"name": "Resolution Law Firm", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "Plot 5B, Chief Collins Street, Lekki Phase 1, Lagos",
     "phone": "+234 8060 363 807", "website": "https://www.resolutionlawng.com",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Technology Law"],
     "google_rating": 4.3, "google_reviews_count": 15, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Resolution+Law+Firm+Lagos"},
    {"name": "Alabi Adesida & Co", "city": "Akure", "state": "Ondo", "country": "Nigeria",
     "address": "18 Oyemekun Road, Akure, Ondo State",
     "phone": "+234 34 230 456", "website": "",
     "practice_areas": ["Litigation", "Real Estate", "Family Law"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Alabi+Adesida+Akure"},
    {"name": "Dele Adesina & Co", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "57 Awolowo Road, Ikoyi, Lagos",
     "phone": "+234 1 269 3333", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Human Rights"],
     "google_rating": 4.1, "google_reviews_count": 8, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Dele+Adesina+Lagos"},

    # ── FCT Abuja ─────────────────────────────────────────────────────────────
    {"name": "Afe Babalola & Co", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1679, Cadastral Zone B06, Wuse II, Abuja",
     "phone": "+234 9 461 8500", "website": "https://www.afebabalolaco.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Human Rights"],
     "google_rating": 4.8, "google_reviews_count": 52, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Afe+Babalola+Abuja"},
    {"name": "Abdullahi Ibrahim & Co", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "No. 12 Aguiyi Ironsi Street, Maitama, Abuja",
     "phone": "+234 9 413 7890", "website": "",
     "practice_areas": ["Corporate & Commercial", "Tax Law", "Government Affairs"],
     "google_rating": 4.3, "google_reviews_count": 11, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Abdullahi+Ibrahim+Abuja"},
    {"name": "Theophilus Donatus Nwosu & Co", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 304, Cadastral Zone, Garki, Abuja",
     "phone": "+234 9 523 4567", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Corporate & Commercial"],
     "google_rating": 4.0, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Nwosu+Associates+Abuja"},
    {"name": "Ladi Rotimi-Williams Chambers", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1244 Ahmadu Bello Way, Wuse Zone 4, Abuja",
     "phone": "+234 9 461 9200", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Oil & Gas"],
     "google_rating": 4.2, "google_reviews_count": 9, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Rotimi+Williams+Chambers+Abuja"},
    {"name": "Abubakar Sani & Associates", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "5 Katsina Ala Street, Wuse Zone 6, Abuja",
     "phone": "+234 9 290 5678", "website": "",
     "practice_areas": ["Criminal Law", "Litigation", "Human Rights"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Abubakar+Sani+Abuja"},

    # ── Rivers State (Port Harcourt) ──────────────────────────────────────────
    {"name": "Princewill Chambers", "city": "Port Harcourt", "state": "Rivers", "country": "Nigeria",
     "address": "14 Tombia Street, GRA Phase 2, Port Harcourt",
     "phone": "+234 84 231 456", "website": "",
     "practice_areas": ["Oil & Gas", "Maritime Law", "Litigation"],
     "google_rating": 4.3, "google_reviews_count": 13, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Princewill+Chambers+Port+Harcourt"},
    {"name": "N.O. Orji & Co", "city": "Port Harcourt", "state": "Rivers", "country": "Nigeria",
     "address": "33 Aba Road, Port Harcourt, Rivers State",
     "phone": "+234 84 462 300", "website": "",
     "practice_areas": ["Corporate & Commercial", "Oil & Gas", "Real Estate"],
     "google_rating": 4.1, "google_reviews_count": 7, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=NO+Orji+Port+Harcourt"},
    {"name": "Briggs & Briggs", "city": "Port Harcourt", "state": "Rivers", "country": "Nigeria",
     "address": "3 Moscow Road, Port Harcourt",
     "phone": "+234 84 771 234", "website": "",
     "practice_areas": ["Maritime Law", "Oil & Gas", "Litigation"],
     "google_rating": 4.2, "google_reviews_count": 10, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Briggs+Briggs+Port+Harcourt"},
    {"name": "Eseimokumo Ogan & Co", "city": "Port Harcourt", "state": "Rivers", "country": "Nigeria",
     "address": "12 Peter Odili Road, Trans Amadi, Port Harcourt",
     "phone": "+234 84 338 901", "website": "",
     "practice_areas": ["Oil & Gas", "Employment & Labour", "Litigation"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ogan+Associates+Port+Harcourt"},

    # ── Oyo State (Ibadan) ────────────────────────────────────────────────────
    {"name": "Chief Afe Babalola & Co Ibadan", "city": "Ibadan", "state": "Oyo", "country": "Nigeria",
     "address": "Plot 1, Afe Babalola Avenue, Oke-Bola, Ibadan",
     "phone": "+234 2 231 0001", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Human Rights"],
     "google_rating": 4.4, "google_reviews_count": 16, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Afe+Babalola+Ibadan"},
    {"name": "Adeleke Thompson & Adeola", "city": "Ibadan", "state": "Oyo", "country": "Nigeria",
     "address": "7 Ringroad, Ibadan, Oyo State",
     "phone": "+234 2 231 5678", "website": "",
     "practice_areas": ["Family Law", "Real Estate", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Adeleke+Thompson+Ibadan"},
    {"name": "Gbenga Biobaku & Co", "city": "Ibadan", "state": "Oyo", "country": "Nigeria",
     "address": "1 Biobaku Close, Agodi GRA, Ibadan",
     "phone": "+234 2 810 2345", "website": "https://www.biobaku.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.2, "google_reviews_count": 9, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Gbenga+Biobaku+Ibadan"},

    # ── Anambra State ─────────────────────────────────────────────────────────
    {"name": "Obiora Egonu & Associates", "city": "Onitsha", "state": "Anambra", "country": "Nigeria",
     "address": "23 New Market Road, Onitsha, Anambra State",
     "phone": "+234 46 481 123", "website": "",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Litigation"],
     "google_rating": 4.0, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Obiora+Egonu+Onitsha"},
    {"name": "Nnamdi Ike Chambers", "city": "Awka", "state": "Anambra", "country": "Nigeria",
     "address": "15 Zik Avenue, Awka, Anambra State",
     "phone": "+234 48 550 234", "website": "",
     "practice_areas": ["Litigation", "Family Law", "Criminal Law"],
     "google_rating": 3.9, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Nnamdi+Ike+Chambers+Awka"},
    {"name": "Uba & Eze Legal Practitioners", "city": "Onitsha", "state": "Anambra", "country": "Nigeria",
     "address": "10 Oguta Road, Onitsha",
     "phone": "+234 46 214 567", "website": "",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Real Estate"],
     "google_rating": 4.1, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Uba+Eze+Legal+Onitsha"},

    # ── Enugu State ───────────────────────────────────────────────────────────
    {"name": "Eze Onyekwere & Associates", "city": "Enugu", "state": "Enugu", "country": "Nigeria",
     "address": "12 Presidential Road, GRA, Enugu",
     "phone": "+234 42 257 890", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.1, "google_reviews_count": 7, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Eze+Onyekwere+Enugu"},
    {"name": "C.O. Nwobike & Co", "city": "Enugu", "state": "Enugu", "country": "Nigeria",
     "address": "27 Chime Avenue, New Haven, Enugu",
     "phone": "+234 42 303 456", "website": "",
     "practice_areas": ["Criminal Law", "Human Rights", "Litigation"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Nwobike+Enugu"},

    # ── Delta State ───────────────────────────────────────────────────────────
    {"name": "Okumagba & Lawani", "city": "Warri", "state": "Delta", "country": "Nigeria",
     "address": "14 Airport Road, Warri, Delta State",
     "phone": "+234 53 254 678", "website": "",
     "practice_areas": ["Oil & Gas", "Corporate & Commercial", "Litigation"],
     "google_rating": 4.2, "google_reviews_count": 9, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Okumagba+Lawani+Warri"},
    {"name": "Esiri & Co", "city": "Asaba", "state": "Delta", "country": "Nigeria",
     "address": "3 Nnebisi Road, Asaba, Delta State",
     "phone": "+234 56 281 234", "website": "",
     "practice_areas": ["Real Estate", "Corporate & Commercial", "Family Law"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Esiri+Co+Asaba"},

    # ── Edo State (Benin City) ────────────────────────────────────────────────
    {"name": "Osazemen Osaghae & Associates", "city": "Benin City", "state": "Edo", "country": "Nigeria",
     "address": "10 Mission Road, Benin City, Edo State",
     "phone": "+234 52 256 789", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Osaghae+Associates+Benin"},
    {"name": "Aiken & Aiken", "city": "Benin City", "state": "Edo", "country": "Nigeria",
     "address": "15 Sapele Road, Benin City",
     "phone": "+234 52 241 345", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aiken+Aiken+Benin+City"},

    # ── Kano State ────────────────────────────────────────────────────────────
    {"name": "Hassan Liman & Co", "city": "Kano", "state": "Kano", "country": "Nigeria",
     "address": "16 Bello Road, Kano Municipal, Kano",
     "phone": "+234 64 630 123", "website": "",
     "practice_areas": ["Litigation", "Commercial Law", "Criminal Law"],
     "google_rating": 4.1, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Hassan+Liman+Kano"},
    {"name": "Mustapha & Associates", "city": "Kano", "state": "Kano", "country": "Nigeria",
     "address": "47 Club Road, Kano G.R.A",
     "phone": "+234 64 312 789", "website": "",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Litigation"],
     "google_rating": 3.9, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Mustapha+Associates+Kano"},
    {"name": "Gambo Sule Law Chambers", "city": "Kano", "state": "Kano", "country": "Nigeria",
     "address": "9 Audu Bako Way, Kano",
     "phone": "+234 64 541 234", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Gambo+Sule+Kano"},

    # ── Kaduna State ──────────────────────────────────────────────────────────
    {"name": "Shehu Usman & Co", "city": "Kaduna", "state": "Kaduna", "country": "Nigeria",
     "address": "35 Constitution Road, Kaduna",
     "phone": "+234 62 240 567", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Criminal Law"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Shehu+Usman+Kaduna"},
    {"name": "Garba Dogo Chambers", "city": "Kaduna", "state": "Kaduna", "country": "Nigeria",
     "address": "12 Kachia Road, Kaduna South",
     "phone": "+234 62 319 012", "website": "",
     "practice_areas": ["Criminal Law", "Family Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Garba+Dogo+Kaduna"},
    {"name": "Alliance Law Firm Kaduna", "city": "Kaduna", "state": "Kaduna", "country": "Nigeria",
     "address": "Plot 31/32 Constitution Road, Kaduna",
     "phone": "+234 62 461 890", "website": "",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Real Estate"],
     "google_rating": 4.1, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Alliance+Law+Firm+Kaduna"},

    # ── Cross River State ─────────────────────────────────────────────────────
    {"name": "Henshaw & Associates", "city": "Calabar", "state": "Cross River", "country": "Nigeria",
     "address": "20 Calabar Road, Calabar, Cross River State",
     "phone": "+234 87 232 456", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Henshaw+Associates+Calabar"},
    {"name": "E.O. Ogar & Co", "city": "Calabar", "state": "Cross River", "country": "Nigeria",
     "address": "7 MCC Road, Calabar",
     "phone": "+234 87 231 789", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ogar+Co+Calabar"},

    # ── Akwa Ibom State ───────────────────────────────────────────────────────
    {"name": "Etuk Chambers", "city": "Uyo", "state": "Akwa Ibom", "country": "Nigeria",
     "address": "Plot 6, Ikot Ekpene Road, Uyo",
     "phone": "+234 85 201 456", "website": "",
     "practice_areas": ["Oil & Gas", "Corporate & Commercial", "Litigation"],
     "google_rating": 4.1, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Etuk+Chambers+Uyo"},
    {"name": "Inyang Usoro & Co", "city": "Uyo", "state": "Akwa Ibom", "country": "Nigeria",
     "address": "38 Abak Road, Uyo, Akwa Ibom",
     "phone": "+234 85 202 567", "website": "",
     "practice_areas": ["Litigation", "Family Law", "Real Estate"],
     "google_rating": 3.9, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Inyang+Usoro+Uyo"},

    # ── Ogun State ────────────────────────────────────────────────────────────
    {"name": "Dada Agboola & Co", "city": "Abeokuta", "state": "Ogun", "country": "Nigeria",
     "address": "5 Idi-Aba Road, Abeokuta, Ogun State",
     "phone": "+234 39 241 234", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Dada+Agboola+Abeokuta"},
    {"name": "Wemimo Olatunji & Co", "city": "Sagamu", "state": "Ogun", "country": "Nigeria",
     "address": "12 Ogidan Road, Sagamu, Ogun State",
     "phone": "+234 37 640 789", "website": "",
     "practice_areas": ["Family Law", "Real Estate", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Olatunji+Sagamu"},

    # ── Osun State ────────────────────────────────────────────────────────────
    {"name": "Yusuf Alli & Co", "city": "Osogbo", "state": "Osun", "country": "Nigeria",
     "address": "15 Gbongan Road, Osogbo, Osun State",
     "phone": "+234 35 241 567", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Criminal Law"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Yusuf+Alli+Osogbo"},
    {"name": "Adeyemi & Associates Osogbo", "city": "Osogbo", "state": "Osun", "country": "Nigeria",
     "address": "3 Station Road, Osogbo",
     "phone": "+234 35 242 789", "website": "",
     "practice_areas": ["Family Law", "Real Estate", "Litigation"],
     "google_rating": 3.7, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Adeyemi+Associates+Osogbo"},

    # ── Ekiti State ───────────────────────────────────────────────────────────
    {"name": "Kayode Ojo & Co", "city": "Ado-Ekiti", "state": "Ekiti", "country": "Nigeria",
     "address": "7 Government House Road, Ado-Ekiti",
     "phone": "+234 30 250 234", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Real Estate"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Kayode+Ojo+Ado+Ekiti"},
    {"name": "Aribisala Chambers", "city": "Ado-Ekiti", "state": "Ekiti", "country": "Nigeria",
     "address": "10 Ado-Iworoko Road, Ado-Ekiti",
     "phone": "+234 30 251 567", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aribisala+Chambers+Ekiti"},

    # ── Kwara State ───────────────────────────────────────────────────────────
    {"name": "Saka Isau & Co", "city": "Ilorin", "state": "Kwara", "country": "Nigeria",
     "address": "22 Fate Road, Ilorin, Kwara State",
     "phone": "+234 31 221 456", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Saka+Isau+Ilorin"},
    {"name": "Sulyman Abdulkadir & Co", "city": "Ilorin", "state": "Kwara", "country": "Nigeria",
     "address": "4 Bank Road, Ilorin",
     "phone": "+234 31 220 789", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Sulyman+Abdulkadir+Ilorin"},

    # ── Imo State ─────────────────────────────────────────────────────────────
    {"name": "Ihejirika & Associates", "city": "Owerri", "state": "Imo", "country": "Nigeria",
     "address": "14 Wetheral Road, Owerri, Imo State",
     "phone": "+234 83 231 456", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ihejirika+Associates+Owerri"},
    {"name": "Ogbonnaya Onu Legal", "city": "Owerri", "state": "Imo", "country": "Nigeria",
     "address": "7 Control Post Road, Owerri",
     "phone": "+234 83 460 234", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ogbonnaya+Onu+Owerri"},

    # ── Abia State ────────────────────────────────────────────────────────────
    {"name": "Okereke & Onyekachi", "city": "Umuahia", "state": "Abia", "country": "Nigeria",
     "address": "9 Library Avenue, Umuahia, Abia State",
     "phone": "+234 88 220 567", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Family Law"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Okereke+Onyekachi+Umuahia"},
    {"name": "Nnanna Njoku & Co", "city": "Aba", "state": "Abia", "country": "Nigeria",
     "address": "25 Aba-Owerri Road, Aba, Abia State",
     "phone": "+234 82 228 901", "website": "",
     "practice_areas": ["Real Estate", "Corporate & Commercial", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Nnanna+Njoku+Aba"},

    # ── Plateau State ─────────────────────────────────────────────────────────
    {"name": "Gyang Pwol & Associates", "city": "Jos", "state": "Plateau", "country": "Nigeria",
     "address": "5 Yakubu Gowon Way, Jos, Plateau State",
     "phone": "+234 73 452 678", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Mining Law"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Gyang+Pwol+Jos"},
    {"name": "Daniel Dalyop Chambers", "city": "Jos", "state": "Plateau", "country": "Nigeria",
     "address": "13 Murtala Muhammed Way, Jos",
     "phone": "+234 73 450 901", "website": "",
     "practice_areas": ["Criminal Law", "Litigation", "Family Law"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Daniel+Dalyop+Jos"},

    # ── Bauchi State ──────────────────────────────────────────────────────────
    {"name": "Aliyu Mohammed & Co", "city": "Bauchi", "state": "Bauchi", "country": "Nigeria",
     "address": "18 Maiduguri Road, Bauchi",
     "phone": "+234 77 542 234", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Corporate & Commercial"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aliyu+Mohammed+Bauchi"},
    {"name": "Ahmad Umar Chambers", "city": "Bauchi", "state": "Bauchi", "country": "Nigeria",
     "address": "7 Yelwa Road, Bauchi",
     "phone": "+234 77 541 567", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ahmad+Umar+Chambers+Bauchi"},

    # ── Borno State ───────────────────────────────────────────────────────────
    {"name": "Mohammed Goni & Associates", "city": "Maiduguri", "state": "Borno", "country": "Nigeria",
     "address": "22 Stadium Road, Maiduguri, Borno State",
     "phone": "+234 76 232 345", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Human Rights"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Mohammed+Goni+Maiduguri"},
    {"name": "Bulama Ibrahim & Co", "city": "Maiduguri", "state": "Borno", "country": "Nigeria",
     "address": "5 Ali Monguno Road, Maiduguri",
     "phone": "+234 76 231 678", "website": "",
     "practice_areas": ["Family Law", "Corporate & Commercial", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Bulama+Ibrahim+Maiduguri"},

    # ── Sokoto State ──────────────────────────────────────────────────────────
    {"name": "Mahe Umar & Co", "city": "Sokoto", "state": "Sokoto", "country": "Nigeria",
     "address": "11 Sultan Abubakar Road, Sokoto",
     "phone": "+234 60 234 567", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Corporate & Commercial"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Mahe+Umar+Sokoto"},
    {"name": "Faruk Idris Chambers", "city": "Sokoto", "state": "Sokoto", "country": "Nigeria",
     "address": "Fodio Road, Sokoto",
     "phone": "+234 60 235 890", "website": "",
     "practice_areas": ["Family Law", "Real Estate", "Litigation"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Faruk+Idris+Sokoto"},

    # ── Kebbi State ───────────────────────────────────────────────────────────
    {"name": "Aminu Salihu & Co", "city": "Birnin Kebbi", "state": "Kebbi", "country": "Nigeria",
     "address": "15 Gwandu Road, Birnin Kebbi",
     "phone": "+234 68 321 234", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aminu+Salihu+Birnin+Kebbi"},

    # ── Zamfara State ─────────────────────────────────────────────────────────
    {"name": "Garba Anka Legal", "city": "Gusau", "state": "Zamfara", "country": "Nigeria",
     "address": "7 Emir Palace Road, Gusau, Zamfara",
     "phone": "+234 63 201 456", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Garba+Anka+Gusau"},

    # ── Katsina State ─────────────────────────────────────────────────────────
    {"name": "Isyaku Babba & Associates", "city": "Katsina", "state": "Katsina", "country": "Nigeria",
     "address": "Sultan Ibrahim Dikko Road, Katsina",
     "phone": "+234 65 432 789", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Corporate & Commercial"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Isyaku+Babba+Katsina"},

    # ── Jigawa State ──────────────────────────────────────────────────────────
    {"name": "Yahaya Danmashi Chambers", "city": "Dutse", "state": "Jigawa", "country": "Nigeria",
     "address": "Emir's Palace Road, Dutse, Jigawa",
     "phone": "+234 64 721 234", "website": "",
     "practice_areas": ["Family Law", "Litigation", "Criminal Law"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Yahaya+Danmashi+Dutse"},

    # ── Adamawa State ─────────────────────────────────────────────────────────
    {"name": "Bagudu Hassan & Co", "city": "Yola", "state": "Adamawa", "country": "Nigeria",
     "address": "18 Jam Lawal Road, Yola, Adamawa State",
     "phone": "+234 75 624 567", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Criminal Law"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Bagudu+Hassan+Yola"},

    # ── Gombe State ───────────────────────────────────────────────────────────
    {"name": "Usman Goje Chambers", "city": "Gombe", "state": "Gombe", "country": "Nigeria",
     "address": "5 Alfa Jibia Road, Gombe",
     "phone": "+234 72 221 678", "website": "",
     "practice_areas": ["Criminal Law", "Family Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Usman+Goje+Gombe"},

    # ── Taraba State ──────────────────────────────────────────────────────────
    {"name": "Danladi Musa & Associates", "city": "Jalingo", "state": "Taraba", "country": "Nigeria",
     "address": "3 Hammaruwa Way, Jalingo, Taraba",
     "phone": "+234 79 221 345", "website": "",
     "practice_areas": ["Litigation", "Criminal Law", "Family Law"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Danladi+Musa+Jalingo"},

    # ── Yobe State ────────────────────────────────────────────────────────────
    {"name": "Ibrahim Geidam Legal", "city": "Damaturu", "state": "Yobe", "country": "Nigeria",
     "address": "Bama Road, Damaturu, Yobe State",
     "phone": "+234 74 621 234", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ibrahim+Geidam+Damaturu"},

    # ── Nasarawa State ────────────────────────────────────────────────────────
    {"name": "Agabi & Agabi Legal", "city": "Lafia", "state": "Nasarawa", "country": "Nigeria",
     "address": "12 Shendam Road, Lafia, Nasarawa",
     "phone": "+234 47 221 456", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Real Estate"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Agabi+Agabi+Lafia"},

    # ── Niger State ───────────────────────────────────────────────────────────
    {"name": "Bello Minna & Co", "city": "Minna", "state": "Niger", "country": "Nigeria",
     "address": "15 Tudun Wada Road, Minna, Niger State",
     "phone": "+234 66 221 789", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Bello+Minna+Minna"},
    {"name": "Yakubu Tanko Chambers", "city": "Minna", "state": "Niger", "country": "Nigeria",
     "address": "7 Paiko Road, Minna",
     "phone": "+234 66 220 567", "website": "",
     "practice_areas": ["Criminal Law", "Family Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Yakubu+Tanko+Minna"},

    # ── Kogi State ────────────────────────────────────────────────────────────
    {"name": "Bello Fagbemi & Co", "city": "Lokoja", "state": "Kogi", "country": "Nigeria",
     "address": "22 Ganaja Road, Lokoja, Kogi State",
     "phone": "+234 58 220 456", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Mining Law"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Bello+Fagbemi+Lokoja"},
    {"name": "Yusuf Ohere Chambers", "city": "Lokoja", "state": "Kogi", "country": "Nigeria",
     "address": "5 Murtala Mohammed Way, Lokoja",
     "phone": "+234 58 221 789", "website": "",
     "practice_areas": ["Criminal Law", "Family Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Yusuf+Ohere+Lokoja"},

    # ── Benue State ───────────────────────────────────────────────────────────
    {"name": "Dooshima Iorhemen & Associates", "city": "Makurdi", "state": "Benue", "country": "Nigeria",
     "address": "11 Ahmadu Bello Way, Makurdi, Benue State",
     "phone": "+234 44 533 456", "website": "",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Dooshima+Iorhemen+Makurdi"},
    {"name": "Tsor Orbunde Legal", "city": "Makurdi", "state": "Benue", "country": "Nigeria",
     "address": "3 Wurukum Road, Makurdi",
     "phone": "+234 44 533 789", "website": "",
     "practice_areas": ["Family Law", "Criminal Law", "Litigation"],
     "google_rating": 3.8, "google_reviews_count": 3, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Tsor+Orbunde+Makurdi"},

    # ── Ebonyi State ──────────────────────────────────────────────────────────
    {"name": "Nweze & Nwankpa", "city": "Abakaliki", "state": "Ebonyi", "country": "Nigeria",
     "address": "6 Bishop Shanahan Road, Abakaliki",
     "phone": "+234 43 221 234", "website": "",
     "practice_areas": ["Litigation", "Family Law", "Corporate & Commercial"],
     "google_rating": 3.9, "google_reviews_count": 4, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Nweze+Nwankpa+Abakaliki"},
    {"name": "Ominyi Okolo Chambers", "city": "Abakaliki", "state": "Ebonyi", "country": "Nigeria",
     "address": "10 Ogoja Road, Abakaliki, Ebonyi",
     "phone": "+234 43 220 567", "website": "",
     "practice_areas": ["Criminal Law", "Litigation", "Real Estate"],
     "google_rating": 3.7, "google_reviews_count": 2, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Ominyi+Okolo+Abakaliki"},

    # ── Bayelsa State ─────────────────────────────────────────────────────────
    {"name": "Tonye Ibanibo & Co", "city": "Yenagoa", "state": "Bayelsa", "country": "Nigeria",
     "address": "14 Isaac Jasper Boro Way, Yenagoa",
     "phone": "+234 89 560 234", "website": "",
     "practice_areas": ["Oil & Gas", "Litigation", "Environmental Law"],
     "google_rating": 4.1, "google_reviews_count": 6, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Tonye+Ibanibo+Yenagoa"},
    {"name": "Peremobowei Ogan Chambers", "city": "Yenagoa", "state": "Bayelsa", "country": "Nigeria",
     "address": "7 Melford Okilo Road, Yenagoa",
     "phone": "+234 89 561 567", "website": "",
     "practice_areas": ["Oil & Gas", "Environmental Law", "Litigation"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Peremobowei+Ogan+Yenagoa"},

    # ── Ondo State ────────────────────────────────────────────────────────────
    {"name": "Adesanya & Co Ondo", "city": "Akure", "state": "Ondo", "country": "Nigeria",
     "address": "25 Oba Adesida Road, Akure, Ondo State",
     "phone": "+234 34 241 789", "website": "",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Real Estate"],
     "google_rating": 4.0, "google_reviews_count": 5, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Adesanya+Co+Akure"},

    # ── Ghana — Accra & Kumasi ────────────────────────────────────────────────
    {"name": "Reindorf Chambers", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "25 Castle Road, Accra, Ghana",
     "phone": "+233 30 266 2100", "website": "https://www.reindorfchambers.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Banking & Finance"],
     "google_rating": 4.8, "google_reviews_count": 67, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Reindorf+Chambers+Accra"},
    {"name": "Bentsi-Enchill Letsa & Ankomah", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "Bentsi-Enchill House, Plot 8, Airport City, Accra",
     "phone": "+233 30 277 6100", "website": "https://www.bela.com.gh",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Energy Law"],
     "google_rating": 4.7, "google_reviews_count": 51, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Bentsi+Enchill+Accra"},
    {"name": "Sam Okudzeto & Associates", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "Royal Caribbean House, Liberation Road, Accra",
     "phone": "+233 30 221 6870", "website": "https://www.samokudzeto.com",
     "practice_areas": ["Litigation", "Human Rights", "Criminal Law"],
     "google_rating": 4.6, "google_reviews_count": 34, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Sam+Okudzeto+Accra"},
    {"name": "Sustineri Attorneys", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "5th Floor, Movenpick Hotel, Accra",
     "phone": "+233 30 296 7000", "website": "https://www.sustineri.com",
     "practice_areas": ["Technology Law", "Intellectual Property", "Corporate & Commercial"],
     "google_rating": 4.7, "google_reviews_count": 28, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Sustineri+Attorneys+Accra"},
    {"name": "B&B Legal Consult", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "Accra Mall Annex, Spintex Road, Accra",
     "phone": "+233 24 443 5678", "website": "",
     "practice_areas": ["Real Estate", "Family Law", "Litigation"],
     "google_rating": 4.3, "google_reviews_count": 15, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=B+B+Legal+Accra"},
    {"name": "F&A Chambers", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "3rd Floor, Fiesta Royale Hotel, North Ridge, Accra",
     "phone": "+233 30 254 9000", "website": "",
     "practice_areas": ["Corporate & Commercial", "Immigration", "Employment & Labour"],
     "google_rating": 4.2, "google_reviews_count": 11, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=F+A+Chambers+Accra"},
    {"name": "Kimathi & Partners Corporate Attorneys", "city": "Accra", "state": "Greater Accra", "country": "Ghana",
     "address": "Accra Financial Centre, Independence Avenue, Accra",
     "phone": "+233 30 290 1234", "website": "https://www.kimathipartners.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Mergers & Acquisitions"],
     "google_rating": 4.6, "google_reviews_count": 39, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Kimathi+Partners+Accra"},
    {"name": "Paa Kwame & Associates", "city": "Kumasi", "state": "Ashanti", "country": "Ghana",
     "address": "35 Harper Road, Adum, Kumasi",
     "phone": "+233 32 202 4567", "website": "",
     "practice_areas": ["Real Estate", "Litigation", "Criminal Law"],
     "google_rating": 4.0, "google_reviews_count": 9, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Paa+Kwame+Kumasi"},
    {"name": "Aryeetey & Partners", "city": "Kumasi", "state": "Ashanti", "country": "Ghana",
     "address": "Lake Road, Nhyiaeso, Kumasi",
     "phone": "+233 32 202 8900", "website": "",
     "practice_areas": ["Corporate & Commercial", "Family Law", "Real Estate"],
     "google_rating": 4.1, "google_reviews_count": 12, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Aryeetey+Partners+Kumasi"},
    {"name": "GLC Legal Group", "city": "Takoradi", "state": "Western", "country": "Ghana",
     "address": "Takoradi Market Circle, Western Region, Ghana",
     "phone": "+233 31 220 1234", "website": "",
     "practice_areas": ["Oil & Gas", "Environmental Law", "Corporate & Commercial"],
     "google_rating": 4.2, "google_reviews_count": 14, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=GLC+Legal+Takoradi"},

    # ── United States — New York ──────────────────────────────────────────────
    {"name": "Sullivan & Cromwell LLP", "city": "New York", "state": "New York", "country": "United States",
     "address": "125 Broad Street, New York, NY 10004",
     "phone": "+1 212 558 4000", "website": "https://www.sullcrom.com",
     "practice_areas": ["Mergers & Acquisitions", "Corporate & Commercial", "Banking & Finance"],
     "google_rating": 4.6, "google_reviews_count": 88, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Sullivan+Cromwell+New+York"},
    {"name": "Skadden Arps Slate Meagher & Flom", "city": "New York", "state": "New York", "country": "United States",
     "address": "One Manhattan West, New York, NY 10001",
     "phone": "+1 212 735 3000", "website": "https://www.skadden.com",
     "practice_areas": ["Mergers & Acquisitions", "Corporate & Commercial", "Litigation"],
     "google_rating": 4.8, "google_reviews_count": 142, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Skadden+Arps+New+York"},
    {"name": "Davis Polk & Wardwell LLP", "city": "New York", "state": "New York", "country": "United States",
     "address": "450 Lexington Avenue, New York, NY 10017",
     "phone": "+1 212 450 4000", "website": "https://www.davispolk.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Mergers & Acquisitions"],
     "google_rating": 4.7, "google_reviews_count": 104, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Davis+Polk+New+York"},
    {"name": "Debevoise & Plimpton LLP", "city": "New York", "state": "New York", "country": "United States",
     "address": "66 Hudson Boulevard East, New York, NY 10001",
     "phone": "+1 212 909 6000", "website": "https://www.debevoise.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Banking & Finance"],
     "google_rating": 4.6, "google_reviews_count": 76, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Debevoise+Plimpton+New+York"},
    {"name": "Cleary Gottlieb Steen & Hamilton", "city": "New York", "state": "New York", "country": "United States",
     "address": "One Liberty Plaza, New York, NY 10006",
     "phone": "+1 212 225 2000", "website": "https://www.clearygottlieb.com",
     "practice_areas": ["Corporate & Commercial", "Mergers & Acquisitions", "Banking & Finance"],
     "google_rating": 4.7, "google_reviews_count": 92, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Cleary+Gottlieb+New+York"},

    # ── United States — California ────────────────────────────────────────────
    {"name": "O'Melveny & Myers LLP", "city": "Los Angeles", "state": "California", "country": "United States",
     "address": "400 S Hope Street, Los Angeles, CA 90071",
     "phone": "+1 213 430 6000", "website": "https://www.omm.com",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Mergers & Acquisitions"],
     "google_rating": 4.5, "google_reviews_count": 65, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=OMelveny+Myers+Los+Angeles"},
    {"name": "Gibson Dunn & Crutcher LLP", "city": "Los Angeles", "state": "California", "country": "United States",
     "address": "333 S Grand Avenue, Los Angeles, CA 90071",
     "phone": "+1 213 229 7000", "website": "https://www.gibsondunn.com",
     "practice_areas": ["Corporate & Commercial", "Mergers & Acquisitions", "Litigation"],
     "google_rating": 4.7, "google_reviews_count": 87, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Gibson+Dunn+Los+Angeles"},
    {"name": "Wilson Sonsini Goodrich & Rosati", "city": "Palo Alto", "state": "California", "country": "United States",
     "address": "650 Page Mill Road, Palo Alto, CA 94304",
     "phone": "+1 650 493 9300", "website": "https://www.wsgr.com",
     "practice_areas": ["Technology Law", "Corporate & Commercial", "Intellectual Property"],
     "google_rating": 4.6, "google_reviews_count": 71, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Wilson+Sonsini+Palo+Alto"},
    {"name": "Cooley LLP", "city": "San Francisco", "state": "California", "country": "United States",
     "address": "3 Embarcadero Center, 20th Floor, San Francisco, CA 94111",
     "phone": "+1 415 693 2000", "website": "https://www.cooley.com",
     "practice_areas": ["Technology Law", "Corporate & Commercial", "Mergers & Acquisitions"],
     "google_rating": 4.5, "google_reviews_count": 58, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Cooley+San+Francisco"},

    # ── United States — Texas ─────────────────────────────────────────────────
    {"name": "Vinson & Elkins LLP", "city": "Houston", "state": "Texas", "country": "United States",
     "address": "845 Texas Avenue, Suite 4700, Houston, TX 77002",
     "phone": "+1 713 758 2222", "website": "https://www.velaw.com",
     "practice_areas": ["Oil & Gas", "Energy Law", "Corporate & Commercial"],
     "google_rating": 4.6, "google_reviews_count": 54, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Vinson+Elkins+Houston"},
    {"name": "Baker Botts LLP", "city": "Houston", "state": "Texas", "country": "United States",
     "address": "910 Louisiana Street, Houston, TX 77002",
     "phone": "+1 713 229 1234", "website": "https://www.bakerbotts.com",
     "practice_areas": ["Oil & Gas", "Corporate & Commercial", "Litigation"],
     "google_rating": 4.5, "google_reviews_count": 48, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Baker+Botts+Houston"},
    {"name": "Jackson Walker LLP", "city": "Dallas", "state": "Texas", "country": "United States",
     "address": "2323 Ross Ave, Suite 600, Dallas, TX 75201",
     "phone": "+1 214 953 6000", "website": "https://www.jw.com",
     "practice_areas": ["Corporate & Commercial", "Real Estate", "Litigation"],
     "google_rating": 4.4, "google_reviews_count": 37, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Jackson+Walker+Dallas"},

    # ── United States — Washington D.C. ──────────────────────────────────────
    {"name": "Arnold & Porter Kaye Scholer LLP", "city": "Washington", "state": "Washington D.C.", "country": "United States",
     "address": "601 Massachusetts Ave NW, Washington, DC 20001",
     "phone": "+1 202 942 5000", "website": "https://www.arnoldporter.com",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Healthcare Law"],
     "google_rating": 4.5, "google_reviews_count": 62, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Arnold+Porter+Washington+DC"},
    {"name": "Covington & Burling LLP", "city": "Washington", "state": "Washington D.C.", "country": "United States",
     "address": "One CityCenter, 850 10th St NW, Washington, DC 20001",
     "phone": "+1 202 662 6000", "website": "https://www.cov.com",
     "practice_areas": ["Litigation", "Corporate & Commercial", "Immigration"],
     "google_rating": 4.6, "google_reviews_count": 71, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Covington+Burling+Washington+DC"},

    # ── Ondo / Warri area extension ───────────────────────────────────────────
    {"name": "Lafe Okafor & Associates", "city": "Warri", "state": "Delta", "country": "Nigeria",
     "address": "7 Effurun Road, Warri, Delta State",
     "phone": "+234 53 255 901", "website": "",
     "practice_areas": ["Oil & Gas", "Maritime Law", "Environmental Law"],
     "google_rating": 4.1, "google_reviews_count": 7, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Lafe+Okafor+Warri"},

    # ── Tech Law / IP focused (Lagos/Abuja) ───────────────────────────────────
    {"name": "IPLink Legal", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "Plot 6 Commercial Avenue, Sabo, Yaba, Lagos",
     "phone": "+234 1 342 1100", "website": "https://www.iplinkng.com",
     "practice_areas": ["Intellectual Property", "Technology Law", "Corporate & Commercial"],
     "google_rating": 4.4, "google_reviews_count": 18, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=IPLink+Legal+Lagos"},
    {"name": "Lex Artifex LLP", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "62A Isaacs Road, Off Adeola Odeku, Victoria Island, Lagos",
     "phone": "+234 803 979 5959", "website": "https://www.lexartifexllp.com",
     "practice_areas": ["Technology Law", "Intellectual Property", "Corporate & Commercial"],
     "google_rating": 4.5, "google_reviews_count": 24, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Lex+Artifex+Lagos"},
    {"name": "Tope Adebayo LP", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "9A Karimu Kotun Street, Victoria Island, Lagos",
     "phone": "+234 1 461 9600", "website": "https://www.topelp.com",
     "practice_areas": ["Corporate & Commercial", "Banking & Finance", "Technology Law"],
     "google_rating": 4.5, "google_reviews_count": 21, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Tope+Adebayo+Lagos"},

    # ── Family / Employment specialists ───────────────────────────────────────
    {"name": "Babalakin & Co", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "142 Ahmadu Bello Way, Victoria Island, Lagos",
     "phone": "+234 1 461 9500", "website": "https://www.babalakinco.com",
     "practice_areas": ["Corporate & Commercial", "Litigation", "Employment & Labour"],
     "google_rating": 4.6, "google_reviews_count": 34, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Babalakin+Co+Lagos"},
    {"name": "Okpoko & Partners", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1193 Mississippi Street, Maitama, Abuja",
     "phone": "+234 9 413 8900", "website": "",
     "practice_areas": ["Employment & Labour", "Human Rights", "Litigation"],
     "google_rating": 4.2, "google_reviews_count": 10, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Okpoko+Partners+Abuja"},

    # ── Real Estate specialists ───────────────────────────────────────────────
    {"name": "Brickfield Road Legal Centre", "city": "Lagos", "state": "Lagos", "country": "Nigeria",
     "address": "4 Brickfield Road, Adeola Odeku, Victoria Island, Lagos",
     "phone": "+234 1 461 8800", "website": "https://www.brickfieldlegal.com",
     "practice_areas": ["Real Estate", "Corporate & Commercial", "Banking & Finance"],
     "google_rating": 4.3, "google_reviews_count": 16, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Brickfield+Road+Legal+Lagos"},
    {"name": "Medici Partners", "city": "Abuja", "state": "FCT Abuja", "country": "Nigeria",
     "address": "Plot 1205, Cadastral Zone, Wuse II, Abuja",
     "phone": "+234 9 461 7700", "website": "",
     "practice_areas": ["Real Estate", "Corporate & Commercial", "Tax Law"],
     "google_rating": 4.3, "google_reviews_count": 13, "source": "google_maps",
     "google_maps_url": "https://maps.google.com/?q=Medici+Partners+Abuja"},
]


@dir_admin_bp.route('/robot')
@require_super_admin
def robot_dashboard():
    """Discovery robots dashboard."""
    from models import SocialCommunity
    from blueprints.social_communities import _SEED_COMMUNITIES
    already_added = DirectoryLawFirm.query.count()
    community_count = SocialCommunity.query.count()
    return render_template('directory_admin/robot.html',
                           already_added=already_added,
                           seed_count=len(_SEED_FIRMS),
                           community_count=community_count,
                           community_seed=len(_SEED_COMMUNITIES))


@dir_admin_bp.route('/external/<int:firm_id>/generate-pitch', methods=['POST'])
@require_super_admin
def generate_pitch(firm_id):
    """Generate AI email pitch + call script for a single firm."""
    import os
    import requests as req_lib
    firm = DirectoryLawFirm.query.get_or_404(firm_id)

    openai_key = os.environ.get('OPENAI_API_KEY', '')
    areas = ', '.join(firm.practice_areas[:4]) if firm.practice_areas else 'legal practice'
    city  = firm.city or firm.country or 'your area'
    has_web = 'Yes' if firm.has_website else 'No (no existing website)'
    social  = json.dumps(firm.social_links) if firm.social_links else 'none found'
    gmb_status = 'Unverified GMB listing' if not firm.gmb_verified else 'Verified GMB listing'
    reviews = f"{firm.google_reviews_count} Google reviews, {firm.google_rating}★" if firm.google_rating else 'no Google rating found'

    _LAWCOLAB_FEATURES = """
LAWCOLAB features:
• Case & Matter Management — track every case, deadline, and document
• Client Portal — clients get 24/7 secure online access to their case updates
• Billing & Invoicing — instant invoice generation, payment tracking, receipts
• Court Calendar — deadline reminders, hearing alerts, court date history
• Team Collaboration — task assignment, internal messaging, document sharing
• Analytics Dashboard — firm performance, revenue, case statistics at a glance
• Client Acquisition Tools — digital intake forms, referral tracking, leads
• Integrations — works alongside existing websites, email, and firm tools
• Custom Feature Development — our developer team builds features on request
• Mobile-Friendly — works on any device, anywhere
"""

    if openai_key:
        try:
            # Email pitch
            prompt_email = f"""You are a top legal software sales writer for LAWCOLAB.

Write a personalized cold-outreach email to this law firm to pitch LAWCOLAB:
- Firm: {firm.name}
- Location: {city}, {firm.state or ''}, {firm.country or 'Nigeria'}
- Practice Areas: {areas}
- Website: {has_web}
- Social Media: {social}
- Google Maps status: {gmb_status}
- Google presence: {reviews}
- Source: Found on Google Maps / public directory

{_LAWCOLAB_FEATURES}

Email structure:
1. Warm, specific greeting referencing how you found them (Google Maps / directory, mention their location/speciality)
2. Brief intro of LAWCOLAB as a Legal Operating System
3. List 4-5 features most relevant to their practice area
4. Emphasize: works WITH or WITHOUT their existing website / current systems
5. Highlight: our developer team readily adds new custom features for their firm
6. Emphasize how LAWCOLAB helps them acquire more clients and grow revenue
7. Clear CTA: free trial / 20-min demo call at https://lawcolab.com
8. Professional sign-off from "LAWCOLAB Growth Team"

Rules:
- Reference their specific practice areas and location naturally
- If no website — position LAWCOLAB as the solution to their digital presence gap
- If unverified GMB — mention we can help them look more professional online
- Sound personal and research-based, never generic or spammy
- Concise and professional: 250-350 words max

Return JSON: {{"subject": "...", "body": "..."}}"""

            r1 = req_lib.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                json={'model': 'gpt-4o-mini', 'messages': [{'role': 'user', 'content': prompt_email}],
                      'response_format': {'type': 'json_object'}, 'max_tokens': 700, 'temperature': 0.82},
                timeout=25,
            )
            email_result = json.loads(r1.json()['choices'][0]['message']['content'])

            # Call script
            prompt_call = f"""You are a legal software sales trainer for LAWCOLAB.

Write a complete phone call script for calling this law firm cold:
- Firm: {firm.name}
- Location: {city}, {firm.state or ''}, {firm.country or 'Nigeria'}
- Practice Areas: {areas}
- Website: {has_web}
- Google status: {gmb_status} — {reviews}

{_LAWCOLAB_FEATURES}

Script structure (use clear headers):
1. OPENING — Warm greeting, introduce yourself by name as "from LAWCOLAB team", state you're calling because you came across their firm on Google Maps / online directories
2. PERMISSION CHECK — Ask if they have 2 minutes (respect their time)
3. PROBLEM STATEMENT — Reference a specific pain most law firms in {city} face (managing cases, billing manually, missing deadlines, no client portal)
4. SOLUTION INTRO — Briefly introduce LAWCOLAB as a legal operating system built for Nigerian / African law firms
5. KEY FEATURES — Mention 3-4 features most relevant to {areas} practice
6. WEBSITE BRIDGE — Whether or not they have a website, LAWCOLAB integrates with their current setup
7. CUSTOM DEVELOPMENT — Mention our developer team can add features specific to their firm
8. SOCIAL PROOF — Mention firms using LAWCOLAB improved client retention and billing efficiency
9. CTA — Offer a free 20-minute screen-share demo, ask for a good time
10. OBJECTION HANDLERS — 3 common objections with confident, respectful responses
11. CLOSING — Thank them, confirm next step, share website https://lawcolab.com

Keep each section practical. Use [PAUSE], [LISTEN], [SMILE] stage directions where helpful."""

            r2 = req_lib.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                json={'model': 'gpt-4o-mini', 'messages': [{'role': 'user', 'content': prompt_call}],
                      'max_tokens': 900, 'temperature': 0.75},
                timeout=25,
            )
            call_script = r2.json()['choices'][0]['message']['content']

        except Exception as e:
            email_result, call_script = _build_template_pitch(firm, areas, city, has_web, gmb_status)
    else:
        email_result, call_script = _build_template_pitch(firm, areas, city, has_web, gmb_status)

    firm.ai_pitch_email = f"Subject: {email_result.get('subject','')}\n\n{email_result.get('body','')}"
    firm.ai_call_script = call_script
    firm.ai_pitch_generated_at = datetime.now()
    db.session.commit()

    return jsonify({
        'success': True,
        'email_subject': email_result.get('subject', ''),
        'email_body': email_result.get('body', ''),
        'call_script': call_script,
    })


def _build_template_pitch(firm, areas, city, has_web, gmb_status):
    """Fallback template pitch when OpenAI is not configured."""
    name = firm.name
    no_web_line = (
        "\n\nI also noticed your firm doesn't yet have a dedicated website — LAWCOLAB "
        "includes a built-in client portal and public profile page, giving you a professional "
        "digital presence from day one."
        if not firm.has_website else ""
    )
    unverified_line = (
        "\n\nI noticed your Google Maps listing appears unverified — LAWCOLAB helps your firm "
        "look polished and credible online, which directly impacts how potential clients find you."
        if not firm.gmb_verified else ""
    )

    email_body = f"""Dear {name} Team,

I came across {name} while researching law firms in {city} on Google Maps and public directories — your reputation in {areas} caught my attention.

My name is [Your Name] from the LAWCOLAB team. We've built LAWCOLAB — a modern Legal Operating System designed specifically for law firms like yours to run like world-class businesses.

Here's what LAWCOLAB can do for {name}:
• 📁 Case Management — track every matter, deadline, and document in one place
• 👥 Client Portal — clients get 24/7 secure online access to their case updates
• 💰 Billing & Invoicing — generate invoices instantly, track every payment
• 📅 Court Calendar — never miss a hearing with smart deadline alerts
• 📊 Analytics — know your firm's revenue and performance at a glance
{no_web_line}{unverified_line}

Whether {name} already has an existing website and tools or is starting fresh, LAWCOLAB integrates seamlessly with your current setup — no disruption to your practice.

Our developer team is also on standby to add custom features tailored specifically to {name}'s workflow — helping you serve more clients and grow your firm's revenue.

I'd love to offer you a free 20-minute demo. No commitment required.

Would you be available for a quick call this week?

Best regards,
[Your Name]
LAWCOLAB Growth Team
https://lawcolab.com"""

    _divider = '\u2500' * 60
    _web_angle = 'No website \u2014 lead with digital presence angle' if not firm.has_website else 'Has website \u2014 lead with efficiency angle'
    if firm.has_website:
        _bridge = "'Even though you already have a website \u2014 LAWCOLAB integrates alongside it, adding the backend systems your firm needs to operate efficiently.'"
    else:
        _bridge = f"'I also noticed {name} doesn't yet have a dedicated website. LAWCOLAB includes a built-in public profile page and client portal \u2014 giving your firm a professional digital presence from day one, alongside all the practice management tools.'"

    call_script = f"""LAWCOLAB CALL SCRIPT \u2014 {name}
Location: {city} | Practice: {areas} | {gmb_status}
{_web_angle}
{_divider}

1. OPENING
"Good [morning/afternoon], may I please speak with the managing partner or firm administrator at {name}?"
[When connected]
"Hello, my name is [Your Name] calling from LAWCOLAB. I'm reaching out because I came across {name} on Google Maps while researching leading law firms in {city} \u2014 particularly in {areas}. I have a very quick question if you have two minutes?"
[PAUSE] [LISTEN]

2. PERMISSION CHECK
"I promise to be brief. Is now a good time for just two minutes?"
[If YES \u2192 continue. If NO \u2192 "No problem at all \u2014 when would be a better time to call back?"]

3. PROBLEM STATEMENT
"I speak with law firms in {city} daily, and the most common challenge I hear is managing cases, client follow-ups, and billing across different tools \u2014 often spreadsheets, WhatsApp, and manual invoices \u2014 which costs the firm hours every week and creates gaps."
[PAUSE] "Does that sound familiar at {name}?"
[LISTEN \u2014 note their response]

4. SOLUTION INTRO
"That's exactly why we built LAWCOLAB \u2014 a complete Legal Operating System for law firms. It brings case management, billing, client communication, and calendars into one platform designed specifically for firms like {name}."

5. KEY FEATURES FOR {areas.upper()}
"For a firm specialising in {areas}, the most valuable features are usually:
\u2014 Case tracking so nothing falls through the cracks
\u2014 Instant invoice generation with payment follow-ups built in
\u2014 A client portal so clients can check their case status anytime
\u2014 Court deadline alerts so you never miss a hearing date"

6. WEBSITE BRIDGE
{_bridge}

7. CUSTOM DEVELOPMENT
"What makes LAWCOLAB unique is that our developer team is always available to build features specific to your firm \u2014 if there's something you wish your current tools could do, we can add it."

8. SOCIAL PROOF
"Firms using LAWCOLAB report spending 60% less time on admin, billing more consistently, and \u2014 importantly \u2014 winning more clients because they present more professionally."

9. CALL TO ACTION
"I'd love to show you exactly what LAWCOLAB looks like for {name} \u2014 it's a free 20-minute screen-share, no commitment at all. What day works best for you this week?"
[PAUSE] [LISTEN]

10. OBJECTION HANDLERS
Q: "We already have a system."
\u2192 "That's great \u2014 LAWCOLAB works alongside your existing tools. Most firms tell us within 30 days they've consolidated everything into LAWCOLAB because it's so much simpler. Can I show you the integration in the demo?"

Q: "We're too busy right now."
\u2192 "I completely understand \u2014 that's actually why LAWCOLAB is so valuable. It's designed to save your team at least 5 hours a week by automating the admin work. The demo is only 20 minutes \u2014 would [specific day/time] work?"

Q: "We can't afford another software."
\u2192 "Totally fair question. LAWCOLAB starts at less than the cost of one billable hour per month \u2014 and most firms recover that in the first week from billing efficiency alone. I'd love to show you the ROI in the demo."

11. CLOSING
"Wonderful \u2014 I'll send a calendar invite to [their email] for [date/time]. The meeting link and a short overview of LAWCOLAB will be in the invite. Have a great day, and I look forward to speaking with you!"
[Note: follow up with intro email after the call]
Website: https://lawcolab.com"""

    return {'subject': f"Running {name} Like a World-Class Law Firm — LAWCOLAB", 'body': email_body}, call_script


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
