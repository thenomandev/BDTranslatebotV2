import os
import logging
import requests

from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters


# =========================
# Logging
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================
# Environment
# =========================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing!")


# =========================
# LibreTranslate
# =========================

LIBRETRANSLATE_URL = os.getenv(
    "LIBRETRANSLATE_URL",
    "https://libretranslate.com/translate"
)

LIBRETRANSLATE_API_KEY = os.getenv(
    "LIBRETRANSLATE_API_KEY"
)


# =========================
# Flask + Telegram
# =========================

bot = Bot(token=TOKEN)

app = Flask(__name__)

dispatcher = Dispatcher(
    bot,
    None,
    use_context=True
)


# =========================
# Translation
# =========================

def translate_text(text):

    if not text or not text.strip():
        return None

    text = text.strip()

    try:

        # Detect language using LibreTranslate
        detect_response = requests.post(
            LIBRETRANSLATE_URL.replace(
                "/translate",
                "/detect"
            ),
            data={
                "q": text
            },
            headers={
                "User-Agent": "BDTranslateBot/1.0"
            },
            timeout=15
        )

        detect_response.raise_for_status()

        detected = detect_response.json()

        if not detected:
            logger.error("Language detection returned empty response.")
            return None

        source_language = detected[0].get("language")

        logger.info(
            "Detected language: %s",
            source_language
        )


        # =========================
        # Destination language
        # =========================

        if source_language == "bn":

            destination = "en"

        else:

            destination = "bn"


        # =========================
        # Translation request
        # =========================

        payload = {
            "q": text,
            "source": source_language,
            "target": destination,
            "format": "text"
        }


        if LIBRETRANSLATE_API_KEY:
            payload["api_key"] = LIBRETRANSLATE_API_KEY


        response = requests.post(
            LIBRETRANSLATE_URL,
            data=payload,
            headers={
                "User-Agent": "BDTranslateBot/1.0"
            },
            timeout=20
        )

        response.raise_for_status()

        result = response.json()

        translated = result.get(
            "translatedText"
        )


        if not translated:
            logger.error(
                "Translation response did not contain translatedText: %s",
                result
            )

            return None


        translated = translated.strip()


        logger.info(
            "Translation successful: %s",
            translated[:100]
        )

        return translated


    except requests.exceptions.Timeout:

        logger.error(
            "Translation server timeout."
        )

        return None


    except requests.exceptions.RequestException as e:

        logger.error(
            "Translation request error: %s",
            e
        )

        return None


    except Exception as e:

        logger.exception(
            "Translation error: %s",
            e
        )

        return None


# =========================
# Normal Messages
# =========================

def handle_message(update, context):

    try:

        if not update.message:
            return

        if not update.message.text:
            return

        text = update.message.text.strip()

        if not text:
            return


        logger.info(
            "Received message: %s",
            text[:100]
        )


        translated = translate_text(text)


        if translated:

            update.message.reply_text(
                f"🔁 {translated}"
            )

        else:

            update.message.reply_text(
                "❌ অনুবাদ করা যায়নি।\n"
                "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
            )


    except Exception:

        logger.exception(
            "Message handler error"
        )


# =========================
# /translate
# =========================

def translate_command(update, context):

    try:

        if not context.args:

            update.message.reply_text(
                "⚠️ দয়া করে /translate এর পরে "
                "কিছু লিখুন।\n\n"
                "উদাহরণ:\n"
                "/translate Hello"
            )

            return


        text = " ".join(
            context.args
        ).strip()


        translated = translate_text(text)


        if translated:

            update.message.reply_text(
                f"🔁 {translated}"
            )

        else:

            update.message.reply_text(
                "❌ অনুবাদ করা যায়নি।"
            )


    except Exception:

        logger.exception(
            "Translate command error"
        )


# =========================
# Handlers
# =========================

dispatcher.add_handler(
    MessageHandler(
        Filters.text & ~Filters.command,
        handle_message
    )
)

dispatcher.add_handler(
    CommandHandler(
        "translate",
        translate_command
    )
)


# =========================
# Webhook
# =========================

@app.route(
    f"/{TOKEN}",
    methods=["POST"]
)
def webhook():

    try:

        data = request.get_json(
            force=True
        )

        if not data:
            return "No data", 400


        logger.info(
            "Telegram webhook received."
        )


        update = Update.de_json(
            data,
            bot
        )


        dispatcher.process_update(
            update
        )


        return "OK", 200


    except Exception:

        logger.exception(
            "Webhook error"
        )

        return "ERROR", 500


# =========================
# Status
# =========================

@app.route("/")
def index():

    return "BD Translate Bot is live!", 200


# =========================
# Webhook Setup
# =========================

def setup_webhook():

    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if not render_url:

        logger.warning(
            "RENDER_EXTERNAL_URL is not available."
        )

        return


    webhook_url = (
        render_url.rstrip("/")
        + "/"
        + TOKEN
    )


    try:

        result = bot.set_webhook(
            url=webhook_url
        )

        logger.info(
            "Webhook setup result: %s",
            result
        )


    except Exception:

        logger.exception(
            "Webhook setup failed."
        )


# =========================
# Start
# =========================

if __name__ == "__main__":

    setup_webhook()


    PORT = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )


    logger.info(
        "Starting Flask server on port %s...",
        PORT
    )


    app.run(
        host="0.0.0.0",
        port=PORT
    )
