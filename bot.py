import os
import logging
from telegram.ext import Updater, MessageHandler, Filters

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]

seen_messages = {}

def handle_message(update, context):
    msg = update.message or update.channel_post
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id
    text = msg.text.strip().lower()
    if chat_id not in seen_messages:
        seen_messages[chat_id] = set()
    if text in seen_messages[chat_id]:
        msg.delete()
    else:
        seen_messages[chat_id].add(text)

updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text, handle_message))
updater.start_polling()
updater.idle()
