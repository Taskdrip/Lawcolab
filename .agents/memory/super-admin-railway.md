---
name: Super Admin on Railway
description: How super admin is created/synced and what env vars Railway needs
---

# Super Admin Railway Deployment

## Rule
`app.py` startup code (inside `with app.app_context()`) creates OR updates the super admin from two env vars:
- `SUPER_ADMIN_EMAIL`
- `SUPER_ADMIN_PASSWORD`

On every startup, if the user already exists, it checks and syncs the role to `ROLE_SUPER_ADMIN`, marks `active=True`, and **re-hashes the password if it changed**. This means changing the env var on Railway automatically propagates on next deploy.

**Why:** Previously the code only created if not exists, so a mis-set password on first deploy could never be corrected without a DB edit. Now setting the env var to a new value and redeploying fixes it.

## Required Railway env vars
1. `SESSION_SECRET` — must be a stable random string (not empty/default)
2. `DATABASE_URL` — PostgreSQL connection string
3. `SUPER_ADMIN_EMAIL` — e.g. admin@lawcolab.com  
4. `SUPER_ADMIN_PASSWORD` — the desired password

## Login URL
Super admin logs in at `/auth/superadmin-access` (NOT `/auth/login`)
