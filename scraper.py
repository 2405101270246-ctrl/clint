import re, time, random, logging
import requests
from bs4 import BeautifulSoup
from config import REQUEST_DELAY, MAX_RETRIES, USER_AGENTS

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{6,}\d)")

# 90% Europe, 10% India
TARGETS = (
    [("europe", city, cat) for city in [
        "london","manchester","birmingham","berlin","munich","hamburg",
        "paris","lyon","amsterdam","rotterdam","madrid","barcelona",
        "rome","milan","warsaw","brussels","lisbon","vienna","dublin",
        "stockholm","oslo","copenhagen","helsinki","zurich","prague",
    ] for cat in [
        "salon","restaurant","plumber","electrician","cleaning-service",
        "bakery","photographer","florist","tailor","mechanic",
        "driving-school","pest-control","locksmith","painter","catering",
    ]] * 9 +
    [("india", city, cat) for city in [
        "mumbai","delhi","bangalore","hyderabad","chennai","pune",
    ] for cat in [
        "salon","restaurant","plumber","electrician","catering",
        "pest-control","photographer","tailor",
    ]]
)


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def _get(url):
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=_headers(), timeout=20)
            if r.status_code == 200:
                return r
            logger.warning(f"HTTP {r.status_code}: {url}")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}: {e}")
            time.sleep(REQUEST_DELAY)
    return None


def _parse_hotfrog(html, region_key, city, category):
    soup  = BeautifulSoup(html, "html.parser")
    leads = []

    # Hotfrog wraps each business in a div with class containing 'listing' or 'result'
    cards = (
        soup.select("div[class*='listing']") or
        soup.select("div[class*='result']") or
        soup.select("div[class*='business']") or
        soup.select("article") or
        soup.select("li[class*='business']")
    )

    logger.debug(f"Hotfrog cards found: {len(cards)} for {category} in {city}")

    for card in cards:
        text = card.get_text(" ", strip=True)
        if len(text) < 10:
            continue

        lead = {
            "name": "", "phone": "", "email": "", "address": "",
            "website": "", "source": f"https://www.hotfrog.com/search/{city}/{category}",
            "region": region_key,
        }

        # Name — try heading tags first
        for sel in ["h2 a", "h3 a", "h2", "h3", "[class*='name']", "[class*='title']"]:
            tag = card.select_one(sel)
            if tag and len(tag.get_text(strip=True)) > 2:
                lead["name"] = tag.get_text(strip=True)
                break

        if not lead["name"]:
            continue

        # Phone
        phones = PHONE_RE.findall(text)
        if phones:
            lead["phone"] = re.sub(r"[\s\-()]", "", phones[0])

        # Email
        emails = EMAIL_RE.findall(text)
        if emails:
            lead["email"] = emails[0].lower()

        # Address
        for sel in ["[class*='address']", "[itemprop='address']", "[class*='location']"]:
            tag = card.select_one(sel)
            if tag:
                lead["address"] = tag.get_text(" ", strip=True)[:150]
                break

        leads.append(lead)

    return leads


def scrape_leads(stop_event):
    plan = list(TARGETS)
    random.shuffle(plan)
    # Deduplicate
    seen, deduped = set(), []
    for item in plan:
        key = (item[0], item[1], item[2])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    for region_key, city, category in deduped:
        if stop_event.is_set():
            return

        url  = f"https://www.hotfrog.com/search/{city}/{category}"
        logger.info(f"[{region_key.upper()}] {category} in {city}")

        resp = _get(url)
        if not resp:
            time.sleep(REQUEST_DELAY)
            continue

        leads = _parse_hotfrog(resp.text, region_key, city, category)
        logger.info(f"  → {len(leads)} raw results")

        for lead in leads:
            if stop_event.is_set():
                return
            yield lead

        time.sleep(REQUEST_DELAY + random.uniform(1, 3))
