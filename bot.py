import logging, threading, asyncio, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN
from scraper import scrape_leads
from processor import process

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REGION_FLAG = {"europe": "🇪🇺", "india": "🇮🇳"}
PORT        = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")


class BotState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.lock       = threading.Lock()
        self.running    = False
        self.count      = 0
        self.status_msg = "Idle"
        self.main_loop  = None   # main asyncio loop reference


state = BotState()


# ── Keyboards ─────────────────────────────────────────────
def control_keyboard(running: bool):
    if running:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("⏹ STOP",    callback_data="stop"),
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶ START",   callback_data="start"),
        InlineKeyboardButton("📊 Status", callback_data="status"),
    ]])


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


# ── Worker — runs in thread, posts back via main loop ─────
def _run_workflow(chat_id, bot):
    def send_sync(text, keyboard=None):
        if state.main_loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            ),
            state.main_loop,
        )
        try:
            future.result(timeout=20)
        except Exception as e:
            logger.error(f"Send error: {e}")

    with state.lock:
        state.count      = 0
        state.status_msg = "Searching..."

    send_sync(
        "🚀 *Lead search started\\!*\n"
        "_Scanning Europe \\(90%\\) \\+ India \\(10%\\)_\n"
        "_Leads arrive one by one\\. Press ⏹ STOP anytime\\._",
        control_keyboard(running=True),
    )

    while not state.stop_event.is_set():
        found_any = False
        for raw_lead in scrape_leads(state.stop_event):
            if state.stop_event.is_set():
                break
            lead = process(raw_lead)
            if not lead:
                continue
            send_sync(_format_lead(lead))
            found_any = True
            with state.lock:
                state.count += 1
                state.status_msg = f"Running — {state.count} leads sent"

        if not state.stop_event.is_set():
            send_sync("⏳ *Cycle done\\. Restarting in 60s\\.*")
            time.sleep(60)

    with state.lock:
        final            = state.count
        state.running    = False
        state.status_msg = f"Stopped — {final} leads total"

    send_sync(
        f"⏹ *Stopped\\.* Total leads sent: *{final}*",
        control_keyboard(running=False),
    )


# ── Handlers ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Lead Gen Bot*\n\n"
        "Finds businesses *without a website or app*\\.\n"
        "🇪🇺 90% Europe \\| 🇮🇳 10% India\n\n"
        "Press *▶ START* to begin\\.",
        parse_mode="MarkdownV2",
        reply_markup=control_keyboard(running=state.running),
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with state.lock:
        msg     = state.status_msg
        running = state.running
    await update.message.reply_text(
        f"*{'🟢 Running' if running else '🔴 Idle'}*\n{_esc(msg)}",
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
            daemon=True,
        ).start()
        await query.edit_message_reply_markup(reply_markup=control_keyboard(running=True))

    elif query.data == "stop":
        with state.lock:
            if not state.running:
                await query.answer("Already stopped.", show_alert=True)
                return
        state.stop_event.set()
        await query.edit_message_reply_markup(reply_markup=control_keyboard(running=False))
        await ctx.application.bot.send_message(
            chat_id=chat_id,
            text="⏹ *Stop signal sent\\.*",
            parse_mode="MarkdownV2",
        )

    elif query.data == "status":
        with state.lock:
            msg     = state.status_msg
            running = state.running
        await query.answer(
            f"{'🟢 Running' if running else '🔴 Idle'} | {msg}",
            show_alert=True,
        )


# ── Entry point ───────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Set TELEGRAM_TOKEN env variable!")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(button_handler))

    if WEBHOOK_URL:
        logger.info(f"Webhook mode → {WEBHOOK_URL}/webhook  port={PORT}")

        async def post_init(application):
            state.main_loop = asyncio.get_event_loop()
            await application.bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook",
                drop_pending_updates=True,
            )
            logger.info("Webhook registered with Telegram ✓")

        app.post_init = post_init
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook",
            drop_pending_updates=True,
        )
    else:
        logger.info("Polling mode (local)...")

        async def post_init(application):
            state.main_loop = asyncio.get_event_loop()

        app.post_init = post_init
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
