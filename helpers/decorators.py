from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_pro:
            flash("An active subscription is required. Subscribe below to get started.", "error")
            return redirect(url_for("billing.pricing"))
        return f(*args, **kwargs)
    return decorated
