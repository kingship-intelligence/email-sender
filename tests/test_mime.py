from email import message_from_string

from app import app, build_campaign_message
from models import User


def test_campaign_message_has_alternatives_headers_and_attachment(user):
    with app.app_context():
        account = User.query.get(user)
        message = build_campaign_message(
            account,
            "recipient@example.com",
            "Hello",
            "<p>Welcome to <strong>Example</strong>.</p>",
            [("notes.txt", b"hello", "text/plain")],
        )

    parsed = message_from_string(message.as_string())
    assert parsed.get_content_type() == "multipart/mixed"
    assert parsed["Reply-To"] == "reply@example.com"
    assert "Example Team" in parsed["From"]
    assert parsed["List-Unsubscribe"]
    assert parsed["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    content_types = [part.get_content_type() for part in parsed.walk()]
    assert "multipart/alternative" in content_types
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "Unsubscribe" in next(
        part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        for part in parsed.walk()
        if part.get_content_type() == "text/plain"
    )


def test_inline_image_is_related(user):
    image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    with app.app_context():
        account = User.query.get(user)
        message = build_campaign_message(
            account,
            "recipient@example.com",
            "Image",
            f'<p>Hello</p><img src="data:image/png;base64,{image}">',
        )

    content_types = [part.get_content_type() for part in message.walk()]
    assert "multipart/related" in content_types
    assert "image/png" in content_types
