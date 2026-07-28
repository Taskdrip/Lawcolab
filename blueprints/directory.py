"""
Public Law Firm Directory — /directory
Smart, filterable directory of law firms on the LAWCOLAB platform
plus external firms discovered via the Google Maps robot.
"""
from flask import Blueprint, render_template, request, jsonify, abort
from app import db
from models import LawFirmShowcase, LawFirm, DirectoryLawFirm
from sqlalchemy import or_, func, desc
import json

directory_bp = Blueprint('directory', __name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

NIGERIAN_STATES = [
    'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue',
    'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu',
    'FCT Abuja', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina',
    'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo',
    'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara'
]

# Supported countries with their states/regions for the directory filter
COUNTRY_REGIONS = {
    'Nigeria': NIGERIAN_STATES,
    'Ghana': [
        'Ahafo', 'Ashanti', 'Bono', 'Bono East', 'Central',
        'Eastern', 'Greater Accra', 'North East', 'Northern', 'Oti',
        'Savannah', 'Upper East', 'Upper West', 'Volta', 'Western', 'Western North'
    ],
    'United States': [
        'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
        'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
        'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
        'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
        'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
        'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
        'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
        'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
        'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
        'West Virginia', 'Wisconsin', 'Wyoming', 'Washington D.C.'
    ],
    'United Kingdom': [
        'England', 'Scotland', 'Wales', 'Northern Ireland',
        'London', 'South East', 'South West', 'East of England',
        'East Midlands', 'West Midlands', 'Yorkshire', 'North West', 'North East'
    ],
    'South Africa': [
        'Eastern Cape', 'Free State', 'Gauteng', 'KwaZulu-Natal',
        'Limpopo', 'Mpumalanga', 'Northern Cape', 'North West', 'Western Cape'
    ],
    'Kenya': [
        'Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret',
        'Central', 'Coast', 'Eastern', 'North Eastern', 'Nyanza',
        'Rift Valley', 'Western'
    ],
}

ALL_COUNTRIES = list(COUNTRY_REGIONS.keys())

PRACTICE_AREA_LIST = [
    'Corporate & Commercial', 'Criminal Law', 'Family Law', 'Real Estate',
    'Employment & Labour', 'Intellectual Property', 'Tax Law', 'Immigration',
    'Banking & Finance', 'Oil & Gas', 'Maritime Law', 'Litigation',
    'Alternative Dispute Resolution', 'Human Rights', 'Technology Law',
    'Environmental Law', 'Healthcare Law', 'Aviation Law', 'Insurance Law',
    'Mergers & Acquisitions', 'Mining Law', 'Arbitration'
]

FIRM_SIZE_OPTIONS = [
    ('solo', 'Solo Practitioner'),
    ('small', 'Small (2–10 lawyers)'),
    ('mid', 'Mid-size (11–50 lawyers)'),
    ('large', 'Large (51–200 lawyers)'),
    ('biglaw', 'Big Law (200+ lawyers)'),
]

def _get_showcase_location_text(showcase):
    """Return a human-readable location for a showcase."""
    locs = showcase.locations
    if locs:
        primary = next((l for l in locs if l.get('is_primary')), locs[0])
        parts = [p for p in [primary.get('city'), primary.get('state'), primary.get('country')] if p]
        return ', '.join(parts)
    if showcase.law_firm and showcase.law_firm.address:
        return showcase.law_firm.address.split('\n')[0]
    return ''


# ── Public Routes ─────────────────────────────────────────────────────────────

@directory_bp.route('/')
def index():
    """Main directory page with filters and spotlight slider."""
    # Filters from query string
    search = request.args.get('q', '').strip()
    state_filter = request.args.get('state', '').strip()
    country_filter = request.args.get('country', '').strip()
    practice_filter = request.args.get('practice', '').strip()
    verified_only = request.args.get('verified', '') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = 12

    # ── Platform showcases (approved ones) ──
    q = LawFirmShowcase.query.filter_by(
        submission_status='approved',
        is_active=True
    ).join(LawFirm)

    if search:
        q = q.filter(
            or_(
                LawFirmShowcase.public_title.ilike(f'%{search}%'),
                LawFirmShowcase.public_description.ilike(f'%{search}%'),
                LawFirmShowcase.practice_areas_json.ilike(f'%{search}%'),
                LawFirm.name.ilike(f'%{search}%'),
            )
        )
    if state_filter:
        q = q.filter(
            or_(
                LawFirmShowcase.locations_json.ilike(f'%{state_filter}%'),
                LawFirm.address.ilike(f'%{state_filter}%'),
            )
        )
    if country_filter:
        q = q.filter(
            or_(
                LawFirmShowcase.locations_json.ilike(f'%{country_filter}%'),
                LawFirm.address.ilike(f'%{country_filter}%'),
            )
        )
    if practice_filter:
        q = q.filter(LawFirmShowcase.practice_areas_json.ilike(f'%{practice_filter}%'))
    if verified_only:
        q = q.filter(LawFirmShowcase.is_verified == True)

    showcases_paginated = q.order_by(
        LawFirmShowcase.is_featured.desc(),
        LawFirmShowcase.average_rating.desc(),
        LawFirmShowcase.showcase_order.asc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # ── Spotlight (featured) for slider ──
    spotlight = LawFirmShowcase.query.filter_by(
        is_featured=True, is_active=True, submission_status='approved'
    ).order_by(LawFirmShowcase.showcase_order.asc()).limit(8).all()

    # ── External directory firms ──
    ext_q = DirectoryLawFirm.query.filter_by(is_active=True)
    if search:
        ext_q = ext_q.filter(
            or_(
                DirectoryLawFirm.name.ilike(f'%{search}%'),
                DirectoryLawFirm.practice_areas_json.ilike(f'%{search}%'),
            )
        )
    if state_filter:
        ext_q = ext_q.filter(DirectoryLawFirm.state.ilike(f'%{state_filter}%'))
    if country_filter:
        ext_q = ext_q.filter(DirectoryLawFirm.country.ilike(f'%{country_filter}%'))
    if practice_filter:
        ext_q = ext_q.filter(DirectoryLawFirm.practice_areas_json.ilike(f'%{practice_filter}%'))

    ext_firms = ext_q.order_by(
        DirectoryLawFirm.google_rating.desc().nullslast(),
        DirectoryLawFirm.name.asc()
    ).limit(50).all()

    # Stats for display
    total_platform = LawFirmShowcase.query.filter_by(
        submission_status='approved', is_active=True).count()
    total_external = DirectoryLawFirm.query.filter_by(is_active=True).count()

    # Count countries covered
    countries_covered = db.session.query(
        DirectoryLawFirm.country
    ).filter(DirectoryLawFirm.is_active == True).distinct().count()

    return render_template(
        'directory/index.html',
        showcases=showcases_paginated,
        spotlight=spotlight,
        ext_firms=ext_firms,
        total_platform=total_platform,
        total_external=total_external,
        countries_covered=countries_covered,
        states=NIGERIAN_STATES,
        country_regions=COUNTRY_REGIONS,
        countries=ALL_COUNTRIES,
        practice_areas=PRACTICE_AREA_LIST,
        firm_sizes=FIRM_SIZE_OPTIONS,
        filters={
            'q': search,
            'state': state_filter,
            'country': country_filter,
            'practice': practice_filter,
            'verified': verified_only,
        }
    )


@directory_bp.route('/firm/<int:showcase_id>')
def firm_profile(showcase_id):
    """Full public profile for a platform showcase."""
    from models import PublicLawFirmReview
    from sqlalchemy import desc as _desc

    showcase = LawFirmShowcase.query.filter_by(
        id=showcase_id,
        is_active=True,
        submission_status='approved'
    ).first_or_404()

    showcase.total_views += 1
    db.session.commit()

    reviews = PublicLawFirmReview.query.filter_by(
        showcase_id=showcase_id,
        is_approved=True,
        is_visible=True
    ).order_by(_desc(PublicLawFirmReview.is_featured), _desc(PublicLawFirmReview.created_at)).all()

    # Rating distribution
    from sqlalchemy import func as _func
    rc = db.session.query(
        PublicLawFirmReview.rating,
        _func.count(PublicLawFirmReview.id)
    ).filter_by(showcase_id=showcase_id, is_approved=True, is_visible=True).group_by(
        PublicLawFirmReview.rating).all()
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r, c in rc:
        rating_dist[r] = c

    return render_template(
        'directory/firm_profile.html',
        showcase=showcase,
        reviews=reviews,
        rating_dist=rating_dist,
        get_location_text=_get_showcase_location_text,
    )


@directory_bp.route('/external/<int:firm_id>')
def external_firm(firm_id):
    """Public view for an external/directory-only firm."""
    firm = DirectoryLawFirm.query.filter_by(id=firm_id, is_active=True).first_or_404()
    return render_template('directory/external_firm.html', firm=firm)


@directory_bp.route('/api/search')
def api_search():
    """JSON endpoint for live search / AJAX filter."""
    q = request.args.get('q', '').strip()
    state = request.args.get('state', '').strip()
    practice = request.args.get('practice', '').strip()
    page = request.args.get('page', 1, type=int)

    query = LawFirmShowcase.query.filter_by(
        submission_status='approved', is_active=True
    ).join(LawFirm)

    if q:
        query = query.filter(
            or_(
                LawFirmShowcase.public_title.ilike(f'%{q}%'),
                LawFirm.name.ilike(f'%{q}%'),
            )
        )
    if state:
        query = query.filter(
            or_(
                LawFirmShowcase.locations_json.ilike(f'%{state}%'),
                LawFirm.address.ilike(f'%{state}%'),
            )
        )
    if practice:
        query = query.filter(LawFirmShowcase.practice_areas_json.ilike(f'%{practice}%'))

    results = query.order_by(LawFirmShowcase.average_rating.desc()).limit(20).all()
    data = []
    for s in results:
        data.append({
            'id': s.id,
            'name': s.public_title or s.law_firm.name,
            'logo': s.logo_image_url or '',
            'rating': float(s.average_rating or 5.0),
            'reviews': s.total_reviews,
            'verified': s.is_verified,
            'location': _get_showcase_location_text(s),
            'url': f'/directory/firm/{s.id}',
        })
    return jsonify({'results': data, 'total': len(data)})
