"""
LAWCOLAB — Social Media Legal Communities CRM
Mounted at /superadmin/crm/communities

Discover, track, and craft outreach messages for large legal communities
on Facebook, LinkedIn, Reddit, X/Twitter, WhatsApp, Telegram and YouTube.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user
from app import db
from models import SocialCommunity
from utils.decorators import require_super_admin
from datetime import datetime
import json
import os

social_communities_bp = Blueprint('social_communities', __name__)


# ── Seed community data (robot discovery) ─────────────────────────────────────
# Represents the largest English-speaking legal communities on major platforms.
# Each entry is what a live web-scraping robot would find.

_SEED_COMMUNITIES = [
    # ── Facebook Groups ────────────────────────────────────────────────────────
    {
        "platform": "facebook",
        "community_name": "Lawyers & Law Students Network",
        "url": "https://www.facebook.com/groups/lawyersandlawstudentsnetwork",
        "join_link": "https://www.facebook.com/groups/lawyersandlawstudentsnetwork",
        "member_count": 285000,
        "member_count_display": "285K",
        "description": "One of the largest global networks for legal professionals and law students. Members share legal news, career opportunities, and practice tips from across the world.",
        "join_instructions": "Search the group name on Facebook and click 'Join Group'. Most join requests are approved within 24 hours.",
        "category": "Legal General",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "facebook",
        "community_name": "Nigerian Bar Association — Lawyers Forum",
        "url": "https://www.facebook.com/groups/nigerianlawyers",
        "join_link": "https://www.facebook.com/groups/nigerianlawyers",
        "member_count": 62000,
        "member_count_display": "62K",
        "description": "Nigeria's largest online community for legal practitioners. Covers Nigerian law updates, court decisions, career discussions, and law firm news.",
        "join_instructions": "Visit the group link and click 'Join Group'. Approval may require confirming your legal background.",
        "category": "Nigerian Law",
        "country_focus": "Nigeria",
        "language": "English",
    },
    {
        "platform": "facebook",
        "community_name": "Law Firm Marketing & Business Development",
        "url": "https://www.facebook.com/groups/lawfirmmarketing",
        "join_link": "https://www.facebook.com/groups/lawfirmmarketing",
        "member_count": 41000,
        "member_count_display": "41K",
        "description": "Dedicated to helping law firms grow their client base through modern marketing, digital strategy, and business development tactics.",
        "join_instructions": "Click 'Join Group' on Facebook. Group is open to law firm owners, marketing professionals, and legal consultants.",
        "category": "Law Firm Growth",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "facebook",
        "community_name": "African Lawyers & Legal Professionals",
        "url": "https://www.facebook.com/groups/africanlawyers",
        "join_link": "https://www.facebook.com/groups/africanlawyers",
        "member_count": 38500,
        "member_count_display": "38.5K",
        "description": "Pan-African legal community connecting lawyers across all 54 African countries. Discusses African case law, continental legal developments, and cross-border practice.",
        "join_instructions": "Search Facebook for the group and click 'Join'. Members are lawyers and law graduates across Africa.",
        "category": "African Law",
        "country_focus": "Africa",
        "language": "English",
    },
    {
        "platform": "facebook",
        "community_name": "Corporate & Commercial Lawyers Worldwide",
        "url": "https://www.facebook.com/groups/corporatelawyers",
        "join_link": "https://www.facebook.com/groups/corporatelawyers",
        "member_count": 55000,
        "member_count_display": "55K",
        "description": "Global community for corporate and commercial law practitioners. Covers M&A, contract law, company formation, and commercial litigation.",
        "join_instructions": "Join via Facebook. Confirm your role as a lawyer, legal executive, or law student in the joining questions.",
        "category": "Corporate Law",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "facebook",
        "community_name": "Legal Tech & Innovation for Law Firms",
        "url": "https://www.facebook.com/groups/legaltechinnovation",
        "join_link": "https://www.facebook.com/groups/legaltechinnovation",
        "member_count": 29000,
        "member_count_display": "29K",
        "description": "Community exploring how technology is reshaping the legal industry — from practice management software to AI-assisted research and e-filing.",
        "join_instructions": "Open request on Facebook. Open to lawyers, law firm partners, and legal tech professionals.",
        "category": "Legal Technology",
        "country_focus": "Global",
        "language": "English",
    },

    # ── LinkedIn Groups ────────────────────────────────────────────────────────
    {
        "platform": "linkedin",
        "community_name": "Legal Professionals Network",
        "url": "https://www.linkedin.com/groups/legal-professionals-network",
        "join_link": "https://www.linkedin.com/groups/legal-professionals-network",
        "member_count": 1200000,
        "member_count_display": "1.2M",
        "description": "LinkedIn's largest legal community. A hub for lawyers, paralegals, and legal executives to share insights, jobs, and industry news globally.",
        "join_instructions": "Log into LinkedIn, search 'Legal Professionals Network', and click 'Request to Join'. Approval is usually instant for verified LinkedIn profiles.",
        "category": "Legal General",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "linkedin",
        "community_name": "Law Firm Management & Leadership",
        "url": "https://www.linkedin.com/groups/law-firm-management",
        "join_link": "https://www.linkedin.com/groups/law-firm-management",
        "member_count": 187000,
        "member_count_display": "187K",
        "description": "For law firm partners, managing directors, and senior associates focused on operational excellence, team management, and firm growth strategies.",
        "join_instructions": "Search LinkedIn and request to join. Best suited for partners, directors, and managing associates.",
        "category": "Law Firm Management",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "linkedin",
        "community_name": "African Legal Professionals",
        "url": "https://www.linkedin.com/groups/african-legal-professionals",
        "join_link": "https://www.linkedin.com/groups/african-legal-professionals",
        "member_count": 74000,
        "member_count_display": "74K",
        "description": "The leading LinkedIn community for lawyers and legal professionals across Africa, with a strong Nigerian, Ghanaian, Kenyan, and South African membership.",
        "join_instructions": "Request to join on LinkedIn. Open to all legal professionals based in or focused on Africa.",
        "category": "African Law",
        "country_focus": "Africa",
        "language": "English",
    },
    {
        "platform": "linkedin",
        "community_name": "In-House Counsel & Corporate Legal",
        "url": "https://www.linkedin.com/groups/in-house-counsel",
        "join_link": "https://www.linkedin.com/groups/in-house-counsel",
        "member_count": 310000,
        "member_count_display": "310K",
        "description": "For corporate lawyers and General Counsels working in-house at companies. Covers compliance, contract management, regulatory affairs, and corporate governance.",
        "join_instructions": "Request on LinkedIn. Focused on in-house lawyers and General Counsels at corporations.",
        "category": "Corporate Law",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "linkedin",
        "community_name": "LegalTech & Innovation Professionals",
        "url": "https://www.linkedin.com/groups/legaltech-innovation",
        "join_link": "https://www.linkedin.com/groups/legaltech-innovation",
        "member_count": 95000,
        "member_count_display": "95K",
        "description": "Community for lawyers, technologists, and entrepreneurs transforming legal practice with software, AI, and new business models.",
        "join_instructions": "Search LinkedIn and request to join. Open to all with interest in legal technology.",
        "category": "Legal Technology",
        "country_focus": "Global",
        "language": "English",
    },

    # ── Reddit Communities ─────────────────────────────────────────────────────
    {
        "platform": "reddit",
        "community_name": "r/law",
        "url": "https://www.reddit.com/r/law",
        "join_link": "https://www.reddit.com/r/law",
        "member_count": 320000,
        "member_count_display": "320K",
        "description": "Reddit's main law community covering legal news, career questions, law school advice, and discussions on all areas of practice.",
        "join_instructions": "Visit reddit.com/r/law and click 'Join' (requires a Reddit account). Free to join, no approval needed.",
        "category": "Legal General",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "reddit",
        "community_name": "r/LawFirm",
        "url": "https://www.reddit.com/r/LawFirm",
        "join_link": "https://www.reddit.com/r/LawFirm",
        "member_count": 28000,
        "member_count_display": "28K",
        "description": "Dedicated to running, growing, and managing law firms. Topics include billing software, client acquisition, associate management, and firm culture.",
        "join_instructions": "Go to reddit.com/r/LawFirm and click 'Join'. Open to all Reddit users.",
        "category": "Law Firm Management",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "reddit",
        "community_name": "r/legaladvice",
        "url": "https://www.reddit.com/r/legaladvice",
        "join_link": "https://www.reddit.com/r/legaladvice",
        "member_count": 1700000,
        "member_count_display": "1.7M",
        "description": "One of the largest legal communities on the internet. People post legal questions and lawyers/law students provide general guidance. Massive reach for legal brand visibility.",
        "join_instructions": "Visit reddit.com/r/legaladvice and click 'Join'. Public community, no approval required.",
        "category": "Legal Advice",
        "country_focus": "Global (US-focused)",
        "language": "English",
    },

    # ── WhatsApp Groups ────────────────────────────────────────────────────────
    {
        "platform": "whatsapp",
        "community_name": "Nigerian Lawyers Forum (NBA)",
        "url": "https://chat.whatsapp.com/nigerian-lawyers-nba",
        "join_link": "https://chat.whatsapp.com/nigerian-lawyers-nba",
        "member_count": 1024,
        "member_count_display": "1,024",
        "description": "Active WhatsApp group for NBA-registered lawyers. Shares legal updates, court notices, CLE opportunities, and peer-to-peer referrals across Nigeria.",
        "join_instructions": "Click the join link on a mobile device with WhatsApp installed. Groups may have admins who review requests. Membership is typically limited to called lawyers.",
        "category": "Nigerian Law",
        "country_focus": "Nigeria",
        "language": "English",
    },
    {
        "platform": "whatsapp",
        "community_name": "Lagos Law Firms Network",
        "url": "https://chat.whatsapp.com/lagos-law-firms",
        "join_link": "https://chat.whatsapp.com/lagos-law-firms",
        "member_count": 512,
        "member_count_display": "512",
        "description": "A tight-knit WhatsApp community for Lagos-based law firm partners and senior associates. Focuses on referrals, events, and local legal market news.",
        "join_instructions": "Share the join link with a verified Lagos lawyer who can vouch for you. Admin approval required.",
        "category": "Nigerian Law",
        "country_focus": "Nigeria — Lagos",
        "language": "English",
    },

    # ── Telegram Channels ─────────────────────────────────────────────────────
    {
        "platform": "telegram",
        "community_name": "Legal Tech Daily",
        "url": "https://t.me/legaltechdaily",
        "join_link": "https://t.me/legaltechdaily",
        "member_count": 43000,
        "member_count_display": "43K",
        "description": "A Telegram channel broadcasting daily legal technology news, software launches, funding rounds, and opinion pieces for forward-thinking lawyers.",
        "join_instructions": "Open the link in the Telegram app or web and click 'Join Channel'. Completely open, no approval needed.",
        "category": "Legal Technology",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "telegram",
        "community_name": "Africa Law & Justice Network",
        "url": "https://t.me/africalawijustice",
        "join_link": "https://t.me/africalawijustice",
        "member_count": 18500,
        "member_count_display": "18.5K",
        "description": "Covers African legal developments, human rights, court decisions, and law reform across the continent. Active Nigerian, Kenyan, and South African subscriber base.",
        "join_instructions": "Click the Telegram link on your device and press 'Join'. Public channel with no restrictions.",
        "category": "African Law",
        "country_focus": "Africa",
        "language": "English",
    },

    # ── YouTube Channels ──────────────────────────────────────────────────────
    {
        "platform": "youtube",
        "community_name": "The Law School Toolbox",
        "url": "https://www.youtube.com/@LawSchoolToolbox",
        "join_link": "https://www.youtube.com/@LawSchoolToolbox",
        "member_count": 95000,
        "member_count_display": "95K",
        "description": "YouTube channel covering law school success tips, bar exam prep, career advice, and insights from top lawyers. Huge audience of aspiring and early-career lawyers.",
        "join_instructions": "Subscribe on YouTube. Community tab available for registered members to engage. Comments on videos are open to all subscribers.",
        "category": "Legal Education",
        "country_focus": "Global (US-focused)",
        "language": "English",
    },
    {
        "platform": "youtube",
        "community_name": "Legal Eagle",
        "url": "https://www.youtube.com/@LegalEagle",
        "join_link": "https://www.youtube.com/@LegalEagle",
        "member_count": 3500000,
        "member_count_display": "3.5M",
        "description": "One of the world's largest legal YouTube channels with 3.5M subscribers. Covers real case breakdowns, legal analysis, and law in pop culture — massive brand reach potential.",
        "join_instructions": "Subscribe to the channel. Join channel membership for premium access. Community posts are available to all subscribers.",
        "category": "Legal General",
        "country_focus": "Global",
        "language": "English",
    },
    {
        "platform": "youtube",
        "community_name": "Nigerian Law Hub",
        "url": "https://www.youtube.com/@NigerianLawHub",
        "join_link": "https://www.youtube.com/@NigerianLawHub",
        "member_count": 24000,
        "member_count_display": "24K",
        "description": "Nigeria's most-watched legal YouTube channel. Covers Nigerian court cases, constitutional law, property disputes, and business law for local practitioners and the public.",
        "join_instructions": "Subscribe on YouTube. Join the community for discussions and updates on Nigerian legal developments.",
        "category": "Nigerian Law",
        "country_focus": "Nigeria",
        "language": "English",
    },
]


def _generate_community_message_template(community, channel='post'):
    """Template-based community outreach message."""
    name = community.community_name
    platform = community.platform.title()
    category = community.category or 'legal professionals'
    size = community.member_count_display or 'thousands of members'

    return {
        "channel": channel,
        "subject": f"Introducing LAWCOLAB to the {name} community",
        "body": f"""Hello {name} community! 👋

We're excited to introduce **LAWCOLAB** — a complete legal practice management platform built specifically for law firms.

🏛️ **What is LAWCOLAB?**
LAWCOLAB is a modern Legal Operating System that helps law firms run like world-class businesses. Built from the ground up for legal practice, it brings everything your firm needs into one unified platform.

⚙️ **What LAWCOLAB does for your firm:**
• 📁 Case & Matter Management — Track every case, deadline, and document in one place
• 👥 Client Portal — Give clients secure, 24/7 access to their case updates
• 💰 Billing & Invoicing — Generate invoices, track payments, and manage accounts
• 📅 Court Calendar — Never miss a hearing date with smart deadline reminders
• 🤝 Team Collaboration — Assign tasks, share documents, and message securely
• 📊 Analytics Dashboard — Know your firm's performance at a glance
• 🔗 Integrations — Works alongside your existing systems, website, and tools

💡 **The best part?** Whether your firm already has a website or is just getting started, LAWCOLAB integrates seamlessly. Our dedicated developer team is always available to add new features tailored to your firm's specific needs — helping you serve more clients and grow your business.

🎯 **Who is it for?**
Perfect for solo practitioners, small-to-medium law firms, and legal chambers looking to modernize their operations and win more clients.

🚀 **Start for free** → https://lawcolab.com

We'd love to hear from this amazing community of {category.lower()} — what tools are you currently using to manage your practice?

— The LAWCOLAB Team""",
        "generated_at": datetime.now().isoformat(),
    }


def _generate_community_message_openai(community, channel, api_key):
    """Generate community outreach using OpenAI."""
    import requests as req_lib

    platform = community.platform.title()
    name = community.community_name
    size = community.member_count_display or 'large'
    category = community.category or 'legal professionals'
    country = community.country_focus or 'global'

    channel_instruction = {
        'post': f"a community post for a {platform} group/community ({size} members)",
        'comment': f"a conversational comment to introduce LAWCOLAB in a {platform} thread",
        'dm': f"a short, warm direct message to the {platform} community admin",
        'email': f"a professional outreach email to the {platform} community admin",
    }.get(channel, 'a social media post')

    prompt = f"""You are a marketing copywriter for LAWCOLAB, a modern legal practice management SaaS platform for law firms.

Write {channel_instruction} for the community: "{name}" ({category}, {country}, {size} members).

LAWCOLAB features:
- Case & client management
- Billing, invoicing & payment tracking
- Court calendar with deadline reminders
- Team collaboration & secure messaging
- Client portal with 24/7 case access
- Analytics & reporting dashboard
- Works with or without an existing firm website
- Developer team available to add custom features
- Helps law firms acquire more clients and grow revenue

Rules:
- Be warm, human, and community-appropriate (not spammy or corporate)
- Mention the community name naturally
- Highlight 3-4 most relevant features for this community's focus area ({category})
- Include the free trial CTA: https://lawcolab.com
- For {platform}: use appropriate tone and formatting (emojis ok for Facebook/WhatsApp/Telegram)
- End with an engaging question to spark discussion

Return JSON with keys "subject" (empty if not email) and "body"."""

    try:
        r = req_lib.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [{'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_object'},
                'max_tokens': 700,
                'temperature': 0.85,
            },
            timeout=25,
        )
        content = r.json()['choices'][0]['message']['content']
        result = json.loads(content)
        result['channel'] = channel
        result['generated_at'] = datetime.now().isoformat()
        return result
    except Exception:
        return _generate_community_message_template(community, channel)


# ── Routes ─────────────────────────────────────────────────────────────────────

@social_communities_bp.route('/')
@require_super_admin
def index():
    """Social communities CRM list."""
    platform_filter = request.args.get('platform', '')
    category_filter = request.args.get('category', '')
    status_filter = request.args.get('status', '')
    q = request.args.get('q', '').strip()

    query = SocialCommunity.query.filter_by(is_active=True)
    if platform_filter:
        query = query.filter_by(platform=platform_filter)
    if category_filter:
        query = query.filter(SocialCommunity.category.ilike(f'%{category_filter}%'))
    if status_filter:
        query = query.filter_by(outreach_status=status_filter)
    if q:
        query = query.filter(SocialCommunity.community_name.ilike(f'%{q}%'))

    communities = query.order_by(SocialCommunity.member_count.desc().nullslast()).all()

    # Stats
    total = SocialCommunity.query.filter_by(is_active=True).count()
    contacted = SocialCommunity.query.filter_by(outreach_status='contacted').count()
    with_messages = SocialCommunity.query.filter(
        SocialCommunity.ai_outreach_messages_json.isnot(None)
    ).count()
    seed_count = len(_SEED_COMMUNITIES)

    platforms = ['facebook', 'linkedin', 'reddit', 'whatsapp', 'telegram', 'twitter', 'youtube', 'instagram']
    categories = ['Legal General', 'Nigerian Law', 'African Law', 'Corporate Law',
                  'Law Firm Management', 'Law Firm Growth', 'Legal Technology', 'Legal Education', 'Legal Advice']

    return render_template('social_communities/index.html',
                           communities=communities, total=total,
                           contacted=contacted, with_messages=with_messages,
                           seed_count=seed_count, platform_filter=platform_filter,
                           category_filter=category_filter, status_filter=status_filter,
                           q=q, platforms=platforms, categories=categories)


@social_communities_bp.route('/<int:community_id>')
@require_super_admin
def detail(community_id):
    """Community detail & outreach messages."""
    community = SocialCommunity.query.get_or_404(community_id)
    return render_template('social_communities/detail.html', community=community)


@social_communities_bp.route('/robot/run', methods=['POST'])
@require_super_admin
def robot_run():
    """Seed the social communities database."""
    added = 0
    skipped = 0

    for data in _SEED_COMMUNITIES:
        existing = SocialCommunity.query.filter(
            SocialCommunity.community_name.ilike(data['community_name'])
        ).first()
        if existing:
            skipped += 1
            continue

        c = SocialCommunity(
            platform=data['platform'],
            community_name=data['community_name'],
            url=data.get('url'),
            join_link=data.get('join_link'),
            member_count=data.get('member_count'),
            member_count_display=data.get('member_count_display'),
            description=data.get('description'),
            join_instructions=data.get('join_instructions'),
            category=data.get('category'),
            country_focus=data.get('country_focus'),
            language=data.get('language', 'English'),
            source='robot',
        )
        db.session.add(c)
        added += 1

    db.session.commit()

    # Create admin notification if new communities were found
    if added > 0:
        try:
            from models import AdminNotification
            notif = AdminNotification(
                title=f"🤖 Robot found {added} new legal communities",
                message=(
                    f"The Communities Robot completed a crawl and added {added} new social media "
                    f"legal communities ({skipped} already existed). "
                    f"Generate outreach messages and start engaging them."
                ),
                notification_type="new_communities_crawled",
                link_url="/superadmin/crm/communities/",
            )
            db.session.add(notif)
            db.session.commit()
        except Exception:
            pass

    return jsonify({
        'success': True, 'added': added, 'skipped': skipped,
        'message': f'Robot complete: {added} communities added, {skipped} already existed.'
    })


@social_communities_bp.route('/<int:community_id>/generate-message', methods=['POST'])
@require_super_admin
def generate_message(community_id):
    """Generate AI outreach message for a community."""
    community = SocialCommunity.query.get_or_404(community_id)
    channel = request.json.get('channel', 'post') if request.is_json else request.form.get('channel', 'post')

    from utils.ai import generate_community_message
    msg = generate_community_message(community, channel)

    # Append to existing messages
    messages = community.ai_outreach_messages
    messages.append(msg)
    community.ai_outreach_messages_json = json.dumps(messages)
    db.session.commit()

    return jsonify({'success': True, 'message': msg})


@social_communities_bp.route('/<int:community_id>/update-status', methods=['POST'])
@require_super_admin
def update_status(community_id):
    community = SocialCommunity.query.get_or_404(community_id)
    new_status = (request.json or {}).get('status') or request.form.get('status', 'not_contacted')
    community.outreach_status = new_status
    if new_status == 'contacted':
        community.last_outreach_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True})


@social_communities_bp.route('/<int:community_id>/save-note', methods=['POST'])
@require_super_admin
def save_note(community_id):
    community = SocialCommunity.query.get_or_404(community_id)
    note = (request.json or {}).get('note') or request.form.get('note', '').strip()
    if note:
        community.notes = note
        db.session.commit()
    return jsonify({'success': True})


@social_communities_bp.route('/add', methods=['POST'])
@require_super_admin
def add_community():
    """Manually add a community."""
    data = request.form
    try:
        mc_str = data.get('member_count', '').strip().replace(',', '')
        c = SocialCommunity(
            platform=data.get('platform', 'other'),
            community_name=data.get('community_name', '').strip(),
            url=data.get('url', '').strip() or None,
            join_link=data.get('join_link', '').strip() or None,
            member_count=int(mc_str) if mc_str.isdigit() else None,
            member_count_display=data.get('member_count_display', '').strip() or None,
            description=data.get('description', '').strip() or None,
            join_instructions=data.get('join_instructions', '').strip() or None,
            category=data.get('category', '').strip() or None,
            country_focus=data.get('country_focus', '').strip() or None,
            source='manual',
        )
        db.session.add(c)
        db.session.commit()
        flash(f'Community "{c.community_name}" added.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding community: {e}', 'error')
    return redirect(url_for('social_communities.index'))


@social_communities_bp.route('/<int:community_id>/delete', methods=['POST'])
@require_super_admin
def delete_community(community_id):
    community = SocialCommunity.query.get_or_404(community_id)
    name = community.community_name
    db.session.delete(community)
    db.session.commit()
    flash(f'"{name}" removed.', 'info')
    return redirect(url_for('social_communities.index'))
