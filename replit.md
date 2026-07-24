# LawFirmOS (LawColab)

A full-stack law firm practice management platform built with Flask, SQLAlchemy, and PostgreSQL.

## Stack
- **Backend**: Python / Flask
- **Database**: PostgreSQL (Replit built-in, via SQLAlchemy)
- **Frontend**: Jinja2 templates, Bootstrap 5, vanilla JS
- **Auth**: Email/password with Flask-Login; Replit OAuth optional
- **Run**: `gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app`

## Features
- Multi-tenant: each law firm is isolated by `law_firm_id`
- Role system: Super Admin → Admin → Team Member → Client
- **Calendar** with court-specific fields (jurisdiction, court type, address, judge)
- Court hearing history log per case event (previous dates + court notes)
- Export court dates to Excel (`.xlsx`) and any event to iCal (`.ics`)
- Case / project management
- Invoice & billing with line items
- Team chat and direct messaging

## Running the app
The workflow `Start application` starts the server on port 5000.  
All tables are created/migrated automatically on startup via `app.py`.

## Environment variables required
| Variable | Purpose |
|---|---|
| `SESSION_SECRET` | Flask session signing key (set in Replit Secrets) |
| `DATABASE_URL` | PostgreSQL connection string (auto-provided by Replit DB) |

## User preferences
- Keep existing project structure and stack; do not migrate to other frameworks.
- Nigerian states pre-loaded in court jurisdiction selector.
