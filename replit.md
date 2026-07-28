# LawFirmOS — LAWCOLAB Platform

## Project Overview
LawFirmOS is a full-stack Python/Flask web application for law firm management. It provides multi-tenant law firm operations (case management, billing, client portals, team collaboration, calendar, invoicing) plus a public **Law Firm Directory & Showcase** system — a Google My Business-style listing hub for Nigerian and global law firms.

## Stack
- **Backend**: Python 3 / Flask + SQLAlchemy (PostgreSQL)
- **Auth**: Flask-Login with role-based access (super_admin, admin, lawyer, client)
- **Frontend**: Jinja2 templates + Bootstrap 5 + vanilla JS
- **PDF generation**: WeasyPrint / ReportLab
- **Deployment**: Gunicorn on Railway (production) / Replit (development)

## How to Run
The app starts via the `Start application` workflow:
```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

## Key Feature Areas
- `/` — Marketing homepage with featured firm showcases
- `/directory` — Public law firm directory with smart filters (state, practice area, verified)
- `/directory/firm/<id>` — Full firm profile with reviews (Google My Business style)
- `/showcase-profile` — Firm admin self-service profile editor (logo, hero, practice areas, locations, team, social media)
- `/showcase-profile/edit` — Edit & submit firm profile for super admin approval
- `/superadmin/directory` — Super admin CRM (HubSpot-style): approve submissions, manage external firms, notes
- `/superadmin/directory/robot` — Google Maps discovery robot (seeds Nigerian law firm data)
- `/showcase` — Showcase admin routes (review/message moderation, verification)
- `/auth` — Login / signup
- `/dashboard` — Firm admin dashboard
- `/admin` — Firm admin management panel
- `/superadmin` — Platform super admin panel

## Architecture
- **`app.py`** — Flask app factory, DB init, migrations run at startup
- **`models.py`** — All SQLAlchemy models
- **`routes.py`** — Blueprint registration + top-level routes
- **`utils/migrations.py`** — Idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migrations
- **`blueprints/`** — Feature blueprints (showcase, directory, directory_admin, showcase_profile, etc.)
- **`templates/`** — Jinja2 HTML templates mirroring blueprint structure
- **`static/uploads/showcase/`** — User-uploaded firm logos and hero images

## Environment Variables / Secrets
- `SESSION_SECRET` — Flask session secret key (required)
- `DATABASE_URL` — PostgreSQL connection string (required in production)
- `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` — Auto-creates super admin on first deploy

## User Preferences
- Keep existing project structure and stack — do not migrate or restructure
- Migrations are idempotent (`IF NOT EXISTS`) — always add new columns via `utils/migrations.py`
- Templates use Bootstrap 5 with LAWCOLAB brand colors (`#0d1b4b` navy, `#FFD700` gold)
