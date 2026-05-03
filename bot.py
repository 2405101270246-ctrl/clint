import logging, asyncio, os, time
from telegram import Bot
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


async def run():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN or CHAT_ID env variable not set!")
        return

    bot   = Bot(token=TELEGRAM_TOKEN)
    stop  = asyncio.Event()   # never set — runs forever
    count = 0

    await bot.send_message(
        chat_id=CHAT_ID,
        text="🚀 *Bot started\\! Searching for leads\\.\\.\\.*",
        parse_mode="MarkdownV2",
    )
    logger.info("Bot started — searching for leads")

    while True:
        found_any = False

        for raw_lead in scrape_leads(stop):
            lead = process(raw_lead)
            if not lead:
                continue
            try:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=_format_lead(lead),
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=True,
                )
                count += 1
                found_any = True
                logger.info(f"Lead #{count} sent: {lead.get('name')}")
            except Exception as e:
                logger.error(f"Send error: {e}")
                await asyncio.sleep(5)

        # All queries done — wait then restart
        wait = 60 if found_any else 120
        logger.info(f"Cycle done ({count} total). Waiting {wait}s before next cycle...")
        await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(run())
