---
name: Showcase migrations pattern
description: Why missing migrations crashed the showcase feature on Railway and how to prevent it
---

The `law_firm_showcases` table existed on Railway from an older schema. When new columns were added to the SQLAlchemy model (tagline, phone, whatsapp, website_url, practice_areas_json, locations_json, team_json, submission_status, etc.) without corresponding `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migrations, every query against `LawFirmShowcase` caused an Internal Server Error — including the homepage which queries featured showcases.

**Why:** `db.create_all()` only creates new tables; it never adds columns to existing ones. The `utils/migrations.py` file is the only mechanism for adding columns to existing tables.

**How to apply:** Any time a new column is added to a model that already has a table in production, add a corresponding entry to the `migrations` list in `utils/migrations.py`. Use `ALTER TABLE <table> ADD COLUMN IF NOT EXISTS …` so it's idempotent.

Tables covered by migrations as of this work:
- `law_firm_showcases` — tagline, phone, whatsapp, website_url, youtube_url, founded_year, firm_size, practice_areas_json, locations_json, team_json, submission_status, submitted_at, approved_at, approved_by_id, rejection_reason, showcase_order, plus social/stats/verification columns
- `public_law_firm_reviews` — reviewer_email, reviewer_company, reviewer_location, review_title, is_featured, is_visible, ip_address, user_agent, approved_at
- `public_law_firm_messages` — sender_phone, sender_company, message_type, is_replied, priority, ip_address, user_agent, read_at, replied_at
- `directory_law_firms` — entire table created via CREATE TABLE IF NOT EXISTS (new model)
- `directory_notes` — entire table created via CREATE TABLE IF NOT EXISTS (new model)
