import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_DOMAIN", "https://example.test")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

import pytest

from app import app, bcrypt, db, limiter
from models import User


@pytest.fixture(autouse=True)
def database():
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SESSION_COOKIE_SECURE=False,
        REMEMBER_COOKIE_SECURE=False,
        RATELIMIT_ENABLED=False,
    )
    with app.app_context():
        limiter.reset()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def user():
    with app.app_context():
        account = User(
            email="owner@example.com",
            password_hash=bcrypt.generate_password_hash("Strong1!").decode(),
            plan="pro",
            verified=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="owner@example.com",
            smtp_from="owner@example.com",
            smtp_sender_name="Example Team",
            smtp_reply_to="reply@example.com",
            smtp_use_tls=True,
        )
        db.session.add(account)
        db.session.commit()
        return account.id


@pytest.fixture
def authenticated_client(client, user):
    response = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "Strong1!"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    return client
