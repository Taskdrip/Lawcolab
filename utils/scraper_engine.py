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
import random
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse, unquote

logger = logging.getLogger(__name__)

# Rotate User-Agents to reduce bot detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def _get_headers():
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

_TIMEOUT = 15

# ── helpers ───────────────────────────────────────────────────────────────────

def _get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=_get_headers(),
                         timeout=_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r
    except Exception as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return None


def _ddg_search(query, max_results=20):
    """DuckDuckGo HTML search — returns list of {title, url, snippet}.
    Falls back to Bing if DDG blocks.
    """
    results = _ddg_search_direct(query, max_results)
    if not results:
        results = _bing_search_fallback(query, max_results)
    return results


def _ddg_search_direct(query, max_results=20):
    """DuckDuckGo HTML search."""
    url = "https://html.duckduckgo.com/html/"
    try:
        r = requests.post(
            url,
            data={"q": query, "b": "", "kl": "us-en"},
            headers=_get_headers(),
            timeout=_TIMEOUT,
        )
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
            href = unquote(m.group(1))
        if not href.startswith("http"):
            continue
        results.append({
            "title":   a.get_text(strip=True),
            "url":     href,
            "snippet": snip.get_text(strip=True) if snip else "",
        })
    return results


def _bing_search_fallback(query, max_results=20):
    """Bing HTML search as fallback when DDG blocks."""
    url = "https://www.bing.com/search"
    try:
        r = requests.get(
            url,
            params={"q": query, "count": max_results},
            headers=_get_headers(),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
    except Exception as exc:
        logger.warning("Bing search fallback failed: %s", exc)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for li in soup.select("li.b_algo")[:max_results]:
        a = li.select_one("h2 a")
        snip_el = li.select_one(".b_caption p") or li.select_one("p")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            continue
        snippet = snip_el.get_text(strip=True) if snip_el else ""
        results.append({
            "title":   a.get_text(strip=True),
            "url":     href,
            "snippet": snippet,
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
        "facebook":  [
            f'site:facebook.com/groups "{keyword}" law OR legal',
            f'facebook group "{keyword}" legal lawyers',
        ],
        "linkedin":  [
            f'site:linkedin.com/groups "{keyword}" law OR legal',
            f'linkedin group "{keyword}" legal professionals',
        ],
        "reddit":    [
            f'site:reddit.com/r "{keyword}" law OR legal',
            f'reddit subreddit "{keyword}" legal',
        ],
        "quora":     [
            f'site:quora.com "{keyword}" law OR legal',
            f'quora "{keyword}" legal question',
        ],
        "youtube":   [
            f'site:youtube.com "{keyword}" law legal community',
            f'youtube channel "{keyword}" legal',
        ],
        "telegram":  [
            f'site:t.me "{keyword}" law legal',
            f'telegram group "{keyword}" lawyers',
        ],
        "all": [
            f'"{keyword}" law firm legal directory',
            f'"{keyword}" lawyers attorneys contact phone',
            f'site:facebook.com/groups "{keyword}" law OR legal community',
            f'site:linkedin.com/groups "{keyword}" law OR legal',
            f'site:reddit.com/r "{keyword}" legal OR law',
            f'"{keyword}" legal community group forum',
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
        time.sleep(random.uniform(0.3, 0.7))

    return results


def search_gmb_listings(keyword, location="", max_results=25):
    """
    Find Google My Business / law firm listings for `keyword` in `location`.
    Uses DuckDuckGo targeted queries.
    Returns result dicts ready for GrabbedResult (listing type).
    """
    results = []
    q_parts = [keyword, "law firm", location] if location else [keyword, "law firm"]
    query = " ".join(p for p in q_parts if p)

    # Multiple search strategies for better coverage
    search_queries = [
        f'"{keyword}" law firm {location} phone address contact',
        f'"{keyword}" {location} attorney solicitor website email',
        f'"{keyword}" law office {location} site:yellowpages.com OR site:yelp.com',
        f'"{query}" contact details',
    ]

    seen = set()

    for sq in search_queries:
        for item in _ddg_search(sq, max_results=15):
            if item["url"] in seen:
                continue
            seen.add(item["url"])

            phone = _extract_phone(item["snippet"] + " " + item["title"])
            addr  = _extract_address(item["snippet"])
            email = _extract_email(item["snippet"])

            results.append({
                "result_type": "listing",
                "platform":    "google_gmb",
                "name":        item["title"],
                "url":         item["url"],
                "description": item["snippet"],
                "snippet":     item["snippet"],
                "phone":       phone,
                "email":       email,
                "address":     addr,
                "website":     item["url"],
                "city":        location,
            })
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
        time.sleep(random.uniform(0.3, 0.6))

    return results[:max_results]


def search_quora(keyword, max_results=20):
    """Find Quora questions/spaces related to keyword."""
    results = []
    queries = [
        f'site:quora.com "{keyword}" law legal',
        f'site:quora.com/topic "{keyword}" lawyer attorney',
        f'quora "{keyword}" legal advice',
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
        f'"{keyword}" legal professionals group online',
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


_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

def _extract_email(text):
    """Extract first email address found in text."""
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


def _guess_platform_from_content(text, title=""):
    """Detect social platform from page body text."""
    t = (text + " " + title).lower()
    if "facebook.com" in t or "fb group" in t:  return "facebook"
    if "linkedin.com" in t:                      return "linkedin"
    if "reddit.com"   in t or "subreddit" in t:  return "reddit"
    if "quora.com"    in t or "quora"    in t:   return "quora"
    if "twitter.com"  in t or "tweet"    in t:   return "twitter"
    if "youtube.com"  in t:                      return "youtube"
    if "telegram"     in t or "t.me"     in t:   return "telegram"
    if "whatsapp"     in t:                       return "whatsapp"
    if "google maps"  in t or "place_id" in t:   return "google_gmb"
    return "web"


def extract_page_contacts(html_text):
    """
    Parse raw HTML and extract structured contact + metadata.
    Returns: title, description, phones, emails, address, member_count,
             member_count_text, links, platform, text_preview.
    """
    soup = BeautifulSoup(html_text[:300000], "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    # Title
    title = ""
    if soup.find("title"):
        title = soup.find("title").get_text(strip=True)[:300]
    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)[:300]

    # Description — meta or first long paragraph
    desc = ""
    meta = soup.find("meta", attrs={"name": "description"}) or \
           soup.find("meta", attrs={"property": "og:description"})
    if meta:
        desc = (meta.get("content") or "")[:500]
    if not desc:
        for p in soup.find_all(["p", "div"]):
            t = p.get_text(strip=True)
            if len(t) > 80:
                desc = t[:500]
                break

    # OG image
    og_img = ""
    og = soup.find("meta", attrs={"property": "og:image"})
    if og:
        og_img = og.get("content", "")[:500]

    # Phones
    phones = list(dict.fromkeys(
        m.strip() for m in _PHONE_RE.findall(text)
        if len(m.strip()) >= 7
    ))[:5]

    # Emails
    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))[:5]

    # Address
    address = _extract_address(text)

    # Member count
    mc, mc_text = _extract_member_count(text)

    # External links (first 12 meaningful ones)
    links = []
    seen_l = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and href not in seen_l:
            label = a.get_text(strip=True)[:80]
            if label and len(label) > 2:
                links.append({"url": href, "label": label})
                seen_l.add(href)
        if len(links) >= 12:
            break

    platform = _guess_platform_from_content(text, title)

    return {
        "title":             title,
        "description":       desc,
        "phones":            phones,
        "emails":            emails,
        "address":           address,
        "member_count":      mc,
        "member_count_text": mc_text or "",
        "links":             links,
        "platform":          platform,
        "og_image":          og_img,
        "text_preview":      text[:1200],
    }


def search_twitter_x(keyword, max_results=20):
    """Search Twitter / X for legal discussions around keyword."""
    results = []
    queries = [
        f'site:twitter.com "{keyword}" law OR legal',
        f'site:x.com "{keyword}" lawyer attorney',
        f'twitter "{keyword}" legal discussion',
    ]
    seen = set()
    for q in queries:
        for item in _ddg_search(q, max_results=12):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            results.append({
                "result_type": "community",
                "platform":    "twitter",
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


def search_ask_the_public(keyword, max_results=20):
    """
    Surface 'people also ask' style questions and public discussions.
    Targets Reddit legal advice, Quora Q&A, general forums.
    """
    results = []
    queries = [
        f'"{keyword}" law "how do I" OR "what is" OR "can I" OR "is it legal"',
        f'site:reddit.com/r/legaladvice "{keyword}"',
        f'site:reddit.com/r/law "{keyword}"',
        f'site:quora.com/q "{keyword}" legal',
        f'"{keyword}" legal question discussion forum answers',
    ]
    seen = set()
    for q in queries:
        for item in _ddg_search(q, max_results=8):
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
        if len(results) >= max_results:
            break
        time.sleep(0.3)
    return results


def search_reddit_threads(keyword, max_results=20):
    """Find Reddit posts and threads on legal topics."""
    results = []
    queries = [
        f'site:reddit.com "{keyword}" law legal',
        f'site:reddit.com/r/legaladvice "{keyword}"',
        f'site:reddit.com/r/business "{keyword}" legal',
        f'reddit.com "{keyword}" lawyer attorney discussion',
    ]
    seen = set()
    for q in queries:
        for item in _ddg_search(q, max_results=10):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            results.append({
                "result_type": "community",
                "platform":    "reddit",
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
