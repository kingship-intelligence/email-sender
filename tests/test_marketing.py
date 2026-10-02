from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_copy_does_not_claim_unlimited_or_delivery_analytics():
    paths = [
        ROOT / "README.md",
        ROOT / "templates" / "pricing.html",
        ROOT / "templates" / "settings.html",
        ROOT / "templates" / "help.html",
    ]
    copy = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)

    assert "unlimited recipients" not in copy
    assert "there is no limit imposed" not in copy
    assert "campaign history &amp; analytics" not in copy
    assert "aes-256 (via fernet)" not in copy
