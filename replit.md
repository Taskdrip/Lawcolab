# LawCoLab — Law Firm OS

A full-stack law firm management platform built with Python/Flask and PostgreSQL.

## Stack
- **Backend**: Python 3.11, Flask, SQLAlchemy, Flask-Login, Flask-WTF, Flask-Limiter
- **Database**: PostgreSQL (Replit managed)
- **Auth**: Email/password with rate-limiting and account lockout; super-admin role
- **PDF/Docs**: WeasyPrint, ReportLab
- **Run server**: Gunicorn

## How to run
The `Start application` workflow runs:
```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```
The app auto-creates/migrates database tables on startup.

## Environment variables
| Variable | Required | Notes |
|---|---|---|
| `SESSION_SECRET` | ✅ Secret | Random 64+ char string — already set |
| `SUPER_ADMIN_EMAIL` | ✅ | Set to `admin@lawcolab.com` |
| `SUPER_ADMIN_PASSWORD` | ✅ Secret | Must be set to create the super admin account |
| `SUPER_ADMIN_FIRST_NAME` | Optional | Default: "Super" |
| `SUPER_ADMIN_LAST_NAME` | Optional | Default: "Admin" |
| `DATABASE_URL` | Auto | Managed by Replit |
| `FLASK_ENV` | ✅ | Set to `production` |

## First login
After setting `SUPER_ADMIN_PASSWORD`, restart the app and navigate to `/auth/superadmin-access`.
Log in with `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD`.

## Key entry points
- `main.py` — WSGI entry point
- `app.py` — Flask app factory, DB init, migrations
- `routes.py` — Blueprint registration
- `models.py` — Core SQLAlchemy models
- `auth.py` — Authentication blueprint

## User preferences
