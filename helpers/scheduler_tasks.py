import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from models import db, User, Campaign, CampaignRecipient, ScheduledCampaign
from helpers.utils import decrypt_password
from helpers.quota import _consume_daily_send_slot, _create_quota_overflow_schedule, _daily_quota_status, DAILY_SEND_LIMIT
from helpers.emails import personalize_text, resolve_recipient_name

def _mark_pending_recipients_failed(campaign: Campaign, error: str):
    pending = CampaignRecipient.query.filter_by(
        campaign_id=campaign.id, status="pending"
    ).all()
    for recipient in pending:
        recipient.status = "failed"
        recipient.error = error

    campaign.sent_ok = CampaignRecipient.query.filter_by(
        campaign_id=campaign.id, status="sent"
    ).count()
    campaign.sent_fail = CampaignRecipient.query.filter_by(
        campaign_id=campaign.id, status="failed"
    ).count()
    campaign.status = "completed"
    db.session.commit()

def _send_campaign_background(campaign_id: int):
    """Background worker: sends all pending recipients for a campaign."""
    from app import app
    from extensions import _pending_attachments

    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return

        campaign.status = "sending"
        db.session.commit()

        user = User.query.get(campaign.user_id)
        if not user or not user.smtp_host or not user.smtp_pass_enc:
            _mark_pending_recipients_failed(
                campaign,
                "SMTP is not fully configured. Update your SMTP settings and resend.",
            )
            return

        try:
            smtp_host  = user.smtp_host
            smtp_port  = user.smtp_port
            smtp_user  = user.smtp_user
            smtp_pass  = decrypt_password(user.smtp_pass_enc)
            use_tls    = user.smtp_use_tls
            from_addr  = user.smtp_from or smtp_user
        except Exception as error:
            _mark_pending_recipients_failed(
                campaign,
                f"Could not load SMTP credentials: {error}",
            )
            return

        subject    = campaign.subject
        body       = campaign.body
        attachments = _pending_attachments.pop(campaign_id, [])

        pending = CampaignRecipient.query.filter_by(
            campaign_id=campaign_id, status="pending"
        ).all()
        ok   = CampaignRecipient.query.filter_by(campaign_id=campaign_id, status="sent").count()
        fail = CampaignRecipient.query.filter_by(campaign_id=campaign_id, status="failed").count()

        def _make_smtp_connection():
            if use_tls:
                srv = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
                srv.ehlo()
                srv.starttls()
            else:
                srv = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            srv.login(smtp_user, smtp_pass)
            return srv

        server = None
        try:
            server = _make_smtp_connection()
        except Exception as e:
            _mark_pending_recipients_failed(campaign, str(e))
            return

        for index, r in enumerate(pending):
            if not _consume_daily_send_slot(campaign.user_id):
                blocked = pending[index:]
                _create_quota_overflow_schedule(
                    campaign.user_id,
                    campaign.name,
                    campaign.subject or "",
                    campaign.body or "",
                    [recipient.email for recipient in blocked],
                    {
                        recipient.email: recipient.name
                        for recipient in blocked
                        if recipient.name
                    },
                )
                quota_error = (
                    f"RushMail's {DAILY_SEND_LIMIT}-email daily limit has been reached. "
                    "This recipient was scheduled automatically for tomorrow."
                )
                for recipient in blocked:
                    recipient.status = "failed"
                    recipient.error = quota_error
                fail += len(blocked)
                campaign.sent_ok = ok
                campaign.sent_fail = fail
                campaign.status = "completed"
                db.session.commit()
                break

            try:
                msg = MIMEMultipart("mixed")
                msg["From"]    = from_addr
                msg["To"]      = r.email
                msg["Subject"] = personalize_text(subject, r.email, r.name or "")
                msg.attach(MIMEText(personalize_text(body, r.email, r.name or ""), "html"))
                for att_name, att_data, att_mime in attachments:
                    maintype, subtype = att_mime.split("/", 1) if "/" in att_mime else ("application", "octet-stream")
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(att_data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=att_name)
                    msg.attach(part)
                raw = msg.as_string()
                try:
                    server.sendmail(from_addr, r.email, raw)
                except smtplib.SMTPServerDisconnected:
                    server = _make_smtp_connection()
                    server.sendmail(from_addr, r.email, raw)
                r.status  = "sent"
                r.sent_at = datetime.utcnow()
                ok += 1
            except Exception as e:
                err_str = str(e)
                if "gmail" in smtp_host.lower():
                    err_lower = err_str.lower()
                    if any(kw in err_lower for kw in (
                        "daily user sending quota exceeded",
                        "daily sending quota exceeded",
                        "too many messages",
                        "rate limit exceeded",
                        "4.7.0",
                        "5.7.0",
                    )):
                        err_str = (
                            "Gmail daily sending limit reached — "
                            "Gmail personal accounts allow 500 emails/day (2,000 on Workspace). "
                            f"Original error: {err_str}"
                        )
                r.status = "failed"
                r.error  = err_str
                fail += 1
            campaign.sent_ok = ok
            campaign.sent_fail = fail
            db.session.commit()

        try:
            server.quit()
        except Exception:
            pass

        campaign.sent_ok   = ok
        campaign.sent_fail = fail
        campaign.status    = "completed"
        db.session.commit()


def _fire_scheduled_campaign(sc_id: int, smtp_cfg: dict):
    from app import app
    with app.app_context():
        sc = ScheduledCampaign.query.get(sc_id)
        if not sc:
            return
        emails = sc.emails
        names_map = sc.names
        subject = sc.subject
        body = sc.body
        from_addr = smtp_cfg["from"] or smtp_cfg["user"]
        quota = _daily_quota_status(sc.user_id)
        send_now = emails[:quota["remaining"]]
        deferred = emails[quota["remaining"]:]
        results = []

        if not send_now:
            if deferred:
                _create_quota_overflow_schedule(
                    sc.user_id, sc.name, subject, body, deferred, names_map
                )
                db.session.commit()
            return

        server = None
        try:
            if smtp_cfg["use_tls"]:
                server = smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=20)
                server.ehlo()
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_cfg["host"], smtp_cfg["port"], timeout=20)
            server.login(smtp_cfg["user"], smtp_cfg["pass"])
        except Exception as error:
            results = [
                (
                    addr,
                    resolve_recipient_name(addr, names_map),
                    "failed",
                    str(error),
                    None,
                )
                for addr in send_now
            ]
        else:
            for index, addr in enumerate(send_now):
                if not _consume_daily_send_slot(sc.user_id):
                    deferred = send_now[index:] + deferred
                    break

                name = resolve_recipient_name(addr, names_map)
                try:
                    msg = MIMEMultipart("mixed")
                    msg["From"] = from_addr
                    msg["To"] = addr
                    msg["Subject"] = personalize_text(subject, addr, name)
                    msg.attach(MIMEText(personalize_text(body, addr, name), "html"))
                    server.sendmail(from_addr, addr, msg.as_string())
                    results.append((addr, name, "sent", "", datetime.utcnow()))
                except Exception as error:
                    results.append((addr, name, "failed", str(error), None))
            try:
                server.quit()
            except Exception:
                pass

        if deferred:
            _create_quota_overflow_schedule(
                sc.user_id, sc.name, subject, body, deferred, names_map
            )

        ok = sum(1 for result in results if result[2] == "sent")
        fail = len(results) - ok
        c = Campaign(
            user_id=sc.user_id,
            name=f"[Scheduled] {sc.name}",
            subject=subject,
            body=body,
            total=len(results),
            sent_ok=ok,
            sent_fail=fail,
            status="completed",
        )
        db.session.add(c)
        db.session.flush()
        for addr, name, status, error, sent_at in results:
            db.session.add(CampaignRecipient(
                campaign_id=c.id,
                email=addr,
                name=name or None,
                status=status,
                error=error or None,
                sent_at=sent_at,
            ))
        db.session.commit()


def _next_occurrence(dt: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return dt + timedelta(days=1)
    if frequency == "monthly":
        month = dt.month + 1
        year = dt.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        import calendar
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)
    return dt + timedelta(weeks=1)


def run_scheduled_campaigns():
    from app import app
    with app.app_context():
        now = datetime.utcnow()
        due = ScheduledCampaign.query.filter(
            ScheduledCampaign.active == True,
            ScheduledCampaign.next_run_at <= now,
        ).all()
        for sc in due:
            old_next = sc.next_run_at
            is_one_off = sc.frequency == "once"
            updated = db.session.execute(
                db.update(ScheduledCampaign)
                .where(
                    ScheduledCampaign.id == sc.id,
                    ScheduledCampaign.next_run_at == old_next,
                )
                .values(
                    next_run_at=old_next if is_one_off else _next_occurrence(old_next, sc.frequency),
                    last_run_at=now,
                    active=(False if is_one_off else ScheduledCampaign.active),
                )
            )
            db.session.commit()
            if updated.rowcount == 0:
                continue
            user = User.query.get(sc.user_id)
            if not user or not user.smtp_host or not user.smtp_pass_enc:
                continue
            smtp_cfg = {
                "host": user.smtp_host,
                "port": user.smtp_port,
                "user": user.smtp_user,
                "pass": decrypt_password(user.smtp_pass_enc),
                "use_tls": user.smtp_use_tls,
                "from": user.smtp_from,
            }
            _fire_scheduled_campaign(sc.id, smtp_cfg)

FREQUENCY_CHOICES = ("once", "daily", "weekly", "monthly")