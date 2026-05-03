import logging, asyncio, os, time, threading
from telegram import Bot
from telegram.error import RetryAfter, TimedOut
from config import TELEGRAM_TOKEN, CHAT_ID
from scraper import scrape_leads
from processor import process

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REGION_FLAG = {"europe": "🇪🇺", "india": "🇮🇳"}


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


def _scrape_worker(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Runs in a background thread — pushes leads into async queue."""
    stop = threading.Event()   # never set — runs forever
    while True:
        logger.info("Scrape cycle starting...")
        found = 0
        for raw_lead in scrape_leads(stop):
            lead = process(raw_lead)
            if not lead:
                continue
            asyncio.run_coroutine_threadsafe(queue.put(lead), loop)
            found += 1
        logger.info(f"Scrape cycle done — {found} leads queued. Sleeping 60s.")
        time.sleep(60)


async def run():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN or CHAT_ID not set in environment!")
        return

    bot   = Bot(token=TELEGRAM_TOKEN)
    queue = asyncio.Queue()
    loop  = asyncio.get_running_loop()
    count = 0

    # Start scraper in background thread
    t = threading.Thread(target=_scrape_worker, args=(queue, loop), daemon=True)
    t.start()
    logger.info("Scraper thread started")

    # Send startup message
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 *Bot started\\! Searching for leads\\.\\.\\.*",
            parse_mode="MarkdownV2",
        )
    except Exception as e:
        logger.error(f"Startup message failed: {e}")

    # Main loop — consume leads from queue and send to Telegram
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
            await queue.put(lead)   # re-queue
        except TimedOut:
            logger.warning("Timed out — retrying in 5s")
            await asyncio.sleep(5)
            await queue.put(lead)
        except Exception as e:
            logger.error(f"Send error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
