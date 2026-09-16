import os
import time
import logging
from queue import Queue

from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
)
from deep_translator import GoogleTranslator


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set!"
    )

PORT = int(os.environ.get("PORT", 5000))

RENDER_URL = os.environ.get(
    "RENDER_EXTERNAL_URL",
    "https://bdtranslatebotv2.onrender.com"
).rstrip("/")

WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"


# =========================================================
# FLASK + TELEGRAM BOT
# =========================================================

app = Flask(__name__)

bot = Bot(token=TOKEN)

update_queue = Queue()

dispatcher = Dispatcher(
    bot,
    update_queue,
    workers=1,
    use_context=True
)


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text):
    """
    Detect Bengali or English.

    Bengali Unicode range:
    U+0980 - U+09FF
    """

    if not text:
        return "en"

    bengali_count = sum(
        1
        for char in text
        if "\u0980" <= char <= "\u09FF"
    )

    english_count = sum(
        1
        for char in text
        if ("A" <= char <= "Z")
        or ("a" <= char <= "z")
    )

    if bengali_count > 0:
        return "bn"

    if english_count > 0:
        return "en"

    # Default
    return "en"


# =========================================================
# TRANSLATION
# =========================================================

def translate_text(text):

    if not text:
        raise ValueError("Empty text.")

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

    last_error = None

    # Retry maximum 3 times
    for attempt in range(1, 4):

        try:

            translator = GoogleTranslator(
                source=source,
                target=target
            )

            result = translator.translate(text)

            if result and result.strip():

                logger.info(
                    f"Translation successful: {result[:150]}"
                )

                return result.strip()

            raise RuntimeError(
                "GoogleTranslator returned an empty result."
            )

        except Exception as e:

            last_error = e

            logger.warning(
                f"Translation attempt "
                f"{attempt}/3 failed: {e}"
            )

            if attempt < 3:
                time.sleep(2)

    raise RuntimeError(
        f"Translation failed after 3 attempts: {last_error}"
    )


# =========================================================
# START COMMAND
# =========================================================

def start(update, context):

    if not update.message:
        return

    try:

        update.message.reply_text(
            "👋 স্বাগতম!\n\n"
            "আমি English ↔ বাংলা অনুবাদ করতে পারি।\n\n"
            "English লিখুন → বাংলা পাবেন\n"
            "বাংলা লিখুন → English পাবেন\n\n"
            "উদাহরণ:\n"
            "Hello → হ্যালো\n"
            "আমি ভালো আছি → I am fine.\n\n"
            "শুধু আপনার লেখা পাঠান।"
        )

    except Exception as e:

        logger.exception(
            f"Start command error: {e}"
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
        f"Telegram message received: {text}"
    )

    try:

        translated = translate_text(text)

        update.message.reply_text(
            translated
        )

        logger.info(
            "Translation reply sent successfully."
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
# /TRANSLATE COMMAND
# =========================================================

def translate_command(update, context):

    if not update.message:
        return

    if not context.args:

        update.message.reply_text(
            "⚠️ অনুবাদ করার জন্য লেখা দিন।\n\n"
            "উদাহরণ:\n"
            "/translate Hello"
        )

        return

    text = " ".join(context.args).strip()

    logger.info(
        f"/translate request: {text}"
    )

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
            "❌ অনুবাদ করা যায়নি।\n"
            "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
        )


# =========================================================
# REGISTER HANDLERS
# =========================================================

dispatcher.add_handler(
    CommandHandler(
        "start",
        start
    )
)

dispatcher.add_handler(
    CommandHandler(
        "translate",
        translate_command
    )
)

dispatcher.add_handler(
    MessageHandler(
        Filters.text & ~Filters.command,
        handle_message
    )
)


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route(
    f"/{TOKEN}",
    methods=["POST"]
)
def webhook():

    logger.info(
        "Telegram webhook received."
    )

    try:

        data = request.get_json(
            force=True
        )

        if not data:

            logger.warning(
                "Webhook received empty JSON."
            )

            return "OK", 200

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
            f"Webhook processing error: {e}"
        )

        return "ERROR", 500


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return (
        "BD Translate Bot is live!",
        200
    )


# =========================================================
# SET TELEGRAM WEBHOOK
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

        # Verify webhook
        info = bot.get_webhook_info()

        logger.info(
            f"Webhook URL configured: "
            f"{info.url}"
        )

        logger.info(
            f"Pending updates: "
            f"{info.pending_update_count}"
        )

        if info.last_error_message:

            logger.error(
                f"Telegram last webhook error: "
                f"{info.last_error_message}"
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
# START SERVER
# =========================================================

if __name__ == "__main__":

    logger.info(
        f"Starting Flask server on port {PORT}..."
    )

    # Setup Telegram webhook
    setup_webhook()

    # Start Flask
    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
    )
