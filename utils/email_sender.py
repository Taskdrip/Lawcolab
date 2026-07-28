"""
utils/email_sender.py — Email provider abstraction for LAWCOLAB Email CRM.

Supports: simulate (default), smtp, resend, mailgun, postmark.
Configure via the Email Settings page in the Super Admin CRM.
"""
import os
import logging
import smtplib
import secrets
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MERGE_TAGS = [
    "{{FirmName}}", "{{ContactName}}", "{{City}}", "{{Country}}",
    "{{PracticeArea}}", "{{Website}}", "{{FreeTrialLink}}", "{{DemoBookingLink}}",
    "{{SalesRep}}", "{{CurrentDate}}",
]

FREE_TRIAL_LINK = "https://lawcolab.com"
DEMO_LINK       = "https://lawcolab.com/#demo"
SALES_REP       = "Abraham Tahbat"


def resolve_merge_tags(text: str, firm=None, contact_name: str = "") -> str:
    """Replace {{MergeTag}} placeholders with real values."""
    if not text:
        return text
    now = datetime.now()
    replacements = {
        "{{FirmName}}":       (firm.name if firm else ""),
        "{{ContactName}}":    contact_name or (firm.name if firm else ""),
        "{{City}}":           (firm.city or "") if firm else "",
        "{{Country}}":        (firm.country or "") if firm else "",
        "{{PracticeArea}}":   (", ".join(firm.practice_areas[:2]) if firm and firm.practice_areas else ""),
        "{{Website}}":        (firm.website or "") if firm else "",
        "{{FreeTrialLink}}":  FREE_TRIAL_LINK,
        "{{DemoBookingLink}}": DEMO_LINK,
        "{{SalesRep}}":       SALES_REP,
        "{{CurrentDate}}":    now.strftime("%B %d, %Y"),
    }
    for tag, value in replacements.items():
        text = text.replace(tag, value or "")
    return text


def generate_tracking_token() -> str:
    return secrets.token_urlsafe(32)


def inject_tracking_pixel(html_body: str, token: str, base_url: str) -> str:
    """Append a 1×1 transparent tracking pixel to the email body."""
    pixel_url = f"{base_url}/superadmin/crm/email/track/open/{token}"
    pixel = f'<img src="{pixel_url}" width="1" height="1" style="display:none" alt="">'
    if "</body>" in html_body:
        return html_body.replace("</body>", f"{pixel}</body>")
    return html_body + pixel


def wrap_links_for_tracking(html_body: str, token: str, base_url: str) -> str:
    """Wrap <a href="..."> links with click-tracking redirect."""
    import re
    def replace_link(m):
        original_url = m.group(1)
        if "/track/" in original_url or "mailto:" in original_url:
            return m.group(0)
        import urllib.parse
        encoded = urllib.parse.quote(original_url, safe="")
        return f'href="{base_url}/superadmin/crm/email/track/click/{token}?url={encoded}"'
    return re.sub(r'href="([^"]+)"', replace_link, html_body)


def get_settings():
    """Load EmailSettings from DB; return None if table not ready yet."""
    try:
        from sqlalchemy import text
        from app import db
        row = db.session.execute(text("SELECT * FROM email_settings LIMIT 1")).fetchone()
        if row:
            return dict(row._mapping)
    except Exception:
        pass
    return None


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    from_name: str = "",
    from_email: str = "",
    reply_to: str = "",
    cc: list = None,
    bcc: list = None,
    tracking_token: str = None,
    base_url: str = "",
    message_id: int = None,
) -> dict:
    """
    Send an email via the configured provider.
    Returns {"success": bool, "provider": str, "provider_message_id": str, "error": str|None}
    """
    settings = get_settings() or {}
    provider  = settings.get("provider", os.environ.get("EMAIL_PROVIDER", "simulate"))
    from_name  = from_name  or settings.get("from_name",  "LAWCOLAB")
    from_email = from_email or settings.get("from_email", "noreply@mail.lawcolab.com")
    reply_to   = reply_to   or settings.get("reply_to", from_email)

    # Inject tracking if token provided
    if tracking_token and base_url and settings.get("track_opens", True):
        body_html = inject_tracking_pixel(body_html, tracking_token, base_url)
    if tracking_token and base_url and settings.get("track_clicks", True):
        body_html = wrap_links_for_tracking(body_html, tracking_token, base_url)

    # Append signature + footer
    sig = settings.get("signature_html") or ""
    footer = settings.get("email_footer") or ""
    unsub = settings.get("unsubscribe_footer") or ""
    if sig or footer or unsub:
        extra = ""
        if sig:
            extra += f'<hr style="margin:24px 0;border:none;border-top:1px solid #e2e8f0">{sig}'
        if footer:
            extra += f'<p style="font-size:12px;color:#999;margin-top:16px">{footer}</p>'
        if unsub:
            extra += f'<p style="font-size:11px;color:#bbb;margin-top:8px">{unsub}</p>'
        if "</body>" in body_html:
            body_html = body_html.replace("</body>", extra + "</body>")
        else:
            body_html += extra

    try:
        if provider == "simulate":
            return _simulate(to_email, subject, message_id)
        elif provider == "smtp":
            return _send_smtp(to_email, subject, body_html, body_text,
                              from_name, from_email, reply_to, cc, bcc, settings)
        elif provider == "resend":
            return _send_resend(to_email, subject, body_html, body_text,
                                from_name, from_email, reply_to, settings)
        elif provider == "mailgun":
            return _send_mailgun(to_email, subject, body_html, body_text,
                                 from_name, from_email, settings)
        elif provider == "postmark":
            return _send_postmark(to_email, subject, body_html, body_text,
                                  from_name, from_email, reply_to, settings)
        else:
            return _simulate(to_email, subject, message_id)
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return {"success": False, "provider": provider,
                "provider_message_id": None, "error": str(e)}


def _simulate(to_email, subject, message_id=None):
    logger.info("[EMAIL SIMULATE] To: %s | Subject: %s", to_email, subject)
    return {"success": True, "provider": "simulate",
            "provider_message_id": f"sim-{secrets.token_hex(8)}", "error": None}


def _send_smtp(to_email, subject, html, text, from_name, from_email,
               reply_to, cc, bcc, settings):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    if cc:
        msg["Cc"] = ", ".join(cc)
    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    host     = settings.get("smtp_host", "")
    port     = int(settings.get("smtp_port", 587))
    user     = settings.get("smtp_user", "")
    password = settings.get("smtp_password", "")
    use_tls  = settings.get("smtp_use_tls", True)

    all_recipients = [to_email] + (cc or []) + (bcc or [])
    if use_tls:
        server = smtplib.SMTP(host, port)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(host, port)
    if user and password:
        server.login(user, password)
    server.sendmail(from_email, all_recipients, msg.as_string())
    server.quit()
    return {"success": True, "provider": "smtp",
            "provider_message_id": msg["Message-ID"] or secrets.token_hex(8), "error": None}


def _send_resend(to_email, subject, html, text, from_name, from_email, reply_to, settings):
    # Prefer env var so Railway/Replit secrets work without saving to DB
    api_key = os.environ.get("RESEND_API_KEY", "") or settings.get("api_key", "")
    if not api_key:
        raise ValueError(
            "Resend API key not configured. Set RESEND_API_KEY in your environment variables "
            "or enter it in the Email Settings page."
        )
    payload = {
        "from": f"{from_name} <{from_email}>",
        "to":   [to_email],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    if reply_to:
        payload["reply_to"] = reply_to
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload, timeout=20,
    )
    # Parse Resend error body for clear user-facing messages
    if not r.ok:
        try:
            err_body = r.json()
            err_msg = err_body.get("message") or err_body.get("name") or r.text
        except Exception:
            err_msg = r.text or f"HTTP {r.status_code}"
        if r.status_code == 403:
            raise ValueError(
                f"Resend domain not verified (403). "
                f"You must verify your sending domain in the Resend dashboard "
                f"(resend.com/domains) before sending from '{from_email}'. "
                f"For testing, change 'From Email' to 'onboarding@resend.dev'. "
                f"Resend says: {err_msg}"
            )
        elif r.status_code == 401:
            raise ValueError(
                f"Resend API key is invalid or expired (401). "
                f"Check your RESEND_API_KEY in Railway environment variables. "
                f"Resend says: {err_msg}"
            )
        elif r.status_code == 422:
            raise ValueError(
                f"Resend rejected the request (422 — invalid data). "
                f"Check that the From Email address is valid and the domain is verified. "
                f"Resend says: {err_msg}"
            )
        else:
            raise ValueError(f"Resend error {r.status_code}: {err_msg}")
    data = r.json()
    return {"success": True, "provider": "resend",
            "provider_message_id": data.get("id"), "error": None}


def _send_mailgun(to_email, subject, html, text, from_name, from_email, settings):
    api_key = settings.get("api_key") or os.environ.get("MAILGUN_API_KEY", "")
    domain  = os.environ.get("MAILGUN_DOMAIN", "")
    if not api_key or not domain:
        raise ValueError("Mailgun API key / domain not configured")
    data = {
        "from": f"{from_name} <{from_email}>",
        "to":   to_email,
        "subject": subject,
        "html": html,
    }
    if text:
        data["text"] = text
    r = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key), data=data, timeout=20,
    )
    r.raise_for_status()
    return {"success": True, "provider": "mailgun",
            "provider_message_id": r.json().get("id"), "error": None}


def _send_postmark(to_email, subject, html, text, from_name, from_email, reply_to, settings):
    api_key = settings.get("api_key") or os.environ.get("POSTMARK_SERVER_TOKEN", "")
    if not api_key:
        raise ValueError("Postmark server token not configured")
    payload = {
        "From":     f"{from_name} <{from_email}>",
        "To":       to_email,
        "Subject":  subject,
        "HtmlBody": html,
    }
    if text:
        payload["TextBody"] = text
    if reply_to:
        payload["ReplyTo"] = reply_to
    r = requests.post(
        "https://api.postmarkapp.com/email",
        headers={"X-Postmark-Server-Token": api_key, "Content-Type": "application/json"},
        json=payload, timeout=20,
    )
    r.raise_for_status()
    return {"success": True, "provider": "postmark",
            "provider_message_id": r.json().get("MessageID"), "error": None}
