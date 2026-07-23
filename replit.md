# LawFirmOS (LAWCOLAB)

A full-stack law firm management platform built with Python Flask, SQLAlchemy, and PostgreSQL.

## Features
- Client & case management
- Team collaboration
- Invoicing & billing
- Escrow and payment processing
- Calendar & scheduling
- Chat & support
- Admin and super-admin dashboards
- Sales & showcase pages

## Stack
- **Backend**: Python 3.11, Flask, Flask-Login, Flask-WTF
- **Database**: PostgreSQL (Replit built-in), SQLAlchemy ORM
- **Auth**: Flask-Login with session management
- **PDF generation**: WeasyPrint, ReportLab
- **Frontend**: Jinja2 templates, static CSS/JS

## How to run
The app starts automatically via the "Start application" workflow:
```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

## Environment variables
- `SESSION_SECRET` — Flask session secret key (set in Replit Secrets)
- `DATABASE_URL` — PostgreSQL connection string (auto-provided by Replit)

## Project structure
- `app.py` — Flask app factory, DB and auth initialization
- `main.py` — Entry point, imports routes
- `routes.py` — Blueprint registration
- `models.py` — Core SQLAlchemy models
- `models_payment.py`, `models_chat.py`, etc. — Additional models
- `auth.py` — Authentication blueprint
- `templates/` — Jinja2 HTML templates
- `static/` — CSS, JS, images

## User preferences
