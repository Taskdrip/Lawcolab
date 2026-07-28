---
name: Global CSS Design System
description: How LAWCOLAB's global stylesheet works and the rule for dark-section text contrast
---

# Global CSS Design System

## Rule
`static/css/simple.css` is the single authoritative global stylesheet loaded by `base.html`. It was rewritten to remove the destructive "everything is black" overrides from the original file.

## Dark sections — white text contract
Any section with a dark background MUST carry one of these CSS classes so the design system forces white text on all children:
- `.lc-dark` — generic dark utility
- `.dir-hero` — directory hero section
- `.dir-stats-bar` — directory stats bar
- `.cta-banner` — call-to-action banners
- `.section-navy` — any full-width navy section

**Why:** `body { color: var(--lc-text) }` (dark) inherits everywhere. Without an explicit override, headings and paragraphs inside dark sections render black-on-dark and become unreadable.

**How to apply:** When building any new page with a dark hero/banner, add one of the above classes to the outer `<section>` element. Do NOT rely on inline `style="color:#fff"` — the design system class covers all children automatically.

## Brand colours
- Navy: `#0d1b4b` (primary dark)
- Gold: `#FFD700` (accent/CTA)
- Light background: `#f0f4f8`
- Surface (card): `#ffffff`
- Text: `#1a1a2e`
- Muted text: `#64748b`
