import time, random, logging
import requests
from config import YELP_API_KEY

logger = logging.getLogger(__name__)

CATEGORIES = [
    "hair","restaurants","plumbing","electricians","cleaning",
    "bakeries","photographers","florists","tailors","auto",
    "drivingschools","pestcontrol","locksmiths","painters","caterers",
    "eventplanning","landscaping","accountants","dentists","tutoring",
]

EUROPE_LOCATIONS = [
    "London, UK", "Manchester, UK", "Birmingham, UK",
    "Berlin, Germany", "Munich, Germany", "Hamburg, Germany",
    "Paris, France", "Lyon, France", "Amsterdam, Netherlands",
    "Madrid, Spain", "Barcelona, Spain", "Rome, Italy",
    "Milan, Italy", "Warsaw, Poland", "Brussels, Belgium",
    "Lisbon, Portugal", "Vienna, Austria", "Dublin, Ireland",
    "Stockholm, Sweden", "Oslo, Norway", "Copenhagen, Denmark",
    "Zurich, Switzerland", "Prague, Czech Republic",
]

INDIA_LOCATIONS = [
    "Mumbai, India", "Delhi, India", "Bangalore, India",
    "Hyderabad, India", "Chennai, India", "Pune, India",
]


def _region(location):
    return "india" if "India" in location else "europe"


def _whatsapp(phone):
    import re
    number = re.sub(r"[^\d]", "", phone)
    return f"https://wa.me/{number}" if number else ""


def _fetch_yelp(category, location):
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params  = {
        "term":       category,
        "location":   location,
        "limit":      20,
        "sort_by":    "rating",
    }
    try:
        r = requests.get(
            "https://api.yelp.com/v3/businesses/search",
            headers=headers, params=params, timeout=15
        )
        if r.status_code == 200:
            return r.json().get("businesses", [])
        logger.warning(f"Yelp {r.status_code}: {category} in {location}")
    except Exception as e:
        logger.error(f"Yelp error: {e}")
    return []


def _to_lead(biz, location):
    region = _region(location)
    phone  = biz.get("phone", "") or biz.get("display_phone", "")
    loc    = biz.get("location", {})
    addr   = ", ".join(filter(None, [
        loc.get("address1", ""),
        loc.get("city", ""),
        loc.get("country", ""),
    ]))

    # Skip if business already has a website
    website = biz.get("url", "")  # this is yelp URL, not their own site
    # Check if they have their own website via attributes
    attrs = biz.get("attributes", {}) or {}
    own_website = attrs.get("business_url", "")

    from processor import generate_message
    lead = {
        "name":      biz.get("name", ""),
        "phone":     phone,
        "whatsapp":  _whatsapp(phone),
        "email":     "",
        "address":   addr,
        "website":   own_website,
        "source":    biz.get("url", ""),
        "region":    region,
    }
    lead["message"] = generate_message(lead)
    return lead


def scrape_leads(stop_event):
    # Build weighted plan: 90% Europe, 10% India
    plan = (
        [(loc, cat) for loc in EUROPE_LOCATIONS for cat in CATEGORIES] * 9 +
        [(loc, cat) for loc in INDIA_LOCATIONS  for cat in CATEGORIES]
    )
    random.shuffle(plan)
    seen = set()

    for location, category in plan:
        if stop_event.is_set():
            return

        key = (location, category)
        if key in seen:
            continue
        seen.add(key)

        logger.info(f"[{_region(location).upper()}] {category} in {location}")
        businesses = _fetch_yelp(category, location)
        logger.info(f"  → {len(businesses)} results from Yelp")

        for biz in businesses:
            if stop_event.is_set():
                return
            # Only send leads without their own website
            if not biz.get("attributes", {}) or True:  # include all, processor will filter
                lead = _to_lead(biz, location)
                if lead["name"]:
                    yield lead

        time.sleep(1 + random.uniform(0.5, 1.5))
