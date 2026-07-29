"""
LawColab Research Robot — Scraper Engine
Provides keyword-based web search for:
  • Google My Business / Places listings  (GMB)
  • Legal communities on Facebook, LinkedIn, Reddit, YouTube, Telegram, WhatsApp
  • Quora questions & spaces
  • General web articles and directories
Uses DuckDuckGo HTML search + targeted site: queries so no API key is needed.
Results are returned as plain dicts ready to be stored as GrabbedResult rows.
"""
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_TIMEOUT = 12


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=_HEADERS,
                         timeout=_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r
    except Exception as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return None


def _ddg_search(query, max_results=20):
    """DuckDuckGo HTML search — returns list of {title, url, snippet}."""
    url = "https://html.duckduckgo.com/html/"
    try:
        r = requests.post(url, data={"q": query, "b": "", "kl": "us-en"},
                          headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("DDG search failed: %s", exc)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for div in soup.select(".result")[:max_results]:
        a = div.select_one(".result__a")
        snip = div.select_one(".result__snippet")
        if not a:
            continue
        href = a.get("href", "")
        # DDG wraps href — extract real URL
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            from urllib.parse import unquote
            href = unquote(m.group(1))
        results.append({
            "title":   a.get_text(strip=True),
            "url":     href,
            "snippet": snip.get_text(strip=True) if snip else "",
        })
    return results


def _guess_platform(url):
    u = url.lower()
    if "facebook.com"  in u: return "facebook"
    if "linkedin.com"  in u: return "linkedin"
    if "reddit.com"    in u: return "reddit"
    if "quora.com"     in u: return "quora"
    if "twitter.com"   in u: return "twitter"
    if "x.com"         in u: return "twitter"
    if "youtube.com"   in u: return "youtube"
    if "telegram.me"   in u or "t.me" in u: return "telegram"
    if "whatsapp.com"  in u: return "whatsapp"
    if "meetup.com"    in u: return "meetup"
    return "web"


def _extract_member_count(text):
    """Try to extract a member/follower number from snippet text."""
    patterns = [
        r"(\d[\d,\.]+)\s*(?:members|followers|subscribers|users|people)",
        r"(\d[\d,\.]+)\s*(?:K|M)\s*(?:members|followers)",
        r"(\d+(?:\.\d+)?)\s*[Mm]illion\s*(?:members|followers|users)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "").replace(".", "")
            try:
                n = int(raw)
                if "million" in text.lower():
                    n *= 1_000_000
                elif "M" in m.group(0):
                    n *= 1_000_000
                elif "K" in m.group(0):
                    n *= 1_000
                return n, m.group(0).strip()
            except ValueError:
                pass
    return None, None


# ── public search functions ───────────────────────────────────────────────────

def search_communities(keyword, platform="all", country="Global", max_results=25):
    """
    Search for online communities/groups related to `keyword`.
    Returns list of result dicts ready for GrabbedResult.
    """
    results = []

    # Build platform-specific site: queries
    platform_queries = {
        "facebook":  [f'site:facebook.com/groups "{keyword}" law OR legal'],
        "linkedin":  [f'site:linkedin.com/groups "{keyword}" law OR legal'],
        "reddit":    [f'site:reddit.com/r "{keyword}" law OR legal'],
        "quora":     [f'site:quora.com "{keyword}" law OR legal'],
        "youtube":   [f'site:youtube.com "{keyword}" law legal community'],
        "telegram":  [f'site:t.me "{keyword}" law legal'],
        "all": [
            f'site:facebook.com/groups "{keyword}" law OR legal community',
            f'site:linkedin.com/groups "{keyword}" law OR legal',
            f'site:reddit.com/r "{keyword}" legal OR law',
            f'site:quora.com "{keyword}" legal question',
            f'"{keyword}" legal community group forum site:meetup.com OR site:discord.com',
        ],
    }

    queries = platform_queries.get(platform, platform_queries["all"])
    if country and country not in ("Global", "All", ""):
        queries = [f'{q} "{country}"' for q in queries]

    seen_urls = set()
    for q in queries:
        for item in _ddg_search(q, max_results=12):
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            mc, mc_text = _extract_member_count(item["snippet"])
            plat = _guess_platform(item["url"])

            # Determine category from keyword
            cat = _categorise(keyword)

            results.append({
                "result_type":       "community",
                "platform":          plat,
                "name":              item["title"],
                "url":               item["url"],
                "join_link":         item["url"],
                "description":       item["snippet"],
                "snippet":           item["snippet"],
                "member_count":      mc,
                "member_count_text": mc_text or "",
                "category":          cat,
                "country_focus":     country,
            })
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
        time.sleep(0.4)

    return results


def search_gmb_listings(keyword, location="", max_results=25):
    """
    Find Google My Business / law firm listings for `keyword` in `location`.
    Uses Google Maps search via DuckDuckGo and Google Maps HTML.
    Returns result dicts ready for GrabbedResult (listing type).
    """
    results = []
    q_parts = [keyword, "law firm", location] if location else [keyword, "law firm"]
    query = " ".join(p for p in q_parts if p)

    gmaps_query = f'site:maps.google.com OR site:google.com/maps "{keyword}" {location}'
    google_query = f'"{keyword}" law firm {location} phone address'

    seen = set()

    # 1) DuckDuckGo — general web results give phone/address snippets
    for item in _ddg_search(google_query, max_results=30):
        if item["url"] in seen:
            continue
        seen.add(item["url"])

        phone = _extract_phone(item["snippet"] + " " + item["title"])
        addr  = _extract_address(item["snippet"])

        results.append({
            "result_type": "listing",
            "platform":    "google_gmb",
            "name":        item["title"],
            "url":         item["url"],
            "description": item["snippet"],
            "snippet":     item["snippet"],
            "phone":       phone,
            "address":     addr,
            "website":     item["url"] if "maps.google" not in item["url"] else "",
            "city":        location,
        })
        if len(results) >= max_results:
            break

    # 2) Try fetching Google Maps search page for richer data
    gmaps_url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    r = _get(gmaps_url)
    if r:
        # Google Maps is JS-heavy but the initial HTML sometimes has metadata
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup.find_all("div", attrs={"aria-label": True}):
            label = tag["aria-label"]
            if any(w in label.lower() for w in ("law", "legal", "attorney", "solicitor")):
                if label not in seen:
                    seen.add(label)
                    results.append({
                        "result_type": "listing",
                        "platform":    "google_gmb",
                        "name":        label,
                        "url":         gmaps_url,
                        "description": label,
                        "snippet":     label,
                        "city":        location,
                    })

    return results[:max_results]


def search_quora(keyword, max_results=20):
    """Find Quora questions/spaces related to keyword."""
    results = []
    queries = [
        f'site:quora.com "{keyword}" law legal',
        f'site:quora.com/topic "{keyword}" lawyer attorney',
    ]
    seen = set()
    for q in queries:
        for item in _ddg_search(q, max_results=15):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            results.append({
                "result_type": "community",
                "platform":    "quora",
                "name":        item["title"],
                "url":         item["url"],
                "join_link":   item["url"],
                "description": item["snippet"],
                "snippet":     item["snippet"],
                "category":    _categorise(keyword),
                "country_focus": "Global",
            })
            if len(results) >= max_results:
                break
        time.sleep(0.3)
    return results


def search_web(keyword, max_results=20):
    """General web search — find articles, directories, forums."""
    results = []
    queries = [
        f'"{keyword}" law legal community forum directory',
        f'"{keyword}" lawyer attorney association network',
    ]
    seen = set()
    for q in queries:
        for item in _ddg_search(q, max_results=15):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            plat = _guess_platform(item["url"])
            results.append({
                "result_type": "community",
                "platform":    plat,
                "name":        item["title"],
                "url":         item["url"],
                "join_link":   item["url"],
                "description": item["snippet"],
                "snippet":     item["snippet"],
                "category":    _categorise(keyword),
                "country_focus": "Global",
            })
            if len(results) >= max_results:
                break
        time.sleep(0.3)
    return results


# ── utilities ─────────────────────────────────────────────────────────────────

_LEGAL_CATEGORIES = {
    "corporate":       ["corporate", "business", "company", "commercial"],
    "criminal":        ["criminal", "crime", "prosecution", "defense"],
    "family":          ["family", "divorce", "custody", "marriage"],
    "property":        ["property", "real estate", "land", "conveyancing"],
    "immigration":     ["immigration", "visa", "citizenship", "asylum"],
    "employment":      ["employment", "labour", "labor", "workplace", "hr"],
    "intellectual":    ["intellectual", "patent", "trademark", "copyright"],
    "court":           ["court", "litigation", "lawsuit", "case"],
    "tax":             ["tax", "revenue", "irs", "hmrc"],
    "startup":         ["startup", "entrepreneur", "fintech", "venture"],
    "human_rights":    ["human rights", "civil rights", "constitutional"],
}

def _categorise(keyword):
    kl = keyword.lower()
    for cat, words in _LEGAL_CATEGORIES.items():
        if any(w in kl for w in words):
            return cat.replace("_", " ").title()
    return "Legal General"


_PHONE_RE = re.compile(
    r'(\+?\d[\d\s\-\(\)\.]{7,}\d)',
)
def _extract_phone(text):
    m = _PHONE_RE.search(text)
    return m.group(1).strip() if m else ""


_ADDRESS_PATTERNS = [
    r'\d+\s+[A-Za-z]+(?:\s+[A-Za-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl)',
]
def _extract_address(text):
    for pat in _ADDRESS_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return ""
