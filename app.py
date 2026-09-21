import os
from dotenv import load_dotenv
from flask import Flask
from flask_session import Session
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, User
from extensions import bcrypt, csrf, limiter, login_manager
import extensions

# Import blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.campaigns import campaigns_bp
from routes.scheduled import scheduled_bp
from routes.settings import settings_bp
from routes.billing import billing_bp
from routes.public import public_bp

load_dotenv()
app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_secret = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET")
if not _secret:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Set it to a strong random value before starting the server."
    )
app.config["SECRET_KEY"] = _secret
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///rushmail.db"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload limit

# ── Server-side sessions ──────────────────────────────────────────────────────
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.getcwd(), ".flask_sessions")
app.config["SESSION_FILE_THRESHOLD"] = 500
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "None"
app.config["REMEMBER_COOKIE_SECURE"] = True

# ── Extensions ────────────────────────────────────────────────────────────────
db.init_app(app)
bcrypt.init_app(app)
csrf.init_app(app)
Session(app)
login_manager.init_app(app)
limiter.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── Blueprints ────────────────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(campaigns_bp)
app.register_blueprint(scheduled_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(public_bp)

# ── Global State ─────────────────────────────────────────────────────────────
extensions._scheduler = None
extensions._pending_attachments = {}

# ── Init DB and Scheduler ────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if "scheduled_campaigns" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("scheduled_campaigns")]
            if "frequency" not in cols:
                db.session.execute(text(
                    "ALTER TABLE scheduled_campaigns ADD COLUMN frequency VARCHAR(20) NOT NULL DEFAULT 'weekly'"
                ))
                db.session.commit()
            if "names_json" not in cols:
                db.session.execute(text(
                    "ALTER TABLE scheduled_campaigns ADD COLUMN names_json TEXT"
                ))
                db.session.commit()
        if "campaign_recipients" in inspector.get_table_names():
            rec_cols = [c["name"] for c in inspector.get_columns("campaign_recipients")]
            if "name" not in rec_cols:
                db.session.execute(text(
                    "ALTER TABLE campaign_recipients ADD COLUMN name VARCHAR(255)"
                ))
                db.session.commit()
        if "users" in inspector.get_table_names():
            user_cols = [c["name"] for c in inspector.get_columns("users")]
            if "verified" not in user_cols:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN verified BOOLEAN NOT NULL DEFAULT TRUE"
                ))
                db.session.commit()
    except Exception:
        db.session.rollback()

if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    from helpers.scheduler_tasks import run_scheduled_campaigns
    extensions._scheduler = BackgroundScheduler(daemon=True)
    extensions._scheduler.add_job(run_scheduled_campaigns, "interval", minutes=1, max_instances=1)
    extensions._scheduler.start()
    print("[scheduler] started")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
