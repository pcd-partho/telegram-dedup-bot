import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]

seen_messages = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id
    text = msg.text.strip().lower()
    if chat_id not in seen_messages:
        seen_messages[chat_id] = set()
    if text in seen_messages[chat_id]:
        await msg.delete()
        logging.info(f"Deleted duplicate: {text[:30]}")
    else:
        seen_messages[chat_id].add(text)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))
app.run_polling()
