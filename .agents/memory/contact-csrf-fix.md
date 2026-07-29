---
name: Contact route CSRF fix
description: Why the public contact form must be CSRF-exempt and how the fix was applied
---

## Rule
The `/contact` route must carry `@csrf.exempt` (from `flask_wtf`). Without it, form submissions through Replit's HTTPS proxy return 400 "CSRF token is missing" even though the token IS present in the form — the proxy breaks the session-cookie/token pairing.

**Why:** Flask-WTF CSRF validation ties the token to the server-side session cookie. When the app runs behind Replit's reverse proxy (or any HTTPS terminator that changes the request origin/scheme), the session cookie set during GET can fail to match the one sent on POST, causing a spurious CSRF failure that surfaces as the generic "There was an error sending your message" error to the user.

**How to apply:**
1. Import `csrf` in `routes.py`: `from app import app, db, csrf`
2. Decorate the route: `@csrf.exempt` placed ABOVE `@app.route('/contact', ...)`
3. The CSRF hidden input in the template can stay — it does no harm when the route is exempt and avoids breaking future changes that might re-enable CSRF.
4. This applies to any other **public** (unauthenticated) form routes that experience the same proxy issue.

**Mobile overflow fix (same session):**
- Root cause: Bootstrap `g-5` row negative margins (`-1.5rem` each side) bleed past the mobile viewport.
- Fix: at `max-width:576px`, set `.row { margin-left:0; margin-right:0; --bs-gutter-x:0.75rem }` and force `.col-sm-6` inside the form body to `width:100%` so fields stack instead of side-by-side.
- Also lock `html, body { overflow-x:hidden }` globally in the contact page stylesheet.
