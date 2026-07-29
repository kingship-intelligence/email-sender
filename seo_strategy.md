# SEO Strategy

## Project overview
RushMail is a SaaS bulk-email campaign tool built with Flask/Jinja2 (SSR). It is a product of Kingship Intelligence. The app renders HTML server-side — no SPA. Public marketing pages are fully crawlable.

## Rendering mode
Server-side rendered (Flask + Jinja2 templates). All public pages return full HTML to crawlers.

## In scope
- Homepage (`/`)
- Login (`/login`)
- Register (`/register`)
- Forgot/reset password pages

## Out of scope
- Authenticated dashboard and app pages (`/dashboard`, `/campaign/**`, `/settings`, `/pricing`, `/help`, `/tutorial`, `/scheduled`) — these require `@login_required` and are not indexable.

## Target audience
Teams running B2B outreach campaigns who want to send personalized bulk email through their own SMTP server, without a full agency setup.

## Primary keywords
- Bulk email campaigns
- Personalized email outreach
- SMTP email sender
- Email campaign tool

## Dismissed categories
- (None yet)
