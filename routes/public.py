from flask import Blueprint, render_template, redirect, url_for, Response
from flask_login import login_required, current_user
from helpers.utils import get_domain

public_bp = Blueprint("public", __name__)

@public_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    return render_template("homepage.html", canonical_url=get_domain() + "/")

@public_bp.route("/help")
@login_required
def help_page():
    return render_template("help.html")

@public_bp.route("/tutorial")
@login_required
def tutorial():
    return render_template("tutorial.html")

@public_bp.route("/robots.txt")
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /dashboard\n"
        "Disallow: /campaign/\n"
        "Disallow: /settings\n"
        "Disallow: /scheduled\n"
        "\n"
        f"Sitemap: {get_domain()}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")

@public_bp.route("/sitemap.xml")
def sitemap_xml():
    domain = get_domain().rstrip("/")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{domain}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{domain}/register</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
</urlset>"""
    return Response(content, mimetype="application/xml")

@public_bp.route("/llms.txt")
def llms_txt():
    content = """# RushMail

> RushMail is a bulk email campaign tool for teams — extract recipients from files or URLs, personalize messages with merge tags, and send or schedule campaigns through your own SMTP server.

## Product
- Homepage: https://rushmail.co/
- Features: recipient extraction, name personalization, AI-assisted copy, SMTP acceptance tracking, campaign scheduling and analytics.
- Owned and operated by Kingship Intelligence (https://kingshipintelligence.com/)

## Contact
- Email: kingshipintelligence@gmail.com
"""
    return Response(content, mimetype="text/plain")
