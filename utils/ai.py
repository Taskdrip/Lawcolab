"""
utils/ai.py — Free Open-Source AI Engine for LAWCOLAB
Uses Groq API (free tier) with Llama 3.3 70B — the world's fastest open-source LLM.
Falls back to smart templates when GROQ_API_KEY is not set.

Get a free API key at: https://console.groq.com (no credit card required)
"""
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama-3.3-70b-versatile"   # open-source Llama 3.3, free tier
FALLBACK_MODEL = "llama-3.1-8b-instant"      # lighter fallback on Groq


def _groq_key():
    return os.environ.get("GROQ_API_KEY", "").strip()


def _call_groq(prompt: str, json_response: bool = True, max_tokens: int = 700, temperature: float = 0.8) -> str | None:
    """
    Call Groq's free Llama 3.3 70B API.
    Returns the raw string content or None on failure.
    """
    key = _groq_key()
    if not key:
        return None

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_response:
        payload["response_format"] = {"type": "json_object"}

    for model in [GROQ_MODEL, FALLBACK_MODEL]:
        try:
            payload["model"] = model
            r = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("Groq call failed with model %s: %s", model, e)
            continue

    return None


# ─── Law Firm Outreach ────────────────────────────────────────────────────────

def generate_firm_outreach(firm, channel: str, msg_type: str) -> dict:
    """
    Generate personalised outreach message for a law firm.
    Returns {"subject": str, "body": str}.
    Uses Groq Llama 3.3 70B if GROQ_API_KEY is set, else templates.
    """
    areas = ", ".join(firm.practice_areas[:3]) if firm.practice_areas else "legal practice"
    city  = f"{firm.city or ''}, {firm.country or ''}".strip(", ")

    type_label = {
        "cold_outreach":   "cold outreach",
        "follow_up":       "first follow-up",
        "second_followup": "second follow-up (softer tone)",
        "meeting_invite":  "meeting invitation",
        "re_engagement":   "re-engagement after silence",
    }.get(msg_type, "cold outreach")

    channel_label = {
        "email":    "professional email",
        "whatsapp": "short friendly WhatsApp message (max 3 lines)",
        "linkedin": "LinkedIn connection note (max 300 chars)",
        "sms":      "brief SMS (max 160 chars)",
    }.get(channel, "email")

    prompt = f"""You are a professional sales copywriter for LAWCOLAB, a modern legal practice management platform for African law firms.

Write a highly personalized {type_label} {channel_label} for this law firm:
- Firm Name: {firm.name}
- Location: {city}
- Practice Areas: {areas}
- Website: {firm.website or 'not available'}
- Description: {(firm.description or '')[:200]}

LAWCOLAB offers: client management, case tracking, billing, court calendar, team collaboration, analytics, client portal, custom feature development.

Rules:
- Sound personal and research-based, NOT generic
- Reference their specific practice areas and location naturally
- Keep it concise and professional
- End with a clear, low-friction CTA linking to https://lawcolab.com
- Do NOT use placeholder text like [Name]

Return a JSON object with exactly two keys: "subject" (for email, empty string for others) and "body"."""

    content = _call_groq(prompt, json_response=True, max_tokens=600, temperature=0.8)
    if content:
        try:
            return json.loads(content)
        except Exception:
            pass

    return _template_firm_message(firm, channel, msg_type)


def _template_firm_message(firm, channel: str, msg_type: str) -> dict:
    """Smart template fallback for firm outreach."""
    areas = ", ".join(firm.practice_areas[:3]) if firm.practice_areas else "legal practice"
    city  = firm.city or firm.country or "your area"
    name  = firm.name

    if channel == "email" and msg_type == "cold_outreach":
        return {
            "subject": f"Helping {name} Run Like a World-Class Firm",
            "body": f"""Dear {name} Team,

I came across {name} while researching leading law firms in {city} — your expertise in {areas} caught our attention.

My name is [Your Name] from LAWCOLAB — a Legal Operating System built specifically for law firms like yours.

Here is what LAWCOLAB can do for {name}:
• Case & Matter Management — every case, deadline, and document in one place
• Client Portal — clients get 24/7 secure access to their case updates
• Billing & Invoicing — instant invoice generation with payment tracking
• Court Calendar — never miss a hearing with smart deadline alerts
• Analytics Dashboard — firm performance and revenue at a glance

Whether {name} already has existing tools or is starting fresh, LAWCOLAB integrates seamlessly with your current setup — no disruption to your practice.

I'd love to offer you a free 20-minute demo. No commitment required.

Would you be available for a quick call this week?

Best regards,
[Your Name]
LAWCOLAB Growth Team
https://lawcolab.com""",
        }
    elif channel == "whatsapp":
        return {
            "subject": "",
            "body": f"Hi {name} Team! 👋 I came across your firm in {city} and wanted to share LAWCOLAB — a platform built for law firms to manage clients, cases, and billing in one place. Would you be open to a quick 20-min demo? 🙏 https://lawcolab.com",
        }
    elif msg_type == "follow_up":
        return {
            "subject": f"Following up — LAWCOLAB for {name}",
            "body": f"""Dear {name} Team,

I wanted to follow up on my previous message about LAWCOLAB.

Many {areas} firms in {city} are already using our platform to streamline their operations and serve more clients.

I'd still love to show you what LAWCOLAB can do for {name} — it only takes 20 minutes.

Best regards,
LAWCOLAB Growth Team
https://lawcolab.com""",
        }
    else:
        return {
            "subject": f"LAWCOLAB — Built for {name}",
            "body": f"Dear {name} Team,\n\nI'd love to show you how LAWCOLAB can help your firm in {city} manage cases, clients, and billing more efficiently.\n\nBest regards,\nLAWCOLAB Growth Team\nhttps://lawcolab.com",
        }


# ─── Law Firm AI Pitch & Call Script ─────────────────────────────────────────

def generate_firm_pitch(firm) -> tuple[dict, str]:
    """
    Generate AI email pitch + phone call script for a directory firm.
    Returns (email_dict, call_script_str).
    """
    areas     = ", ".join(firm.practice_areas[:4]) if firm.practice_areas else "legal practice"
    city      = firm.city or firm.country or "your area"
    has_web   = "Yes" if firm.has_website else "No (no existing website)"
    gmb_status = "Verified GMB listing" if firm.gmb_verified else "Unverified GMB listing"
    reviews   = (f"{firm.google_reviews_count} Google reviews, {firm.google_rating}★"
                 if firm.google_rating else "no Google rating found")
    no_web_line = (
        "\n\nI also noticed your firm doesn't yet have a dedicated website — LAWCOLAB "
        "includes a built-in client portal and public profile page, giving you a professional "
        "digital presence from day one." if not firm.has_website else ""
    )
    unverified_line = (
        "\n\nI noticed your Google Maps listing appears unverified — LAWCOLAB helps your firm "
        "look polished and credible online, which directly impacts how potential clients find you."
        if not firm.gmb_verified else ""
    )

    features = """LAWCOLAB features:
• Case & Matter Management — track every case, deadline, and document
• Client Portal — clients get 24/7 secure online access to their case updates
• Billing & Invoicing — instant invoice generation, payment tracking, receipts
• Court Calendar — deadline reminders, hearing alerts, court date history
• Team Collaboration — task assignment, internal messaging, document sharing
• Analytics Dashboard — firm performance, revenue, case statistics at a glance
• Client Acquisition Tools — digital intake forms, referral tracking, leads
• Custom Feature Development — our developer team builds features on request
• Mobile-Friendly — works on any device, anywhere"""

    # Email pitch
    email_prompt = f"""You are a top legal software sales writer for LAWCOLAB.

Write a personalized cold-outreach email to this law firm to pitch LAWCOLAB:
- Firm: {firm.name}
- Location: {city}, {firm.state or ''}, {firm.country or 'Nigeria'}
- Practice Areas: {areas}
- Website: {has_web}
- Google Maps status: {gmb_status}
- Google presence: {reviews}

{features}

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
- Sound personal and research-based, never generic or spammy
- Concise and professional: 250-350 words max

Return JSON: {{"subject": "...", "body": "..."}}"""

    email_content = _call_groq(email_prompt, json_response=True, max_tokens=700, temperature=0.82)
    if email_content:
        try:
            email_result = json.loads(email_content)
        except Exception:
            email_result = None
    else:
        email_result = None

    # Call script
    call_prompt = f"""You are a legal software sales trainer for LAWCOLAB.

Write a complete phone call script for calling this law firm:
- Firm: {firm.name}
- Location: {city}, {firm.state or ''}, {firm.country or 'Nigeria'}
- Practice Areas: {areas}
- Website: {has_web}
- Google status: {gmb_status} — {reviews}

{features}

Script structure (use clear headers):
1. OPENING — Warm greeting, introduce yourself as "from LAWCOLAB team"
2. PERMISSION CHECK — Ask if they have 2 minutes
3. PROBLEM STATEMENT — Pain most law firms in {city} face
4. SOLUTION INTRO — LAWCOLAB as a legal operating system for African law firms
5. KEY FEATURES — 3-4 features most relevant to {areas}
6. WEBSITE BRIDGE — LAWCOLAB works with or without their current website
7. CUSTOM DEVELOPMENT — Mention our developer team
8. CTA — Offer a free 20-minute screen-share demo
9. OBJECTION HANDLERS — 3 common objections with confident responses
10. CLOSING — Thank them, confirm next step, share https://lawcolab.com

Use [PAUSE], [LISTEN], [SMILE] stage directions where helpful."""

    call_content = _call_groq(call_prompt, json_response=False, max_tokens=900, temperature=0.75)

    if not email_result:
        email_result, fallback_call = _template_pitch(firm, areas, city, has_web, gmb_status, no_web_line, unverified_line)
        if not call_content:
            call_content = fallback_call
    elif not call_content:
        _, fallback_call = _template_pitch(firm, areas, city, has_web, gmb_status, no_web_line, unverified_line)
        call_content = fallback_call

    return email_result, call_content


def _template_pitch(firm, areas, city, has_web, gmb_status, no_web_line="", unverified_line=""):
    """Fallback template pitch when Groq is not configured."""
    name = firm.name
    if firm.has_website:
        web_bridge = f"'Even though you already have a website — LAWCOLAB integrates alongside it, adding the backend systems your firm needs to operate efficiently.'"
    else:
        web_bridge = f"'I also noticed {name} doesn't yet have a dedicated website. LAWCOLAB includes a built-in public profile page and client portal — giving your firm a professional digital presence from day one.'"

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

I'd love to offer you a free 20-minute demo. No commitment required.

Would you be available for a quick call this week?

Best regards,
[Your Name]
LAWCOLAB Growth Team
https://lawcolab.com"""

    _div = "─" * 60
    call_script = f"""LAWCOLAB CALL SCRIPT — {name}
Location: {city} | Practice: {areas} | {gmb_status}
{_div}

1. OPENING
"Good [morning/afternoon], may I please speak with the managing partner or firm administrator at {name}?"
[When connected]
"Hello, my name is [Your Name] calling from LAWCOLAB. I came across {name} on Google Maps while researching leading law firms in {city} — particularly in {areas}. I have a very quick question if you have two minutes?"
[PAUSE] [LISTEN]

2. PERMISSION CHECK
"I promise to be brief. Is now a good time for just two minutes?"
[If YES → continue. If NO → "No problem at all — when would be a better time to call back?"]

3. PROBLEM STATEMENT
"I speak with law firms in {city} daily, and the most common challenge I hear is managing cases, client follow-ups, and billing across different tools — often spreadsheets, WhatsApp, and manual invoices — which costs the firm hours every week."
[PAUSE] "Does that sound familiar at {name}?"

4. SOLUTION INTRO
"That's exactly why we built LAWCOLAB — a complete Legal Operating System for law firms. It brings case management, billing, client communication, and calendars into one platform designed specifically for firms like {name}."

5. KEY FEATURES FOR {areas.upper()}
"For a firm specialising in {areas}, the most valuable features are usually:
— Case tracking so nothing falls through the cracks
— Instant invoice generation with payment follow-ups built in
— A client portal so clients can check their case status anytime
— Court deadline alerts so you never miss a hearing date"

6. WEBSITE BRIDGE
{web_bridge}

7. CUSTOM DEVELOPMENT
"Our developer team is on standby to add features specific to {name}'s workflow at no extra charge."

8. CTA
"I'd love to show you a 20-minute screen-share demo — completely free, no commitment. When works best for you this week?"
[LISTEN — book the time]

9. OBJECTION HANDLERS
Objection: "We already have a system."
Response: "That's great — LAWCOLAB is designed to work alongside your existing tools, not replace them. Most firms find it fills in the gaps their current setup doesn't cover."

Objection: "We're too busy right now."
Response: "Completely understand — that's actually why most firms reach out. LAWCOLAB is designed to save time, not add to it. The demo is just 20 minutes and I can work around your schedule."

Objection: "How much does it cost?"
Response: "We have plans starting from as low as ₦39/month — less than the cost of a single client meeting. There's also a free trial so you can see the value before committing."

10. CLOSING
"Thank you so much for your time, [Name]. I'll send you a quick email with our website: https://lawcolab.com — you can also book a demo directly there. Have a great [day/week]!"
[Confirm name, email, next step]"""

    return {"subject": f"Helping {name} Run Like a World-Class Firm", "body": email_body}, call_script


# ─── Community Outreach ───────────────────────────────────────────────────────

def generate_community_message(community, channel: str) -> dict:
    """
    Generate community outreach message.
    Returns {"subject": str, "body": str, "channel": str}.
    """
    platform = community.platform.title()
    name     = community.community_name
    size     = community.member_count_display or "large"
    category = community.category or "legal professionals"
    country  = community.country_focus or "global"

    channel_instruction = {
        "post":    f"a community post for a {platform} group/community ({size} members)",
        "comment": f"a conversational comment to introduce LAWCOLAB in a {platform} thread",
        "dm":      f"a short, warm direct message to the {platform} community admin",
        "email":   f"a professional outreach email to the {platform} community admin",
    }.get(channel, "a social media post")

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

    content = _call_groq(prompt, json_response=True, max_tokens=700, temperature=0.85)
    if content:
        try:
            result = json.loads(content)
            result["channel"] = channel
            return result
        except Exception:
            pass

    return _template_community_message(community, channel)


def _template_community_message(community, channel: str) -> dict:
    """Smart template fallback for community outreach."""
    name     = community.community_name
    platform = community.platform.title()
    category = community.category or "legal professionals"

    body = f"""👋 Hello {name} community!

We wanted to introduce ourselves — we're LAWCOLAB, a Legal Operating System built specifically for law firms and legal professionals.

🎯 **What LAWCOLAB does for your practice:**
✅ Case & Client Management — all your matters in one place
✅ Billing & Invoicing — get paid faster with instant invoice generation
✅ Court Calendar — smart deadline reminders so you never miss a hearing
✅ Client Portal — clients get 24/7 secure access to their case updates
✅ Team Collaboration — internal messaging and document sharing

🎯 **Who is it for?**
Perfect for solo practitioners, small-to-medium law firms, and legal chambers looking to modernize their operations and win more clients.

🚀 **Start for free** → https://lawcolab.com

We'd love to hear from this amazing community of {category.lower()} — what tools are you currently using to manage your practice?

— The LAWCOLAB Team"""

    subject = f"LAWCOLAB — Legal Operating System for {category}" if channel == "email" else ""
    return {"subject": subject, "body": body, "channel": channel}
