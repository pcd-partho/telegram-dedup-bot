import os
import logging
import threading
import time
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
MONGO_URL = os.environ["MONGO_URL"]

client = MongoClient(MONGO_URL)
db = client["nocopybot"]
seen_col = db["seen_messages"]
watchlist_col = db["watchlist"]
stats_col = db["stats"]
active_col = db["active"]

AUTO_DELETE_PHRASES = [
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
    "nocopy stats",
    "payment failed",
    "not enough funds",
    "tmh",
    "top-up your balance",
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

def delete_message_after_delay(context, chat_id, message_id, delay=30):
    def _delete():
        time.sleep(delay)
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logging.warning(f"Could not delete: {e}")
    thread = threading.Thread(target=_delete)
    thread.daemon = True
    thread.start()

def is_seen(chat_id, content_hash):
    return seen_col.find_one({"chat_id": chat_id, "hash": content_hash}) is not None

def mark_seen(chat_id, content_hash):
    seen_col.update_one(
        {"chat_id": chat_id, "hash": content_hash},
        {"$set": {"chat_id": chat_id, "hash": content_hash}},
        upsert=True
    )

def get_message_hash(msg):
    if msg.document:
        return f"doc_{msg.document.file_unique_id}"
    elif msg.video:
        return f"vid_{msg.video.file_unique_id}"
    elif msg.photo:
        return f"photo_{msg.photo[-1].file_unique_id}"
    elif msg.audio:
        return f"audio_{msg.audio.file_unique_id}"
    elif msg.text:
        return f"text_{msg.text.strip().lower()}"
    return None

def get_deleted_count(chat_id):
    doc = stats_col.find_one({"chat_id": chat_id})
    return doc["count"] if doc else 0

def increment_deleted(chat_id):
    stats_col.update_one(
        {"chat_id": chat_id},
        {"$inc": {"count": 1}},
        upsert=True
    )

def is_active(chat_id):
    doc = active_col.find_one({"chat_id": chat_id})
    return doc["active"] if doc else True

def set_active(chat_id, value):
    active_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"active": value}},
        upsert=True
    )

def get_watchlist(chat_id):
    doc = watchlist_col.find_one({"chat_id": chat_id})
    if not doc:
        return {"movies": [], "series": [], "upcoming": [], "leftover": []}
    return doc

def save_watchlist(chat_id, wl):
    watchlist_col.update_one(
        {"chat_id": chat_id},
        {"$set": wl},
        upsert=True
    )

def start(update, context):
    chat_id = update.effective_chat.id
    set_active(chat_id, True)
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='stats'),
         InlineKeyboardButton("ℹ️ Status", callback_data='status')],
        [InlineKeyboardButton("🔴 Stop NoCopy", callback_data='stop'),
         InlineKeyboardButton("🟢 Start NoCopy", callback_data='start')],
        [InlineKeyboardButton("📋 My Watchlist", callback_data='watchlist')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "🚫 *Welcome to NoCopy Bot!*\n\n"
        "I delete duplicates & manage your watchlist!\n\n"
        "Use the menu below:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def show_watchlist(chat_id, context, query=None):
    wl = get_watchlist(chat_id)
    text = "📋 *My Watchlist*\n\n"
    categories = [
        ("🎬 Movies", "movies"),
        ("📺 Series", "series"),
        ("⏳ Upcoming", "upcoming"),
        ("⏸️ Left Over", "leftover")
    ]
    keyboard = []
    has_items = False
    for cat_name, cat_key in categories:
        items = wl.get(cat_key, [])
        if items:
            has_items = True
            text += f"{cat_name}:\n"
            for i, item in enumerate(items):
                status = "✅" if item.get("watched") else "🔲"
                text += f"{status} {item['name']}\n"
                if not item.get("watched"):
                    keyboard.append([
                        InlineKeyboardButton(
                            f"✅ Watched: {item['name'][:20]}",
                            callback_data=f"watched_{cat_key}_{i}"
                        )
                    ])
            text += "\n"
    if not has_items:
        text += "Nothing added yet!\n\nForward any movie/series message to add it! 😊"
    keyboard.append([InlineKeyboardButton("🗑️ Clear Watched", callback_data='clear_watched')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        msg = context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode='Markdown', reply_markup=reply_markup
        )
        delete_message_after_delay(context, chat_id, msg.message_id, delay=30)

def stop_cmd(update, context):
    chat_id = update.effective_chat.id
    set_active(chat_id, False)
    update.message.reply_text("🔴 *NoCopy is now STOPPED!*", parse_mode='Markdown')

def status_cmd(update, context):
    chat_id = update.effective_chat.id
    state = "🟢 ACTIVE" if is_active(chat_id) else "🔴 STOPPED"
    update.message.reply_text(f"ℹ️ *NoCopy Status:* {state}", parse_mode='Markdown')

def stats_cmd(update, context):
    chat_id = update.effective_chat.id
    count = get_deleted_count(chat_id)
    update.message.reply_text(
        f"📊 *NoCopy Stats*\n\n🗑️ Duplicates deleted: *{count}*",
        parse_mode='Markdown'
    )

def watchlist_cmd(update, context):
    chat_id = update.effective_chat.id
    show_watchlist(chat_id, context)

def handle_forward(update, context):
    msg = update.message or update.channel_post
    if not msg:
        return
    is_forwarded = (msg.forward_from or msg.forward_from_chat or msg.forward_date)
    has_media = (msg.document or msg.video or msg.audio or msg.photo)
    if is_forwarded or has_media:
        name = ""
        if msg.caption:
            name = msg.caption[:50]
        elif msg.text:
            name = msg.text[:50]
        elif msg.document and msg.document.file_name:
            name = msg.document.file_name[:50]
        elif msg.video:
            name = msg.caption[:50] if msg.caption else "Video File"
        else:
            name = "Media File"
        keyboard = [
            [
                InlineKeyboardButton("🎬 Movie", callback_data=f"add_movies_{name}"),
                InlineKeyboardButton("📺 Series", callback_data=f"add_series_{name}"),
            ],
            [
                InlineKeyboardButton("⏳ Upcoming", callback_data=f"add_upcoming_{name}"),
                InlineKeyboardButton("⏸️ Left Over", callback_data=f"add_leftover_{name}"),
            ],
            [InlineKeyboardButton("❌ Skip", callback_data="skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg.reply_text(
            f"📋 *Add to Watchlist?*\n\n`{name}`\n\nChoose category:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

def handle_message(update, context):
    msg = update.message or update.channel_post
    if not msg:
        return
    chat_id = msg.chat_id
    if not is_active(chat_id):
        return
    is_forwarded = (msg.forward_from or msg.forward_from_chat or msg.forward_date)
    has_media = (msg.document or msg.video or msg.audio or msg.photo)
    if is_forwarded or has_media:
        handle_forward(update, context)
        content_hash = get_message_hash(msg)
        if content_hash:
            if is_seen(chat_id, content_hash):
                try:
                    msg.delete()
                    increment_deleted(chat_id)
                except:
                    pass
            else:
                mark_seen(chat_id, content_hash)
        return
    if msg.text:
        text = msg.text.strip().lower()
        if text.startswith('/'):
            return
        if should_auto_delete(text):
            delete_after_delay(msg, delay=30)
            return
        content_hash = get_message_hash(msg)
        if content_hash:
            if is_seen(chat_id, content_hash):
                try:
                    msg.delete()
                    increment_deleted(chat_id)
                except:
                    pass
            else:
                mark_seen(chat_id, content_hash)

def button(update, context):
    query = update.callback_query
    query.answer()
    chat_id = query.message.chat_id
    if query.data == 'stats':
        count = get_deleted_count(chat_id)
        query.edit_message_text(
            f"📊 *NoCopy Stats*\n\n🗑️ Duplicates deleted: *{count}*",
            parse_mode='Markdown'
        )
    elif query.data == 'status':
        state = "🟢 ACTIVE" if is_active(chat_id) else "🔴 STOPPED"
        query.edit_message_text(f"ℹ️ *NoCopy Status:* {state}", parse_mode='Markdown')
    elif query.data == 'stop':
        set_active(chat_id, False)
        query.edit_message_text("🔴 *NoCopy is now STOPPED!*", parse_mode='Markdown')
    elif query.data == 'start':
        set_active(chat_id, True)
        query.edit_message_text("🟢 *NoCopy is now ACTIVE!*", parse_mode='Markdown')
    elif query.data == 'watchlist':
        show_watchlist(chat_id, context, query=query)
    elif query.data.startswith('add_'):
        parts = query.data.split('_', 2)
        cat_key = parts[1]
        name = parts[2] if len(parts) > 2 else "Unknown"
        wl = get_watchlist(chat_id)
        if cat_key not in wl:
            wl[cat_key] = []
        wl[cat_key].append({"name": name, "watched": False})
        save_watchlist(chat_id, wl)
        cat_names = {
            "movies": "🎬 Movies",
            "series": "📺 Series",
            "upcoming": "⏳ Upcoming",
            "leftover": "⏸️ Left Over"
        }
        query.edit_message_text(
            f"✅ *Added to {cat_names[cat_key]}!*\n\n`{name}`",
            parse_mode='Markdown'
        )
    elif query.data.startswith('watched_'):
        parts = query.data.split('_', 2)
        cat_key = parts[1]
        idx = int(parts[2])
        wl = get_watchlist(chat_id)
        if idx < len(wl.get(cat_key, [])):
            wl[cat_key][idx]["watched"] = True
        save_watchlist(chat_id, wl)
        show_watchlist(chat_id, context, query=query)
    elif query.data == 'clear_watched':
        wl = get_watchlist(chat_id)
        for cat in ["movies", "series", "upcoming", "leftover"]:
            wl[cat] = [item for item in wl.get(cat, []) if not item.get("watched")]
        save_watchlist(chat_id, wl)
        show_watchlist(chat_id, context, query=query)
    elif query.data == 'skip':
        query.edit_message_text("❌ *Skipped!*", parse_mode='Markdown')

updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("stop", stop_cmd))
dp.add_handler(CommandHandler("status", status_cmd))
dp.add_handler(CommandHandler("stats", stats_cmd))
dp.add_handler(CommandHandler("watchlist", watchlist_cmd))
dp.add_handler(CallbackQueryHandler(button))
dp.add_handler(MessageHandler(Filters.all, handle_message))
updater.start_polling()
updater.idle()
