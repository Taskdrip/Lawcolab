# LawColab (LawFirmOS)

A full-stack law firm management platform built with Python Flask, SQLite/PostgreSQL, and Jinja2 templates.

## Stack

- **Backend**: Python 3.11 / Flask
- **Database**: PostgreSQL (Replit-managed, via `DATABASE_URL`)
- **Auth**: Flask-Login + Flask-Dance (OAuth)
- **Templates**: Jinja2 (server-side rendered)
- **PDF generation**: WeasyPrint + ReportLab
- **WSGI server**: Gunicorn

## How to run

The app starts automatically via the **Start application** workflow:

```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

Entry point: `main.py` → imports `app` from `app.py` and all routes from `routes.py`.

## Key files

- `app.py` — Flask app factory, DB config, login manager, CSRF setup
- `models.py` — Core SQLAlchemy models (User, Client, Case, Invoice, etc.)
- `models_payment.py` / `models_payment_custom.py` — Payment models
- `models_chat.py` — Chat/messaging models
- `models_audit.py` — Audit log models
- `routes.py` — Route registrations (imports blueprints)
- `templates/` — Jinja2 HTML templates
- `utils/` — Decorators, forms, notifications, trial access helpers
- `uploads/` — User-uploaded files (profiles, payment evidence)

## Environment variables / secrets

- `SESSION_SECRET` — Flask session secret key (already set)
- `DATABASE_URL` — PostgreSQL connection string (auto-provided by Replit)

## User preferences
