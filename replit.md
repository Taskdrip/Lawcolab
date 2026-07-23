# LawColab / LawFirmOS

A full-stack law firm management platform built with Python Flask + PostgreSQL.

## Features
- Multi-tenant law firm management (clients, cases, invoices, team)
- Role-based access: Super Admin, Admin, Team Member, Client
- Real-time team chat and support chat
- Escrow and payment management
- Billing / invoice generation (PDF via WeasyPrint)
- Trial subscription system (3-day free trial on signup)
- Dashboard with sliders and legal news (managed by Super Admin)

## Stack
- **Backend**: Python 3.11, Flask 3.x
- **Database**: PostgreSQL (via Flask-SQLAlchemy)
- **Auth**: Flask-Login + email/password
- **Security**: Flask-Limiter (rate limiting), brute-force lockout, security headers
- **PDF**: WeasyPrint / ReportLab
- **Frontend**: Jinja2 templates, Bootstrap 5, vanilla JS

## Running on Replit

The app is configured to run via gunicorn on port 5000.

### Required secrets (set in Replit Secrets panel)
| Secret | Purpose |
|---|---|
| `SESSION_SECRET` | Flask session signing key |
| `SUPER_ADMIN_EMAIL` | Email for the platform super admin |
| `SUPER_ADMIN_PASSWORD` | Password for the platform super admin |

### Optional secrets
| Secret | Default |
|---|---|
| `SUPER_ADMIN_FIRST_NAME` | "Super" |
| `SUPER_ADMIN_LAST_NAME` | "Admin" |

### First-time setup
1. Set the secrets above in the Replit Secrets panel
2. Click **Run** — the app creates all DB tables and seeds the super admin automatically
3. Visit `/auth/superadmin-access` to log in as super admin

## Deploying to Railway
See [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) for the full Railway deployment guide.

## Security Architecture
- **Rate limiting**: 10 login attempts/min per IP (Flask-Limiter, in-memory)
- **Brute-force lockout**: DB-backed — accounts lock for 30 min after 10 failed logins
- **Security headers**: X-Frame-Options, HSTS, X-Content-Type-Options, CSP, Referrer-Policy
- **Secure cookies**: HttpOnly=True, SameSite=Lax, Secure=True in production
- **CSRF**: Flask-WTF CSRF protection enabled globally
- **ProxyFix**: Correctly handles Railway's TLS-terminating reverse proxy

## User Preferences
- Keep existing project structure — do not restructure blueprints or rename routes
- Use proper `logging` (not `print`) for all server-side output
