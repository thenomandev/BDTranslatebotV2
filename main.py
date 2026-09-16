import os
import time
import logging
from queue import Queue

import requests
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

PORT = int(os.getenv("PORT", "5000"))

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://bdtranslatebotv2.onrender.com"
).rstrip("/")

WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

bot = Bot(token=TOKEN)

update_queue = Queue()

dispatcher = Dispatcher(
    bot,
    update_queue,
    workers=2,
    use_context=True
)


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text):

    if not text:
        return "en"

    bengali = sum(
        1 for char in text
        if "\u0980" <= char <= "\u09FF"
    )

    return "bn" if bengali > 0 else "en"


# =========================================================
# TRANSLATOR 1 - LIBRETRANSLATE
# =========================================================

def libre_translate(text, source, target):

    url = os.getenv(
        "LIBRETRANSLATE_URL",
        "https://libretranslate.com/translate"
    )

    api_key = os.getenv("LIBRETRANSLATE_API_KEY")

    data = {
        "q": text,
        "source": source,
        "target": target,
        "format": "text"
    }

    if api_key:
        data["api_key"] = api_key

    response = requests.post(
        url,
        data=data,
        timeout=15,
        headers={
            "User-Agent": "BDTranslateBot/1.0"
        }
    )

    logger.info(
        f"LibreTranslate status: {response.status_code}"
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"LibreTranslate HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    result = response.json().get("translatedText")

    if not result:
        raise RuntimeError("LibreTranslate returned empty result.")

    return result.strip()


# =========================================================
# TRANSLATOR 2 - MYMEMORY
# =========================================================

def mymemory_translate(text, source, target):

    url = "https://api.mymemory.translated.net/get"

    params = {
        "q": text,
        "langpair": f"{source}|{target}"
    }

    response = requests.get(
        url,
        params=params,
        timeout=15,
        headers={
            "User-Agent": "BDTranslateBot/1.0"
        }
    )

    logger.info(
        f"MyMemory status: {response.status_code}"
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"MyMemory HTTP {response.status_code}"
        )

    data = response.json()

    result = data.get(
        "responseData",
        {}
    ).get("translatedText")

    if not result:
        raise RuntimeError(
            "MyMemory returned empty result."
        )

    return result.strip()


# =========================================================
# TRANSLATION
# =========================================================

def translate_text(text):

    source = detect_language(text)

    if source == "bn":
        target = "en"
    else:
        target = "bn"

    logger.info(
        f"Translation: {source} -> {target} | "
        f"Text: {text[:100]}"
    )

    # -----------------------------------------------------
    # Try LibreTranslate
    # -----------------------------------------------------

    try:

        result = libre_translate(
            text,
            source,
            target
        )

        logger.info(
            "Translation successful using LibreTranslate."
        )

        return result

    except Exception as e:

        logger.warning(
            f"LibreTranslate failed: {e}"
        )


    # -----------------------------------------------------
    # Wait before fallback
    # -----------------------------------------------------

    time.sleep(1)


    # -----------------------------------------------------
    # Try MyMemory
    # -----------------------------------------------------

    try:

        result = mymemory_translate(
            text,
            source,
            target
        )

        logger.info(
            "Translation successful using MyMemory."
        )

        return result

    except Exception as e:

        logger.warning(
            f"MyMemory failed: {e}"
        )


    # -----------------------------------------------------
    # Both failed
    # -----------------------------------------------------

    raise RuntimeError(
        "All translation services failed."
    )


# =========================================================
# START
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
        "শুধু English অথবা বাংলা লেখা পাঠান।"
    )


# =========================================================
# NORMAL MESSAGE
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

        logger.info(
            f"Translation result: {translated[:200]}"
        )

        update.message.reply_text(
            translated
        )

    except Exception as e:

        logger.exception(
            f"Translation error: {e}"
        )

        update.message.reply_text(
            "❌ অনুবাদ করা যায়নি।\n"
            "Translation service বর্তমানে ব্যস্ত।\n"
            "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
        )


# =========================================================
# /TRANSLATE
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

    try:

        translated = translate_text(text)

        update.message.reply_text(
            f"🔁 {translated}"
        )

    except Exception as e:

        logger.exception(
            f"/translate error: {e}"
        )

        update.message.reply_text(
            "❌ অনুবাদ করা যায়নি।"
        )


# =========================================================
# HANDLERS
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
# WEBHOOK
# =========================================================

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():

    logger.info(
        "Telegram webhook received."
    )

    try:

        data = request.get_json(force=True)

        update = Update.de_json(
            data,
            bot
        )

        dispatcher.process_update(
            update
        )

        return "OK", 200

    except Exception as e:

        logger.exception(
            f"Webhook error: {e}"
        )

        return "ERROR", 500


# =========================================================
# HEALTH
# =========================================================

@app.route("/", methods=["GET"])
def index():

    return "BD Translate Bot is live!", 200


# =========================================================
# SET WEBHOOK
# =========================================================

def setup_webhook():

    try:

        logger.info(
            "Setting Telegram webhook..."
        )

        result = bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True
        )

        logger.info(
            f"Webhook setup result: {result}"
        )

        info = bot.get_webhook_info()

        logger.info(
            f"Webhook URL: {info.url}"
        )

        logger.info(
            f"Pending updates: {info.pending_update_count}"
        )

        if info.last_error_message:

            logger.error(
                f"Telegram webhook error: "
                f"{info.last_error_message}"
            )

        return True

    except Exception as e:

        logger.exception(
            f"Webhook setup failed: {e}"
        )

        return False


# =========================================================
# RUN
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
