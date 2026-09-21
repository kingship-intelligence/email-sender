import os
import stripe
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, User
from extensions import csrf
from helpers.utils import get_domain

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
STRIPE_ENABLED = bool(STRIPE_SECRET_KEY)

if STRIPE_ENABLED:
    stripe.api_key = STRIPE_SECRET_KEY

billing_bp = Blueprint("billing", __name__)

@billing_bp.route("/pricing")
@login_required
def pricing():
    return render_template("pricing.html", stripe_enabled=STRIPE_ENABLED)

@billing_bp.route("/subscribe")
@login_required
def subscribe():
    if not STRIPE_ENABLED:
        flash("Payments are not configured yet.", "error")
        return redirect(url_for("billing.pricing"))
    if not STRIPE_PRO_PRICE_ID:
        flash("Pro plan price not configured. Contact support.", "error")
        return redirect(url_for("billing.pricing"))

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
        return redirect(url_for("billing.pricing"))

@billing_bp.route("/subscribe/success")
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
    flash("Welcome to RushMail Pro! Your account is now active.", "success")
    return redirect(url_for("dashboard.dashboard"))

@billing_bp.route("/billing-portal")
@login_required
def billing_portal():
    if not STRIPE_ENABLED or not current_user.stripe_customer_id:
        flash("Billing portal is not available.", "error")
        return redirect(url_for("settings.settings"))
    try:
        domain = get_domain()
        portal = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{domain}/settings",
        )
        return redirect(portal.url, code=303)
    except stripe.error.StripeError as e:
        flash(f"Could not open billing portal: {e.user_message}", "error")
        return redirect(url_for("settings.settings"))

@billing_bp.route("/webhook", methods=["POST"])
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
