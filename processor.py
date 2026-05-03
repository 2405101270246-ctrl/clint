import re
from config import REGIONS

SEEN = set()

JUNK_NAMES  = re.compile(
    r"(advertisement|sponsored|\bad\b|google|facebook|instagram"
    r"|justdial|indiamart|sulekha|tripadvisor|yelp|booking\.com)", re.I
)
VALID_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
VALID_PHONE = re.compile(r"^\+?[\d]{7,15}$")

SKIP_SOURCES = [
    "justdial", "indiamart", "sulekha", "tradeindia",
    "tripadvisor", "yelp", "booking.com", "trustpilot",
    "yellowpages", "thomsonlocal", "yell.com",
]


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
    if not lead.get("name") or len(lead["name"]) < 3:
        return False
    if JUNK_NAMES.search(lead.get("name", "")):
        return False
    if not lead.get("phone") and not lead.get("email"):
        return False
    if lead.get("website"):
        return False
    source = lead.get("source", "")
    if any(d in source for d in SKIP_SOURCES):
        return False
    return True


def clean(lead: dict) -> dict:
    region_key = lead.get("region", "europe")
    lead["name"]    = lead.get("name", "").strip().title()
    lead["address"] = lead.get("address", "").strip()

    phone = _clean_phone(lead.get("phone", ""), region_key)
    lead["phone"]     = phone if VALID_PHONE.match(phone) else ""
    lead["whatsapp"]  = _whatsapp_link(lead["phone"]) if lead["phone"] else ""

    email = lead.get("email", "").strip().lower()
    lead["email"] = email if VALID_EMAIL.match(email) else ""

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
    else:
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
