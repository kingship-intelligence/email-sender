from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from models import db, User
from extensions import bcrypt, limiter
from helpers.auth import (
    validate_password, 
    make_verification_token, verify_verification_token,
    make_reset_token, verify_reset_token,
    _send_auth_email
)
from helpers.utils import get_domain

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"], error_message="Too many login attempts. Please wait 15 minutes and try again.")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            if not user.verified:
                flash(
                    "Please verify your email before signing in. "
                    "<a href=\"" + url_for("auth.resend_verification", email=user.email) + "\">Resend verification email</a>",
                    "error"
                )
                return render_template("login.html", canonical_url=get_domain() + "/login")
            login_user(user)
            return redirect(url_for("dashboard.dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html", canonical_url=get_domain() + "/login")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        policy_errors = validate_password(password)
        if policy_errors:
            return render_template("register.html", password_errors=policy_errors, email=email, canonical_url=get_domain() + "/register")
        elif password != password2:
            flash("Passwords do not match.", "error")
            return render_template("register.html", password_errors=[], email=email, canonical_url=get_domain() + "/register")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(
                email=email,
                password_hash=bcrypt.generate_password_hash(password).decode(),
                verified=False,
            )
            db.session.add(user)
            db.session.commit()
            token = make_verification_token(user.id)
            verify_url = get_domain() + url_for("auth.verify_email", token=token)
            sent = _send_auth_email(
                user,
                "Verify your RushMail account",
                f"""
                <p>Hi,</p>
                <p>Thanks for signing up to RushMail! Click the button below to verify your email address.
                This link expires in 24 hours.</p>
                <p><a href="{verify_url}" style="background:#f97316;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">Verify Email</a></p>
                <p>Or paste this link into your browser:<br><a href="{verify_url}">{verify_url}</a></p>
                """,
            )
            if sent:
                flash("Account created! Check your email to verify your address before signing in.", "success")
            else:
                flash(
                    f'Account created! Email delivery is not configured, so click this link to verify your account: '
                    f'<a href="{verify_url}">{verify_url}</a>',
                    "success"
                )
            return redirect(url_for("auth.login"))
    return render_template("register.html", password_errors=[], canonical_url=get_domain() + "/register")


@auth_bp.route("/verify/<token>")
def verify_email(token):
    user_id = verify_verification_token(token)
    if not user_id:
        flash("That verification link is invalid or has expired.", "error")
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("auth.login"))
    if user.verified:
        flash("Your email is already verified — you can sign in.", "success")
        return redirect(url_for("auth.login"))
    user.verified = True
    db.session.commit()
    flash("Email verified! You can now sign in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/resend-verification")
def resend_verification():
    email = request.args.get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if user and not user.verified:
        token = make_verification_token(user.id)
        verify_url = get_domain() + url_for("auth.verify_email", token=token)
        _send_auth_email(
            user,
            "Verify your RushMail account",
            f"""
            <p>Hi,</p>
            <p>Here's your new verification link. It expires in 24 hours.</p>
            <p><a href="{verify_url}" style="background:#f97316;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">Verify Email</a></p>
            <p>Or paste this link:<br><a href="{verify_url}">{verify_url}</a></p>
            """,
        )
    flash("If that address is registered and unverified, we sent a new link. Check your inbox.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = make_reset_token(user.id)
            reset_url = get_domain() + url_for("auth.reset_password", token=token)
            _send_auth_email(
                user,
                "Reset your RushMail password",
                f"""
                <p>Hi,</p>
                <p>Someone requested a password reset for your RushMail account.
                Click the button below to set a new password. This link expires in 1 hour.</p>
                <p><a href="{reset_url}" style="background:#f97316;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">Reset Password</a></p>
                <p>If you didn't request this, you can safely ignore this email.</p>
                <p>Or paste this link:<br><a href="{reset_url}">{reset_url}</a></p>
                """,
            )
        flash("If an account with that email exists, we've sent a reset link. Check your inbox.", "success")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html", canonical_url=get_domain() + "/forgot-password")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user_id = verify_reset_token(token)
    if not user_id:
        flash("That reset link is invalid or has expired (links expire after 1 hour).", "error")
        return redirect(url_for("auth.forgot_password"))
    user = db.session.get(User, user_id)
    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        password  = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        policy_errors = validate_password(password)
        _reset_canonical = get_domain() + "/forgot-password"
        if policy_errors:
            return render_template("reset_password.html", token=token, password_errors=policy_errors, canonical_url=_reset_canonical)
        elif password != password2:
            return render_template("reset_password.html", token=token, password_errors=[], mismatch=True, canonical_url=_reset_canonical)
        else:
            user.password_hash = bcrypt.generate_password_hash(password).decode()
            user.verified = True
            db.session.commit()
            flash("Password updated! You can now sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset_password.html", token=token, password_errors=[], canonical_url=get_domain() + "/forgot-password")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
