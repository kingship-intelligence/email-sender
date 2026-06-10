from datetime import datetime
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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    campaigns = db.relationship("Campaign", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def is_pro(self):
        return self.plan == "pro"

    @property
    def send_limit(self):
        return None if self.is_pro else 50


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
    status = db.Column(db.String(20), default="pending")
    error = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
