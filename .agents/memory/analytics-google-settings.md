---
name: Analytics & Google Settings
description: Comprehensive analytics dashboard + Google Settings management built for super admin
---

# Analytics & Google Settings

## What was built
- `/superadmin/web-analytics` — fully rewritten analytics dashboard with 5 tabs:
  - **Overview**: KPI cards (count-up animation), traffic trend chart, top pages, referrers, AI robot panel
  - **Traffic**: pages bar chart, browser breakdown, OS table
  - **Geographic**: countries with flag emojis, country donut chart
  - **Audience**: device donut, browser, engagement metrics, visit summary
  - **Google Settings**: GA4, GSC, GTM, domain config form with DB persistence

## Key files
- `templates/superadmin/web_analytics.html` — complete rewrite (~700 lines)
- `blueprints/superadmin.py` — added `save_google_settings()` POST route + `_get_site_setting()` / `_set_site_setting()` helpers
- `utils/migrations.py` — added `site_settings` table (key-value store)
- `templates/base.html` — enhanced SEO: WebSite + Organization schema.org, canonical URL fix, preconnect hints, mobile meta tags
- `static/css/simple.css` — fixed card-header headings (h1-h6 + span + p) to be white

## Google Settings persistence
- Settings stored in `site_settings` table (key VARCHAR PK, value TEXT)
- Priority: env var > DB value — env vars take precedence and show as readonly
- Keys: `ga4_measurement_id`, `gsc_verification`, `gtm_id`, `site_domain`
- Route: POST `/superadmin/google-settings`

## SEO improvements
- Added 3-schema JSON-LD: SoftwareApplication + Organization + WebSite (with SearchAction)
- Canonical URL now strips query params: `{{ request.host_url.rstrip('/') }}{{ request.path }}`
- Added preconnect for fonts, CDN, dns-prefetch for GTM

**Why:** Super admin needed single place to manage all Google integrations + comprehensive analytics visibility.
