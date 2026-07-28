# LawCoLab — Legal Practice OS

A full-stack SaaS web application for law firms. Built with Python/Flask, PostgreSQL, and Jinja2 templates.

## Stack

- **Backend**: Python 3.11, Flask, SQLAlchemy (Flask-SQLAlchemy)
- **Database**: PostgreSQL (via `DATABASE_URL` env var; provided by Replit's database integration)
- **Auth**: Flask-Login with custom session management
- **Frontend**: Jinja2 templates, Bootstrap, vanilla JS
- **PDF generation**: WeasyPrint + ReportLab
- **Background jobs / limits**: Flask-Limiter
- **Server**: Gunicorn (port 5000)

## How to run

The app starts automatically via the **"Start application"** workflow:

```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

Entry point: `main.py` → imports `app` from `app.py` and registers all routes via `routes.py`.

## Key environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (set by Replit DB integration) |
| `SESSION_SECRET` | Yes | Flask session signing key (set as Replit secret) |
| `FLASK_ENV` | Yes | Set to `production` in `.replit` userenv |
| `SUPER_ADMIN_EMAIL` | Optional | Auto-creates super admin on first boot if set with `SUPER_ADMIN_PASSWORD` |
| `SUPER_ADMIN_PASSWORD` | Optional | See above |
| `STRIPE_SECRET_KEY` | Optional | Needed for Stripe payment flows |

## Project structure

```
app.py          — Flask app factory, DB, login manager setup
main.py         — Entry point (imports app + routes)
routes.py       — All route registrations
models.py       — Core SQLAlchemy models
models_*.py     — Additional model modules (chat, payment, audit)
auth.py         — Authentication routes/logic
utils/          — Decorators, forms, migrations, notifications, security
templates/      — Jinja2 HTML templates (organized by feature)
uploads/        — User-uploaded files (profiles, payment evidence)
```

## User preferences

- Keep the existing Flask/SQLAlchemy/Jinja2 stack — do not migrate to another framework.
- Maintain existing file structure; add new features as separate modules.
