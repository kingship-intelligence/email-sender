from app import app
from models import User


def test_public_registration_is_disabled(client):
    response = client.post(
        "/register",
        data={
            "email": "new@example.com",
            "password": "Strong1!",
            "password2": "Strong1!",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app.app_context():
        assert User.query.filter_by(email="new@example.com").first() is None


def test_settings_page_exposes_account_controls(authenticated_client):
    response = authenticated_client.get("/settings")
    assert response.status_code == 200
    assert b"Download my data" in response.data
    assert b"Reply-To" in response.data


def test_account_export_excludes_secrets(authenticated_client):
    response = authenticated_client.get("/account/export")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["account"]["email"] == "owner@example.com"
    serialized = response.get_data(as_text=True)
    assert "password_hash" not in serialized
    assert "smtp_pass_enc" not in serialized


def test_account_deletion_requires_password(authenticated_client, user):
    response = authenticated_client.post(
        "/account/delete",
        data={"password": "wrong", "confirmation": "DELETE"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert User.query.get(user) is not None


def test_account_deletion_removes_local_user(authenticated_client, user):
    response = authenticated_client.post(
        "/account/delete",
        data={"password": "Strong1!", "confirmation": "DELETE"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert User.query.get(user) is None


def test_settings_reject_header_injection(authenticated_client, user):
    response = authenticated_client.post(
        "/settings",
        data={
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "owner@example.com",
            "smtp_from": "owner@example.com",
            "smtp_sender_name": "Example\nBcc: victim@example.com",
            "smtp_reply_to": "reply@example.com",
            "smtp_use_tls": "on",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert User.query.get(user).smtp_sender_name == "Example Team"
