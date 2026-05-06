import os
import logging
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import threading
import time

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]

seen_messages = {}
deleted_count = {}
is_active = {}

AUTO_DELETE_PHRASES = [
    "📊 nocopy stats",
    "i could not find the file you requested",
    "is the movie you asked about released ott",
    "pay attention to the following",
    "ask for correct spelling",
    "do not ask for movies that are not released",
    "sorry no files were found for your request",
    "check your spelling in google and try again",
    "movie request format",
    "series request format",
    "dont use",
]

def should_auto_delete(text):
    text_lower = text.lower().strip()
    for phrase in AUTO_DELETE_PHRASES:
        if phrase in text_lower:
            return True
    return False

def delete_after_delay(msg, delay=30):
    def _delete():
        time.sleep(delay)
        try:
            msg.delete()
        except Exception as e:
            logging.warning(f"Could not delete: {e}")
    thread = threading.Thread(target=_delete)
    thread.daemon = True
    thread.start()

def start(update, context):
    chat_id = update.effective_chat.id
    is_active[chat_id] = True
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='stats'),
         InlineKeyboardButton("ℹ️ Status", callback_data='status')],
        [InlineKeyboardButton("🔴 Stop NoCopy", callback_data='stop'),
         InlineKeyboardButton("🟢 Start NoCopy", callback_data='start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "🚫 *Welcome to NoCopy Bot!*\n\n"
        "I automatically delete duplicate messages!\n\n"
        "Use the menu below to control me:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def stop(update, context):
    chat_id = update.effective_chat.id
    is_active[chat_id] = False
    update.message.reply_text(
        "🔴 *NoCopy is now STOPPED!*\n\nDuplicates will no longer be deleted.",
        parse_mode='Markdown'
    )

def status(update, context):
    chat_id = update.effective_chat.id
    active = is_active.get(chat_id, True)
    state = "🟢 ACTIVE" if active else "🔴 STOPPED"
    update.message.reply_text(
        f"ℹ️ *NoCopy Status:* {state}",
        parse_mode='Markdown'
    )

def stats(update, context):
    chat_id = update.effective_chat.id
    count = deleted_count.get(chat_id, 0)
    update.message.reply_text(
        f"📊 *NoCopy Stats*\n\n🗑️ Duplicates deleted: *{count}*",
        parse_mode='Markdown'
    )

def handle_message(update, context):
    msg = update.message or update.channel_post
    if not msg or not msg.text:
        return
    chat_id = msg.chat_id
    if not is_active.get(chat_id, True):
        return
    text = msg.text.strip().lower()
    if text.startswith('/'):
        return

    if should_auto_delete(text):
        delete_after_delay(msg, delay=30)
        return

    if chat_id not in seen_messages:
        seen_messages[chat_id] = set()
    if text in seen_messages[chat_id]:
        msg.delete()
        deleted_count[chat_id] = deleted_count.get(chat_id, 0) + 1
    else:
        seen_messages[chat_id].add(text)

def button(update, context):
    query = update.callback_query
    query.answer()
    chat_id = query.message.chat_id
    if query.data == 'stats':
        count = deleted_count.get(chat_id, 0)
        query.edit_message_text(
            f"📊 *NoCopy Stats*\n\n🗑️ Duplicates deleted: *{count}*",
            parse_mode='Markdown'
        )
    elif query.data == 'status':
        active = is_active.get(chat_id, True)
        state = "🟢 ACTIVE" if active else "🔴 STOPPED"
        query.edit_message_text(
            f"ℹ️ *NoCopy Status:* {state}",
            parse_mode='Markdown'
        )
    elif query.data == 'stop':
        is_active[chat_id] = False
        query.edit_message_text(
            "🔴 *NoCopy is now STOPPED!*",
            parse_mode='Markdown'
        )
    elif query.data == 'start':
        is_active[chat_id] = True
        query.edit_message_text(
            "🟢 *NoCopy is now ACTIVE!*",
            parse_mode='Markdown'
        )

updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("stop", stop))
dp.add_handler(CommandHandler("status", status))
dp.add_handler(CommandHandler("stats", stats))
dp.add_handler(CallbackQueryHandler(button))
dp.add_handler(MessageHandler(Filters.text, handle_message))
updater.start_polling()
updater.idle()
