import logging, threading, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN
from scraper import scrape_leads
from processor import process

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REGION_FLAG = {"europe": "🇪🇺", "india": "🇮🇳"}


class BotState:
    def __init__(self):
        self.stop_event  = threading.Event()
        self.lock        = threading.Lock()
        self.running     = False
        self.count       = 0
        self.status_msg  = "Idle"


state = BotState()


# ── Keyboards ─────────────────────────────────────────────
def control_keyboard(running: bool):
    if running:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("⏹ STOP", callback_data="stop"),
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ]])
    else:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("▶ START", callback_data="start"),
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ]])


# ── Formatters ────────────────────────────────────────────
def _esc(text: str) -> str:
    """Escape MarkdownV2 special chars."""
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
    region  = lead.get("region", "europe")
    flag    = REGION_FLAG.get(region, "🌍")

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
    lines += [
        "",
        f"✉️ *Ready\\-to\\-send:*",
        f"```\n{msg}\n```",
    ]
    return "\n".join(lines)


# ── Worker thread ─────────────────────────────────────────
def _run_workflow(chat_id, bot):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def send(text, keyboard=None):
        try:
            await bot.send_message(
                chat_id=chat_id, text=text,
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Send error: {e}")

    with state.lock:
        state.count      = 0
        state.status_msg = "🔍 Searching..."

    loop.run_until_complete(send(
        "🚀 *Lead search started\\!*\n_Scanning Europe \\(90%\\) \\+ India \\(10%\\)\\.\\.\\._",
        control_keyboard(running=True)
    ))

    for raw_lead in scrape_leads(state.stop_event):
        if state.stop_event.is_set():
            break
        lead = process(raw_lead)
        if not lead:
            continue

        loop.run_until_complete(send(_format_lead(lead)))

        with state.lock:
            state.count += 1
            state.status_msg = f"✅ Running — {state.count} leads found"

    with state.lock:
        final_count      = state.count
        state.running    = False
        state.status_msg = f"✅ Done — {final_count} leads total"

    stopped = state.stop_event.is_set()
    summary = (
        f"⏹ *Stopped\\.* Found *{final_count}* leads so far\\."
        if stopped else
        f"✅ *All done\\!* Found *{final_count}* leads\\."
    )
    loop.run_until_complete(send(summary, control_keyboard(running=False)))
    loop.close()


# ── Handlers ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Lead Gen Bot*\n\n"
        "Finds local businesses *without a website or app*\\.\n"
        "🇪🇺 90% Europe \\| 🇮🇳 10% India\n\n"
        "Press *▶ START* to begin\\.",
        parse_mode="MarkdownV2",
        reply_markup=control_keyboard(running=state.running),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Commands:*\n"
        "/start \\— Show control panel\n"
        "/status \\— Current run status\n"
        "/help \\— This message",
        parse_mode="MarkdownV2",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with state.lock:
        msg = state.status_msg
        running = state.running
    status = "🟢 Running" if running else "🔴 Idle"
    await update.message.reply_text(
        f"*Status:* {_esc(status)}\n*Info:* {_esc(msg)}",
        parse_mode="MarkdownV2",
        reply_markup=control_keyboard(running=running),
    )


async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "start":
        with state.lock:
            if state.running:
                await query.answer("⚠️ Already running!", show_alert=True)
                return
            state.running = True
            state.stop_event.clear()

        threading.Thread(
            target=_run_workflow,
            args=(chat_id, ctx.application.bot),
            daemon=True
        ).start()

        await query.edit_message_reply_markup(reply_markup=control_keyboard(running=True))

    elif query.data == "stop":
        state.stop_event.set()
        await query.edit_message_reply_markup(reply_markup=control_keyboard(running=False))
        await ctx.application.bot.send_message(
            chat_id=chat_id,
            text="⏹ *Stop signal sent\\. Finishing current search\\.\\.\\.*",
            parse_mode="MarkdownV2",
        )

    elif query.data == "status":
        with state.lock:
            msg     = state.status_msg
            running = state.running
        status = "🟢 Running" if running else "🔴 Idle"
        await query.answer(f"{status} | {msg}", show_alert=True)


# ── Entry point ───────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Set TELEGRAM_TOKEN env variable!")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    main()
