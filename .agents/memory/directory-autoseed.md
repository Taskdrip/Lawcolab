---
name: Directory Auto-Seed
description: How directory firms get populated automatically on first startup
---

# Directory Auto-Seed

## Rule
`app.py` startup checks if `DirectoryLawFirm.query.count() == 0` and imports all entries from `_SEED_FIRMS` in `blueprints/directory_admin.py` if so.

**Why:** Previously the directory showed "No firms found" until a super admin manually triggered the robot. Now the 131+ seed firms appear immediately after deployment.

## Seed data coverage (as of last update)
- **Nigeria**: ~100 firms across all 36 states + FCT Abuja
- **Ghana**: ~10 firms (Accra/Kumasi/Takoradi)
- **United States**: ~15 firms (New York, California, Texas, DC)

## Adding more countries
Edit `_SEED_FIRMS` list in `blueprints/directory_admin.py` and also add the country + regions to `COUNTRY_REGIONS` dict in `blueprints/directory.py`. The robot admin panel (`/superadmin/directory/robot`) can re-run to import additional firms without duplicates.
