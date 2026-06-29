import os
import re
import json
import hashlib
import base64
import smtplib
import ipaddress
import socket
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, flash, Response, stream_with_context
)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from cryptography.fernet import Fernet

import stripe
import requests as req_lib
from bs4 import BeautifulSoup
import openpyxl
import csv
import io

from models import db, User, Campaign, CampaignRecipient

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
    "DATABASE_URL", "sqlite:///mailblast.db"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload limit

# ── Server-side sessions ──────────────────────────────────────────────────────
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.getcwd(), ".flask_sessions")
app.config["SESSION_FILE_THRESHOLD"] = 500
app.config["SESSION_PERMANENT"] = False

db.init_app(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)
Session(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "error"

# ── Stripe ────────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
STRIPE_ENABLED = bool(STRIPE_SECRET_KEY)

if STRIPE_ENABLED:
    stripe.api_key = STRIPE_SECRET_KEY

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Helpers ───────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def get_fernet():
    raw = app.config["SECRET_KEY"].encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_password(plain: str) -> str:
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()


def extract_emails(text: str) -> list[str]:
    found = EMAIL_RE.findall(text)
    seen = set()
    result = []
    for e in found:
        e_lower = e.lower()
        if e_lower not in seen:
            seen.add(e_lower)
            result.append(e_lower)
    return result


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def get_domain():
    domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if domain:
        return f"https://{domain}"
    return request.host_url.rstrip("/")


# ── Subscription guard ────────────────────────────────────────────────────────
def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_pro:
            flash("An active subscription is required. Subscribe below to get started.", "error")
            return redirect(url_for("pricing"))
        return f(*args, **kwargs)
    return decorated


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != password2:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(
                email=email,
                password_hash=bcrypt.generate_password_hash(password).decode()
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created! Subscribe below to get started.", "success")
            return redirect(url_for("pricing"))
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
@subscription_required
def dashboard():
    campaigns = (
        Campaign.query
        .filter_by(user_id=current_user.id)
        .order_by(Campaign.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", campaigns=campaigns)


# ── Campaign ──────────────────────────────────────────────────────────────────
@app.route("/campaign/new")
@login_required
@subscription_required
def campaign_new():
    return render_template("campaign_new.html")


@app.route("/campaign/<int:campaign_id>")
@login_required
@subscription_required
def campaign_detail(campaign_id):
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first_or_404()
    recipients = CampaignRecipient.query.filter_by(campaign_id=campaign.id).all()
    return render_template("campaign_detail.html", campaign=campaign, recipients=recipients)


@app.route("/extract", methods=["POST"])
@login_required
@subscription_required
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    f = request.files["file"]
    filename = f.filename.lower()
    text = ""

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            wb = openpyxl.load_workbook(f, data_only=True)
            for sheet in wb.worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value:
                            text += str(cell.value) + " "

        elif filename.endswith(".csv"):
            raw = f.read()
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError:
                decoded = raw.decode("latin-1")
            reader = csv.reader(io.StringIO(decoded))
            for row in reader:
                text += " ".join(row) + " "

        elif filename.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + " "

        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(f)
            for para in doc.paragraphs:
                text += para.text + " "
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text += cell.text + " "

        else:
            raw = f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")

    except Exception as e:
        return jsonify({"error": f"Could not parse file: {e}"}), 400

    emails = extract_emails(text)
    return jsonify({"emails": emails, "total": len(emails)})


def _hostname_is_safe(hostname: str) -> bool:
    """Return False if any resolved IP for hostname is a non-public address."""
    try:
        infos = socket.getaddrinfo(hostname, None)
        if not infos:
            return False
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def _is_ssrf_safe(url: str) -> bool:
    """Return False if the URL scheme is not http/https or resolves to a non-public address."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        return _hostname_is_safe(hostname)
    except Exception:
        return False


def _safe_fetch(url: str, max_redirects: int = 5) -> "req_lib.Response":
    """Fetch a URL, validating SSRF safety at every redirect hop."""
    _HEADERS = {"User-Agent": "Mozilla/5.0"}
    for _ in range(max_redirects + 1):
        if not _is_ssrf_safe(url):
            raise ValueError(f"Blocked: {url} resolves to a private/internal address")
        resp = req_lib.get(url, timeout=10, headers=_HEADERS, allow_redirects=False)
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location:
                break
            if location.startswith("/"):
                parsed = urlparse(url)
                url = f"{parsed.scheme}://{parsed.netloc}{location}"
            else:
                url = location
        else:
            resp.raise_for_status()
            return resp
    raise ValueError("Too many redirects or redirect loop detected")


@app.route("/extract-url", methods=["POST"])
@login_required
@subscription_required
def extract_url():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not _is_ssrf_safe(url):
        return jsonify({"error": "That URL is not allowed."}), 400
    try:
        resp = _safe_fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not fetch URL: {e}"}), 400

    emails = extract_emails(text)
    return jsonify({"emails": emails, "total": len(emails)})


@app.route("/generate", methods=["POST"])
@login_required
@subscription_required
def generate():
    if not OPENAI_API_KEY:
        return jsonify({"error": "OpenAI is not configured. Contact support."}), 503

    data = request.get_json()
    brief = (data or {}).get("brief", "").strip()
    if not brief:
        return jsonify({"error": "Campaign brief is required."}), 400

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a marketing copywriter. Write a concise, engaging marketing email. "
                        "Return ONLY valid JSON with keys 'subject' (string, max 80 chars) and 'body' (string, plain text, 150-300 words). "
                        "No markdown, no extra keys, no explanations."
                    )
                },
                {
                    "role": "user",
                    "content": f"Campaign brief: {brief}"
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
        )
        result = json.loads(response.choices[0].message.content)
        if "subject" not in result or "body" not in result:
            raise ValueError("Missing keys in AI response")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"AI generation failed: {e}"}), 500


@app.route("/send-bulk", methods=["POST"])
@login_required
@subscription_required
def send_bulk():
    # Accept multipart/form-data (with optional file attachments)
    emails_raw = request.form.get("emails", "[]")
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    campaign_name = (request.form.get("name", "Campaign") or "Campaign").strip()

    try:
        emails = json.loads(emails_raw)
    except Exception:
        return jsonify({"error": "Invalid emails payload."}), 400

    if not emails or not subject or not body:
        return jsonify({"error": "emails, subject, and body are required."}), 400

    if not current_user.smtp_host:
        return jsonify({"error": "SMTP is not configured. Go to Settings."}), 400

    # Read uploaded attachments into memory
    attachment_files = request.files.getlist("attachments")
    attachments = []
    for att_file in attachment_files:
        if att_file and att_file.filename:
            att_data = att_file.read()
            attachments.append((att_file.filename, att_data, att_file.mimetype or "application/octet-stream"))

    smtp_host = current_user.smtp_host
    smtp_port = current_user.smtp_port
    smtp_user = current_user.smtp_user
    smtp_pass = decrypt_password(current_user.smtp_pass_enc)
    use_tls = current_user.smtp_use_tls
    from_addr = current_user.smtp_from or smtp_user

    # Create campaign record
    campaign = Campaign(
        user_id=current_user.id,
        name=campaign_name,
        subject=subject,
        body=body,
        total=len(emails),
    )
    db.session.add(campaign)
    db.session.flush()

    recipients = []
    for email in emails:
        r = CampaignRecipient(campaign_id=campaign.id, email=email)
        db.session.add(r)
        recipients.append(r)
    db.session.commit()

    def stream():
        ok = 0
        fail = 0
        server = None
        try:
            if use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.ehlo()
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            server.login(smtp_user, smtp_pass)
        except Exception as e:
            for r in recipients:
                r.status = "failed"
                r.error = str(e)
                fail += 1
                yield json.dumps({"email": r.email, "status": "failed", "error": str(e)}) + "\n"
            campaign.sent_ok = 0
            campaign.sent_fail = fail
            campaign.status = "completed"
            db.session.commit()
            yield json.dumps({"done": True, "ok": ok, "fail": fail, "campaign_id": campaign.id}) + "\n"
            return

        for r in recipients:
            try:
                msg = MIMEMultipart("mixed")
                msg["From"] = from_addr
                msg["To"] = r.email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                for att_name, att_data, att_mime in attachments:
                    maintype, subtype = att_mime.split("/", 1) if "/" in att_mime else ("application", "octet-stream")
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(att_data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=att_name)
                    msg.attach(part)

                server.sendmail(from_addr, r.email, msg.as_string())
                r.status = "sent"
                r.sent_at = datetime.utcnow()
                ok += 1
                yield json.dumps({"email": r.email, "status": "sent"}) + "\n"
            except Exception as e:
                r.status = "failed"
                r.error = str(e)
                fail += 1
                yield json.dumps({"email": r.email, "status": "failed", "error": str(e)}) + "\n"
            db.session.commit()

        try:
            server.quit()
        except Exception:
            pass

        campaign.sent_ok = ok
        campaign.sent_fail = fail
        campaign.status = "completed"
        db.session.commit()
        yield json.dumps({"done": True, "ok": ok, "fail": fail, "campaign_id": campaign.id}) + "\n"

    return Response(stream_with_context(stream()), mimetype="application/x-ndjson")


# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/settings", methods=["GET", "POST"])
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
        return redirect(url_for("settings"))
    return render_template("settings.html", stripe_enabled=STRIPE_ENABLED)


# ── Stripe / Pricing ──────────────────────────────────────────────────────────
@app.route("/pricing")
@login_required
def pricing():
    return render_template("pricing.html", stripe_enabled=STRIPE_ENABLED)


@app.route("/subscribe")
@login_required
def subscribe():
    if not STRIPE_ENABLED:
        flash("Payments are not configured yet.", "error")
        return redirect(url_for("pricing"))
    if not STRIPE_PRO_PRICE_ID:
        flash("Pro plan price not configured. Contact support.", "error")
        return redirect(url_for("pricing"))

    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.session.commit()

        domain = get_domain()
        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRO_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url=f"{domain}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{domain}/pricing",
        )
        return redirect(session.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Stripe error: {e.user_message}", "error")
        return redirect(url_for("pricing"))


@app.route("/subscribe/success")
@login_required
def subscribe_success():
    session_id = request.args.get("session_id")
    if session_id and STRIPE_ENABLED:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if (
                session.customer
                and current_user.stripe_customer_id
                and session.customer == current_user.stripe_customer_id
                and session.payment_status in ("paid", "no_payment_required")
                and session.subscription
            ):
                current_user.stripe_subscription_id = session.subscription
                current_user.plan = "pro"
                db.session.commit()
        except Exception:
            pass
    flash("Welcome to MailBlast Pro! Your account is now active.", "success")
    return redirect(url_for("dashboard"))


@app.route("/billing-portal")
@login_required
def billing_portal():
    if not STRIPE_ENABLED or not current_user.stripe_customer_id:
        flash("Billing portal is not available.", "error")
        return redirect(url_for("settings"))
    try:
        domain = get_domain()
        portal = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{domain}/settings",
        )
        return redirect(portal.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Could not open billing portal: {e.user_message}", "error")
        return redirect(url_for("settings"))


@app.route("/webhook", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    if not STRIPE_ENABLED or not STRIPE_WEBHOOK_SECRET:
        return jsonify({"error": "Webhooks not configured"}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid payload"}), 400

    if event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        user = User.query.filter_by(stripe_customer_id=sub["customer"]).first()
        if user:
            user.stripe_subscription_id = sub["id"]
            user.plan = "pro" if sub["status"] in ("active", "trialing") else "free"
            db.session.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        user = User.query.filter_by(stripe_customer_id=sub["customer"]).first()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            db.session.commit()

    return jsonify({"received": True})


# ── Help ──────────────────────────────────────────────────────────────────────
@app.route("/help")
@login_required
def help_page():
    return render_template("help.html")


# ── Tutorial ──────────────────────────────────────────────────────────────────
@app.route("/tutorial")
@login_required
def tutorial():
    return render_template("tutorial.html")


# ── Init ──────────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
