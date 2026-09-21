from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Campaign, CampaignRecipient
from helpers.decorators import subscription_required

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
@subscription_required
def dashboard():
    campaigns = (
        Campaign.query
        .filter_by(user_id=current_user.id)
        .order_by(Campaign.created_at.desc())
        .all()
    )

    campaign_metrics = {
        campaign.id: {"sent": 0, "failed": 0, "pending": 0}
        for campaign in campaigns
    }
    campaign_ids = list(campaign_metrics)
    if campaign_ids:
        recipient_counts = (
            db.session.query(
                CampaignRecipient.campaign_id,
                CampaignRecipient.status,
                db.func.count(CampaignRecipient.id),
            )
            .filter(CampaignRecipient.campaign_id.in_(campaign_ids))
            .group_by(CampaignRecipient.campaign_id, CampaignRecipient.status)
            .all()
        )
        for campaign_id, status, count in recipient_counts:
            if status in campaign_metrics[campaign_id]:
                campaign_metrics[campaign_id][status] = count

    for campaign in campaigns:
        metrics = campaign_metrics[campaign.id]
        recipient_total = metrics["sent"] + metrics["failed"] + metrics["pending"]
        if recipient_total == 0 and campaign.total:
            metrics["sent"] = campaign.sent_ok or 0
            metrics["failed"] = campaign.sent_fail or 0
            metrics["pending"] = max(
                campaign.total - metrics["sent"] - metrics["failed"], 0
            )
        metrics["total"] = max(
            campaign.total or 0,
            metrics["sent"] + metrics["failed"] + metrics["pending"],
        )
        attempted = metrics["sent"] + metrics["failed"]
        metrics["sent_rate"] = round(metrics["sent"] / attempted * 100, 1) if attempted else None
        metrics["failure_rate"] = round(metrics["failed"] / attempted * 100, 1) if attempted else None
        metrics["unsent"] = metrics["failed"] + metrics["pending"]
        metrics["can_retry"] = (
            metrics["unsent"] > 0 and campaign.status not in ("queued", "sending")
        )

    stats = {
        "campaigns": len(campaigns),
        "sent_ok": sum(metrics["sent"] for metrics in campaign_metrics.values()),
        "sent_fail": sum(metrics["failed"] for metrics in campaign_metrics.values()),
    }
    attempted = stats["sent_ok"] + stats["sent_fail"]
    stats["sent_rate"] = round(stats["sent_ok"] / attempted * 100, 1) if attempted else None
    stats["failure_rate"] = round(stats["sent_fail"] / attempted * 100, 1) if attempted else None
    return render_template(
        "dashboard.html",
        campaigns=campaigns,
        campaign_metrics=campaign_metrics,
        stats=stats,
    )
