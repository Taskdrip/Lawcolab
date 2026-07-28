---
name: Social Communities & Enhanced Robot Feature
description: Documents the social communities CRM + enhanced directory robot + per-firm AI pitch generation added to the platform.
---

# Social Communities CRM + Enhanced Directory Robot

## What was built

### 1. Social Media Legal Communities CRM
- **Model**: `SocialCommunity` in `models.py` — stores platform, community_name, url, join_link, member_count, description, join_instructions, category, country_focus, outreach_status, ai_outreach_messages_json
- **Blueprint**: `blueprints/social_communities.py` — mounted at `/superadmin/crm/communities`
- **Templates**: `templates/social_communities/index.html` (list + robot) and `templates/social_communities/detail.html` (detail + generate messages)
- **Seed data**: 20 pre-loaded communities across Facebook, LinkedIn, Reddit, WhatsApp, Telegram, YouTube
- **Robot route**: `POST /superadmin/crm/communities/robot/run`
- **AI generation**: `POST /superadmin/crm/communities/<id>/generate-message?channel=post|comment|dm|email`

### 2. Enhanced Directory Robot
- **New fields on DirectoryLawFirm**: `gmb_verified`, `ai_pitch_email`, `ai_call_script`, `ai_pitch_generated_at`
- **New route**: `POST /superadmin/directory/external/<id>/generate-pitch` — generates AI email pitch + call script per firm
- **Fallback template**: `_build_template_pitch()` in `blueprints/directory_admin.py` — works without OpenAI key
- **Social links edit**: `POST /superadmin/directory/external/<id>/update-social` — save Facebook/LinkedIn/Twitter/Instagram/YouTube/TikTok links

### 3. Updated CRM profile page
- `templates/directory_admin/external_detail.html` — now shows GMB verified status, social media links (editable), AI pitch email section, call script section with copy buttons, pipeline stage selector

### 4. Updated robot dashboard
- `templates/directory_admin/robot.html` — now shows both GMB robot and Social Communities robot side-by-side; passes `community_count` and `community_seed` vars from `robot_dashboard()` route

## Blueprint registration
- `crm_bp` at `/superadmin/crm` — added in `routes.py`
- `social_communities_bp` at `/superadmin/crm/communities` — added in `routes.py`

## Migrations added (utils/migrations.py)
- `gmb_verified BOOLEAN DEFAULT FALSE` on `directory_law_firms`
- `ai_pitch_email TEXT` on `directory_law_firms`
- `ai_call_script TEXT` on `directory_law_firms`
- `ai_pitch_generated_at TIMESTAMP` on `directory_law_firms`
- Full `social_communities` table CREATE IF NOT EXISTS
- Indexes: `idx_sc_platform`, `idx_sc_outreach_status`

**Why:** f-strings with backslashes cause SyntaxError in Python 3.11 — use unicode escapes (`\u2014`) or pre-compute variables outside the f-string.
