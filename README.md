# RushMail

A self-hostable bulk email campaign platform built with Flask. Users bring their own SMTP credentials, build recipient lists by extracting email addresses from files or web pages, write copy by hand or with AI assistance, and send or schedule campaigns — with per-recipient delivery tracking and Stripe-powered subscriptions.

## Features

- **Bulk sending** — send a campaign to any list of recipients through the user's own SMTP server, with optional file attachments. Delivery progress streams live to the browser (NDJSON), and every recipient's sent/failed status and error is recorded.
- **Recipient extraction** — upload a `.xlsx`, `.xls`, `.csv`, `.pdf`, `.docx`, or plain-text file, or point at a URL, and RushMail pulls out and deduplicates every email address it finds. URL fetching is SSRF-guarded (private/internal addresses are blocked, redirects re-validated hop by hop).
- **AI copywriting** — generate a subject line and body from a short campaign brief using OpenAI (`gpt-4o-mini`).
- **Scheduled campaigns** — one-off, daily, weekly, or monthly sends run by a background APScheduler job, with optimistic locking so concurrent workers never double-send. Each run is recorded as a campaign in the dashboard.
- **Accounts and security** — email verification, password reset, bcrypt password hashing with a strength policy, login rate limiting, CSRF protection, and server-side sessions. Per-user SMTP passwords are encrypted at rest with Fernet.
- **Billing** — free plan (50-email send limit) and a Pro plan via Stripe Checkout, with webhook-driven subscription state and a customer billing portal.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Flask, Flask-Login, Flask-WTF (CSRF), Flask-Limiter, Flask-Session |
| Database | SQLAlchemy — SQLite by default, PostgreSQL via `DATABASE_URL` |
| Scheduling | APScheduler (in-process background scheduler) |
| Payments | Stripe (Checkout, webhooks, billing portal) |
| AI | OpenAI API |
| Parsing | openpyxl, pdfplumber, python-docx, BeautifulSoup |
| Frontend | Server-rendered Jinja2 templates + vanilla JS |

## Getting started

Requires Python 3.11+. Dependencies are managed with [uv](https://docs.astral.sh/uv/) (a `uv.lock` is committed), but plain pip works too.

```bash
git clone https://github.com/kingship-intelligence/email-sender.git
cd email-sender

# with uv
uv sync

# set the one required environment variable
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# run the dev server (http://localhost:5000)
uv run python app.py
```

Tables are created automatically on first start (`db.create_all()` plus lightweight column migrations). By default data is stored in a local SQLite file (`rushmail.db`).

For production, use Gunicorn:

```bash
gunicorn --bind=0.0.0.0:5000 --workers=2 app:app
```

## Configuration

All configuration is via environment variables.

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` (or `SESSION_SECRET`) | **Yes** | Signs sessions, auth tokens, and derives the Fernet key that encrypts stored SMTP passwords. The app refuses to start without it. Changing it invalidates stored SMTP passwords. |
| `DATABASE_URL` | No | PostgreSQL connection string. Defaults to SQLite (`rushmail.db`). `postgres://` URLs are rewritten to `postgresql://` automatically. |
| `OPENAI_API_KEY` | No | Enables the AI email generator. Without it, `/generate` returns 503. |
| `STRIPE_SECRET_KEY` | No | Enables billing. Without it, Stripe features are disabled. |
| `STRIPE_PUBLISHABLE_KEY` | No | Client-side Stripe key. |
| `STRIPE_WEBHOOK_SECRET` | No | Verifies webhook signatures on `POST /webhook`. |
| `STRIPE_PRO_PRICE_ID` | No | Price ID for the Pro subscription used at checkout. |
| `AUTH_SMTP_HOST` / `AUTH_SMTP_PORT` / `AUTH_SMTP_USER` / `AUTH_SMTP_PASS` / `AUTH_SMTP_FROM` / `AUTH_SMTP_TLS` | No | App-level SMTP used for transactional emails (verification, password reset). If unset, the app falls back to the user's own SMTP settings, or shows the verification link directly in the UI. |

Note that campaign email itself is always sent through each **user's own SMTP server**, configured in Settings inside the app — the `AUTH_SMTP_*` variables are only for account emails.

## How it works

1. **Register and verify** — new accounts must verify their email (link expires in 24 h). Passwords must include an uppercase letter, a number, and a special character.
2. **Subscribe** — most app features sit behind an active subscription (`subscription_required`). With Stripe unconfigured, plans can't change, so for local development you may want to flip a user's `plan` column to `pro` directly in the database.
3. **Configure SMTP** — each user enters their SMTP host, port, credentials, and From address in Settings. The password is Fernet-encrypted before storage.
4. **Build a campaign** — paste addresses, upload a file, or extract from a URL; write the copy or generate it with AI; optionally attach files (32 MB request limit).
5. **Send or schedule** — send immediately and watch per-recipient results stream in, or schedule the campaign for later with a recurrence. A background job checks for due schedules every minute.

## Project structure

```
app.py           # All routes, config, SMTP sending, Stripe, scheduler
models.py        # SQLAlchemy models: User, Campaign, CampaignRecipient, ScheduledCampaign
templates/       # Jinja2 pages (dashboard, campaign wizard, settings, auth, ...)
static/          # CSS and JS (campaign wizard logic in campaign.js)
scripts/         # post-merge deployment hook
pyproject.toml   # Dependencies (managed with uv)
.replit          # Replit run/deploy configuration
```

## License

MIT — see [LICENSE](LICENSE).
