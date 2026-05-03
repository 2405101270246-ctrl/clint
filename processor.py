import re
from config import REGIONS

SEEN = set()

JUNK_NAMES  = re.compile(
    r"(advertisement|sponsored|\bad\b|google|facebook|instagram"
    r"|justdial|indiamart|sulekha|tripadvisor|yelp|booking\.com"
    r"|wikipedia|linkedin|twitter|youtube)", re.I
)
VALID_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
VALID_PHONE = re.compile(r"^\+?[\d]{7,15}$")

SKIP_SOURCES = [
    "justdial", "indiamart", "sulekha", "tradeindia",
    "tripadvisor", "yelp", "booking.com", "trustpilot",
    "yellowpages", "thomsonlocal", "yell.com",
    "wikipedia.org", "linkedin.com", "facebook.com",
]

# These domains = business already has website — skip
HAS_WEBSITE_DOMAINS = re.compile(
    r"\.(com|co\.uk|de|fr|nl|es|it|pl|se|be|pt|ch|at|dk|no|fi|ie|cz|ro|hu|gr|in|net|org)\b",
    re.I
)


def _clean_phone(phone: str, region_key: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone)
    prefix  = REGIONS.get(region_key, {}).get("phone_prefix")
    if prefix and cleaned.isdigit():
        if region_key == "india":
            if len(cleaned) == 10:
                cleaned = prefix + cleaned
            elif cleaned.startswith("0") and len(cleaned) == 11:
                cleaned = prefix + cleaned[1:]
    return cleaned


def _whatsapp_link(phone: str) -> str:
    number = re.sub(r"[^\d]", "", phone)
    return f"https://wa.me/{number}"


def _dedup_key(lead: dict) -> str:
    return lead.get("phone") or lead.get("email") or lead.get("name", "").lower()


def is_valid(lead: dict) -> bool:
    name = lead.get("name", "")
    if not name or len(name) < 3:
        return False
    if JUNK_NAMES.search(name):
        return False

    # Skip known directory/listing sources
    source = lead.get("source", "")
    if any(d in source for d in SKIP_SOURCES):
        return False

    # Skip businesses that already have their own website
    website = lead.get("website", "")
    if website and HAS_WEBSITE_DOMAINS.search(website) and not any(d in website for d in SKIP_SOURCES):
        return False

    # Must have at least name + one of: phone, email, address
    has_contact = bool(lead.get("phone")) or bool(lead.get("email"))
    has_address = bool(lead.get("address"))
    if not has_contact and not has_address:
        return False

    return True


def clean(lead: dict) -> dict:
    region_key = lead.get("region", "europe")
    lead["name"]    = lead.get("name", "").strip().title()
    lead["address"] = lead.get("address", "").strip()

    phone = _clean_phone(lead.get("phone", ""), region_key)
    lead["phone"]    = phone if VALID_PHONE.match(phone) else ""
    lead["whatsapp"] = _whatsapp_link(lead["phone"]) if lead["phone"] else ""

    email = lead.get("email", "").strip().lower()
    lead["email"] = email if VALID_EMAIL.match(email) else ""

    # Clear website field — we want businesses WITHOUT websites
    # Only set if it's clearly a dedicated business website (not a directory)
    website = lead.get("website", "")
    if website and any(d in website for d in SKIP_SOURCES):
        lead["website"] = ""

    return lead


def is_duplicate(lead: dict) -> bool:
    key = _dedup_key(lead)
    if not key or key in SEEN:
        return True
    SEEN.add(key)
    return False


def generate_message(lead: dict) -> str:
    name       = lead.get("name") or "there"
    region_key = lead.get("region", "europe")
    lang       = REGIONS.get(region_key, {}).get("message_lang", "en")

    if lang == "hi":
        return (
            f"Hi {name}! 👋 Aapka business abhi online nahi hai.\n"
            f"Main aapke liye ek professional website + app bana sakta hoon "
            f"jisse zyada customers milenge. Free demo dekhna chahenge? 😊"
        )
    return (
        f"Hi {name}! 👋 I noticed your business doesn't have a website yet.\n"
        f"I build professional websites & apps that bring in more customers — "
        f"quick, affordable & tailored for you. Want a free demo? 😊"
    )


def process(lead: dict):
    lead = clean(lead)
    if not is_valid(lead):
        return None
    if is_duplicate(lead):
        return None
    lead["message"] = generate_message(lead)
    return lead
