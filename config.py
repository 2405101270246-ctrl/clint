import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")  # Your Telegram chat/user ID

# ── Region split: 90% Europe, 10% India ──────────────────
REGIONS = {
    "europe": {
        "locations": [
            # UK
            "London", "Manchester", "Birmingham", "Leeds", "Glasgow",
            # Germany
            "Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne",
            # France
            "Paris", "Lyon", "Marseille", "Toulouse", "Nice",
            # Netherlands
            "Amsterdam", "Rotterdam", "Utrecht", "The Hague",
            # Spain
            "Madrid", "Barcelona", "Seville", "Valencia",
            # Italy
            "Rome", "Milan", "Naples", "Turin",
            # Poland
            "Warsaw", "Krakow", "Wroclaw",
            # Sweden
            "Stockholm", "Gothenburg", "Malmo",
            # Belgium
            "Brussels", "Antwerp", "Ghent",
            # Portugal
            "Lisbon", "Porto",
            # Switzerland
            "Zurich", "Geneva", "Basel",
            # Austria
            "Vienna", "Graz", "Salzburg",
            # Denmark
            "Copenhagen", "Aarhus",
            # Norway
            "Oslo", "Bergen",
            # Finland
            "Helsinki", "Tampere",
            # Ireland
            "Dublin", "Cork",
            # Czech Republic
            "Prague", "Brno",
            # Romania
            "Bucharest", "Cluj",
            # Hungary
            "Budapest",
            # Greece
            "Athens", "Thessaloniki",
        ],
        "queries": [
            'local restaurant "contact us" phone email -site:tripadvisor.com -site:yelp.com',
            'hair salon "call us" phone email -site:facebook.com',
            'plumber electrician "contact" phone email',
            'cleaning service "phone number" email contact',
            'bakery cafe "contact us" phone email',
            'driving school "contact" phone email',
            'personal trainer fitness "contact" phone email',
            'accountant bookkeeper "contact us" phone email',
            'photographer videographer "contact" phone email',
            'florist flower shop "contact" phone email',
            'tailor alterations "contact" phone email',
            'mechanic garage "contact us" phone email',
            'dentist clinic "contact" phone email',
            'tutoring lessons "contact" phone email',
            'catering service "contact us" phone email',
            'pest control "contact" phone email',
            'landscaping gardening "contact" phone email',
            'locksmith "contact" phone email',
            'painter decorator "contact" phone email',
            'event planner "contact us" phone email',
        ],
        "weight": 9,   # 90%
        "phone_prefix": None,   # keep as-is for Europe
        "message_lang": "en",
    },
    "india": {
        "locations": [
            "Mumbai", "Delhi", "Bangalore", "Hyderabad",
            "Chennai", "Pune", "Ahmedabad", "Kolkata",
        ],
        "queries": [
            'restaurant "call us" -site:zomato.com -site:swiggy.com phone number',
            'salon "contact us" phone email -site:justdial.com',
            'boutique tailoring contact phone email',
            'coaching classes tutor phone email contact',
            'carpenter plumber electrician phone contact email',
            'catering service phone number email contact',
            'event decorator contact phone email',
            'pest control phone number email contact',
        ],
        "weight": 1,   # 10%
        "phone_prefix": "+91",
        "message_lang": "hi",
    },
}

MAX_RESULTS_PER_QUERY = 5
REQUEST_DELAY         = 4    # seconds — increase to 6-8 if Google blocks
MAX_RETRIES           = 3

# Rotate user agents to reduce blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]
