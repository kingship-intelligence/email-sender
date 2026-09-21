import os
import smtplib
from email.mime.text import MIMEText
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db
from extensions import limiter
from helpers.decorators import subscription_required
from helpers.utils import encrypt_password, decrypt_password
from helpers.quota import _daily_quota_status, _consume_daily_send_slot, DAILY_SEND_LIMIT

STRIPE_ENABLED = bool(os.environ.get("STRIPE_SECRET_KEY", ""))

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
@subscription_required
def settings():
    if request.method == "POST":
        current_user.smtp_host = request.form.get("smtp_host", "").strip() or None
        current_user.smtp_port = int(request.form.get("smtp_port", 587) or 587)
        current_user.smtp_user = request.form.get("smtp_user", "").strip() or None
        current_user.smtp_from = request.form.get("smtp_from", "").strip() or None
        current_user.smtp_use_tls = "smtp_use_tls" in request.form
        new_pass = request.form.get("smtp_pass", "").strip()
        if new_pass:
            current_user.smtp_pass_enc = encrypt_password(new_pass)
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("settings.settings"))
    return render_template("settings.html", stripe_enabled=STRIPE_ENABLED)


@settings_bp.route("/settings/test-email", methods=["POST"])
@login_required
@subscription_required
@limiter.limit("5 per minute")
def settings_test_email():
    """Send a test email to the user's own address using their saved SMTP settings."""
    if not (current_user.smtp_host and current_user.smtp_user and current_user.smtp_pass_enc):
        return jsonify({"error": "Save your SMTP settings first, then send a test."}), 400
    quota = _daily_quota_status(current_user.id)
    if quota["remaining"] == 0:
        return jsonify({
            "error": (
                f"Today's {DAILY_SEND_LIMIT}-email limit is reached. "
                "Try the SMTP test again tomorrow."
            )
        }), 429
    try:
        smtp_pass = decrypt_password(current_user.smtp_pass_enc)
    except Exception:
        return jsonify({"error": "Stored SMTP password could not be decrypted. Re-enter and save it."}), 400

    from_addr = current_user.smtp_from or current_user.smtp_user
    msg = MIMEText(
        "This is a test email from RushMail.\n\n"
        "If you're reading this, your SMTP settings are working and you're ready to send campaigns.",
        "plain",
    )
    msg["Subject"] = "RushMail SMTP test"
    msg["From"] = from_addr
    to_addr = current_user.smtp_from or current_user.smtp_user
    msg["To"] = to_addr

    try:
        if not _consume_daily_send_slot(current_user.id):
            return jsonify({
                "error": f"Today's {DAILY_SEND_LIMIT}-email limit is reached."
            }), 429
        if current_user.smtp_use_tls:
            server = smtplib.SMTP(current_user.smtp_host, current_user.smtp_port, timeout=15)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(current_user.smtp_host, current_user.smtp_port, timeout=15)
        server.login(current_user.smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

    return jsonify({"ok": True, "message": f"Test email sent to {to_addr} — check your inbox."})
