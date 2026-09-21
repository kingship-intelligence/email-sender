import json
import re
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, ScheduledCampaign
from helpers.decorators import subscription_required
from helpers.quota import _daily_quota_status
from helpers.scheduler_tasks import FREQUENCY_CHOICES

scheduled_bp = Blueprint("scheduled", __name__)

def _validate_schedule_input(name, subject, body, emails_list, first_run, frequency):
    errors = []
    if not name:
        errors.append("Campaign name is required.")
    if not subject:
        errors.append("Subject is required.")
    if not body:
        errors.append("Body is required.")
    if not emails_list:
        errors.append("At least one email address is required.")
    if frequency not in FREQUENCY_CHOICES:
        errors.append("Invalid frequency.")

    next_run_at = None
    if not first_run:
        errors.append("First send date/time is required.")
    else:
        try:
            next_run_at = datetime.strptime(first_run, "%Y-%m-%dT%H:%M")
        except ValueError:
            errors.append("Invalid date/time format.")

    return errors, next_run_at


@scheduled_bp.route("/scheduled", methods=["GET", "POST"])
@login_required
@subscription_required
def scheduled():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        emails_raw = request.form.get("emails", "").strip()
        first_run = request.form.get("first_run", "").strip()
        frequency = request.form.get("frequency", "weekly").strip().lower()

        emails_list = []
        names_map = {}
        for line in emails_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(.*?)<([^>]+)>\s*$", line)
            if m:
                recip_name, recip_email = m.group(1).strip(), m.group(2).strip().lower()
            else:
                recip_name, recip_email = "", line.lower()
            if recip_email not in emails_list:
                emails_list.append(recip_email)
            if recip_name:
                names_map[recip_email] = recip_name

        errors, next_run_at = _validate_schedule_input(name, subject, body, emails_list, first_run, frequency)

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            sc = ScheduledCampaign(
                user_id=current_user.id,
                name=name,
                subject=subject,
                body=body,
                emails_json=json.dumps(emails_list),
                names_json=json.dumps(names_map),
                next_run_at=next_run_at,
                frequency=frequency,
            )
            db.session.add(sc)
            db.session.commit()
            flash(f'{frequency.capitalize()} schedule "{name}" created — first send on {next_run_at.strftime("%b %d, %Y at %H:%M")} UTC.', "success")
        return redirect(url_for("scheduled.scheduled"))

    schedules = ScheduledCampaign.query.filter_by(user_id=current_user.id).order_by(ScheduledCampaign.created_at.desc()).all()
    return render_template(
        "scheduled.html",
        schedules=schedules,
        daily_quota=_daily_quota_status(current_user.id),
    )


@scheduled_bp.route("/campaign/schedule", methods=["POST"])
@login_required
@subscription_required
def campaign_schedule():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    first_run = (data.get("first_run") or "").strip()
    frequency = (data.get("frequency") or "weekly").strip().lower()
    emails_list = data.get("emails") or []
    emails_list = [str(e).strip().lower() for e in emails_list if str(e).strip()]
    emails_list = list(dict.fromkeys(emails_list))

    names_map = data.get("names") or {}
    if not isinstance(names_map, dict):
        names_map = {}
    names_map = {
        str(k).strip().lower(): str(v).strip()
        for k, v in names_map.items()
        if str(k).strip() and str(v).strip()
    }

    errors, next_run_at = _validate_schedule_input(name, subject, body, emails_list, first_run, frequency)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    sc = ScheduledCampaign(
        user_id=current_user.id,
        name=name,
        subject=subject,
        body=body,
        emails_json=json.dumps(emails_list),
        names_json=json.dumps(names_map),
        next_run_at=next_run_at,
        frequency=frequency,
    )
    db.session.add(sc)
    db.session.commit()
    return jsonify({
        "ok": True,
        "message": f'{frequency.capitalize()} schedule "{name}" created — first send on {next_run_at.strftime("%b %d, %Y at %H:%M")} UTC.',
    })


@scheduled_bp.route("/scheduled/<int:sc_id>/toggle", methods=["POST"])
@login_required
@subscription_required
def scheduled_toggle(sc_id):
    sc = ScheduledCampaign.query.filter_by(id=sc_id, user_id=current_user.id).first_or_404()
    sc.active = not sc.active
    db.session.commit()
    state = "resumed" if sc.active else "paused"
    flash(f'Schedule "{sc.name}" {state}.', "success")
    return redirect(url_for("scheduled.scheduled"))


@scheduled_bp.route("/scheduled/<int:sc_id>/delete", methods=["POST"])
@login_required
@subscription_required
def scheduled_delete(sc_id):
    sc = ScheduledCampaign.query.filter_by(id=sc_id, user_id=current_user.id).first_or_404()
    db.session.delete(sc)
    db.session.commit()
    flash(f'Schedule "{sc.name}" deleted.', "success")
    return redirect(url_for("scheduled.scheduled"))
