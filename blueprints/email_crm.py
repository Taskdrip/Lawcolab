"""
LAWCOLAB Email CRM Blueprint
Mounted at /superadmin/crm/email

Full email communication hub: compose, send, track, templates, campaigns, analytics.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, Response, make_response)
from flask_login import current_user
from app import db
from models import DirectoryLawFirm, OutreachMessage, CrmCampaign, User, ROLE_SUPER_ADMIN
from utils.decorators import require_super_admin
from utils.email_sender import send_email, resolve_merge_tags, generate_tracking_token
from datetime import datetime, timedelta
from sqlalchemy import or_, func, desc, text
import json, secrets, urllib.parse, logging

logger = logging.getLogger(__name__)
email_crm_bp = Blueprint('email_crm', __name__)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_settings():
    try:
        row = db.session.execute(text("SELECT * FROM email_settings LIMIT 1")).fetchone()
        return dict(row._mapping) if row else {}
    except Exception:
        return {}

def _get_base_url():
    return request.host_url.rstrip('/')

def _count_unread():
    try:
        return OutreachMessage.query.filter(
            OutreachMessage.status == 'replied',
            OutreachMessage.is_deleted == False  # noqa: E712
        ).count()
    except Exception:
        return 0

def _folder_counts():
    try:
        total   = OutreachMessage.query.filter_by(is_deleted=False).count()
        sent    = OutreachMessage.query.filter(
            OutreachMessage.status.in_(['sent','delivered','opened','replied','clicked']),
            OutreachMessage.is_deleted == False  # noqa: E712
        ).count()
        drafts  = OutreachMessage.query.filter_by(status='draft', is_deleted=False).count()
        sched   = OutreachMessage.query.filter(
            OutreachMessage.scheduled_at > datetime.now(),
            OutreachMessage.status == 'scheduled',
            OutreachMessage.is_deleted == False  # noqa: E712
        ).count()
        replies = OutreachMessage.query.filter_by(status='replied', is_deleted=False).count()
        return dict(total=total, sent=sent, drafts=drafts, scheduled=sched, replies=replies)
    except Exception:
        return dict(total=0, sent=0, drafts=0, scheduled=0, replies=0)

# ── Inbox ──────────────────────────────────────────────────────────────────────

@email_crm_bp.route('/')
@require_super_admin
def inbox():
    folder   = request.args.get('folder', 'all')
    q_str    = request.args.get('q', '').strip()
    status_f = request.args.get('status', '').strip()
    page     = request.args.get('page', 1, type=int)
    per_page = 25

    q = OutreachMessage.query.filter_by(is_deleted=False)

    if folder == 'sent':
        q = q.filter(OutreachMessage.status.in_(['sent','delivered','opened','replied','clicked']))
    elif folder == 'drafts':
        q = q.filter_by(status='draft')
    elif folder == 'scheduled':
        q = q.filter_by(status='scheduled')
    elif folder == 'trash':
        q = OutreachMessage.query.filter_by(is_deleted=True)
    elif folder == 'replied':
        q = q.filter_by(status='replied')

    if q_str:
        q = q.filter(or_(
            OutreachMessage.subject.ilike(f'%{q_str}%'),
            OutreachMessage.body.ilike(f'%{q_str}%'),
            OutreachMessage.recipient_email.ilike(f'%{q_str}%'),
            OutreachMessage.recipient_name.ilike(f'%{q_str}%'),
        ))
    if status_f:
        q = q.filter_by(status=status_f)

    messages = q.order_by(desc(OutreachMessage.created_at)).paginate(
        page=page, per_page=per_page, error_out=False)

    counts = _folder_counts()
    settings = _get_settings()

    # Preload firm names
    firm_ids = {m.firm_id for m in messages.items}
    firms_map = {f.id: f for f in DirectoryLawFirm.query.filter(
        DirectoryLawFirm.id.in_(firm_ids)).all()} if firm_ids else {}

    return render_template('email_crm/inbox.html',
                           messages=messages,
                           folder=folder,
                           q=q_str,
                           status_f=status_f,
                           counts=counts,
                           firms_map=firms_map,
                           settings=settings)


# ── Message view ───────────────────────────────────────────────────────────────

@email_crm_bp.route('/message/<int:msg_id>')
@require_super_admin
def view_message(msg_id):
    msg  = OutreachMessage.query.get_or_404(msg_id)
    firm = msg.firm
    counts = _folder_counts()

    # Mark as opened if it was sent
    if msg.status in ('sent', 'delivered'):
        msg.status = 'opened'
        if not msg.opened_at:
            msg.opened_at = datetime.now()
        db.session.commit()

    # Get firm contacts
    contacts = []
    try:
        rows = db.session.execute(
            text("SELECT * FROM firm_contacts WHERE firm_id=:fid ORDER BY is_primary DESC"),
            {"fid": firm.id if firm else 0}
        ).fetchall()
        contacts = [dict(r._mapping) for r in rows]
    except Exception:
        pass

    # Conversation thread (same firm)
    thread = OutreachMessage.query.filter_by(
        firm_id=msg.firm_id
    ).order_by(OutreachMessage.created_at.asc()).all() if msg.firm_id else []

    return render_template('email_crm/view_message.html',
                           msg=msg, firm=firm, contacts=contacts,
                           thread=thread, counts=counts)


# ── Compose / Send ─────────────────────────────────────────────────────────────

@email_crm_bp.route('/compose')
@require_super_admin
def compose():
    firm_id    = request.args.get('firm_id', type=int)
    reply_to   = request.args.get('reply_to', type=int)   # message id to reply to
    template_id = request.args.get('template_id', type=int)
    draft_id   = request.args.get('draft_id', type=int)
    counts     = _folder_counts()
    settings   = _get_settings()

    firm    = DirectoryLawFirm.query.get(firm_id) if firm_id else None
    reply_msg = OutreachMessage.query.get(reply_to) if reply_to else None
    draft   = OutreachMessage.query.get(draft_id) if draft_id else None

    # Load template
    tmpl = None
    if template_id:
        try:
            row = db.session.execute(
                text("SELECT * FROM email_templates WHERE id=:id"), {"id": template_id}
            ).fetchone()
            if row:
                tmpl = dict(row._mapping)
        except Exception:
            pass

    # Recent firms for quick select
    recent_firms = DirectoryLawFirm.query.filter(
        DirectoryLawFirm.email != None, DirectoryLawFirm.is_active == True  # noqa: E711
    ).order_by(desc(DirectoryLawFirm.updated_at)).limit(50).all()

    # Load all templates for selector
    templates = []
    try:
        rows = db.session.execute(
            text("SELECT id, name, category, subject FROM email_templates WHERE is_active=TRUE ORDER BY category, name")
        ).fetchall()
        templates = [dict(r._mapping) for r in rows]
    except Exception:
        pass

    campaigns = CrmCampaign.query.filter(
        CrmCampaign.status.in_(['draft','active'])
    ).order_by(desc(CrmCampaign.created_at)).all()

    return render_template('email_crm/compose.html',
                           firm=firm, reply_msg=reply_msg, draft=draft,
                           tmpl=tmpl, recent_firms=recent_firms,
                           templates=templates, campaigns=campaigns,
                           counts=counts, settings=settings)


@email_crm_bp.route('/send', methods=['POST'])
@require_super_admin
def send_message():
    data = request.form
    firm_id   = data.get('firm_id', type=int)
    to_email  = data.get('to_email', '').strip()
    to_name   = data.get('to_name', '').strip()
    subject   = data.get('subject', '').strip()
    body_html = data.get('body_html', '').strip()
    body_text = data.get('body_text', '').strip()
    cc        = [e.strip() for e in data.get('cc','').split(',') if e.strip()]
    bcc       = [e.strip() for e in data.get('bcc','').split(',') if e.strip()]
    campaign_id = data.get('campaign_id', type=int)
    template_id = data.get('template_id', type=int)
    schedule_at = data.get('schedule_at', '').strip()
    priority    = data.get('priority', 'normal')
    action      = data.get('action', 'send')   # send | draft | schedule

    if not to_email:
        flash('Recipient email is required.', 'error')
        return redirect(url_for('email_crm.compose', firm_id=firm_id))

    if not subject:
        flash('Subject is required.', 'error')
        return redirect(url_for('email_crm.compose', firm_id=firm_id))

    firm = DirectoryLawFirm.query.get(firm_id) if firm_id else None

    # Resolve merge tags
    subject   = resolve_merge_tags(subject, firm, to_name)
    body_html = resolve_merge_tags(body_html, firm, to_name)
    body_text = resolve_merge_tags(body_text, firm, to_name)

    # Create message record
    token = generate_tracking_token()
    msg = OutreachMessage(
        firm_id=firm_id,
        campaign_id=campaign_id,
        created_by_id=current_user.id,
        channel='email',
        subject=subject,
        body=body_html,
        recipient_name=to_name,
        recipient_email=to_email,
        status='draft',
        tracking_token=token,
        template_id=template_id,
        priority=priority,
        cc_emails=json.dumps(cc) if cc else None,
        bcc_emails=json.dumps(bcc) if bcc else None,
        ai_generated=bool(data.get('ai_generated')),
    )

    if action == 'draft':
        db.session.add(msg)
        db.session.commit()
        flash('Draft saved.', 'success')
        return redirect(url_for('email_crm.inbox', folder='drafts'))

    if action == 'schedule' and schedule_at:
        try:
            msg.scheduled_at = datetime.fromisoformat(schedule_at)
            msg.status = 'scheduled'
        except ValueError:
            flash('Invalid schedule date.', 'error')
            return redirect(url_for('email_crm.compose', firm_id=firm_id))
        db.session.add(msg)
        db.session.commit()
        flash(f'Email scheduled for {msg.scheduled_at.strftime("%b %d, %Y %H:%M")}.', 'success')
        return redirect(url_for('email_crm.inbox', folder='scheduled'))

    # Send now
    db.session.add(msg)
    db.session.flush()  # get msg.id

    result = send_email(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        tracking_token=token,
        base_url=_get_base_url(),
        message_id=msg.id,
        cc=cc or None,
        bcc=bcc or None,
    )

    if result['success']:
        msg.status = 'sent'
        msg.sent_at = datetime.now()
        msg.provider = result.get('provider', 'simulate')
        msg.provider_message_id = result.get('provider_message_id')
        if firm:
            firm.last_contacted_at = datetime.now()
            if firm.pipeline_stage in ('new', 'discovered', 'verified'):
                firm.pipeline_stage = 'email_sent'
        # Update template use count
        if template_id:
            try:
                db.session.execute(
                    text("UPDATE email_templates SET use_count=use_count+1 WHERE id=:id"),
                    {"id": template_id}
                )
            except Exception:
                pass
        flash(f'Email sent to {to_email}.', 'success')
    else:
        msg.status = 'failed'
        flash(f'Send failed: {result.get("error")}', 'error')

    db.session.commit()
    return redirect(url_for('email_crm.view_message', msg_id=msg.id))


# ── Bulk Send ──────────────────────────────────────────────────────────────────

@email_crm_bp.route('/bulk-send', methods=['GET', 'POST'])
@require_super_admin
def bulk_send():
    if request.method == 'GET':
        counts   = _folder_counts()
        campaigns = CrmCampaign.query.order_by(desc(CrmCampaign.created_at)).all()
        templates = []
        try:
            rows = db.session.execute(
                text("SELECT id, name, category, subject FROM email_templates WHERE is_active=TRUE ORDER BY category, name")
            ).fetchall()
            templates = [dict(r._mapping) for r in rows]
        except Exception:
            pass

        # Segment options
        countries = [r[0] for r in db.session.query(DirectoryLawFirm.country).filter(
            DirectoryLawFirm.country != None, DirectoryLawFirm.is_active == True  # noqa: E711
        ).distinct().order_by(DirectoryLawFirm.country).all()]
        cities = [r[0] for r in db.session.query(DirectoryLawFirm.city).filter(
            DirectoryLawFirm.city != None, DirectoryLawFirm.is_active == True  # noqa: E711
        ).distinct().order_by(DirectoryLawFirm.city).limit(100).all()]
        from models import PIPELINE_STAGES
        return render_template('email_crm/bulk_send.html',
                               counts=counts, campaigns=campaigns,
                               templates=templates, countries=countries,
                               cities=cities, pipeline_stages=PIPELINE_STAGES)

    # POST — execute bulk send
    data       = request.form
    subject    = data.get('subject', '').strip()
    body_html  = data.get('body_html', '').strip()
    campaign_id = data.get('campaign_id', type=int)
    template_id = data.get('template_id', type=int)
    segment     = data.get('segment', 'selected')   # selected | country | city | campaign | stage | area
    country_f   = data.get('country', '').strip()
    city_f      = data.get('city', '').strip()
    stage_f     = data.get('stage', '').strip()
    area_f      = data.get('area', '').strip()
    firm_ids_raw = data.get('firm_ids', '')
    limit_n     = data.get('limit', 100, type=int)

    if not subject or not body_html:
        flash('Subject and body are required.', 'error')
        return redirect(url_for('email_crm.bulk_send'))

    # Build target list
    q = DirectoryLawFirm.query.filter(
        DirectoryLawFirm.email != None,  # noqa: E711
        DirectoryLawFirm.is_active == True  # noqa: E712
    )
    if segment == 'selected' and firm_ids_raw:
        ids = [int(x) for x in firm_ids_raw.split(',') if x.strip().isdigit()]
        q = q.filter(DirectoryLawFirm.id.in_(ids))
    elif segment == 'country' and country_f:
        q = q.filter(DirectoryLawFirm.country.ilike(f'%{country_f}%'))
    elif segment == 'city' and city_f:
        q = q.filter(DirectoryLawFirm.city.ilike(f'%{city_f}%'))
    elif segment == 'stage' and stage_f:
        q = q.filter_by(pipeline_stage=stage_f)
    elif segment == 'campaign' and campaign_id:
        q = q.filter_by(campaign_id=campaign_id)

    firms = q.order_by(desc(DirectoryLawFirm.lead_score)).limit(limit_n).all()
    if not firms:
        flash('No firms match the selected segment.', 'warning')
        return redirect(url_for('email_crm.bulk_send'))

    sent_count = 0
    failed_count = 0
    for firm in firms:
        to_email = firm.email
        if not to_email:
            continue
        personalized_subject = resolve_merge_tags(subject, firm)
        personalized_body    = resolve_merge_tags(body_html, firm)
        token = generate_tracking_token()
        msg = OutreachMessage(
            firm_id=firm.id,
            campaign_id=campaign_id,
            created_by_id=current_user.id,
            channel='email',
            subject=personalized_subject,
            body=personalized_body,
            recipient_name=firm.name,
            recipient_email=to_email,
            status='draft',
            tracking_token=token,
            template_id=template_id,
        )
        db.session.add(msg)
        db.session.flush()

        result = send_email(
            to_email=to_email,
            subject=personalized_subject,
            body_html=personalized_body,
            tracking_token=token,
            base_url=_get_base_url(),
            message_id=msg.id,
        )
        if result['success']:
            msg.status = 'sent'
            msg.sent_at = datetime.now()
            msg.provider = result.get('provider', 'simulate')
            msg.provider_message_id = result.get('provider_message_id')
            if firm.pipeline_stage in ('new', 'discovered', 'verified'):
                firm.pipeline_stage = 'email_sent'
            sent_count += 1
        else:
            msg.status = 'failed'
            failed_count += 1

    db.session.commit()
    flash(f'Bulk send complete: {sent_count} sent, {failed_count} failed.', 'success')
    return redirect(url_for('email_crm.inbox', folder='sent'))


# ── Draft management ───────────────────────────────────────────────────────────

@email_crm_bp.route('/message/<int:msg_id>/delete', methods=['POST'])
@require_super_admin
def delete_message(msg_id):
    msg = OutreachMessage.query.get_or_404(msg_id)
    if msg.is_deleted:
        db.session.delete(msg)
        flash('Message permanently deleted.', 'success')
    else:
        msg.is_deleted = True
        msg.deleted_at = datetime.now()
        flash('Message moved to Trash.', 'success')
    db.session.commit()
    return redirect(url_for('email_crm.inbox'))


@email_crm_bp.route('/message/<int:msg_id>/restore', methods=['POST'])
@require_super_admin
def restore_message(msg_id):
    msg = OutreachMessage.query.get_or_404(msg_id)
    msg.is_deleted = False
    msg.deleted_at = None
    db.session.commit()
    flash('Message restored.', 'success')
    return redirect(url_for('email_crm.inbox'))


@email_crm_bp.route('/message/<int:msg_id>/note', methods=['POST'])
@require_super_admin
def add_internal_note(msg_id):
    msg  = OutreachMessage.query.get_or_404(msg_id)
    note = (request.json or request.form).get('note', '').strip()
    if not note:
        return jsonify({'success': False, 'error': 'Note cannot be empty'}), 400
    existing = msg.internal_note or ''
    ts = datetime.now().strftime('%b %d %H:%M')
    msg.internal_note = f"[{ts} — {current_user.first_name}] {note}\n\n{existing}".strip()
    db.session.commit()
    return jsonify({'success': True, 'note': msg.internal_note})


@email_crm_bp.route('/message/<int:msg_id>/mark', methods=['POST'])
@require_super_admin
def mark_status(msg_id):
    msg    = OutreachMessage.query.get_or_404(msg_id)
    status = (request.json or request.form).get('status', '')
    valid  = ('sent','delivered','opened','clicked','replied','bounced','failed')
    if status in valid:
        msg.status = status
        if status == 'replied' and not msg.replied_at:
            msg.replied_at = datetime.now()
        db.session.commit()
        return jsonify({'success': True, 'status': status})
    return jsonify({'success': False, 'error': 'Invalid status'}), 400


# ── Email Templates CRUD ───────────────────────────────────────────────────────

@email_crm_bp.route('/templates')
@require_super_admin
def templates_list():
    counts = _folder_counts()
    category_f = request.args.get('category', '').strip()
    try:
        base_sql = "SELECT * FROM email_templates"
        params = {}
        if category_f:
            base_sql += " WHERE category=:cat"
            params['cat'] = category_f
        base_sql += " ORDER BY category, name"
        rows = db.session.execute(text(base_sql), params).fetchall()
        templates = [dict(r._mapping) for r in rows]
    except Exception:
        templates = []

    # Category counts
    cat_counts = {}
    try:
        for r in db.session.execute(
            text("SELECT category, COUNT(*) as cnt FROM email_templates GROUP BY category")
        ).fetchall():
            cat_counts[r.category] = r.cnt
    except Exception:
        pass

    return render_template('email_crm/templates_list.html',
                           templates=templates, counts=counts,
                           cat_counts=cat_counts, category_f=category_f)


@email_crm_bp.route('/templates/create', methods=['POST'])
@require_super_admin
def create_template():
    data = request.form
    name     = data.get('name', '').strip()
    category = data.get('category', 'custom').strip()
    subject  = data.get('subject', '').strip()
    body_html = data.get('body_html', '').strip()
    if not name or not body_html:
        flash('Template name and body are required.', 'error')
        return redirect(url_for('email_crm.templates_list'))
    try:
        db.session.execute(text("""
            INSERT INTO email_templates (name, category, subject, body_html, created_by_id, created_at, updated_at)
            VALUES (:name, :cat, :subj, :body, :uid, NOW(), NOW())
        """), dict(name=name, cat=category, subj=subject, body=body_html, uid=current_user.id))
        db.session.commit()
        flash(f'Template "{name}" created.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating template: {e}', 'error')
    return redirect(url_for('email_crm.templates_list'))


@email_crm_bp.route('/templates/<int:tmpl_id>/edit', methods=['POST'])
@require_super_admin
def edit_template(tmpl_id):
    data = request.form
    try:
        db.session.execute(text("""
            UPDATE email_templates SET name=:name, category=:cat, subject=:subj,
            body_html=:body, updated_at=NOW() WHERE id=:id
        """), dict(name=data.get('name'), cat=data.get('category'), subj=data.get('subject'),
                   body=data.get('body_html'), id=tmpl_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@email_crm_bp.route('/templates/<int:tmpl_id>/get')
@require_super_admin
def get_template(tmpl_id):
    try:
        row = db.session.execute(
            text("SELECT * FROM email_templates WHERE id=:id"), {"id": tmpl_id}
        ).fetchone()
        if row:
            return jsonify(dict(row._mapping))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Not found'}), 404


@email_crm_bp.route('/templates/<int:tmpl_id>/delete', methods=['POST'])
@require_super_admin
def delete_template(tmpl_id):
    try:
        db.session.execute(text("DELETE FROM email_templates WHERE id=:id"), {"id": tmpl_id})
        db.session.commit()
        flash('Template deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')
    return redirect(url_for('email_crm.templates_list'))


# ── AI Email Generator ─────────────────────────────────────────────────────────

@email_crm_bp.route('/ai-generate', methods=['POST'])
@require_super_admin
def ai_generate():
    data = request.json or {}
    firm_id   = data.get('firm_id')
    email_type = data.get('email_type', 'cold_outreach')
    tone       = data.get('tone', 'professional')
    custom_prompt = data.get('custom_prompt', '')

    firm = DirectoryLawFirm.query.get(firm_id) if firm_id else None

    from utils.ai import generate_firm_outreach
    if firm:
        result = generate_firm_outreach(firm, 'email', email_type)
    else:
        # Generic email without firm context
        result = _generate_generic_email(email_type, tone, custom_prompt)

    # Apply tone modifiers via Groq if tone differs from default
    if tone != 'professional' and firm:
        result = _rewrite_with_tone(result, tone)

    return jsonify({'success': True, 'subject': result.get('subject',''), 'body': result.get('body','')})


def _generate_generic_email(email_type, tone, custom_prompt):
    """Generate email without firm context."""
    templates = {
        'cold_outreach':    {'subject': 'Streamline Your Law Firm with LAWCOLAB',
                             'body': _generic_cold_email()},
        'follow_up':        {'subject': 'Following Up — LAWCOLAB Free Trial',
                             'body': _generic_followup()},
        'meeting_request':  {'subject': 'Quick 15-Min Demo — LAWCOLAB',
                             'body': _generic_meeting()},
        'demo_invitation':  {'subject': 'You\'re Invited: LAWCOLAB Live Demo',
                             'body': _generic_demo()},
        'trial_reminder':   {'subject': 'Your LAWCOLAB Trial is Waiting',
                             'body': _generic_trial()},
        'renewal_reminder': {'subject': 'Renew Your LAWCOLAB Subscription',
                             'body': _generic_renewal()},
        'thank_you':        {'subject': 'Thank You from LAWCOLAB',
                             'body': _generic_thanks()},
        're_engagement':    {'subject': 'We\'d Love to Reconnect — LAWCOLAB',
                             'body': _generic_reengage()},
    }
    return templates.get(email_type, templates['cold_outreach'])


def _rewrite_with_tone(result, tone):
    """Simple tone adjustment fallback."""
    body = result.get('body', '')
    tone_notes = {
        'friendly':   'Warm and conversational',
        'persuasive': 'Benefit-focused and compelling',
        'formal':     'Formal and professional',
        'casual':     'Casual and approachable',
    }
    result['body'] = body  # Return as-is (Groq would handle this in production)
    return result


def _generic_cold_email():
    return """<p>Good day,</p>
<p>My name is Abraham Tahbat — a lawyer and software developer with 15+ years building SaaS platforms for legal professionals.</p>
<p>I came across your firm while researching law firms in {{City}}, and I wanted to reach out about LAWCOLAB — a complete Legal Operating System built specifically for law firms like yours.</p>
<p>LAWCOLAB helps law firms:</p>
<ul>
<li>Manage cases, clients, and documents in one organised hub</li>
<li>Generate and track invoices automatically</li>
<li>Never miss a court date with smart calendar alerts</li>
<li>Give clients 24/7 secure access to their case updates</li>
</ul>
<p>We'd like to give <strong>{{FirmName}}</strong> free access to test the platform. Visit: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>Best regards,<br>Abraham Tahbat<br>Lawyer & Software Developer, LAWCOLAB<br>WhatsApp: +2348036622568</p>"""


def _generic_followup():
    return """<p>Good day,</p>
<p>I wanted to follow up on my earlier message about LAWCOLAB — I know inboxes get busy!</p>
<p>{{FirmName}} is exactly the type of firm that gets the most from our platform. Would you have 15 minutes this week for a quick demo?</p>
<p>Book directly: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>Warm regards,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_meeting():
    return """<p>Good day,</p>
<p>I'd love to show you LAWCOLAB in action — just 15 minutes and you'll see exactly how it can help {{FirmName}}.</p>
<p>Pick a time that works for you: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>Best,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_demo():
    return """<p>Good day {{ContactName}},</p>
<p>You're invited to a live LAWCOLAB demo tailored for {{FirmName}}.</p>
<p>We'll walk through case management, billing, client portal, and your firm's public directory listing — all in 20 minutes.</p>
<p>Reserve your spot: <a href="{{DemoBookingLink}}">{{DemoBookingLink}}</a></p>
<p>See you there!<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_trial():
    return """<p>Good day,</p>
<p>Your free LAWCOLAB trial is ready and waiting for <strong>{{FirmName}}</strong>.</p>
<p>Log in now at <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a> and explore all features — no credit card required.</p>
<p>Let me know if you need help getting started.</p>
<p>Best,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_renewal():
    return """<p>Good day,</p>
<p>Your LAWCOLAB subscription is coming up for renewal.</p>
<p>We value having {{FirmName}} as part of our community. Renew now to continue uninterrupted access to all features.</p>
<p>Any questions? WhatsApp us: +2348036622568</p>
<p>Best,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_thanks():
    return """<p>Good day {{ContactName}},</p>
<p>Thank you for choosing LAWCOLAB — we're thrilled to have {{FirmName}} on board.</p>
<p>If you ever have questions or need help, our team is always available.</p>
<p>Warm regards,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


def _generic_reengage():
    return """<p>Good day,</p>
<p>We noticed it's been a while since {{FirmName}} visited LAWCOLAB — and we've added some exciting new features since then.</p>
<p>Come back and take a look: <a href="{{FreeTrialLink}}">{{FreeTrialLink}}</a></p>
<p>We'd love to reconnect — WhatsApp us anytime: +2348036622568</p>
<p>Best,<br>{{SalesRep}}<br>LAWCOLAB</p>"""


# ── Firm Contacts ──────────────────────────────────────────────────────────────

@email_crm_bp.route('/contacts/<int:firm_id>')
@require_super_admin
def firm_contacts(firm_id):
    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    counts = _folder_counts()
    try:
        rows = db.session.execute(
            text("SELECT * FROM firm_contacts WHERE firm_id=:fid ORDER BY is_primary DESC, name"),
            {"fid": firm_id}
        ).fetchall()
        contacts = [dict(r._mapping) for r in rows]
    except Exception:
        contacts = []
    return render_template('email_crm/contacts.html',
                           firm=firm, contacts=contacts, counts=counts)


@email_crm_bp.route('/contacts/<int:firm_id>/add', methods=['POST'])
@require_super_admin
def add_contact(firm_id):
    data = request.form
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    try:
        db.session.execute(text("""
            INSERT INTO firm_contacts
            (firm_id, name, email, phone, whatsapp, job_title, department, preferred_language,
             notes, is_primary, created_at, updated_at)
            VALUES (:fid, :name, :email, :phone, :wa, :title, :dept, :lang, :notes, :primary, NOW(), NOW())
        """), dict(
            fid=firm_id, name=name,
            email=data.get('email',''), phone=data.get('phone',''),
            wa=data.get('whatsapp',''), title=data.get('job_title',''),
            dept=data.get('department',''), lang=data.get('preferred_language','English'),
            notes=data.get('notes',''), primary=bool(data.get('is_primary'))
        ))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@email_crm_bp.route('/contacts/delete/<int:contact_id>', methods=['POST'])
@require_super_admin
def delete_contact(contact_id):
    try:
        db.session.execute(text("DELETE FROM firm_contacts WHERE id=:id"), {"id": contact_id})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Analytics ──────────────────────────────────────────────────────────────────

@email_crm_bp.route('/analytics')
@require_super_admin
def analytics():
    counts = _folder_counts()

    # Totals
    total_sent = OutreachMessage.query.filter(
        OutreachMessage.status.in_(['sent','delivered','opened','clicked','replied'])
    ).count()
    total_opened  = OutreachMessage.query.filter(OutreachMessage.status.in_(['opened','clicked','replied'])).count()
    total_clicked = OutreachMessage.query.filter(OutreachMessage.status.in_(['clicked','replied'])).count()
    total_replied = OutreachMessage.query.filter_by(status='replied').count()
    total_bounced = OutreachMessage.query.filter_by(status='bounced').count()
    total_failed  = OutreachMessage.query.filter_by(status='failed').count()

    open_rate    = round(total_opened  / total_sent * 100 if total_sent else 0, 1)
    click_rate   = round(total_clicked / total_sent * 100 if total_sent else 0, 1)
    reply_rate   = round(total_replied / total_sent * 100 if total_sent else 0, 1)
    bounce_rate  = round(total_bounced / total_sent * 100 if total_sent else 0, 1)

    # Daily trend (last 14 days)
    daily_trend = []
    for i in range(13, -1, -1):
        d = datetime.now() - timedelta(days=i)
        start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)
        cnt = OutreachMessage.query.filter(
            OutreachMessage.sent_at >= start,
            OutreachMessage.sent_at < end,
        ).count()
        daily_trend.append({'date': start.strftime('%b %d'), 'count': cnt})

    # Status breakdown
    status_data = {}
    for row in db.session.query(OutreachMessage.status, func.count(OutreachMessage.id)).group_by(
            OutreachMessage.status).all():
        status_data[row[0] or 'draft'] = row[1]

    # Top campaigns
    top_campaigns = db.session.query(
        CrmCampaign.name,
        func.count(OutreachMessage.id).label('cnt')
    ).join(OutreachMessage, OutreachMessage.campaign_id == CrmCampaign.id, isouter=True
    ).group_by(CrmCampaign.id, CrmCampaign.name
    ).order_by(desc('cnt')).limit(5).all()

    # Top templates
    top_templates = []
    try:
        rows = db.session.execute(text("""
            SELECT name, use_count FROM email_templates
            ORDER BY use_count DESC LIMIT 5
        """)).fetchall()
        top_templates = [dict(r._mapping) for r in rows]
    except Exception:
        pass

    # Region stats
    region_data = db.session.query(
        DirectoryLawFirm.country,
        func.count(OutreachMessage.id).label('cnt')
    ).join(OutreachMessage, OutreachMessage.firm_id == DirectoryLawFirm.id, isouter=True
    ).filter(DirectoryLawFirm.country != None  # noqa: E711
    ).group_by(DirectoryLawFirm.country).order_by(desc('cnt')).limit(8).all()

    # Today's count
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = OutreachMessage.query.filter(
        OutreachMessage.sent_at >= today_start
    ).count()

    return render_template('email_crm/analytics.html',
                           counts=counts,
                           total_sent=total_sent, total_opened=total_opened,
                           total_clicked=total_clicked, total_replied=total_replied,
                           total_bounced=total_bounced, total_failed=total_failed,
                           open_rate=open_rate, click_rate=click_rate,
                           reply_rate=reply_rate, bounce_rate=bounce_rate,
                           daily_trend=json.dumps(daily_trend),
                           status_data=json.dumps(status_data),
                           top_campaigns=top_campaigns,
                           top_templates=top_templates,
                           region_data=region_data,
                           sent_today=sent_today)


# ── Settings ───────────────────────────────────────────────────────────────────

@email_crm_bp.route('/settings')
@require_super_admin
def settings():
    counts   = _folder_counts()
    s        = _get_settings()
    return render_template('email_crm/settings.html', counts=counts, s=s)


@email_crm_bp.route('/settings/save', methods=['POST'])
@require_super_admin
def save_settings():
    data = request.form
    try:
        existing = db.session.execute(text("SELECT id FROM email_settings LIMIT 1")).fetchone()
        params = dict(
            provider    = data.get('provider', 'simulate'),
            smtp_host   = data.get('smtp_host', ''),
            smtp_port   = int(data.get('smtp_port') or 587),
            smtp_user   = data.get('smtp_user', ''),
            smtp_password = data.get('smtp_password', '') or None,
            smtp_use_tls  = bool(data.get('smtp_use_tls')),
            api_key     = data.get('api_key', '') or None,
            from_name   = data.get('from_name', 'LAWCOLAB'),
            from_email  = data.get('from_email', 'noreply@lawcolab.com'),
            reply_to    = data.get('reply_to', '') or None,
            signature_html   = data.get('signature_html', '') or None,
            email_footer     = data.get('email_footer', '') or None,
            brand_color      = data.get('brand_color', '#0d1b4b'),
            company_logo_url = data.get('company_logo_url', '') or None,
            track_opens  = bool(data.get('track_opens')),
            track_clicks = bool(data.get('track_clicks')),
            unsubscribe_footer = data.get('unsubscribe_footer', '') or None,
            daily_send_limit   = int(data.get('daily_send_limit') or 500),
        )
        if existing:
            db.session.execute(text("""
                UPDATE email_settings SET
                  provider=:provider, smtp_host=:smtp_host, smtp_port=:smtp_port,
                  smtp_user=:smtp_user, smtp_password=COALESCE(:smtp_password, smtp_password),
                  smtp_use_tls=:smtp_use_tls, api_key=COALESCE(:api_key, api_key),
                  from_name=:from_name, from_email=:from_email, reply_to=:reply_to,
                  signature_html=:signature_html, email_footer=:email_footer,
                  brand_color=:brand_color, company_logo_url=:company_logo_url,
                  track_opens=:track_opens, track_clicks=:track_clicks,
                  unsubscribe_footer=:unsubscribe_footer, daily_send_limit=:daily_send_limit,
                  updated_at=NOW()
            """), params)
        else:
            db.session.execute(text("""
                INSERT INTO email_settings
                (provider, smtp_host, smtp_port, smtp_user, smtp_password, smtp_use_tls,
                 api_key, from_name, from_email, reply_to, signature_html, email_footer,
                 brand_color, company_logo_url, track_opens, track_clicks,
                 unsubscribe_footer, daily_send_limit, updated_at)
                VALUES (:provider, :smtp_host, :smtp_port, :smtp_user, :smtp_password, :smtp_use_tls,
                        :api_key, :from_name, :from_email, :reply_to, :signature_html, :email_footer,
                        :brand_color, :company_logo_url, :track_opens, :track_clicks,
                        :unsubscribe_footer, :daily_send_limit, NOW())
            """), params)
        db.session.commit()
        flash('Email settings saved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving settings: {e}', 'error')
    return redirect(url_for('email_crm.settings'))


@email_crm_bp.route('/settings/test', methods=['POST'])
@require_super_admin
def test_send():
    to_email = request.json.get('email', current_user.email)
    result = send_email(
        to_email=to_email,
        subject='LAWCOLAB Email CRM — Test Message',
        body_html='<p>This is a test email from your LAWCOLAB Email CRM. If you see this, your email provider is configured correctly! 🎉</p>',
        base_url=_get_base_url(),
    )
    return jsonify(result)


# ── Open/Click Tracking ────────────────────────────────────────────────────────

@email_crm_bp.route('/track/open/<token>')
def track_open(token):
    """Tracking pixel endpoint — returns 1×1 transparent GIF."""
    try:
        msg = OutreachMessage.query.filter_by(tracking_token=token).first()
        if msg:
            if msg.status in ('sent', 'delivered'):
                msg.status = 'opened'
                msg.opened_at = msg.opened_at or datetime.now()
            msg.open_count = (msg.open_count or 0) + 1
            # Log tracking event
            try:
                db.session.execute(text("""
                    INSERT INTO email_tracking_events (message_id, event_type, ip_address, user_agent, created_at)
                    VALUES (:mid, 'open', :ip, :ua, NOW())
                """), dict(mid=msg.id, ip=request.remote_addr,
                           ua=request.headers.get('User-Agent', '')[:500]))
            except Exception:
                pass
            db.session.commit()
    except Exception:
        pass
    # Return transparent 1x1 GIF
    gif = b'GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;'
    resp = make_response(gif)
    resp.headers['Content-Type']  = 'image/gif'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@email_crm_bp.route('/track/click/<token>')
def track_click(token):
    """Click tracking — redirect to original URL."""
    original_url = request.args.get('url', '/')
    try:
        decoded_url = urllib.parse.unquote(original_url)
        msg = OutreachMessage.query.filter_by(tracking_token=token).first()
        if msg:
            if msg.status == 'opened':
                msg.status = 'clicked'
            if not msg.clicked_at:
                msg.clicked_at = datetime.now()
            msg.click_count = (msg.click_count or 0) + 1
            try:
                db.session.execute(text("""
                    INSERT INTO email_tracking_events
                    (message_id, event_type, ip_address, user_agent, url_clicked, created_at)
                    VALUES (:mid, 'click', :ip, :ua, :url, NOW())
                """), dict(mid=msg.id, ip=request.remote_addr,
                           ua=request.headers.get('User-Agent', '')[:500],
                           url=decoded_url[:1000]))
            except Exception:
                pass
            db.session.commit()
        return redirect(decoded_url)
    except Exception:
        return redirect('/')


# ── Automation ─────────────────────────────────────────────────────────────────

@email_crm_bp.route('/automation')
@require_super_admin
def automation():
    counts = _folder_counts()
    automations = []
    try:
        rows = db.session.execute(
            text("SELECT * FROM email_automations ORDER BY created_at DESC")
        ).fetchall()
        automations = [dict(r._mapping) for r in rows]
        for a in automations:
            steps = db.session.execute(
                text("SELECT * FROM email_automation_steps WHERE automation_id=:aid ORDER BY step_order"),
                {"aid": a['id']}
            ).fetchall()
            a['steps'] = [dict(s._mapping) for s in steps]
    except Exception:
        pass
    return render_template('email_crm/automation.html', counts=counts, automations=automations)


@email_crm_bp.route('/automation/create', methods=['POST'])
@require_super_admin
def create_automation():
    data = request.form
    name         = data.get('name', '').strip()
    description  = data.get('description', '').strip()
    trigger_type = data.get('trigger_type', 'manual').strip()
    if not name:
        flash('Automation name required.', 'error')
        return redirect(url_for('email_crm.automation'))
    try:
        db.session.execute(text("""
            INSERT INTO email_automations (name, description, trigger_type, is_active, created_by_id, created_at, updated_at)
            VALUES (:name, :desc, :ttype, FALSE, :uid, NOW(), NOW())
        """), dict(name=name, desc=description, ttype=trigger_type, uid=current_user.id))
        db.session.commit()
        flash(f'Automation "{name}" created.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')
    return redirect(url_for('email_crm.automation'))


@email_crm_bp.route('/automation/<int:auto_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_automation(auto_id):
    try:
        db.session.execute(text("""
            UPDATE email_automations SET is_active = NOT is_active, updated_at=NOW() WHERE id=:id
        """), {"id": auto_id})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Search ─────────────────────────────────────────────────────────────────────

@email_crm_bp.route('/search')
@require_super_admin
def search():
    q        = request.args.get('q', '').strip()
    counts   = _folder_counts()
    messages = []
    if q:
        messages = OutreachMessage.query.filter(
            OutreachMessage.is_deleted == False,  # noqa: E712
            or_(
                OutreachMessage.subject.ilike(f'%{q}%'),
                OutreachMessage.body.ilike(f'%{q}%'),
                OutreachMessage.recipient_email.ilike(f'%{q}%'),
                OutreachMessage.recipient_name.ilike(f'%{q}%'),
            )
        ).order_by(desc(OutreachMessage.created_at)).limit(50).all()
    return render_template('email_crm/search.html', messages=messages,
                           q=q, counts=counts)
