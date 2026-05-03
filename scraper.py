import re, time, random, logging
import requests
from bs4 import BeautifulSoup
from config import MAX_RESULTS_PER_QUERY, REQUEST_DELAY, MAX_RETRIES, REGIONS, USER_AGENTS

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")
WEBSITE_RE = re.compile(
    r"https?://(?!(?:www\.)?(?:google|facebook|instagram|twitter|youtube|linkedin"
    r"|yelp|tripadvisor|justdial|indiamart|sulekha|booking|trustpilot|duckduckgo)\.)[\w.\-/]+", re.I
)
ADDR_RE = re.compile(
    r"[^.]*\d[^.]*(?:road|street|nagar|colony|lane|avenue|sector|block|floor|building"
    r"|close|drive|place|square|way|court|crescent|grove|park|gardens)[^.]*", re.I
)
SKIP_SOURCES = [
    "justdial", "indiamart", "sulekha", "tradeindia",
    "tripadvisor", "yelp", "booking.com", "trustpilot",
    "yellowpages", "thomsonlocal", "yell.com", "duckduckgo",
]


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _get(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=15)
            r.raise_for_status()
            return r
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def _parse_result(result_div, region_key):
    lead = {
        "name": "", "phone": "", "email": "", "address": "",
        "website": "", "source": "", "region": region_key,
    }

    # DuckDuckGo result title
    title_tag = result_div.find("a", class_="result__a") or result_div.find("h2")
    if title_tag:
        lead["name"] = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        if href and not href.startswith("//duckduckgo"):
            lead["source"] = href

    full_text = result_div.get_text(" ", strip=True)

    emails = EMAIL_RE.findall(full_text)
    if emails:
        lead["email"] = emails[0].lower()

    phones = PHONE_RE.findall(full_text)
    if phones:
        lead["phone"] = re.sub(r"[\s\-()]", "", phones[0])

    websites = WEBSITE_RE.findall(full_text)
    if websites:
        lead["website"] = websites[0]

    addr_match = ADDR_RE.search(full_text)
    if addr_match:
        lead["address"] = addr_match.group(0).strip()[:150]

    return lead


def _fetch_ddg(query, region_key):
    """Fetch results from DuckDuckGo HTML search — no API, no blocks."""
    params = {"q": query, "kl": "wt-wt", "kp": "-2", "k1": "-1"}
    resp = _get("https://html.duckduckgo.com/html/", params=params)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = soup.select("div.result, div.results_links")
    leads = []
    for r in results:
        lead = _parse_result(r, region_key)
        if lead["name"] and len(lead["name"]) > 3:
            # Skip directory sites
            if not any(d in lead.get("source", "") for d in SKIP_SOURCES):
                leads.append(lead)
    return leads


def _build_plan():
    plan = []
    for region_key, region_data in REGIONS.items():
        weight = region_data["weight"]
        combos = [
            (region_key, loc, q)
            for loc in region_data["locations"]
            for q in region_data["queries"]
        ]
        plan.extend(combos * weight)
    random.shuffle(plan)
    # Deduplicate
    seen, deduped = set(), []
    for item in plan:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def scrape_leads(stop_event):
    plan = _build_plan()
    for region_key, location, base_query in plan:
        if stop_event.is_set():
            return
        query = f"{base_query} {location}"
        logger.info(f"[{region_key.upper()}] {query}")
        leads = _fetch_ddg(query, region_key)
        for lead in leads:
            if stop_event.is_set():
                return
            yield lead
        time.sleep(REQUEST_DELAY + random.uniform(1, 3))
