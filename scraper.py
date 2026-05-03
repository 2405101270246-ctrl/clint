import re, time, random, logging, os
import requests
from config import REQUEST_DELAY

logger = logging.getLogger(__name__)

SERP_API_KEY = os.environ.get("SERP_API_KEY", "")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{7,}\d)")

QUERIES_EUROPE = [
    "salon owner contact phone no website",
    "restaurant owner contact phone no website",
    "plumber contact phone email",
    "electrician contact phone email",
    "cleaning service contact phone email",
    "bakery contact phone email",
    "photographer contact phone email",
    "florist contact phone email",
    "tailor contact phone email",
    "mechanic contact phone email",
    "driving school contact phone",
    "pest control contact phone",
    "locksmith contact phone",
    "painter decorator contact phone",
    "catering contact phone email",
    "event planner contact phone email",
    "personal trainer contact phone",
    "accountant contact phone email",
    "dog groomer contact phone",
    "beauty salon contact phone email",
]

QUERIES_INDIA = [
    "salon owner contact phone number",
    "restaurant owner contact phone",
    "shop owner contact phone email",
    "coaching classes contact phone",
    "carpenter plumber contact phone",
    "catering service contact phone",
    "event decorator contact phone",
    "photographer contact phone email",
]

EUROPE_CITIES = [
    "London", "Manchester", "Birmingham", "Leeds",
    "Berlin", "Munich", "Hamburg", "Frankfurt",
    "Paris", "Lyon", "Marseille",
    "Amsterdam", "Rotterdam",
    "Madrid", "Barcelona",
    "Rome", "Milan",
    "Warsaw", "Brussels", "Lisbon",
    "Vienna", "Dublin", "Stockholm",
    "Oslo", "Copenhagen", "Zurich", "Prague",
]

INDIA_CITIES = [
    "Mumbai", "Delhi", "Bangalore",
    "Hyderabad", "Chennai", "Pune",
]


def _whatsapp(phone):
    number = re.sub(r"[^\d]", "", phone)
    return f"https://wa.me/{number}" if number else ""


def _search(query, region_key):
    """Search via SerpApi — guaranteed results, no IP blocking."""
    if not SERP_API_KEY:
        logger.error("SERP_API_KEY not set!")
        return []

    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "q":       query,
                "api_key": SERP_API_KEY,
                "num":     10,
                "hl":      "en",
                "gl":      "uk" if region_key == "europe" else "in",
            },
            timeout=20,
        )
        if r.status_code != 200:
            logger.warning(f"SerpApi {r.status_code}: {r.text[:200]}")
            return []

        data    = r.json()
        results = data.get("organic_results", [])
        leads   = []

        for result in results:
            snippet = result.get("snippet", "")
            title   = result.get("title", "")
            link    = result.get("link", "")

            # Skip big directory/listing sites
            skip = ["justdial", "indiamart", "tripadvisor", "yelp",
                    "facebook", "instagram", "linkedin", "wikipedia",
                    "zomato", "swiggy", "booking.com", "trustpilot"]
            if any(s in link.lower() for s in skip):
                continue

            text   = f"{title} {snippet}"
            phones = PHONE_RE.findall(text)
            emails = EMAIL_RE.findall(text)

            lead = {
                "name":     title,
                "phone":    re.sub(r"[\s\-()]", "", phones[0]) if phones else "",
                "email":    emails[0].lower() if emails else "",
                "address":  "",
                "website":  link,
                "source":   link,
                "region":   region_key,
                "whatsapp": _whatsapp(re.sub(r"[\s\-()]", "", phones[0])) if phones else "",
            }

            # Only keep if has phone or email
            if lead["phone"] or lead["email"]:
                leads.append(lead)

        return leads

    except Exception as e:
        logger.error(f"SerpApi error: {e}")
        return []


def _build_plan():
    plan = []
    for city in EUROPE_CITIES:
        for q in QUERIES_EUROPE:
            plan.append(("europe", city, q))
    for city in INDIA_CITIES:
        for q in QUERIES_INDIA:
            plan.append(("india", city, q))
    random.shuffle(plan)
    return plan


def scrape_leads(stop_event):
    plan = _build_plan()
    for region_key, city, query in plan:
        if stop_event.is_set():
            return

        full_query = f"{query} {city}"
        logger.info(f"[{region_key.upper()}] {full_query}")

        leads = _search(full_query, region_key)
        logger.info(f"  → {len(leads)} leads found")

        for lead in leads:
            if stop_event.is_set():
                return
            yield lead

        time.sleep(REQUEST_DELAY + random.uniform(1, 2))
