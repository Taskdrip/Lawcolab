"""
blueprints/claim.py — Law Firm Listing Claim Flow
Mounted at /directory/claim

Allows law firms to claim their listing on the LAWCOLAB Smart Legal Directory.
They can add logo, background image, description, social links, and more.
Admin is notified of new claim requests.
"""
import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from models import DirectoryLawFirm, AdminNotification
from datetime import datetime

claim_bp = Blueprint("claim", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_FOLDER = os.path.join("uploads", "claims")


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_upload(file, subfolder: str) -> str | None:
    """Save uploaded file; return relative URL or None."""
    if not file or not file.filename:
        return None
    if not _allowed_file(file.filename):
        return None
    from werkzeug.utils import secure_filename
    import uuid
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(UPLOAD_FOLDER, subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file.save(path)
    return f"/uploads/claims/{subfolder}/{filename}"


# ─── Public claim routes ──────────────────────────────────────────────────────

@claim_bp.route("/<int:firm_id>", methods=["GET"])
def claim_form(firm_id):
    """Show the claim listing form for a directory firm."""
    firm = DirectoryLawFirm.query.filter_by(id=firm_id, is_active=True).first_or_404()

    if firm.is_claimed:
        flash("This listing has already been claimed.", "info")
        return redirect(url_for("directory.external_firm", firm_id=firm_id))

    if firm.claim_pending:
        flash("A claim request for this listing is already under review.", "info")
        return redirect(url_for("directory.external_firm", firm_id=firm_id))

    # Pre-populate social links from stored JSON
    social = firm.social_links if hasattr(firm, "social_links") else {}

    return render_template("directory/claim.html", firm=firm, social=social)


@claim_bp.route("/<int:firm_id>/submit", methods=["POST"])
def submit_claim(firm_id):
    """Process claim form submission."""
    firm = DirectoryLawFirm.query.filter_by(id=firm_id, is_active=True).first_or_404()

    if firm.is_claimed or firm.claim_pending:
        flash("This listing is already claimed or under review.", "warning")
        return redirect(url_for("directory.external_firm", firm_id=firm_id))

    # Collect form data
    contact_name  = request.form.get("contact_name", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()
    your_role     = request.form.get("your_role", "").strip()
    description   = request.form.get("description", "").strip()
    tagline       = request.form.get("tagline", "").strip()
    website       = request.form.get("website", "").strip()
    address       = request.form.get("address", "").strip()

    social_links = {
        "facebook":  request.form.get("facebook", "").strip(),
        "linkedin":  request.form.get("linkedin", "").strip(),
        "twitter":   request.form.get("twitter", "").strip(),
        "instagram": request.form.get("instagram", "").strip(),
        "whatsapp":  request.form.get("whatsapp_url", "").strip(),
        "youtube":   request.form.get("youtube", "").strip(),
    }
    # Remove empty
    social_links = {k: v for k, v in social_links.items() if v}

    if not contact_name or not contact_email:
        flash("Your name and email are required.", "danger")
        return redirect(url_for("claim.claim_form", firm_id=firm_id))

    # Handle file uploads
    logo_url = _save_upload(request.files.get("logo"), "logos")
    bg_url   = _save_upload(request.files.get("background_image"), "backgrounds")

    # Save claim data to firm record
    firm.claim_pending      = True
    firm.claim_contact_name  = contact_name
    firm.claim_contact_email = contact_email
    firm.claim_contact_phone = contact_phone
    firm.claim_contact_role  = your_role
    firm.claim_description   = description or firm.description
    firm.claim_tagline       = tagline
    firm.claim_social_json   = json.dumps(social_links) if social_links else None
    firm.claim_logo_url      = logo_url
    firm.claim_bg_url        = bg_url
    firm.claim_website       = website
    firm.claim_address       = address
    firm.claim_submitted_at  = datetime.now()

    # Update firm fields with submitted data if better than existing
    if description:
        firm.description = description
    if website and not firm.website:
        firm.website = website
    if social_links:
        firm.social_links_json = json.dumps(social_links)

    # Create admin notification
    notif = AdminNotification(
        title=f"New Claim Request: {firm.name}",
        message=(
            f"{contact_name} ({contact_email}) from {firm.name} has submitted a listing claim request. "
            f"Role: {your_role or 'not specified'}. "
            f"Review and verify their identity before approving."
        ),
        notification_type="new_claim",
        link_url=url_for("dir_admin.external_detail", firm_id=firm_id, _external=False),
        firm_id=firm_id,
    )
    db.session.add(notif)
    db.session.commit()

    flash("Your claim request has been submitted! Our team will review and contact you within 48 hours.", "success")
    return redirect(url_for("claim.claim_success", firm_id=firm_id))


@claim_bp.route("/<int:firm_id>/success")
def claim_success(firm_id):
    """Claim submission success page."""
    firm = DirectoryLawFirm.query.filter_by(id=firm_id).first_or_404()
    return render_template("directory/claim_success.html", firm=firm)


# ─── Admin claim management ───────────────────────────────────────────────────

@claim_bp.route("/admin/approve/<int:firm_id>", methods=["POST"])
def admin_approve_claim(firm_id):
    """Super admin: approve a claim request."""
    from flask_login import current_user
    from utils.decorators import require_super_admin
    from models import ROLE_SUPER_ADMIN

    if not current_user.is_authenticated or current_user.role != ROLE_SUPER_ADMIN:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    firm.is_claimed    = True
    firm.claim_pending = False
    firm.crm_status    = "converted"
    firm.pipeline_stage = "converted"

    # Apply submitted claim data
    if firm.claim_logo_url:
        firm.logo_url = firm.claim_logo_url
    if firm.claim_description:
        firm.description = firm.claim_description

    # Notify admin of approval
    notif = AdminNotification(
        title=f"Claim Approved: {firm.name}",
        message=f"The listing claim for {firm.name} has been approved. Contact: {firm.claim_contact_email}",
        notification_type="claim_approved",
        link_url=url_for("dir_admin.external_detail", firm_id=firm_id, _external=False),
        firm_id=firm_id,
        is_read=True,
    )
    db.session.add(notif)
    db.session.commit()
    return jsonify({"success": True})


@claim_bp.route("/admin/reject/<int:firm_id>", methods=["POST"])
def admin_reject_claim(firm_id):
    """Super admin: reject a claim request."""
    from flask_login import current_user
    from models import ROLE_SUPER_ADMIN

    if not current_user.is_authenticated or current_user.role != ROLE_SUPER_ADMIN:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    firm = DirectoryLawFirm.query.get_or_404(firm_id)
    firm.claim_pending = False
    db.session.commit()
    return jsonify({"success": True})
