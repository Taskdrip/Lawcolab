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


# ─── Shared brand voice constants ────────────────────────────────────────────

_SENDER = "Abraham Tahbat"
_WA     = "+2348036622568"
_URL    = "https://lawcolab.com"

_FEATURES_BLOCK = """LAWCOLAB features:
• Case & Matter Management — every case, document, and deadline in one organised hub
• Client Portal — clients get 24/7 secure online access to their case updates & invoices
• Billing & Invoicing — generate professional invoices instantly, track every payment
• Court Calendar & Deadline Alerts — automated reminders so no hearing date is ever missed
• Team Collaboration — task assignment, internal messaging, and document sharing
• Analytics Dashboard — real-time revenue, case load, and performance insights at a glance
• Client Acquisition Tools — digital intake forms, referral tracking, and lead management
• Smart Business Directory — firm listed globally; clients search by practice area & location
• Custom Feature Development — our in-house dev team builds features on request at no extra cost
• Fully Mobile — works on any device, anywhere"""

_BRAND_CONTEXT = f"""LAWCOLAB Brand Context:
- Sender: {_SENDER} — a lawyer and web developer with 15+ years building SaaS platforms
- Product: LAWCOLAB — a complete Legal Operating System for law firms and legal practitioners
- Mission: Help African law firms run like world-class businesses
- Web App: {_URL}  (free trial access provided)
- WhatsApp: {_WA}"""


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
        "whatsapp": "short WhatsApp message (max 5 lines, warm and human)",
        "linkedin": "LinkedIn connection note (max 300 chars)",
        "sms":      "brief SMS (max 160 chars)",
    }.get(channel, "email")

    prompt = f"""You are writing on behalf of {_SENDER} for LAWCOLAB.

{_BRAND_CONTEXT}

{_FEATURES_BLOCK}

Write a {type_label} {channel_label} to this law firm:
- Firm Name: {firm.name}
- Location: {city}
- Practice Areas: {areas}
- Website: {firm.website or 'none'}
- Description: {(firm.description or '')[:200]}

Strict rules:
1. Open with "Good day" — warm, human, never robotic
2. {_SENDER} introduces himself as a lawyer AND web developer with 15+ years of SaaS experience
3. Mention specifically how we discovered their firm (Google Maps / public legal directory / online research in {city})
4. Name 2-3 real pain points law firms and legal practitioners face daily
5. Present LAWCOLAB as the solution — mention the Smart Business Directory (clients find them globally by practice area & location)
6. Tell them we've granted them FREE access to test the platform at {_URL}
7. Invite them to suggest any features they'd like — our dev team builds on request
8. Close with WhatsApp: {_WA} and website: {_URL}
9. Sign off as "{_SENDER} — Lawyer & Software Developer, LAWCOLAB"
10. Be brief, captivating, personal — NOT generic or spammy. Max 300 words for email, 5 lines for WhatsApp.

Return JSON with exactly two keys: "subject" (for email, empty string for others) and "body"."""

    content = _call_groq(prompt, json_response=True, max_tokens=700, temperature=0.8)
    if content:
        try:
            return json.loads(content)
        except Exception:
            pass

    return _template_firm_message(firm, channel, msg_type)


def _template_firm_message(firm, channel: str, msg_type: str) -> dict:
    """Fallback template — Abraham Tahbat's personal voice."""
    areas = ", ".join(firm.practice_areas[:3]) if firm.practice_areas else "legal practice"
    city  = firm.city or firm.country or "your area"
    name  = firm.name

    if channel == "whatsapp":
        return {
            "subject": "",
            "body": (
                f"Good day {name} Team 👋\n\n"
                f"I'm Abraham Tahbat — a lawyer & web developer. I came across your firm while researching {areas} practices in {city}.\n\n"
                f"I built LAWCOLAB to solve the exact problems most law firms face — juggling cases, chasing payments, missing court dates, and losing clients to disorganisation.\n\n"
                f"We've given your firm free access to test the platform → {_URL}\n\n"
                f"It includes case management, billing, a client portal, court calendar, team tools, analytics, and a Smart Business Directory that puts your firm in front of clients searching by practice area globally.\n\n"
                f"Try it and let me know what features you'd like added — our dev team builds on request.\n\n"
                f"Reach me on WhatsApp: {_WA}"
            ),
        }

    if msg_type == "follow_up":
        return {
            "subject": f"Following up — Free LAWCOLAB Access for {name}",
            "body": (
                f"Good day {name} Team,\n\n"
                f"I'm following up on my earlier message about LAWCOLAB.\n\n"
                f"Your free access is still active at {_URL} — I'd love to hear your thoughts once you've had a chance to explore the platform.\n\n"
                f"Most {areas} firms we've spoken with in {city} are dealing with the same three challenges: scattered case files, slow invoicing, and no system to track which clients are following up. LAWCOLAB solves all three in one place.\n\n"
                f"If there's a feature you'd like to see built specifically for your firm, just let us know — our dev team handles that.\n\n"
                f"WhatsApp: {_WA} | Web: {_URL}\n\n"
                f"Best regards,\n{_SENDER}\nLawyer & Software Developer — LAWCOLAB"
            ),
        }

    if msg_type == "second_followup":
        return {
            "subject": f"Last note — LAWCOLAB for {name}",
            "body": (
                f"Good day {name} Team,\n\n"
                f"I'll keep this brief — I've reached out a couple of times about LAWCOLAB and I don't want to intrude.\n\n"
                f"If the timing hasn't been right, your free access is still live at {_URL} whenever you're ready.\n\n"
                f"If there's something specific holding you back, I'm happy to address it directly — even if it's just a 5-minute WhatsApp chat.\n\n"
                f"WhatsApp: {_WA}\n\n"
                f"Either way, wishing {name} continued success.\n\n"
                f"Warm regards,\n{_SENDER} — LAWCOLAB"
            ),
        }

    # Default: cold outreach email
    web_note = (
        f"I also noticed {name} doesn't yet have a dedicated website. "
        f"LAWCOLAB includes a public firm profile and client portal — your professional digital presence, built in."
        if not firm.has_website else ""
    )

    return {
        "subject": f"Good day {name} — Free Access to LAWCOLAB for Your Firm",
        "body": (
            f"Good day {name} Team,\n\n"
            f"My name is Abraham Tahbat — I am both a lawyer and a web developer with over 15 years of experience building SaaS platforms. "
            f"I discovered {name} while researching {areas} firms in {city} through Google Maps and public legal directories, and I wanted to reach out personally.\n\n"
            f"I've seen first-hand the challenges law firms and legal practitioners face every day: cases managed on spreadsheets, invoices sent on WhatsApp, court dates tracked in notebooks, and clients left wondering about their case status. "
            f"These problems cost firms hours every week — and clients.\n\n"
            f"That's exactly why I built LAWCOLAB — a complete Legal Operating System designed to help firms like {name} run like world-class businesses:\n\n"
            f"• Case & Matter Management — every file, document, and deadline in one place\n"
            f"• Client Portal — clients check case updates 24/7, reducing phone calls\n"
            f"• Billing & Invoicing — generate and track invoices in seconds\n"
            f"• Court Calendar — automated alerts so no hearing date is missed\n"
            f"• Team Collaboration — tasks, messaging, and documents shared securely\n"
            f"• Analytics Dashboard — revenue and performance insights at a glance\n"
            f"• Smart Business Directory — your firm listed globally; clients find you by practice area and location\n"
            f"• Custom Features — tell us what you need, our dev team builds it\n"
            f"{('• ' + web_note + chr(10)) if web_note else ''}\n"
            f"I've gone ahead and set up free access for {name} — you can log in and explore the full platform right now:\n"
            f"👉 {_URL}\n\n"
            f"Have a look, and tell us what additional features would make LAWCOLAB perfect for your firm. We integrate any suggestion.\n\n"
            f"You can reach me directly on WhatsApp: {_WA}\n\n"
            f"Looking forward to helping {name} serve more clients and grow.\n\n"
            f"Warm regards,\n"
            f"Abraham Tahbat\n"
            f"Lawyer & Software Developer\n"
            f"LAWCOLAB — {_URL}"
        ),
    }


# ─── Law Firm AI Pitch & Call Script ─────────────────────────────────────────

def generate_firm_pitch(firm) -> tuple[dict, str]:
    """
    Generate AI email pitch + phone call script for a directory firm.
    Returns (email_dict, call_script_str).
    """
    areas      = ", ".join(firm.practice_areas[:4]) if firm.practice_areas else "legal practice"
    city       = firm.city or firm.country or "your area"
    state      = firm.state or ""
    country    = firm.country or "Nigeria"
    has_web    = firm.has_website
    gmb_status = "Verified GMB" if firm.gmb_verified else "Unverified GMB"
    reviews    = (f"{firm.google_reviews_count} Google reviews, {firm.google_rating}★"
                  if firm.google_rating else "no Google reviews found")

    no_web_note = (
        "Note: this firm has NO website — emphasise that LAWCOLAB gives them an instant "
        "professional public profile and client portal, their digital front door."
        if not has_web else
        "Note: this firm has a website — emphasise that LAWCOLAB works alongside it, not replacing it."
    )
    gmb_note = (
        "Note: Google Maps listing is UNVERIFIED — mention that LAWCOLAB's Smart Directory listing "
        "boosts their online credibility and client discoverability."
        if not firm.gmb_verified else ""
    )

    # ── Email pitch ───────────────────────────────────────────────────
    email_prompt = f"""You are writing on behalf of {_SENDER} for LAWCOLAB.

{_BRAND_CONTEXT}

{_FEATURES_BLOCK}

Write a highly personalized cold-outreach pitch EMAIL to this law firm:
- Firm: {firm.name}
- Location: {city}, {state}, {country}
- Practice Areas: {areas}
- Website: {"exists" if has_web else "NONE"}
- Google Maps: {gmb_status} — {reviews}
- {no_web_note}
{gmb_note}

Exact structure to follow:
1. GREETING — "Good day [Firm Name] Team," — warm and human
2. DISCOVERY — {_SENDER} explains he discovered them while researching {areas} firms in {city} via Google Maps & public legal directories
3. INTRO — {_SENDER} introduces himself: lawyer AND web developer, 15+ years building SaaS platforms; built LAWCOLAB from lived experience of the legal industry
4. PROBLEM — 2-3 specific daily pain points law firms and legal practitioners face (case chaos, invoice delays, missed court dates, zero online visibility, slow client communication)
5. SOLUTION — LAWCOLAB solves all of this; list ALL features including the Smart Business Directory (clients find them globally by practice area & location)
6. FREE ACCESS — tell them we've granted free access to test the full platform at {_URL}
7. CUSTOM FEATURES — invite them to suggest any features they'd like built; our dev team delivers
8. CTA — WhatsApp {_WA} and website {_URL}
9. SIGN-OFF — "{_SENDER} | Lawyer & Software Developer — LAWCOLAB"

Rules:
- Max 320 words. Brief, captivating, personal — never generic or corporate.
- Use bullet points for the features section only
- No placeholder text like [Name] — write it ready to send

Return JSON: {{"subject": "...", "body": "..."}}"""

    email_content = _call_groq(email_prompt, json_response=True, max_tokens=800, temperature=0.8)
    email_result = None
    if email_content:
        try:
            email_result = json.loads(email_content)
        except Exception:
            pass

    # ── Call script ───────────────────────────────────────────────────
    call_prompt = f"""You are writing a phone call script on behalf of {_SENDER} for LAWCOLAB.

{_BRAND_CONTEXT}

{_FEATURES_BLOCK}

Write a complete, ready-to-use phone call script for this law firm:
- Firm: {firm.name}
- Location: {city}, {state}, {country}
- Practice Areas: {areas}
- Website: {"exists" if has_web else "NONE — highlight free public profile"}
- Google Maps: {gmb_status} — {reviews}

Script sections (use bold headers):
1. OPENING — "Good day, may I speak with the managing partner or firm administrator?"
   When connected: {_SENDER} introduces himself as a lawyer & web developer calling from LAWCOLAB; mentions he found their firm on Google Maps while researching {areas} firms in {city}
2. PERMISSION — "Do you have just two minutes? I promise this is relevant to your firm."
3. PROBLEM — 3 specific pains most {areas} firms in {city} deal with daily
4. SOLUTION — LAWCOLAB as a Legal Operating System; highlight Smart Business Directory (clients find them globally)
5. KEY FEATURES — 4 features most relevant to {areas}
6. FREE ACCESS — "I've already set up free access for {firm.name} at {_URL} — please test it today"
7. CUSTOM DEVELOPMENT — "Whatever feature you need, tell us — our dev team builds it at no extra cost"
8. CTA — Invite them to WhatsApp {_WA} or visit {_URL}
9. OBJECTION HANDLERS — 3 objections with sharp, confident responses
10. CLOSING — Confirm next step, leave WhatsApp number {_WA}

Use [PAUSE], [LISTEN], [SMILE] stage directions. Ready-to-read script, professional tone."""

    call_content = _call_groq(call_prompt, json_response=False, max_tokens=1000, temperature=0.75)

    if not email_result:
        email_result, fallback_call = _template_pitch(firm, areas, city, has_web, gmb_status)
        if not call_content:
            call_content = fallback_call
    elif not call_content:
        _, fallback_call = _template_pitch(firm, areas, city, has_web, gmb_status)
        call_content = fallback_call

    return email_result, call_content


def _template_pitch(firm, areas, city, has_web, gmb_status):
    """Fallback pitch template — Abraham Tahbat personal voice."""
    name = firm.name
    _div = "─" * 60

    web_note = (
        f"I also noticed {name} doesn't yet have a dedicated website. "
        f"LAWCOLAB gives you an instant professional public profile and client portal — "
        f"your digital front door, built in from day one."
    ) if not has_web else (
        f"LAWCOLAB works seamlessly alongside your existing website — "
        f"adding the backend systems and Smart Directory listing your firm needs to grow."
    )

    email_body = (
        f"Good day {name} Team,\n\n"
        f"My name is Abraham Tahbat — I am both a lawyer and a web developer with over 15 years "
        f"of experience building SaaS web applications. I came across {name} while researching "
        f"{areas} firms in {city} through Google Maps and public legal directories, and I wanted "
        f"to reach out personally.\n\n"
        f"After years in legal practice, I understand the daily challenges law firms face: "
        f"cases scattered across notebooks and WhatsApp threads, invoices delayed or forgotten, "
        f"court dates missed, and potential clients unable to find you online. These problems "
        f"don't just cost time — they cost revenue and reputation.\n\n"
        f"I built LAWCOLAB to eliminate all of that:\n\n"
        f"• 📁 Case & Matter Management — every file, deadline, and document in one hub\n"
        f"• 👥 Client Portal — clients check case updates 24/7, reducing phone calls by 60%\n"
        f"• 💰 Billing & Invoicing — generate professional invoices instantly, track every payment\n"
        f"• 📅 Court Calendar & Alerts — automated reminders so no hearing is ever missed\n"
        f"• 🤝 Team Collaboration — tasks, messaging, and documents shared securely\n"
        f"• 📊 Analytics Dashboard — revenue, case load, and performance at a glance\n"
        f"• 🌍 Smart Business Directory — your firm listed globally; clients find you by practice area & location\n"
        f"• 🛠️ Custom Features — tell us what you need, our dev team builds it\n\n"
        f"{web_note}\n\n"
        f"I've gone ahead and set up FREE access for {name} — explore the full platform today:\n"
        f"👉 {_URL}\n\n"
        f"Try it and let me know what features would make LAWCOLAB perfect for your firm. "
        f"Our development team integrates any suggestion.\n\n"
        f"Reach me directly on WhatsApp: {_WA}\n\n"
        f"Looking forward to helping {name} serve more clients and grow.\n\n"
        f"Warm regards,\n"
        f"Abraham Tahbat\n"
        f"Lawyer & Software Developer\n"
        f"LAWCOLAB — {_URL}"
    )

    web_bridge = (
        f'"I also noticed {name} doesn\'t yet have a dedicated website. '
        f'LAWCOLAB gives you an instant public profile page and client portal — your professional digital presence, built in."'
    ) if not has_web else (
        f'"Even though {name} already has a website, LAWCOLAB works alongside it — '
        f'adding case management, billing, and a Smart Directory listing that puts your firm in front of new clients globally."'
    )

    call_script = (
        f"LAWCOLAB CALL SCRIPT — {name}\n"
        f"Location: {city} | Practice: {areas} | {gmb_status}\n"
        f"{_div}\n\n"
        f"1. OPENING\n"
        f"\"Good day, may I please speak with the managing partner or firm administrator at {name}?\"\n"
        f"[When connected]\n"
        f"\"Good day! My name is Abraham Tahbat — I'm a lawyer and web developer calling from LAWCOLAB. "
        f"I came across {name} on Google Maps while researching {areas} firms in {city} and I wanted to reach out personally. "
        f"Do you have just two minutes? I promise it's relevant to your firm.\"\n"
        f"[PAUSE] [LISTEN]\n\n"
        f"2. PERMISSION CHECK\n"
        f"\"Is now a good time for just two minutes?\"\n"
        f"[If YES → continue. If NO → \"No problem — when would be a good time to call back? I'll be brief.\"]\n\n"
        f"3. PROBLEM STATEMENT\n"
        f"\"From speaking with law firms in {city} daily, the most common challenges I hear are: "
        f"cases managed on spreadsheets or WhatsApp, invoices sent late and often forgotten, "
        f"court dates tracked in notebooks — and potential clients who simply cannot find the firm online.\"\n"
        f"[PAUSE] \"Does any of that sound familiar at {name}?\"\n"
        f"[LISTEN]\n\n"
        f"4. SOLUTION INTRO\n"
        f"\"That's exactly why I built LAWCOLAB — a complete Legal Operating System that brings "
        f"case management, billing, client communication, court calendars, and a Smart Business Directory "
        f"into one platform. Clients can find {name} globally by searching your practice area and location.\"\n\n"
        f"5. KEY FEATURES FOR {areas.upper()}\n"
        f"\"For a firm specialising in {areas}, the features that make the biggest immediate impact are:\n"
        f"— Case tracking so every matter, deadline, and document is organised\n"
        f"— Instant invoice generation with automated payment follow-ups\n"
        f"— A client portal so clients check their own case updates 24/7\n"
        f"— Court deadline alerts — automated, so nothing is ever missed\n"
        f"— Smart Directory listing — new clients find {name} by practice area and location\"\n\n"
        f"6. WEBSITE BRIDGE\n"
        f"{web_bridge}\n\n"
        f"7. FREE ACCESS\n"
        f"\"I've already set up free access for {name} at {_URL} — please log in and explore the "
        f"full platform today. No credit card, no commitment.\"\n\n"
        f"8. CUSTOM DEVELOPMENT\n"
        f"\"Our in-house developer team is on standby to add features specific to {name}'s workflow — "
        f"at no extra cost. Whatever you need built, we do it.\"\n\n"
        f"9. CTA\n"
        f"\"Please visit {_URL} to test the platform, and message me directly on WhatsApp: {_WA} — "
        f"I personally respond to every message.\"\n"
        f"[LISTEN — note their questions]\n\n"
        f"10. OBJECTION HANDLERS\n\n"
        f"Objection: \"We already have a system.\"\n"
        f"Response: \"That's great — LAWCOLAB is designed to work alongside your existing tools, "
        f"not replace them. Most firms find it fills the gaps their current setup doesn't cover, "
        f"especially the Smart Directory for client acquisition.\"\n\n"
        f"Objection: \"We're too busy right now.\"\n"
        f"Response: \"That's actually the exact reason most firms reach out to us — LAWCOLAB is "
        f"designed to save time, not add to it. The free access is already set up. "
        f"Just log in when you have 10 minutes and see for yourself.\"\n\n"
        f"Objection: \"How much does it cost?\"\n"
        f"Response: \"Your free access is already active — test everything first, no cost. "
        f"Once you see the value, plans are very affordable. Less than the cost of one missed invoice.\"\n\n"
        f"11. CLOSING\n"
        f"\"Thank you so much for your time. I'll send your free access link right now. "
        f"You can also reach me on WhatsApp anytime: {_WA}. "
        f"Have a wonderful day and I look forward to hearing from you!\"\n"
        f"[Confirm WhatsApp / email for follow-up]"
    )

    return {"subject": f"Good day {name} — Free Access to LAWCOLAB for Your Firm", "body": email_body}, call_script


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
        "post":    f"a community post for a {platform} group ({size} members) — can use emojis, conversational",
        "comment": f"a short conversational comment to introduce LAWCOLAB in a {platform} thread — max 5 lines",
        "dm":      f"a short, warm direct message to the {platform} community admin — personal and human",
        "email":   f"a professional outreach email to the {platform} community admin",
    }.get(channel, "a social media post")

    prompt = f"""You are writing on behalf of {_SENDER} for LAWCOLAB.

{_BRAND_CONTEXT}

{_FEATURES_BLOCK}

Write {channel_instruction} for the community: "{name}" ({category}, {country}, {size} members).

Exact structure to follow:
1. GREETING — Warm human opener addressing the community by name. For DMs: "Good day [admin name / Sir/Ma]"
2. INTRO — {_SENDER} introduces himself: a lawyer AND web developer with 15+ years of SaaS experience who discovered this community while researching {category} groups
3. PROBLEM — 2-3 daily pains that members of this community face in managing their legal practice
4. SOLUTION — LAWCOLAB as the answer; include the Smart Business Directory (members listed globally, found by clients based on practice area & location)
5. ALL FEATURES — list all features concisely
6. FREE ACCESS — members of "{name}" get free access to test at {_URL}
7. CUSTOM FEATURES — invite community members to suggest any feature they'd like built
8. CTA — WhatsApp {_WA} and {_URL}
9. SIGN-OFF — "{_SENDER} | Lawyer & Software Developer — LAWCOLAB"

Rules:
- Tone: warm, human, captivating — NOT corporate or spammy
- For {platform}: use appropriate formatting (emojis welcome for Facebook/WhatsApp/Telegram; professional for LinkedIn/email)
- Max 350 words for posts/emails, max 6 lines for DMs/comments
- End with a genuine question to spark engagement (e.g. "What's the biggest challenge you face managing your practice right now?")

Return JSON with keys "subject" (email only, empty string for others) and "body"."""

    content = _call_groq(prompt, json_response=True, max_tokens=800, temperature=0.85)
    if content:
        try:
            result = json.loads(content)
            result["channel"] = channel
            return result
        except Exception:
            pass

    return _template_community_message(community, channel)


def _template_community_message(community, channel: str) -> dict:
    """Fallback template — Abraham Tahbat personal voice for community outreach."""
    name     = community.community_name
    platform = community.platform.title()
    category = community.category or "legal professionals"
    country  = community.country_focus or "global"

    use_emoji = community.platform.lower() in ("facebook", "whatsapp", "telegram", "instagram")

    if channel == "dm":
        body = (
            f"Good day Sir/Ma 👋\n\n"
            f"My name is Abraham Tahbat — a lawyer and web developer. "
            f"I came across the {name} community while researching {category} groups online and I'm genuinely impressed by what you've built.\n\n"
            f"I'd love to introduce LAWCOLAB to your members — a Legal Operating System I built to help law firms manage cases, billing, court calendars, and client communication in one place. "
            f"It also has a Smart Business Directory that puts members' firms in front of clients searching globally by practice area and location.\n\n"
            f"We'd love to offer all {name} members free access to test it: {_URL}\n\n"
            f"Would you be open to me sharing this with the community? Happy to chat on WhatsApp: {_WA}\n\n"
            f"Thank you — Abraham Tahbat | LAWCOLAB"
        )
        subject = ""

    elif channel == "email":
        body = (
            f"Good day {name} Admin,\n\n"
            f"My name is Abraham Tahbat — I am a lawyer and web developer with over 15 years of experience "
            f"building SaaS platforms. I came across the {name} community while researching {category} groups in {country} and wanted to reach out personally.\n\n"
            f"I understand the daily struggles legal practitioners face: cases tracked on paper and WhatsApp, "
            f"invoices delayed or lost, court dates missed, and being invisible online to potential clients. "
            f"These aren't small problems — they cost firms clients, revenue, and reputation every single day.\n\n"
            f"I built LAWCOLAB to solve all of this:\n\n"
            f"• 📁 Case & Matter Management — every file, deadline, and document organised\n"
            f"• 👥 Client Portal — clients check case updates 24/7, no more constant calls\n"
            f"• 💰 Billing & Invoicing — generate professional invoices instantly, track every payment\n"
            f"• 📅 Court Calendar & Alerts — automated reminders, no missed hearings\n"
            f"• 🤝 Team Collaboration — tasks, messaging, and documents shared securely\n"
            f"• 📊 Analytics Dashboard — revenue, caseload, and performance at a glance\n"
            f"• 🌍 Smart Business Directory — members listed globally; clients find them by practice area & location\n"
            f"• 🛠️ Custom Features — we build whatever your members need\n\n"
            f"I'd love to offer every member of {name} free access to test the full platform:\n"
            f"👉 {_URL}\n\n"
            f"And I'd genuinely welcome any feature suggestions from your community — our dev team builds on request.\n\n"
            f"Reach me on WhatsApp: {_WA}\n\n"
            f"What's the biggest challenge your members currently face managing their practice?\n\n"
            f"Warm regards,\n"
            f"Abraham Tahbat\n"
            f"Lawyer & Software Developer — LAWCOLAB\n"
            f"{_URL}"
        )
        subject = f"Free LAWCOLAB Access for Every {name} Member — Built by a Fellow Lawyer"

    else:
        # Post / comment
        em = lambda x: x if use_emoji else ""
        body = (
            f"{em('👋 ')}Good day {name}!\n\n"
            f"My name is Abraham Tahbat — I'm a lawyer and web developer with 15+ years of experience building SaaS platforms. "
            f"I've been following this incredible community of {category} and I want to share something I built from personal experience in the legal industry.\n\n"
            f"Most law firms and legal practitioners I know are still managing cases on WhatsApp, chasing invoices manually, missing court deadlines, and remaining invisible to potential clients online. "
            f"I built {em('⚡ ')}LAWCOLAB to fix all of that:\n\n"
            f"{em('📁 ')}Case & Matter Management — every file and deadline organised\n"
            f"{em('👥 ')}Client Portal — clients track their cases 24/7\n"
            f"{em('💰 ')}Billing & Invoicing — professional invoices in seconds\n"
            f"{em('📅 ')}Court Calendar & Alerts — never miss a hearing\n"
            f"{em('🌍 ')}Smart Business Directory — clients find YOUR firm globally by practice area & location\n"
            f"{em('🛠️ ')}Custom Features — suggest anything, our dev team builds it\n\n"
            f"{em('🎁 ')}We've set up FREE access for {name} members — test the full platform today:\n"
            f"{em('👉 ')}{_URL}\n\n"
            f"WhatsApp: {_WA}\n\n"
            f"I'd love to know — what's the biggest challenge you face running your practice day-to-day? {em('💬')}\n\n"
            f"— Abraham Tahbat | Lawyer & Software Developer — LAWCOLAB"
        )
        subject = ""

    return {"subject": subject, "body": body, "channel": channel}
