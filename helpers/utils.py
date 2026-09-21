import base64
import hashlib
from cryptography.fernet import Fernet
from flask import current_app, request
import os

def get_domain():
    domain = os.environ.get("APP_DOMAIN", "")
    if domain:
        return domain.rstrip("/")
    return request.host_url.rstrip("/")

def get_fernet():
    raw = current_app.config["SECRET_KEY"].encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)

def encrypt_password(plain: str) -> str:
    return get_fernet().encrypt(plain.encode()).decode()

def decrypt_password(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()
