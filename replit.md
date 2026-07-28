# LawCoLab (LawFirmOS)

A full-stack web application for law firms — client management, case tracking, billing, team collaboration, calendar, and analytics.

## Stack
- **Backend:** Python / Flask
- **Database:** SQLite (dev) / PostgreSQL (production via `DATABASE_URL`)
- **Auth:** Flask-Login with session cookies; Flask-Dance for OAuth
- **PDF generation:** WeasyPrint + ReportLab
- **Frontend:** Jinja2 templates, Bootstrap

## Running the app
```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```
The workflow "Start application" is already configured.

## Environment variables
| Variable | Required | Notes |
|---|---|---|
| `SESSION_SECRET` | Yes (prod) | Flask session signing key |
| `DATABASE_URL` | No | PostgreSQL URL; defaults to SQLite if unset |
| `SUPER_ADMIN_EMAIL` | No | Auto-creates super admin on first deploy |
| `SUPER_ADMIN_PASSWORD` | No | Paired with `SUPER_ADMIN_EMAIL` |

## Key entry points
- `main.py` — WSGI entry; imports `app` and all routes
- `app.py` — Flask app factory, DB setup, migrations
- `routes/` — route blueprints
- `models/` — SQLAlchemy models
- `templates/` — Jinja2 HTML templates
- `utils/` — decorators, forms, migrations helpers

## User preferences
<!-- Add user preferences here -->
