"""
LAWCOLAB v2 — AI Law Firm Growth Engine CRM
Mounted at /superadmin/crm

Full-featured CRM: Pipeline, Discovery, Outreach, Campaigns, Analytics.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response)
from flask_login import current_user
from app import db
from models import (
    DirectoryLawFirm, DirectoryNote, CrmCampaign, OutreachMessage,
    LeadTask, User, ROLE_SUPER_ADMIN, PIPELINE_STAGES
)
from utils.decorators import require_super_admin
from datetime import datetime, timedelta
from sqlalchemy import or_, func, desc, text
import json, csv, io, re

crm_bp = Blueprint('crm', __name__)

# ── Pipeline stage config ─────────────────────────────────────────────────────
STAGE_META = {
    'new':               {'label': 'New Lead',         'color': '#6c757d', 'icon': 'star'},
    'discovered':        {'label': 'Discovered',       'color': '#0d6efd', 'icon': 'search'},
    'verified':          {'label': 'Verified',         'color': '#6610f2', 'icon': 'check-circle'},
    'contacted':         {'label': 'Contacted',        'color': '#fd7e14', 'icon': 'phone'},
    'email_sent':        {'label': 'Email Sent',       'color': '#ffc107', 'icon': 'envelope'},
    'whatsapp_sent':     {'label': 'WhatsApp Sent',    'color': '#20c997', 'icon': 'whatsapp'},
    'interested':        {'label': 'Interested',       'color': '#198754', 'icon': 'heart'},
    'meeting_scheduled': {'label': 'Meeting Sched.',   'color': '#6f42c1', 'icon': 'calendar'},
    'demo_completed':    {'label': 'Demo Done',        'color': '#0dcaf0', 'icon': 'play-circle'},
    'negotiating':       {'label': 'Negotiating',      'color': '#d63384', 'icon': 'handshake'},
    'won':               {'label': 'Won',              'color': '#0d6832', 'icon': 'trophy'},
    'lost':              {'label': 'Lost',             'color': '#dc3545', 'icon': 'times-circle'},
    'customer':          {'label': 'Customer',         'color': '#b8860b', 'icon': 'crown'},
}


def _score_firm(firm):
    """Algorithmic lead score 0–100."""
    score = 0
    if firm.website:           score += 20
    if firm.email:             score += 15
    if firm.phone:             score += 10
    if firm.whatsapp:          score += 8
    if firm.google_rating:
        score += min(int(float(firm.google_rating) * 3), 15)
    if firm.google_reviews_count:
        score += min(int(firm.google_reviews_count / 5), 10)
    if firm.practice_areas:    score += 5
    if firm.description:       score += 5
    if firm.founding_year:     score += 3
    if firm.firm_size and firm.firm_size not in ('solo',):
        score += 4
    if firm.decision_makers_json and firm.decision_makers:
        score += 5
    return min(score, 100)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@crm_bp.route('/')
@require_super_admin
def index():
    total = DirectoryLawFirm.query.count()
    stage_counts = dict(
        db.session.query(DirectoryLawFirm.pipeline_stage, func.count(DirectoryLawFirm.id))
        .group_by(DirectoryLawFirm.pipeline_stage).all()
    )
    campaigns = CrmCampaign.query.order_by(desc(CrmCampaign.created_at)).limit(5).all()
    recent_leads = DirectoryLawFirm.query.order_by(
        desc(DirectoryLawFirm.updated_at)).limit(8).all()
    overdue_tasks = LeadTask.query.filter(
        LeadTask.status == 'open',
        LeadTask.due_at < datetime.now()
    ).count()
    recent_messages = OutreachMessage.query.order_by(
        desc(OutreachMessage.created_at)).limit(5).all()

    # Pipeline funnel
    funnel = [
        {'stage': s, 'meta': STAGE_META[s], 'count': stage_counts.get(s, 0)}
        for s in PIPELINE_STAGES
    ]
    won_count = stage_counts.get('won', 0) + stage_counts.get('customer', 0)
    conversion_rate = round((won_count / total * 100) if total else 0, 1)

    return render_template('crm/index.html',
                           total=total,
                           stage_counts=stage_counts,
                           funnel=funnel,
                           campaigns=campaigns,
                           recent_leads=recent_leads,
                           overdue_tasks=overdue_tasks,
                           recent_messages=recent_messages,
                           conversion_rate=conversion_rate,
                           stage_meta=STAGE_META)


# ── Leads List ────────────────────────────────────────────────────────────────

@crm_bp.route('/leads')
@require_super_admin
def leads():
    q_str   = request.args.get('q', '').strip()
    stage_f = request.args.get('stage', '').strip()
    country_f = request.args.get('country', '').strip()
    sort_by  = request.args.get('sort', 'updated_at')
    view     = request.args.get('view', 'table')   # table | card | kanban
    page     = request.args.get('page', 1, type=int)
    per_page = 30

    q = DirectoryLawFirm.query.filter_by(is_active=True)
    if q_str:
        q = q.filter(or_(
            DirectoryLawFirm.name.ilike(f'%{q_str}%'),
            DirectoryLawFirm.city.ilike(f'%{q_str}%'),
            DirectoryLawFirm.email.ilike(f'%{q_str}%'),
        ))
    if stage_f:
        q = q.filter_by(pipeline_stage=stage_f)
    if country_f:
        q = q.filter(DirectoryLawFirm.country.ilike(f'%{country_f}%'))

    sort_map = {
        'updated_at': DirectoryLawFirm.updated_at.desc(),
        'lead_score':  DirectoryLawFirm.lead_score.desc(),
        'name':        DirectoryLawFirm.name.asc(),
        'created_at':  DirectoryLawFirm.created_at.desc(),
    }
    q = q.order_by(sort_map.get(sort_by, DirectoryLawFirm.updated_at.desc()))

    if view == 'kanban':
        # Load all for kanban (no pagination)
        all_firms = q.limit(500).all()
        kanban_cols = {
            s: [f for f in all_firms if (f.pipeline_stage or 'new') == s]
            for s in PIPELINE_STAGES
        }
        return render_template('crm/pipeline.html',
                               kanban_cols=kanban_cols,
                               stage_meta=STAGE_META,
                               stages=PIPELINE_STAGES,
                               total=len(all_firms))

    firms = q.paginate(page=page, per_page=per_page, error_out=False)

    stage_counts = dict(
        db.session.query(DirectoryLawFirm.pipeline_stage, func.count(DirectoryLawFirm.id))
        .filter_by(is_active=True).group_by(DirectoryLawFirm.pipeline_stage).all()
    )

    return render_template('crm/leads.html',
                           firms=firms,
                           stage_counts=stage_counts,
                           stage_meta=STAGE_META,
                           stages=PIPELINE_STAGES,
                           filters=dict(q=q_str, stage=stage_f, country=country_f),
                           sort=sort_by,
                           view=view)


# ── Lead Detail (AJAX JSON + full page) ──────────────────────────────────────

@crm_bp.route('/lead/<int:firm_id>')
@require_super_admin
def lead_detail(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    notes = DirectoryNote.query.filter_by(firm_id=firm.id).order_by(
        desc(DirectoryNote.created_at)).all()
    tasks = LeadTask.query.filter_by(firm_id=firm.id).order_by(
        LeadTask.status, desc(LeadTask.created_at)).all()
    messages = OutreachMessage.query.filter_by(firm_id=firm.id).order_by(
        desc(OutreachMessage.created_at)).all()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'id': firm.id, 'name': firm.name, 'email': firm.email or '',
            'phone': firm.phone or '', 'whatsapp': firm.whatsapp or '',
            'website': firm.website or '', 'city': firm.city or '',
            'state': firm.state or '', 'country': firm.country or '',
            'pipeline_stage': firm.pipeline_stage or 'new',
            'lead_score': firm.lead_score or 0,
            'practice_areas': firm.practice_areas,
            'description': firm.description or '',
            'decision_makers': firm.decision_makers,
            'stage_color': firm.pipeline_stage_color,
            'stage_label': firm.pipeline_stage_label,
        })

    return render_template('crm/lead_detail.html',
                           firm=firm, notes=notes, tasks=tasks,
                           messages=messages, stage_meta=STAGE_META,
                           stages=PIPELINE_STAGES)


# ── Lead Update APIs ──────────────────────────────────────────────────────────

@crm_bp.route('/lead/<int:firm_id>/stage', methods=['POST'])
@require_super_admin
def update_stage(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    stage = request.json.get('stage') if request.is_json else request.form.get('stage')
    if stage in PIPELINE_STAGES:
        firm.pipeline_stage = stage
        if stage in ('contacted', 'email_sent', 'whatsapp_sent'):
            firm.last_contacted_at = datetime.now()
        db.session.commit()
        return jsonify({'success': True, 'stage': stage, 'label': STAGE_META[stage]['label'],
                        'color': STAGE_META[stage]['color']})
    return jsonify({'success': False, 'error': 'Invalid stage'}), 400


@crm_bp.route('/lead/<int:firm_id>/score', methods=['POST'])
@require_super_admin
def recalculate_score(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    firm.lead_score = _score_firm(firm)
    db.session.commit()
    return jsonify({'success': True, 'score': firm.lead_score})


@crm_bp.route('/lead/<int:firm_id>/note', methods=['POST'])
@require_super_admin
def add_note(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    text_val = (request.json or request.form).get('text', '').strip()
    note_type = (request.json or request.form).get('type', 'general')
    if not text_val:
        return jsonify({'success': False, 'error': 'Note text required'}), 400
    note = DirectoryNote(firm_id=firm.id, created_by_id=current_user.id,
                         note_text=text_val, note_type=note_type)
    db.session.add(note)
    db.session.commit()
    return jsonify({'success': True, 'note': {
        'id': note.id, 'text': note.note_text, 'type': note.note_type,
        'author': current_user.full_name,
        'created_at': note.created_at.strftime('%b %d, %Y %H:%M'),
    }})


@crm_bp.route('/lead/<int:firm_id>/task', methods=['POST'])
@require_super_admin
def add_task(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    data = request.json or request.form
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Title required'}), 400
    due_str = data.get('due_at', '')
    due_at = None
    if due_str:
        try:
            due_at = datetime.fromisoformat(due_str)
        except Exception:
            pass
    task = LeadTask(
        firm_id=firm.id, created_by_id=current_user.id,
        assigned_to_id=current_user.id,
        title=title, description=data.get('description', ''),
        task_type=data.get('task_type', 'follow_up'),
        priority=data.get('priority', 'normal'), due_at=due_at,
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'success': True, 'task_id': task.id})


@crm_bp.route('/lead/<int:firm_id>/task/<int:task_id>/complete', methods=['POST'])
@require_super_admin
def complete_task(firm_id, task_id):
    task = LeadTask.query.get_or_404(task_id)
    task.status = 'done'
    task.completed_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True})


# ── Bulk Actions ──────────────────────────────────────────────────────────────

@crm_bp.route('/bulk', methods=['POST'])
@require_super_admin
def bulk_action():
    data = request.json or {}
    ids = [int(i) for i in data.get('ids', []) if str(i).isdigit()]
    action = data.get('action', '')
    stage = data.get('stage', '')
    if not ids:
        return jsonify({'success': False, 'error': 'No leads selected'}), 400

    firms = DirectoryLawFirm.query.filter(DirectoryLawFirm.id.in_(ids)).all()
    count = len(firms)

    if action == 'set_stage' and stage in PIPELINE_STAGES:
        for f in firms:
            f.pipeline_stage = stage
    elif action == 'score':
        for f in firms:
            f.lead_score = _score_firm(f)
    elif action == 'archive':
        for f in firms:
            f.is_active = False
    elif action == 'delete':
        for f in firms:
            db.session.delete(f)
    else:
        return jsonify({'success': False, 'error': 'Unknown action'}), 400

    db.session.commit()
    return jsonify({'success': True, 'count': count, 'action': action})


# ── Export CSV ───────────────────────────────────────────────────────────────

@crm_bp.route('/export')
@require_super_admin
def export_csv():
    stage_f = request.args.get('stage', '')
    q = DirectoryLawFirm.query.filter_by(is_active=True)
    if stage_f:
        q = q.filter_by(pipeline_stage=stage_f)
    firms = q.order_by(desc(DirectoryLawFirm.lead_score)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['ID', 'Name', 'Stage', 'Score', 'Country', 'City',
                     'State', 'Phone', 'WhatsApp', 'Email', 'Website',
                     'Practice Areas', 'Firm Size', 'Google Rating',
                     'Google Reviews', 'Source', 'Created'])
    for f in firms:
        writer.writerow([
            f.id, f.name, f.pipeline_stage or 'new', f.lead_score or 0,
            f.country or '', f.city or '', f.state or '',
            f.phone or '', f.whatsapp or '', f.email or '', f.website or '',
            ', '.join(f.practice_areas), f.firm_size or '', f.google_rating or '',
            f.google_reviews_count or 0, f.source or '', f.created_at.strftime('%Y-%m-%d'),
        ])

    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=lawcolab_leads.csv'}
    )


# ── AI Discovery Robot ────────────────────────────────────────────────────────

@crm_bp.route('/discovery')
@require_super_admin
def discovery():
    recent = DirectoryLawFirm.query.filter_by(source='ai_discovery').order_by(
        desc(DirectoryLawFirm.created_at)).limit(20).all()
    total = DirectoryLawFirm.query.count()
    return render_template('crm/discovery.html', recent=recent, total=total)


@crm_bp.route('/discovery/search', methods=['POST'])
@require_super_admin
def discovery_search():
    """AI-powered lead discovery using Exa web search."""
    query = request.json.get('query', '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Query is required'}), 400

    import requests as req_lib

    # Build smart search query
    search_query = f"law firm {query} contact phone email website"

    try:
        # Call Exa search via internal proxy
        resp = req_lib.post(
            'https://api.exa.ai/search',
            headers={
                'x-api-key': 'replit_managed',  # Placeholder; use proper proxy in prod
                'Content-Type': 'application/json',
            },
            json={
                'query': search_query,
                'numResults': 10,
                'type': 'neural',
                'contents': {
                    'text': {'maxCharacters': 1000},
                    'highlights': {'numSentences': 3},
                },
            },
            timeout=15,
        )

        if resp.status_code != 200:
            raise Exception(f"Exa returned {resp.status_code}")

        results = resp.json().get('results', [])
        found = []

        for r in results:
            title = r.get('title', '').strip()
            url = r.get('url', '').strip()
            snippet = (r.get('text') or '')[:500]

            if not title or not url:
                continue

            # Skip non-law-firm results
            legal_keywords = ['law', 'legal', 'attorney', 'solicitor', 'barrister',
                               'advocate', 'counsel', 'chambers', 'llp', 'partner']
            if not any(k in (title + snippet).lower() for k in legal_keywords):
                continue

            # Deduplicate by website domain
            domain = _extract_domain(url)
            if domain:
                existing = DirectoryLawFirm.query.filter(
                    DirectoryLawFirm.website.ilike(f'%{domain}%')
                ).first()
                if existing:
                    found.append({'status': 'duplicate', 'name': existing.name, 'id': existing.id})
                    continue

            # Extract what we can from the snippet
            firm = DirectoryLawFirm(
                name=_clean_title(title),
                website=url,
                description=snippet[:500] if snippet else None,
                source='ai_discovery',
                has_website=True,
                website_status='active',
                is_active=True,
                crm_status='new',
                pipeline_stage='discovered',
                lead_score=0,
            )

            # Try to infer location from query
            location_words = _parse_location(query)
            if location_words.get('city'):
                firm.city = location_words['city']
            if location_words.get('country'):
                firm.country = location_words['country']

            firm.lead_score = _score_firm(firm)
            db.session.add(firm)
            db.session.flush()
            found.append({'status': 'added', 'name': firm.name, 'id': firm.id,
                          'website': url})

        db.session.commit()
        added = sum(1 for f in found if f['status'] == 'added')
        dupes = sum(1 for f in found if f['status'] == 'duplicate')
        return jsonify({
            'success': True,
            'found': found,
            'added': added,
            'duplicates': dupes,
            'message': f'Found {len(results)} results → {added} new firms added, {dupes} duplicates skipped.',
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _extract_domain(url):
    try:
        m = re.search(r'https?://(?:www\.)?([^/]+)', url)
        return m.group(1) if m else None
    except Exception:
        return None


def _clean_title(title):
    # Remove common site suffixes
    for suffix in [' - Home', ' | Home', ' – Home', ' - Law Firm', ' | Law Firm']:
        title = title.replace(suffix, '')
    return title.strip()[:250]


def _parse_location(query):
    """Very simple location extraction from natural language query."""
    countries = {
        'nigeria': 'Nigeria', 'uk': 'United Kingdom', 'united kingdom': 'United Kingdom',
        'england': 'United Kingdom', 'canada': 'Canada', 'dubai': 'United Arab Emirates',
        'uae': 'United Arab Emirates', 'usa': 'United States', 'united states': 'United States',
        'ghana': 'Ghana', 'kenya': 'Kenya', 'south africa': 'South Africa',
        'australia': 'Australia', 'india': 'India',
    }
    cities = ['lagos', 'abuja', 'london', 'toronto', 'dubai', 'dubai', 'accra',
              'nairobi', 'johannesburg', 'cape town', 'sydney', 'mumbai', 'ibadan',
              'port harcourt', 'kano', 'new york', 'manchester', 'birmingham']
    ql = query.lower()
    result = {}
    for k, v in countries.items():
        if k in ql:
            result['country'] = v
            break
    for city in cities:
        if city in ql:
            result['city'] = city.title()
            break
    return result


# ── AI Outreach Generator ─────────────────────────────────────────────────────

@crm_bp.route('/outreach')
@require_super_admin
def outreach():
    leads_q = DirectoryLawFirm.query.filter(
        DirectoryLawFirm.is_active == True,
        DirectoryLawFirm.pipeline_stage.in_(['new', 'discovered', 'verified', 'contacted'])
    ).order_by(desc(DirectoryLawFirm.lead_score)).limit(100).all()

    campaigns = CrmCampaign.query.order_by(desc(CrmCampaign.created_at)).all()
    recent_msgs = OutreachMessage.query.order_by(desc(OutreachMessage.created_at)).limit(20).all()

    return render_template('crm/outreach.html',
                           leads=leads_q,
                           campaigns=campaigns,
                           recent_msgs=recent_msgs)


@crm_bp.route('/outreach/generate', methods=['POST'])
@require_super_admin
def generate_outreach():
    """Generate AI-personalized outreach messages."""
    import os
    data = request.json or {}
    firm_ids = [int(i) for i in data.get('firm_ids', []) if str(i).isdigit()]
    channel = data.get('channel', 'email')
    msg_type = data.get('message_type', 'cold_outreach')

    if not firm_ids:
        return jsonify({'success': False, 'error': 'Select at least one firm'}), 400

    firms = DirectoryLawFirm.query.filter(DirectoryLawFirm.id.in_(firm_ids)).all()
    generated = []

    openai_key = os.environ.get('OPENAI_API_KEY', '')

    for firm in firms:
        if openai_key:
            msg = _generate_with_openai(firm, channel, msg_type, openai_key)
        else:
            msg = _generate_template_message(firm, channel, msg_type)

        generated.append({
            'firm_id': firm.id,
            'firm_name': firm.name,
            'subject': msg['subject'],
            'body': msg['body'],
        })

    return jsonify({'success': True, 'messages': generated})


@crm_bp.route('/outreach/save', methods=['POST'])
@require_super_admin
def save_outreach():
    """Save generated outreach message to DB."""
    data = request.json or {}
    firm_id = data.get('firm_id')
    if not firm_id:
        return jsonify({'success': False, 'error': 'firm_id required'}), 400

    msg = OutreachMessage(
        firm_id=int(firm_id),
        created_by_id=current_user.id,
        campaign_id=data.get('campaign_id'),
        channel=data.get('channel', 'email'),
        message_type=data.get('message_type', 'cold_outreach'),
        subject=data.get('subject', ''),
        body=data.get('body', ''),
        recipient_name=data.get('recipient_name', ''),
        recipient_email=data.get('recipient_email', ''),
        status='draft',
        ai_generated=data.get('ai_generated', True),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({'success': True, 'message_id': msg.id})


@crm_bp.route('/outreach/mark-sent/<int:msg_id>', methods=['POST'])
@require_super_admin
def mark_sent(msg_id):
    msg = OutreachMessage.query.get_or_404(msg_id)
    msg.status = 'sent'
    msg.sent_at = datetime.now()
    firm = msg.firm
    if firm:
        firm.last_contacted_at = datetime.now()
        if firm.pipeline_stage in ('new', 'discovered', 'verified'):
            firm.pipeline_stage = 'contacted'
    db.session.commit()
    return jsonify({'success': True})


def _generate_template_message(firm, channel, msg_type):
    """Template-based message when no OpenAI key is set."""
    areas = ', '.join(firm.practice_areas[:3]) if firm.practice_areas else 'legal practice'
    city = firm.city or firm.country or 'your area'
    name = firm.name

    if channel == 'email' and msg_type == 'cold_outreach':
        return {
            'subject': f"Helping {name} Modernize Client Management",
            'body': f"""Dear {name} Team,

I came across {name} while researching leading law firms in {city}.

We recently built LAWCOLAB — a modern legal operating system that helps firms like yours manage clients, cases, billing, calendars, and secure communication in one unified platform.

Considering your expertise in {areas}, I believe LAWCOLAB could save your team hours every week while significantly improving your client experience.

I'd love to offer you a complimentary demo and a free trial — no commitment required.

Would you be open to a 20-minute call this week?

Best regards,
LAWCOLAB Growth Team
https://lawcolab.com"""
        }
    elif channel == 'whatsapp':
        return {
            'subject': '',
            'body': f"Hi {name} Team! 👋 I came across your firm in {city} and wanted to share LAWCOLAB — a platform that helps law firms manage clients, cases, and billing in one place. Would you be open to a quick demo? 🙏"
        }
    elif msg_type == 'follow_up':
        return {
            'subject': f"Following up — LAWCOLAB for {name}",
            'body': f"""Dear {name} Team,

I wanted to follow up on my previous message about LAWCOLAB.

Many {areas} firms in {city} are already using our platform to streamline their operations.

I'd still love to show you what LAWCOLAB can do for {name} — it only takes 20 minutes.

Best regards,
LAWCOLAB Growth Team"""
        }
    else:
        return {
            'subject': f"LAWCOLAB — Built for {name}",
            'body': f"Dear {name} Team,\n\nI'd love to show you how LAWCOLAB can help your firm in {city} manage cases, clients, and billing more efficiently.\n\nBest regards,\nLAWCOLAB Growth Team"
        }


def _generate_with_openai(firm, channel, msg_type, api_key):
    """Generate message using OpenAI API."""
    import requests as req_lib
    areas = ', '.join(firm.practice_areas[:3]) if firm.practice_areas else 'general legal practice'
    city = f"{firm.city or ''}, {firm.country or ''}".strip(', ')

    type_label = {
        'cold_outreach': 'cold outreach',
        'follow_up': 'first follow-up',
        'second_followup': 'second follow-up (softer tone)',
        'meeting_invite': 'meeting invitation',
        're_engagement': 're-engagement after silence',
    }.get(msg_type, 'cold outreach')

    channel_label = {
        'email': 'professional email',
        'whatsapp': 'short friendly WhatsApp message (max 3 lines)',
        'linkedin': 'LinkedIn connection note (max 300 chars)',
        'sms': 'brief SMS (max 160 chars)',
    }.get(channel, 'email')

    prompt = f"""You are a professional sales copywriter for LAWCOLAB, a modern legal practice management platform.

Write a highly personalized {type_label} {channel_label} for this law firm:
- Firm Name: {firm.name}
- Location: {city}
- Practice Areas: {areas}
- Website: {firm.website or 'not available'}
- Description: {(firm.description or '')[:200]}

LAWCOLAB offers: client management, case tracking, billing, calendar, team collaboration, analytics.

Rules:
- Sound personal and research-based, NOT generic
- Reference their specific practice areas and location
- Keep it concise and professional
- End with a clear, low-friction CTA
- Do NOT use placeholder text like [Name]

Return a JSON object with exactly two keys: "subject" (for email, empty string for others) and "body"."""

    try:
        r = req_lib.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [{'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_object'},
                'max_tokens': 600,
                'temperature': 0.8,
            },
            timeout=20,
        )
        content = r.json()['choices'][0]['message']['content']
        return json.loads(content)
    except Exception:
        return _generate_template_message(firm, channel, msg_type)


# ── Campaigns ─────────────────────────────────────────────────────────────────

@crm_bp.route('/campaigns')
@require_super_admin
def campaigns():
    camps = CrmCampaign.query.order_by(desc(CrmCampaign.created_at)).all()
    return render_template('crm/campaigns.html', campaigns=camps)


@crm_bp.route('/campaigns/create', methods=['POST'])
@require_super_admin
def create_campaign():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Campaign name is required.', 'error')
        return redirect(url_for('crm.campaigns'))
    camp = CrmCampaign(
        name=name,
        description=request.form.get('description', ''),
        target_country=request.form.get('target_country', ''),
        target_practice_area=request.form.get('target_practice_area', ''),
        created_by_id=current_user.id,
        status='draft',
    )
    db.session.add(camp)
    db.session.commit()
    flash(f'Campaign "{name}" created.', 'success')
    return redirect(url_for('crm.campaign_detail', campaign_id=camp.id))


@crm_bp.route('/campaigns/<int:campaign_id>')
@require_super_admin
def campaign_detail(campaign_id):
    camp = CrmCampaign.query.get_or_404(campaign_id)
    msgs = OutreachMessage.query.filter_by(campaign_id=camp.id).order_by(
        desc(OutreachMessage.created_at)).all()
    leads_in = DirectoryLawFirm.query.filter_by(campaign_id=camp.id).all()

    # Metrics
    sent = sum(1 for m in msgs if m.status in ('sent', 'delivered', 'opened', 'replied'))
    opened = sum(1 for m in msgs if m.status in ('opened', 'replied'))
    replied = sum(1 for m in msgs if m.status == 'replied')
    open_rate = round(opened / sent * 100 if sent else 0, 1)
    reply_rate = round(replied / sent * 100 if sent else 0, 1)

    return render_template('crm/campaign_detail.html',
                           campaign=camp, messages=msgs, leads=leads_in,
                           sent=sent, opened=opened, replied=replied,
                           open_rate=open_rate, reply_rate=reply_rate)


@crm_bp.route('/campaigns/<int:campaign_id>/status', methods=['POST'])
@require_super_admin
def update_campaign_status(campaign_id):
    camp = CrmCampaign.query.get_or_404(campaign_id)
    camp.status = request.json.get('status', camp.status)
    db.session.commit()
    return jsonify({'success': True, 'status': camp.status})


# ── Analytics ─────────────────────────────────────────────────────────────────

@crm_bp.route('/analytics')
@require_super_admin
def analytics():
    total = DirectoryLawFirm.query.filter_by(is_active=True).count()

    # Stage distribution
    stage_data = dict(
        db.session.query(DirectoryLawFirm.pipeline_stage, func.count(DirectoryLawFirm.id))
        .filter_by(is_active=True).group_by(DirectoryLawFirm.pipeline_stage).all()
    )

    # Country distribution (top 10)
    country_data = db.session.query(
        DirectoryLawFirm.country, func.count(DirectoryLawFirm.id)
    ).filter_by(is_active=True).group_by(DirectoryLawFirm.country).order_by(
        func.count(DirectoryLawFirm.id).desc()
    ).limit(10).all()

    # Source breakdown
    source_data = dict(
        db.session.query(DirectoryLawFirm.source, func.count(DirectoryLawFirm.id))
        .group_by(DirectoryLawFirm.source).all()
    )

    # Monthly new leads (last 6 months)
    monthly = []
    for i in range(5, -1, -1):
        d = datetime.now() - timedelta(days=30 * i)
        start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_day = (start + timedelta(days=32)).replace(day=1)
        count = DirectoryLawFirm.query.filter(
            DirectoryLawFirm.created_at >= start,
            DirectoryLawFirm.created_at < end_day,
        ).count()
        monthly.append({'month': start.strftime('%b %Y'), 'count': count})

    # Lead score distribution
    score_buckets = {
        '0-20': DirectoryLawFirm.query.filter(DirectoryLawFirm.lead_score.between(0, 20)).count(),
        '21-40': DirectoryLawFirm.query.filter(DirectoryLawFirm.lead_score.between(21, 40)).count(),
        '41-60': DirectoryLawFirm.query.filter(DirectoryLawFirm.lead_score.between(41, 60)).count(),
        '61-80': DirectoryLawFirm.query.filter(DirectoryLawFirm.lead_score.between(61, 80)).count(),
        '81-100': DirectoryLawFirm.query.filter(DirectoryLawFirm.lead_score.between(81, 100)).count(),
    }

    # Outreach stats
    total_msgs = OutreachMessage.query.count()
    sent_msgs = OutreachMessage.query.filter(OutreachMessage.status.in_(['sent', 'delivered', 'opened', 'replied'])).count()
    replied_msgs = OutreachMessage.query.filter_by(status='replied').count()

    won = stage_data.get('won', 0) + stage_data.get('customer', 0)
    conversion_rate = round(won / total * 100 if total else 0, 1)

    return render_template('crm/analytics.html',
                           total=total,
                           stage_data=stage_data,
                           country_data=country_data,
                           source_data=source_data,
                           monthly=monthly,
                           score_buckets=score_buckets,
                           total_msgs=total_msgs,
                           sent_msgs=sent_msgs,
                           replied_msgs=replied_msgs,
                           conversion_rate=conversion_rate,
                           won=won,
                           stage_meta=STAGE_META)


# ── Score All Leads (batch) ───────────────────────────────────────────────────

@crm_bp.route('/score-all', methods=['POST'])
@require_super_admin
def score_all():
    firms = DirectoryLawFirm.query.filter_by(is_active=True).all()
    for f in firms:
        f.lead_score = _score_firm(f)
    db.session.commit()
    return jsonify({'success': True, 'scored': len(firms)})
