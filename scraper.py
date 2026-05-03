import re, time, random, logging
import requests
from bs4 import BeautifulSoup
from config import REQUEST_DELAY, MAX_RETRIES, REGIONS, USER_AGENTS

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")

SEARCH_CATEGORIES = [
    "salon", "restaurant", "plumber", "electrician", "cleaning",
    "bakery", "driving school", "photographer", "florist", "tailor",
    "mechanic", "dentist", "tutor", "catering", "pest control",
    "landscaping", "locksmith", "painter", "event planner", "accountant",
]

EUROPE_CITIES = [
    "London", "Manchester", "Birmingham",
    "Berlin", "Munich", "Hamburg",
    "Paris", "Lyon", "Marseille",
    "Amsterdam", "Rotterdam",
    "Madrid", "Barcelona",
    "Rome", "Milan",
    "Warsaw", "Brussels",
    "Lisbon", "Vienna", "Dublin",
]

INDIA_CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Pune"]

SKIP_DOMAINS = [
    "facebook", "instagram", "twitter", "youtube", "linkedin",
    "tripadvisor", "yelp", "booking", "trustpilot", "justdial",
    "indiamart", "sulekha", "zomato", "swiggy", "wikipedia",
]


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _get(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=20)
            if r.status_code == 200:
                return r
            logger.warning(f"HTTP {r.status_code} for {url}")
            time.sleep(REQUEST_DELAY * (attempt + 1))
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            time.sleep(REQUEST_DELAY * (attempt + 1))
    return None


def _scrape_yell(category, city):
    """Scrape yell.com for UK businesses."""
    leads = []
    url = f"https://www.yell.com/ucs/UcsSearchAction.do"
    params = {"keywords": category, "location": city, "pageNum": 1}
    resp = _get(url, params=params)
    if not resp:
        return leads

    soup = BeautifulSoup(resp.text, "html.parser")
    for card in soup.select("article.businessCapsule"):
        lead = {"name": "", "phone": "", "email": "", "address": "", "website": "", "source": "", "region": "europe"}
        name_tag = card.select_one("h2.businessCapsule--name a, .businessCapsule--name")
        if name_tag:
            lead["name"] = name_tag.get_text(strip=True)
        phone_tag = card.select_one("[class*='phone'], [itemprop='telephone']")
        if phone_tag:
            lead["phone"] = phone_tag.get_text(strip=True)
        addr_tag = card.select_one("[itemprop='address'], .businessCapsule--address")
        if addr_tag:
            lead["address"] = addr_tag.get_text(" ", strip=True)[:150]
        link_tag = card.select_one("a[href]")
        if link_tag:
            lead["source"] = "https://www.yell.com" + link_tag.get("href", "")
        if lead["name"]:
            leads.append(lead)
    return leads


def _scrape_hotfrog(category, city, region_key):
    """Scrape hotfrog.com — works globally."""
    leads = []
    url = f"https://www.hotfrog.com/search/{city.lower().replace(' ', '-')}/{category.lower().replace(' ', '-')}"
    resp = _get(url)
    if not resp:
        return leads

    soup = BeautifulSoup(resp.text, "html.parser")
    for card in soup.select("div.search-result, div.business-card, article"):
        lead = {"name": "", "phone": "", "email": "", "address": "", "website": "", "source": url, "region": region_key}
        name_tag = card.select_one("h2 a, h3 a, .business-name a, .name")
        if name_tag:
            lead["name"] = name_tag.get_text(strip=True)
        text = card.get_text(" ", strip=True)
        phones = PHONE_RE.findall(text)
        if phones:
            lead["phone"] = re.sub(r"[\s\-()]", "", phones[0])
        emails = EMAIL_RE.findall(text)
        if emails:
            lead["email"] = emails[0].lower()
        if lead["name"] and len(lead["name"]) > 3:
            leads.append(lead)
    return leads


def _scrape_cylex(category, city, region_key):
    """Scrape cylex-uk.co.uk or cylex.de — free business directory."""
    leads = []
    if region_key == "europe" and city in ["London", "Manchester", "Birmingham", "Dublin"]:
        base = "https://www.cylex-uk.co.uk"
        url  = f"{base}/companies/{category.replace(' ', '-')}_{city.replace(' ', '-')}.html"
    elif region_key == "europe" and city in ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"]:
        base = "https://www.cylex.de"
        url  = f"{base}/firmen/{category.replace(' ', '-')}_{city.replace(' ', '-')}.html"
    else:
        return leads

    resp = _get(url)
    if not resp:
        return leads

    soup = BeautifulSoup(resp.text, "html.parser")
    for card in soup.select("div.company-info, div.result-item, li.result"):
        lead = {"name": "", "phone": "", "email": "", "address": "", "website": "", "source": url, "region": region_key}
        name_tag = card.select_one("h2 a, h3 a, .company-name, .name")
        if name_tag:
            lead["name"] = name_tag.get_text(strip=True)
        text = card.get_text(" ", strip=True)
        phones = PHONE_RE.findall(text)
        if phones:
            lead["phone"] = re.sub(r"[\s\-()]", "", phones[0])
        addr_tag = card.select_one("[itemprop='address'], .address")
        if addr_tag:
            lead["address"] = addr_tag.get_text(" ", strip=True)[:150]
        if lead["name"] and len(lead["name"]) > 3:
            leads.append(lead)
    return leads


def _build_plan():
    """Build weighted search plan: 90% Europe, 10% India."""
    plan = []
    for cat in SEARCH_CATEGORIES:
        for city in EUROPE_CITIES:
            plan.append(("europe", city, cat))
            plan.append(("europe", city, cat))  # 2x weight
    for cat in SEARCH_CATEGORIES:
        for city in INDIA_CITIES:
            plan.append(("india", city, cat))
    random.shuffle(plan)
    return plan


def scrape_leads(stop_event):
    plan = _build_plan()
    for region_key, city, category in plan:
        if stop_event.is_set():
            return

        logger.info(f"[{region_key.upper()}] {category} in {city}")
        leads = []

        # Try multiple sources
        if city in ["London", "Manchester", "Birmingham"]:
            leads = _scrape_yell(category, city)

        if not leads:
            leads = _scrape_cylex(category, city, region_key)

        if not leads:
            leads = _scrape_hotfrog(category, city, region_key)

        for lead in leads:
            if stop_event.is_set():
                return
            yield lead

        time.sleep(REQUEST_DELAY + random.uniform(1, 2))
