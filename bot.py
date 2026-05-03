import logging, asyncio, os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Bot
from telegram.error import RetryAfter, TimedOut
from config import TELEGRAM_TOKEN, CHAT_ID
from scraper import scrape_leads
from processor import process

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REGION_FLAG = {"europe": "🇪🇺", "india": "🇮🇳"}
PORT        = int(os.environ.get("PORT", 10000))


# ── Minimal HTTP server — satisfies Render port check ─────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok","bot":"Lead Gen Bot"}')
    def log_message(self, *args):
        pass   # silence access logs


def _run_health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


# ── Formatters ────────────────────────────────────────────
def _esc(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_lead(lead: dict) -> str:
    name    = _esc(lead.get("name") or "N/A")
    address = _esc(lead.get("address") or "N/A")
    phone   = _esc(lead.get("phone") or "")
    email   = _esc(lead.get("email") or "")
    source  = lead.get("source") or ""
    wa      = lead.get("whatsapp") or ""
    msg     = _esc(lead.get("message") or "")
    flag    = REGION_FLAG.get(lead.get("region", "europe"), "🌍")
    contact = phone if phone else email if email else "N/A"

    lines = [
        f"{flag} *Business:* {name}",
        f"📍 *Location:* {address}",
        f"📞 *Contact:* {contact}",
    ]
    if wa:
        lines.append(f"💬 *WhatsApp:* [Click to Chat]({wa})")
    if source:
        lines.append(f"🔗 *Source:* [Link]({_esc(source)})")
    lines += ["", "✉️ *Ready\\-to\\-send:*", f"```\n{msg}\n```"]
    return "\n".join(lines)


# ── Scraper thread ────────────────────────────────────────
def _scrape_worker(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    stop = threading.Event()
    while True:
        logger.info("Scrape cycle starting...")
        found = 0
        for raw_lead in scrape_leads(stop):
            lead = process(raw_lead)
            if not lead:
                continue
            asyncio.run_coroutine_threadsafe(queue.put(lead), loop)
            found += 1
            time.sleep(1)   # extra delay between leads to avoid 429
        logger.info(f"Cycle done — {found} leads. Sleeping 120s.")
        time.sleep(120)


# ── Main async loop ───────────────────────────────────────
async def run():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN or CHAT_ID not set!")
        return

    bot   = Bot(token=TELEGRAM_TOKEN)
    queue = asyncio.Queue()
    loop  = asyncio.get_running_loop()
    count = 0

    # Start health server + scraper thread
    threading.Thread(target=_run_health_server, daemon=True).start()
    threading.Thread(target=_scrape_worker, args=(queue, loop), daemon=True).start()
    logger.info(f"Health server on port {PORT} | Scraper started")

    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 *Bot started\\! Searching for leads\\.\\.\\.*",
            parse_mode="MarkdownV2",
        )
        logger.info("Startup message sent to Telegram")
    except Exception as e:
        logger.error(f"Startup message failed: {e}")
        logger.error("Check CHAT_ID — must be your personal numeric ID from @userinfobot")

    while True:
        lead = await queue.get()
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=_format_lead(lead),
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
            count += 1
            logger.info(f"Lead #{count} sent: {lead.get('name')}")
        except RetryAfter as e:
            logger.warning(f"Rate limited — sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            await queue.put(lead)
        except TimedOut:
            await asyncio.sleep(5)
            await queue.put(lead)
        except Exception as e:
            logger.error(f"Send error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
