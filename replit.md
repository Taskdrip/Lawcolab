# LawColab / LawFirmOS

## Project Overview
**LawColab** is a full-stack Python/Flask web application — a complete Legal Operating System (OS) for law firms. It includes client management, case tracking, billing, calendaring, a public law firm directory, a CRM pipeline, social community discovery, email outreach, a Research Robot browser, and analytics.

**Stack:** Python 3.11 · Flask · SQLAlchemy · SQLite (dev) / PostgreSQL (prod) · Gunicorn · Bootstrap 5 · Chart.js

## How to Run
The app is started with:
```
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```
Entry point: `main.py` → `app.py` (Flask factory) → `routes.py` (blueprint registration)

## Key Modules
| Area | Blueprint/File | URL Prefix |
|---|---|---|
| Public site | `blueprints/public.py` | `/` |
| Auth | `auth.py` | `/auth` |
| Super Admin | `blueprints/superadmin.py` | `/superadmin` |
| CRM Pipeline | `blueprints/crm.py` | `/superadmin/crm` |
| Social Communities | `blueprints/social_communities.py` | `/superadmin/crm/communities` |
| **Research Robot** | `blueprints/research_robot.py` | `/superadmin/research-robot` |
| Email CRM | `blueprints/email_crm.py` | `/superadmin/crm/email` |
| Directory | `blueprints/directory.py` | `/directory` |
| Directory Admin | `blueprints/directory_admin.py` | `/superadmin/directory` |
| Showcase | `blueprints/showcase.py` | `/showcase` |
| Calendar | `blueprints/calendar.py` | `/calendar` |
| Invoices | `blueprints/invoices/routes.py` | `/invoices` |
| Payments | `blueprints/payment_management.py` | (mounted directly) |

## Database
- **Dev:** SQLite (`lawcolab_dev.db`)
- **Prod:** PostgreSQL via `DATABASE_URL` env var
- **Migrations:** `utils/migrations.py` — runs on every startup, idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern

## Models
- `models.py` — core models (User, LawFirm, DirectoryLawFirm, SocialCommunity, etc.)
- `models_chat.py` — chat/support models
- `models_payment.py` + `models_payment_custom.py` — payment models
- `models_audit.py` — audit logs
- `models_grabber.py` — Research Robot models (ResearchSession, GrabbedResult, SocialEngagement)

## Research Robot (New Feature)
CRM Grabber Browser at `/superadmin/research-robot/`:
- **Search & Scan** — keyword-based web scraping across Facebook, LinkedIn, Reddit, Quora, YouTube, Telegram, Google GMB
- **Scraper engine** — `utils/scraper_engine.py` — uses DuckDuckGo HTML search + BeautifulSoup
- **One-click grab** — push scraped results directly to DirectoryLawFirm CRM or SocialCommunity tables
- **Session history** — every scan is logged with results count and conversion rate
- **Social Engagement Tracker** — log comments/posts made on external platforms, track likes/shares/views
- **Web Browser** — in-app browser for visiting and extracting data from community pages

## Environment Secrets
| Secret | Purpose |
|---|---|
| `SESSION_SECRET` | Flask session encryption (required) |
| `DATABASE_URL` | PostgreSQL connection string (optional, falls back to SQLite) |
| `SUPER_ADMIN_EMAIL` | Auto-created super admin email |
| `SUPER_ADMIN_PASSWORD` | Auto-created super admin password |
| `GA4_MEASUREMENT_ID` | Google Analytics 4 |
| `GSC_VERIFICATION` | Google Search Console meta tag |

## User Preferences
- Maintain the existing project structure — do not restructure or rename modules without asking
- New database columns must always go through `utils/migrations.py` (ADD COLUMN IF NOT EXISTS pattern)
- All new pages should use the matching base template (crm/base_crm.html for CRM area, research_robot/base.html for robot area, etc.)
- Super admin routes use `@require_super_admin` decorator from `utils/decorators.py`
