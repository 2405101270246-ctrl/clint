# Lead Generation Bot — Website/App Client Finder

## What it does
- Finds local businesses **without a website or app**
- 🇪🇺 **90% Europe** | 🇮🇳 **10% India** targeting
- Sends each lead to Telegram with WhatsApp direct chat link
- Ready-to-send outreach message included with every lead

---

## Quick Start

### 1. Install
```cmd
pip install -r requirements.txt
```

### 2. Run
```cmd
set TELEGRAM_TOKEN=8728049984:AAFPKb5kZAKPYFeWBaDgGJMeeAq62C_P51g
python bot.py
```

### 3. Telegram
- Open your bot → send `/start`
- Press **▶ START** → leads arrive one by one
- Press **⏹ STOP** → stops immediately
- Press **📊 Status** → see live count

---

## Telegram Output
```
🇪🇺 Business: Sharma Salon London
📍 Location: 12 Baker Street, London
📞 Contact: +447911123456
💬 WhatsApp: [Click to Chat](https://wa.me/447911123456)
🔗 Source: [Link](https://...)

✉️ Ready-to-send:
Hi Sharma Salon London! 👋 I noticed your business doesn't have
a website yet. I build professional websites & apps that bring
in more customers. Want a free demo? 😊
```

---

## Commands
| Command | Action |
|---|---|
| `/start` | Show control panel with START/STOP buttons |
| `/status` | Live status — how many leads found |
| `/help` | Command list |

---

## Customize (`config.py`)
- `REGIONS` → add/remove cities, change queries per region
- `MAX_RESULTS_PER_QUERY` → more pages = more leads (but slower)
- `REQUEST_DELAY` → increase to 6-8 if Google blocks you

## File Structure
```
clint/
├── bot.py          ← Telegram bot (entry point)
├── scraper.py      ← Google search + HTML parsing, region-aware
├── processor.py    ← Filter, clean, dedup, generate message
├── config.py       ← All settings, region definitions
└── requirements.txt
```

## Notes
- Google may CAPTCHA after many requests — bot auto-waits 30s and retries
- User-Agent rotates automatically to reduce blocking
- Deduplication is in-memory (resets on restart)
- No paid APIs, no Google Maps API, 100% free
