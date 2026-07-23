# LAWCOLAB — Railway Deployment Guide

## Prerequisites
- GitHub account (push this repo to GitHub first)
- Railway account at [railway.app](https://railway.app)

## Step-by-Step Deployment

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Railway deployment"
git push origin main
```

### 2. Create Railway Project
1. Go to [railway.app](https://railway.app) → New Project
2. Choose **Deploy from GitHub repo**
3. Select your LAWCOLAB repository

### 3. Add PostgreSQL Database
In your Railway project:
1. Click **New** → **Database** → **Add PostgreSQL**
2. Railway automatically sets `DATABASE_URL` in your environment

### 4. Set Environment Variables
In Railway project → **Variables**, add every variable below:

| Variable | Required | Description |
|---|---|---|
| `SESSION_SECRET` | ✅ Yes | Random 64+ character secret (generate below) |
| `FLASK_ENV` | ✅ Yes | Set to `production` |
| `SUPER_ADMIN_EMAIL` | ✅ Yes | Email address for the platform super admin |
| `SUPER_ADMIN_PASSWORD` | ✅ Yes | Strong password for the super admin (16+ chars) |
| `SUPER_ADMIN_FIRST_NAME` | ⬜ Optional | Super admin first name (default: "Super") |
| `SUPER_ADMIN_LAST_NAME` | ⬜ Optional | Super admin last name (default: "Admin") |
| `DATABASE_URL` | Auto | Set automatically by Railway PostgreSQL plugin |

**Generate a secure SESSION_SECRET:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Security Notes
- `SESSION_COOKIE_SECURE` is automatically enabled when `FLASK_ENV=production`
- The super admin is created automatically on first deploy if `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD` are set
- Login endpoint is rate-limited (10 req/min per IP) and accounts lock after 10 failed attempts
- Security headers (X-Frame-Options, HSTS, CSP, etc.) are applied to every response
- The `/auth/superadmin-direct-login` bypass route has been **permanently removed**

### 6. Deploy
Railway detects `railway.toml` and `Procfile` automatically. The app deploys with:
```
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 --forwarded-allow-ips='*' --preload main:app
```

### 7. First Login
After deploy, navigate to `https://your-app.railway.app/auth/superadmin-access`  
Login with the `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD` you set above.

## Troubleshooting

### Database connection errors
- Confirm PostgreSQL plugin is added and `DATABASE_URL` is set
- Railway uses `postgres://` prefix — the app auto-converts it to `postgresql://`

### 500 errors on startup
- Check that `SESSION_SECRET` is set (non-empty)
- Check Railway logs: `railway logs`

### Super admin can't log in
- Verify `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD` are set **before first deploy**
- If already deployed without them, set the vars and redeploy — the seed runs again
  and will create the account if it doesn't exist

### Rate limit errors (429)
- Login is limited to 10 attempts per minute per IP
- Accounts lock for 30 minutes after 10 consecutive bad passwords
- Wait for the lockout period or reset `failed_login_attempts = 0` directly in the DB

## Environment Variables Quick Reference
```
SESSION_SECRET=<64-char random hex>
FLASK_ENV=production
SUPER_ADMIN_EMAIL=admin@yourdomain.com
SUPER_ADMIN_PASSWORD=<strong-password>
SUPER_ADMIN_FIRST_NAME=John
SUPER_ADMIN_LAST_NAME=Doe
```
