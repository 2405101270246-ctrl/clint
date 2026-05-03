import logging, threading, asyncio, os
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN
from scraper import scrape_leads
from processor import process

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REGION_FLAG = {"europe": "🇪🇺", "india": "🇮🇳"}
PORT        = int(os.environ.get("PORT", 8443))
# Set this manually in Render env vars: https://your-app-name.onrender.com
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")

flask_app  = Flask(__name__)
tg_app     = None
bot_loop   = None


class BotState:
    def __init__(self):
        self.stop_event  = threading.Event()
        self.lock        = threading.Lock()
        self.running     = False
        self.count       = 0
        self.status_msg  = "Idle"


state = BotState()


# ── Flask routes ──────────────────────────────────────────
@flask_app.get("/")
def health():
    return jsonify({"status": "ok", "leads_found": state.count, "running": state.running})


@flask_app.post("/webhook")
def webhook():
    data = request.get_json(force=True)
    asyncio.run_coroutine_threadsafe(
        tg_app.process_update(Update.de_json(data, tg_app.bot)),
        bot_loop
    ).result(timeout=30)
    return "ok"


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


# ── Telegram handlers ─────────────────────────────────────
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
        msg     = state.status_msg
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


# ── Bot runner (runs in background thread with its own loop) ──
def _run_bot_polling():
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    bot_loop.run_until_complete(tg_app.initialize())
    bot_loop.run_until_complete(tg_app.start())
    bot_loop.run_forever()


# ── Entry point ───────────────────────────────────────────
def main():
    global tg_app, bot_loop
    if not TELEGRAM_TOKEN:
        raise ValueError("Set TELEGRAM_TOKEN env variable!")

    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start",  cmd_start))
    tg_app.add_handler(CommandHandler("help",   cmd_help))
    tg_app.add_handler(CommandHandler("status", cmd_status))
    tg_app.add_handler(CallbackQueryHandler(button_handler))

    if WEBHOOK_URL:
        # ── Webhook mode (Render Web Service) ────────────
        # Start bot event loop in background thread
        t = threading.Thread(target=_run_bot_polling, daemon=True)
        t.start()
        # Wait for loop to be ready
        import time; time.sleep(2)
        # Register webhook with Telegram
        asyncio.run_coroutine_threadsafe(
            tg_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"),
            bot_loop
        ).result(timeout=15)
        logger.info(f"Webhook set → {WEBHOOK_URL}/webhook")
        logger.info(f"Starting Flask on port {PORT}")
        flask_app.run(host="0.0.0.0", port=PORT, threaded=True)
    else:
        # ── Polling mode (local dev) ──────────────────────
        logger.info("Starting polling (local)...")
        tg_app.run_polling()


if __name__ == "__main__":
    main()
