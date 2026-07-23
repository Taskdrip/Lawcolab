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
In Railway project → **Variables**, add:

| Variable | Value |
|---|---|
| `SESSION_SECRET` | A random 40+ character string (e.g. generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `FLASK_ENV` | `production` |

`DATABASE_URL` is set automatically by the PostgreSQL plugin.

### 5. Deploy
Railway detects `railway.toml` and `Procfile` automatically. Your app will deploy with:
```
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 main:app
```

### 6. Create Super Admin (First Deploy Only)
After successful deployment, open the Railway shell and run:
```bash
python3 init_super_admin.py
```
This creates: `superadmin@lawcolab.com` / `superadmin123`

Or use the admin account already seeded in Replit:
- Email: `admin@lawcolab.com`
- Password: `LawColab2025!`

### 7. Verify
Visit your Railway deployment URL. The landing page should load and you should be able to log in at `/auth/login`.

## Key Files
| File | Purpose |
|---|---|
| `railway.toml` | Railway build & deploy config |
| `Procfile` | Web process command |
| `requirements.txt` | Python dependencies |
| `main.py` | App entry point |
| `wsgi.py` | WSGI entry point |

## Troubleshooting
- **Database errors**: Confirm `DATABASE_URL` is set and PostgreSQL plugin is connected
- **500 errors**: Check Railway logs; most likely a missing env variable
- **Static files not loading**: Ensure `static/` folder is committed to git (check `.gitignore`)
- **App won't start**: Verify `gunicorn` is in `requirements.txt` ✓

## Health Check
Railway pings `GET /` — the landing page must return 200. It does by default.
