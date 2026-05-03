import re, time, random, logging
import requests
from bs4 import BeautifulSoup
from config import MAX_RESULTS_PER_QUERY, REQUEST_DELAY, MAX_RETRIES, REGIONS, USER_AGENTS

logger = logging.getLogger(__name__)

EMAIL_RE   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE   = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")
WEBSITE_RE = re.compile(
    r"https?://(?!(?:www\.)?(?:google|facebook|instagram|twitter|youtube|linkedin"
    r"|yelp|tripadvisor|justdial|indiamart|sulekha|booking|trustpilot)\.)[\w.\-/]+", re.I
)
ADDR_RE = re.compile(
    r"[^.]*\d[^.]*(?:road|street|nagar|colony|lane|avenue|sector|block|floor|building"
    r"|close|drive|place|square|way|court|crescent|grove|park|gardens)[^.]*", re.I
)


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
            # Basic CAPTCHA detection
            if "captcha" in r.text.lower() or "unusual traffic" in r.text.lower():
                logger.warning("CAPTCHA detected — waiting 30s")
                time.sleep(30)
                continue
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

    title_tag = result_div.find("h3")
    if title_tag:
        lead["name"] = title_tag.get_text(strip=True)

    a_tag = result_div.find("a", href=True)
    if a_tag:
        href = a_tag["href"]
        if href.startswith("/url?q="):
            href = href.split("/url?q=")[1].split("&")[0]
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


def _fetch_page_leads(query, region_key, start=0):
    params = {"q": query, "start": start, "num": 10, "hl": "en"}
    resp = _get("https://www.google.com/search", params=params)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = soup.select("div.tF2Cxc, div.g, div.MjjYud > div")
    leads = []
    for r in results:
        lead = _parse_result(r, region_key)
        if lead["name"]:
            leads.append(lead)
    return leads


def _build_search_plan():
    """Build ordered list of (region_key, location, query) weighted by region weight."""
    plan = []
    for region_key, region_data in REGIONS.items():
        weight = region_data["weight"]
        for location in region_data["locations"]:
            for query in region_data["queries"]:
                for _ in range(weight):
                    plan.append((region_key, location, query))
    random.shuffle(plan)
    # Deduplicate while preserving weighted order
    seen = set()
    deduped = []
    for item in plan:
        key = (item[0], item[1], item[2])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def scrape_leads(stop_event):
    plan = _build_search_plan()
    for region_key, location, base_query in plan:
        if stop_event.is_set():
            return
        query = f"{base_query} {location}"
        logger.info(f"[{region_key.upper()}] Searching: {query}")
        for page in range(0, MAX_RESULTS_PER_QUERY * 10, 10):
            if stop_event.is_set():
                return
            leads = _fetch_page_leads(query, region_key, start=page)
            if not leads:
                break
            for lead in leads:
                yield lead
            time.sleep(REQUEST_DELAY + random.uniform(1.0, 2.5))
