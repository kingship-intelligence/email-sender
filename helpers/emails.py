import re
import socket
import ipaddress
import requests as req_lib
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

GENERIC_LOCALPARTS = {
    "info", "contact", "sales", "support", "admin", "hello", "hi", "team",
    "office", "mail", "email", "enquiries", "inquiries", "inquiry", "help",
    "hr", "careers", "jobs", "billing", "accounts", "accounting", "marketing",
    "press", "media", "noreply", "no-reply", "donotreply", "newsletter",
    "webmaster", "postmaster", "abuse", "security", "service", "services",
    "orders", "bookings", "reception", "general", "feedback", "notifications",
    "alerts", "news", "updates", "subscribe", "unsubscribe", "recruiting",
}

def derive_name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    if local.lower() in GENERIC_LOCALPARTS:
        return ""
    local = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local)
    tokens = []
    for part in re.split(r"[._\-+\s]+", local.lower()):
        part = re.sub(r"\d+", "", part)
        if len(part) >= 2 and part.isalpha() and part not in GENERIC_LOCALPARTS:
            tokens.append(part.capitalize())
        if len(tokens) == 2:
            break
    return " ".join(tokens)

_MERGE_TAG_RE = re.compile(
    r"\{\{\s*(name|first_name|firstname|last_name|lastname|email)\s*(?:\|([^}]*))?\}\}",
    re.IGNORECASE,
)

def personalize_text(text: str, email: str, full_name: str) -> str:
    parts = (full_name or "").split()
    values = {
        "email": email,
        "name": (full_name or "").strip(),
        "first_name": parts[0] if parts else "",
        "last_name": parts[-1] if len(parts) > 1 else "",
    }

    def repl(m):
        key = m.group(1).lower().replace("firstname", "first_name").replace("lastname", "last_name")
        fallback = (m.group(2) or "").strip()
        val = values.get(key, "")
        if val:
            return val
        if fallback:
            return fallback
        return email if key == "email" else "there"

    return _MERGE_TAG_RE.sub(repl, text)

def resolve_recipient_name(email: str, names_map: dict) -> str:
    provided = (names_map.get(email) or "").strip() if isinstance(names_map, dict) else ""
    return provided or derive_name_from_email(email)

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

def _hostname_is_safe(hostname: str) -> bool:
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

def _safe_fetch(url: str, max_redirects: int = 5) -> req_lib.Response:
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
