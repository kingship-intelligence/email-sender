from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(20), default="free")
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))

    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(255))
    smtp_pass_enc = db.Column(db.Text)
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_from = db.Column(db.String(255))

    verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    campaigns = db.relationship("Campaign", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def is_pro(self):
        return self.plan == "pro"


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), default="Untitled Campaign")
    subject = db.Column(db.String(500))
    body = db.Column(db.Text)
    status = db.Column(db.String(20), default="completed")
    total = db.Column(db.Integer, default=0)
    sent_ok = db.Column(db.Integer, default=0)
    sent_fail = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recipients = db.relationship(
        "CampaignRecipient", backref="campaign", lazy=True, cascade="all, delete-orphan"
    )


class CampaignRecipient(db.Model):
    __tablename__ = "campaign_recipients"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    status = db.Column(db.String(20), default="pending")
    error = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)


class ScheduledCampaign(db.Model):
    __tablename__ = "scheduled_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=False)
    emails_json = db.Column(db.Text, nullable=False)
    names_json = db.Column(db.Text)
    next_run_at = db.Column(db.DateTime, nullable=False)
    last_run_at = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)
    frequency = db.Column(db.String(20), default="weekly", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("scheduled_campaigns", lazy=True, cascade="all, delete-orphan"))

    @property
    def emails(self):
        import json
        return json.loads(self.emails_json or "[]")

    @property
    def names(self):
        import json
        try:
            data = json.loads(self.names_json or "{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
