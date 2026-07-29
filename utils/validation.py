"""
Validation helpers for CRM edit forms.
Validates URLs, emails, phone numbers and detects potential duplicate records.
"""
import re
from urllib.parse import urlparse


def validate_url(value):
    """Return (ok, error_message). Allows empty/None."""
    if not value or not value.strip():
        return True, None
    v = value.strip()
    try:
        parsed = urlparse(v)
        if parsed.scheme not in ('http', 'https'):
            return False, f'URL must start with http:// or https:// — got "{v[:60]}"'
        if not parsed.netloc:
            return False, f'URL has no domain — got "{v[:60]}"'
        return True, None
    except Exception:
        return False, f'Invalid URL: "{v[:60]}"'


def validate_email(value):
    """Return (ok, error_message). Allows empty/None."""
    if not value or not value.strip():
        return True, None
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if re.match(pattern, value.strip()):
        return True, None
    return False, f'Invalid email address: "{value.strip()[:80]}"'


def validate_phone(value):
    """Return (ok, error_message). Allows empty/None. Accepts international formats."""
    if not value or not value.strip():
        return True, None
    cleaned = re.sub(r'[\s\-().+]', '', value.strip())
    if re.match(r'^\d{6,15}$', cleaned):
        return True, None
    return False, f'Invalid phone number: "{value.strip()[:40]}" (digits only, 6–15 digits)'


def validate_firm_fields(data):
    """Validate all editable DirectoryLawFirm fields. Returns list of error strings."""
    errors = []
    for field in ('website', 'source_url', 'logo_url'):
        ok, msg = validate_url(data.get(field))
        if not ok:
            errors.append(msg)
    ok, msg = validate_email(data.get('email'))
    if not ok:
        errors.append(msg)
    for field in ('phone', 'whatsapp'):
        ok, msg = validate_phone(data.get(field))
        if not ok:
            errors.append(msg)
    # Validate social links URLs
    social_raw = data.get('social_links_json') or '{}'
    try:
        import json
        social = json.loads(social_raw) if isinstance(social_raw, str) else social_raw
        for platform, url in (social or {}).items():
            ok, msg = validate_url(url)
            if not ok:
                errors.append(f'Social link ({platform}): {msg}')
    except Exception:
        errors.append('Social links JSON is malformed')
    return errors


def validate_community_fields(data):
    """Validate all editable SocialCommunity fields. Returns list of error strings."""
    errors = []
    for field in ('url', 'join_link', 'logo_url'):
        ok, msg = validate_url(data.get(field))
        if not ok:
            errors.append(msg)
    ok, msg = validate_email(data.get('email'))
    if not ok:
        errors.append(msg)
    for field in ('phone', 'whatsapp'):
        ok, msg = validate_phone(data.get(field))
        if not ok:
            errors.append(msg)
    return errors


def detect_firm_duplicates(db, DirectoryLawFirm, name, city, exclude_id=None):
    """Return list of potential duplicate DirectoryLawFirm records."""
    if not name:
        return []
    q = DirectoryLawFirm.query.filter(
        DirectoryLawFirm.name.ilike(f'%{name.strip()}%')
    )
    if city and city.strip():
        q = q.filter(DirectoryLawFirm.city.ilike(f'%{city.strip()}%'))
    if exclude_id:
        q = q.filter(DirectoryLawFirm.id != exclude_id)
    return q.limit(5).all()


def detect_community_duplicates(db, SocialCommunity, name, platform, exclude_id=None):
    """Return list of potential duplicate SocialCommunity records."""
    if not name:
        return []
    q = SocialCommunity.query.filter(
        SocialCommunity.community_name.ilike(f'%{name.strip()}%')
    )
    if platform:
        q = q.filter(SocialCommunity.platform == platform)
    if exclude_id:
        q = q.filter(SocialCommunity.id != exclude_id)
    return q.limit(5).all()
