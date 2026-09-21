import json
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from models import db, Campaign, DailySendUsage, ScheduledCampaign

DAILY_SEND_LIMIT = 400

def _utc_tomorrow_start(now=None):
    now = now or datetime.utcnow()
    return (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)

def _seed_daily_send_count(user_id: int, usage_date) -> int:
    day_start = datetime.combine(usage_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    campaigns = Campaign.query.filter(
        Campaign.user_id == user_id,
        Campaign.created_at >= day_start,
        Campaign.created_at < day_end,
    ).all()
    return sum((campaign.sent_ok or 0) + (campaign.sent_fail or 0) for campaign in campaigns)

def _daily_usage_row(user_id: int) -> DailySendUsage:
    usage_date = datetime.utcnow().date()
    usage = DailySendUsage.query.filter_by(
        user_id=user_id, usage_date=usage_date
    ).first()
    if usage:
        return usage

    try:
        usage = DailySendUsage(
            user_id=user_id,
            usage_date=usage_date,
            attempt_count=_seed_daily_send_count(user_id, usage_date),
        )
        db.session.add(usage)
        db.session.commit()
        return usage
    except IntegrityError:
        db.session.rollback()
        return DailySendUsage.query.filter_by(
            user_id=user_id, usage_date=usage_date
        ).one()

def _daily_quota_status(user_id: int) -> dict:
    usage = _daily_usage_row(user_id)
    used = usage.attempt_count or 0
    return {
        "limit": DAILY_SEND_LIMIT,
        "used": used,
        "remaining": max(DAILY_SEND_LIMIT - used, 0),
    }

def _consume_daily_send_slot(user_id: int) -> bool:
    usage = _daily_usage_row(user_id)
    updated = db.session.execute(
        db.update(DailySendUsage)
        .where(
            DailySendUsage.id == usage.id,
            DailySendUsage.attempt_count < DAILY_SEND_LIMIT,
        )
        .values(attempt_count=DailySendUsage.attempt_count + 1)
    )
    if updated.rowcount:
        db.session.commit()
        return True
    db.session.rollback()
    return False

def _create_quota_overflow_schedule(
    user_id: int,
    name: str,
    subject: str,
    body: str,
    emails: list[str],
    names_map: dict,
) -> ScheduledCampaign:
    overflow_name = (
        name if name.endswith("(daily limit remainder)")
        else f"{name} (daily limit remainder)"
    )
    overflow_names = {
        email: names_map[email]
        for email in emails
        if email in names_map and names_map[email]
    }
    schedule = ScheduledCampaign(
        user_id=user_id,
        name=overflow_name,
        subject=subject,
        body=body,
        emails_json=json.dumps(emails),
        names_json=json.dumps(overflow_names),
        next_run_at=_utc_tomorrow_start(),
        frequency="once",
    )
    db.session.add(schedule)
    return schedule
