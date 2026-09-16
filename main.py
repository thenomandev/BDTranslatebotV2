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
# Environment Variables
# =========================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing!")


# LibreTranslate API
LIBRETRANSLATE_URL = os.getenv(
    "LIBRETRANSLATE_URL",
    "https://libretranslate.com/translate"
)

LIBRETRANSLATE_API_KEY = os.getenv(
    "LIBRETRANSLATE_API_KEY"
)


# =========================
# Flask + Telegram Bot
# =========================

bot = Bot(token=TOKEN)

app = Flask(__name__)


# =========================
# Telegram Dispatcher
# =========================

dispatcher = Dispatcher(
    bot,
    None,
    use_context=True
)


# =========================
# Translation Function
# =========================

def translate_text(text):

    if not text or not text.strip():
        return None

    text = text.strip()

    try:

        # Detect Bangla locally
        has_bangla = any(
            "\u0980" <= char <= "\u09FF"
            for char in text
        )


        # =========================
        # Bangla -> English
        # =========================

        if has_bangla:

            source_language = "bn"
            destination_language = "en"


        # =========================
        # English/Other -> Bangla
        # =========================

        else:

            source_language = "auto"
            destination_language = "bn"


        logger.info(
            "Translation: %s -> %s",
            source_language,
            destination_language
        )


        # =========================
        # API Payload
        # =========================

        payload = {
            "q": text,
            "source": source_language,
            "target": destination_language,
            "format": "text"
        }


        # Add API key if available
        if LIBRETRANSLATE_API_KEY:

            payload["api_key"] = LIBRETRANSLATE_API_KEY


        # =========================
        # Translation Request
        # =========================

        response = requests.post(
            LIBRETRANSLATE_URL,
            data=payload,
            headers={
                "User-Agent": "BDTranslateBot/1.0",
                "Accept": "application/json"
            },
            timeout=20
        )


        logger.info(
            "Translation API status: %s",
            response.status_code
        )


        logger.info(
            "Translation API response: %s",
            response.text[:500]
        )


        response.raise_for_status()


        # =========================
        # Parse Response
        # =========================

        result = response.json()


        translated = result.get(
            "translatedText"
        )


        if not translated:

            logger.error(
                "No translatedText returned: %s",
                result
            )

            return None


        translated = translated.strip()


        logger.info(
            "Translation successful: %s",
            translated[:200]
        )


        return translated


    except requests.exceptions.Timeout:

        logger.error(
            "Translation API timeout."
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
# Normal Message Handler
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
            text[:200]
        )


        translated = translate_text(
            text
        )


        if translated:

            update.message.reply_text(
                f"🔁 {translated}"
            )


        else:

            update.message.reply_text(
                "❌ অনুবাদ করা যায়নি।\n"
                "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
            )


    except Exception as e:

        logger.exception(
            "Message handler error: %s",
            e
        )


# =========================
# /translate Command
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


        logger.info(
            "Translate command: %s",
            text[:200]
        )


        translated = translate_text(
            text
        )


        if translated:

            update.message.reply_text(
                f"🔁 {translated}"
            )


        else:

            update.message.reply_text(
                "❌ অনুবাদ করা যায়নি।\n"
                "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
            )


    except Exception as e:

        logger.exception(
            "Translate command error: %s",
            e
        )


# =========================
# Telegram Handlers
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
# Webhook Endpoint
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

            logger.warning(
                "Empty webhook data."
            )

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


    except Exception as e:

        logger.exception(
            "Webhook error: %s",
            e
        )

        return "ERROR", 500


# =========================
# Home / Health Check
# =========================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return "BD Translate Bot is live!", 200


# =========================
# Setup Telegram Webhook
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

        logger.info(
            "Setting Telegram webhook..."
        )


        result = bot.set_webhook(
            url=webhook_url
        )


        logger.info(
            "Webhook setup result: %s",
            result
        )


        webhook_info = bot.get_webhook_info()


        logger.info(
            "Webhook URL configured: %s",
            webhook_info.url
        )


        logger.info(
            "Pending updates: %s",
            webhook_info.pending_update_count
        )


    except Exception as e:

        logger.exception(
            "Webhook setup failed: %s",
            e
        )


# =========================
# Start Server
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
