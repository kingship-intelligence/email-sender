import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from models import User
from flask import current_app

_PASS_RE_UPPER   = re.compile(r"[A-Z]")
_PASS_RE_DIGIT   = re.compile(r"\d")
_PASS_RE_SPECIAL = re.compile(r"[!@#$%^&*()\-_=+\[\]{};:',.<>?/\\|`~]")

def validate_password(password: str) -> list[str]:
    """Return a list of unmet password policy requirements (empty = OK)."""
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not _PASS_RE_UPPER.search(password):
        errors.append("one uppercase letter")
    if not _PASS_RE_DIGIT.search(password):
        errors.append("one number")
    if not _PASS_RE_SPECIAL.search(password):
        errors.append("one special character (!@#$%^&* …)")
    return errors

def _get_serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)

def make_verification_token(user_id: int) -> str:
    return _get_serializer("email-verify").dumps(user_id)

def verify_verification_token(token: str, max_age: int = 86400):
    """Return user_id or None (token invalid / expired after 24 h)."""
    try:
        return _get_serializer("email-verify").loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def make_reset_token(user_id: int) -> str:
    return _get_serializer("password-reset").dumps(user_id)

def verify_reset_token(token: str, max_age: int = 3600):
    """Return user_id or None (token invalid / expired after 1 h)."""
    try:
        return _get_serializer("password-reset").loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def _smtp_send(host, port, user, password, use_tls, from_addr, to_addr, msg_str) -> bool:
    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg_str)
        server.quit()
        return True
    except Exception:
        return False

def _send_auth_email(user: User, subject: str, body_html: str) -> bool:
    """Send a transactional email for account verification or password reset."""
    _APP_SMTP_HOST = os.environ.get("AUTH_SMTP_HOST", "")
    _APP_SMTP_PORT = int(os.environ.get("AUTH_SMTP_PORT", "587") or "587")
    _APP_SMTP_USER = os.environ.get("AUTH_SMTP_USER", "")
    _APP_SMTP_PASS = os.environ.get("AUTH_SMTP_PASS", "")
    _APP_SMTP_FROM = os.environ.get("AUTH_SMTP_FROM", "")
    _APP_SMTP_TLS  = os.environ.get("AUTH_SMTP_TLS", "true").lower() != "false"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"]      = user.email
    msg.attach(MIMEText(body_html, "html"))

    if _APP_SMTP_HOST and _APP_SMTP_USER and _APP_SMTP_PASS:
        from_addr = _APP_SMTP_FROM or _APP_SMTP_USER
        msg["From"] = from_addr
        if _smtp_send(_APP_SMTP_HOST, _APP_SMTP_PORT, _APP_SMTP_USER,
                      _APP_SMTP_PASS, _APP_SMTP_TLS, from_addr, user.email,
                      msg.as_string()):
            return True

    if user.smtp_host and user.smtp_pass_enc:
        try:
            from helpers.utils import decrypt_password # will create this later
            smtp_pass = decrypt_password(user.smtp_pass_enc)
            from_addr = user.smtp_from or user.smtp_user
            if "From" not in msg:
                msg["From"] = from_addr
            if _smtp_send(user.smtp_host, user.smtp_port, user.smtp_user,
                          smtp_pass, user.smtp_use_tls, from_addr, user.email,
                          msg.as_string()):
                return True
        except Exception:
            pass

    return False
