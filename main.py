import os
import logging
import requests
from queue import Queue

from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
)


# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================================================
# Configuration
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

PORT = int(os.environ.get("PORT", 5000))

RENDER_URL = os.environ.get(
    "RENDER_EXTERNAL_URL",
    "https://bdtranslatebotv2.onrender.com"
)

WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"


# =========================================================
# Flask + Telegram
# =========================================================

app = Flask(__name__)

bot = Bot(token=TOKEN)

update_queue = Queue()

dispatcher = Dispatcher(
    bot,
    update_queue,
    workers=4,
    use_context=True
)


# =========================================================
# Language Detection
# =========================================================

def detect_language(text):
    """
    Detect Bengali or English.
    """

    if not text:
        return "en"

    bengali_count = sum(
        1 for char in text
        if "\u0980" <= char <= "\u09FF"
    )

    if bengali_count > 0:
        return "bn"

    return "en"


# =========================================================
# Translation
# =========================================================

def translate_text(text):

    source_lang = detect_language(text)

    if source_lang == "bn":
        source = "bn"
        target = "en"
    else:
        source = "en"
        target = "bn"

    logger.info(
        f"Translation: {source} -> {target} | Text: {text[:100]}"
    )

    url = "https://api.mymemory.translated.net/get"

    params = {
        "q": text,
        "langpair": f"{source}|{target}"
    }

    headers = {
        "User-Agent": "BDTranslateBot/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=15
    )

    logger.info(
        f"MyMemory API status: {response.status_code}"
    )

    response.raise_for_status()

    data = response.json()

    response_data = data.get("responseData", {})

    translated = response_data.get("translatedText")

    if not translated:
        raise RuntimeError(
            f"No translation returned: {data}"
        )

    translated = translated.strip()

    if not translated:
        raise RuntimeError(
            "Empty translation returned."
        )

    logger.info(
        f"Translation successful: {translated[:200]}"
    )

    return translated


# =========================================================
# /start
# =========================================================

def start(update, context):

    if not update.message:
        return

    update.message.reply_text(
        "👋 স্বাগতম!\n\n"
        "আমি English ↔ বাংলা অনুবাদ করতে পারি।\n\n"
        "উদাহরণ:\n"
        "Hello → হ্যালো\n"
        "How are you? → আপনি কেমন আছেন?\n"
        "আমি ভালো আছি → I am fine.\n\n"
        "আপনি শুধু English বা বাংলা লেখা পাঠান।"
    )


# =========================================================
# Normal Message
# =========================================================

def handle_message(update, context):

    if not update.message:
        return

    text = update.message.text

    if not text:
        return

    text = text.strip()

    if not text:
        return

    logger.info(
        f"Telegram message received: {text[:200]}"
    )

    try:

        translated = translate_text(text)

        update.message.reply_text(
            translated
        )

    except Exception as e:

        logger.exception(
            f"Translation error: {e}"
        )

        update.message.reply_text(
            "❌ অনুবাদ করা যায়নি।\n"
            "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
        )


# =========================================================
# /translate Command
# =========================================================

def translate_command(update, context):

    if not update.message:
        return

    if not context.args:

        update.message.reply_text(
            "⚠️ অনুবাদ করার জন্য text দিন।\n\n"
            "উদাহরণ:\n"
            "/translate Hello"
        )

        return

    text = " ".join(context.args)

    logger.info(
        f"/translate request: {text[:200]}"
    )

    try:

        translated = translate_text(text)

        update.message.reply_text(
            f"🔁 {translated}"
        )

    except Exception as e:

        logger.exception(
            f"Command translation error: {e}"
        )

        update.message.reply_text(
            "❌ অনুবাদ করা যায়নি।\n"
            "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
        )


# =========================================================
# Register Handlers
# =========================================================

dispatcher.add_handler(
    CommandHandler("start", start)
)

dispatcher.add_handler(
    CommandHandler("translate", translate_command)
)

dispatcher.add_handler(
    MessageHandler(
        Filters.text & ~Filters.command,
        handle_message
    )
)


# =========================================================
# Webhook
# =========================================================

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():

    logger.info(
        "Telegram webhook received."
    )

    try:

        data = request.get_json(force=True)

        if not data:
            logger.warning(
                "Empty webhook data received."
            )
            return "OK", 200

        update = Update.de_json(
            data,
            bot
        )

        dispatcher.process_update(update)

        return "OK", 200

    except Exception as e:

        logger.exception(
            f"Webhook processing error: {e}"
        )

        return "ERROR", 500


# =========================================================
# Health Check
# =========================================================

@app.route("/", methods=["GET"])
def index():

    return "BD Translate Bot is live!", 200


# =========================================================
# Webhook Setup
# =========================================================

def setup_webhook():

    try:

        logger.info(
            "========================================"
        )

        logger.info(
            "Setting Telegram webhook..."
        )

        logger.info(
            f"Webhook URL: {RENDER_URL}/[TOKEN]"
        )

        result = bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True
        )

        logger.info(
            f"Webhook setup result: {result}"
        )

        webhook_info = bot.get_webhook_info()

        logger.info(
            f"Webhook URL configured: "
            f"{webhook_info.url}"
        )

        logger.info(
            f"Pending updates: "
            f"{webhook_info.pending_update_count}"
        )

        if webhook_info.last_error_message:

            logger.error(
                f"Telegram webhook error: "
                f"{webhook_info.last_error_message}"
            )

        else:

            logger.info(
                "Telegram webhook has no reported errors."
            )

        logger.info(
            "========================================"
        )

        return True

    except Exception as e:

        logger.exception(
            f"Failed to setup Telegram webhook: {e}"
        )

        return False


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":

    logger.info(
        f"Starting Flask server on port {PORT}..."
    )

    setup_webhook()

    app.run(
        host="0.0.0.0",
        port=PORT
    )
