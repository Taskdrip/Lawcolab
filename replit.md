# LawFirmOS / LawColab

A full-stack law firm management SaaS platform built with Python Flask.

## Stack
- **Backend**: Flask + SQLAlchemy (PostgreSQL in production, falls back to SQLite for dev)
- **Auth**: Flask-Login, Flask-Dance (OAuth)
- **Payments**: Manual bank transfer (Zenith Bank NGN) + crypto (USDT multi-network)
- **Run server**: Gunicorn (`gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app`)

## How to run
The workflow `Start application` is configured and runs automatically.
Requires `SESSION_SECRET` environment variable (already set).
Optionally set `DATABASE_URL` for PostgreSQL (otherwise SQLite is used in dev).

## Key routes
- `/` — Landing page
- `/pricing` — Subscription plans (geo-aware NGN pricing for Nigerian visitors)
- `/sales/popup` — Sales funnel popup
- `/sales/checkout` — Stripe-style checkout (requires session from lead form)
- `/auth/login`, `/auth/signup` — Authentication
- `/dashboard` — Main app dashboard (requires login)

## Payment setup
- **Bank transfer**: Zenith Bank · Lawcolab Global · Account `1310505179` (NGN)
- **Geo-detection**: Nigerian IPs automatically shown NGN prices via `/sales/api/currency-settings`
- **August discount**: 40% off all NGN prices throughout August for Nigerian law firms (auto-applied)
- Crypto wallets and additional payment gateways configurable by super admin

## Project structure
- `app.py` — Flask app factory, DB setup, context processors
- `main.py` — Entry point
- `routes.py` — Blueprint registration
- `models.py` — Core models (User, LawFirm, Cases, PopupSettings…)
- `models_payment.py` / `models_payment_custom.py` — Payment models
- `blueprints/` — Feature blueprints (sales, auth, dashboard, admin, invoices…)
- `templates/` — Jinja2 templates

## User preferences
- Naira (NGN) bank transfer: Zenith Bank, Lawcolab Global, account 1310505179
- 40% August discount for Nigerian law firms (month == 8, currency == NGN)
- Checkout should look clean and minimal like Stripe
