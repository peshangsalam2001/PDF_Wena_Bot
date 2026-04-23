import os
import time
import json
import threading
from datetime import datetime
from threading import Thread

import telebot
from telebot import types
from PIL import Image
import fitz  # PyMuPDF
from flask import Flask

# === CONFIG ===
API_TOKEN = '7797825619:AAFpZfVlP74eIxJCFG9VKV3GlnGObMr-A0o'
CHANNEL_USERNAME = '@PeshangAcademy'
ADMIN_CONTACT_LINK = 'https://t.me/MasterLordBoss'
BOT_OWNER_ID = 1908245207
STATS_FILE = 'bot_stats.json'

bot = telebot.TeleBot(API_TOKEN)

# Media buffers
media_group_buffers = {}
last_media_time = {}

# === Flask Keep Alive ===
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run_flask, daemon=True).start()


# === Stats ===
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {
            "total_users": 0,
            "monthly_users": {},
            "new_users_this_month": []
        }
    with open(STATS_FILE, 'r') as f:
        return json.load(f)

def save_stats(stats):
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)

def update_user_stats(user_id):
    stats = load_stats()
    month = datetime.now().strftime("%Y-%m")

    user_id_str = str(user_id)

    if user_id_str not in stats["new_users_this_month"]:
        stats["total_users"] += 1
        stats["new_users_this_month"].append(user_id_str)

    stats["monthly_users"].setdefault(month, [])
    if user_id_str not in stats["monthly_users"][month]:
        stats["monthly_users"][month].append(user_id_str)

    save_stats(stats)

def get_stats():
    stats = load_stats()
    month = datetime.now().strftime("%Y-%m")

    total = stats.get('total_users', 0)
    monthly = len(stats.get('monthly_users', {}).get(month, []))
    new_this_month = len(stats.get("new_users_this_month", []))

    return total, monthly, new_this_month


# === Subscription Check ===
def is_user_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'creator', 'administrator']
    except Exception:
        return False


# === Helpers ===
def send_join_message(chat_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "سەردانی کەناڵەکەمان بکە ❤️",
        url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
    ))
    bot.send_message(
        chat_id,
        "👋 تکایە سەردانی کەناڵەکەمان بکە بۆ بەکارهێنانی بۆتەکە",
        reply_markup=kb
    )

def send_error(chat_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "🧑🏻‍💻 پەیوەندی بکە بە خاوەنی بۆت",
        url=ADMIN_CONTACT_LINK
    ))
    bot.send_message(
        chat_id,
        "⚠ ببورە کێشەیەکی تەکنیکی هەیە لە بۆتەکە",
        reply_markup=kb
    )


# === Commands ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    update_user_stats(user_id)

    if not is_user_subscribed(user_id):
        send_join_message(chat_id)
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "سەردانی کەناڵەکەمان بکە ❤️",
        url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
    ))

    bot.send_message(
        chat_id,
        "👋 بەخێربێیت بۆ بۆتی گۆڕینی وێنە بۆ پی دی ئێف و پی دی ئێف بۆ وێنە\n\n"
        "🚀 ئەم بۆتە ئەم دوو ئەرکەی هەیە:\n\n"
        "- فایلی پی دی ئێف بنێرە تاکو بیکەم بە وێنە\n"
        "- وێنە بنێرە تاکو بیکەم بە فایلێکی پی دی ئێف",
        reply_markup=kb
    )

@bot.message_handler(commands=['info'])
def handle_info(message):
    if message.from_user.id != BOT_OWNER_ID:
        return

    total, monthly, new_this_month = get_stats()

    bot.send_message(
        message.chat.id,
        f"📊 ئاماری بۆت:\n"
        f"- 👥 کۆی بەکارهێنەرەکان: {total}\n"
        f"- 📅 بەکارهێنەری ئەم مانگە: {monthly}\n"
        f"- 🆕 بەکارهێنەری نوێی ئەم مانگە: {new_this_month}"
    )


# === Photo Handling ===
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_user_subscribed(user_id):
        return

    media_group_id = message.media_group_id

    if media_group_id:
        media_group_buffers.setdefault(media_group_id, []).append(message)
        last_media_time[media_group_id] = time.time()

        bot.send_message(
            chat_id,
            f"🖼 وێنەی {len(media_group_buffers[media_group_id])} وەرگیرا"
        )
    else:
        bot.send_message(chat_id, "🖼 وێنەی یەکەم وەرگیرا")
        process_images_to_pdf(chat_id, [message.photo[-1].file_id])


def media_group_watcher():
    while True:
        time.sleep(2)
        now = time.time()

        expired = [
            gid for gid, t in last_media_time.items()
            if now - t > 2
        ]

        for gid in expired:
            msgs = media_group_buffers.pop(gid, [])
            last_media_time.pop(gid, None)

            file_ids = [m.photo[-1].file_id for m in msgs]
            process_images_to_pdf(msgs[0].chat.id, file_ids)


def process_images_to_pdf(chat_id, file_ids):
    try:
        images = []

        for fid in file_ids:
            file_info = bot.get_file(fid)
            downloaded = bot.download_file(file_info.file_path)

            temp_path = f"temp_{fid}.jpg"
            with open(temp_path, 'wb') as f:
                f.write(downloaded)

            img = Image.open(temp_path).convert('RGB')
            images.append(img)
            os.remove(temp_path)

        pdf_path = f"output_{chat_id}.pdf"
        images[0].save(pdf_path, save_all=True, append_images=images[1:])

        with open(pdf_path, 'rb') as pdf:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(
                "سەردانی کەناڵەکەمان بکە ❤️",
                url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
            ))

            bot.send_document(
                chat_id,
                pdf,
                caption="📄 فەرموو ئەمە فایلی پی دی ئێفەکەتە",
                reply_markup=kb
            )

        os.remove(pdf_path)

    except Exception:
        send_error(chat_id)


# === PDF Handling ===
@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_user_subscribed(user_id):
        return

    if message.document.mime_type != 'application/pdf':
        bot.send_message(chat_id, "🔄 تکایە وێنە یاخود فایلی پی دی ئێف بنێرە")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        pdf_path = f"input_{chat_id}.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(downloaded)

        doc = fitz.open(pdf_path)

        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_path = f"page_{i}_{chat_id}.png"
            pix.save(img_path)

            with open(img_path, 'rb') as img:
                bot.send_photo(chat_id, img, caption=f"🖼 وێنەی {i + 1}")

            os.remove(img_path)

        doc.close()
        os.remove(pdf_path)

    except Exception:
        send_error(chat_id)


# === Fallback ===
@bot.message_handler(func=lambda m: True)
def handle_other(message):
    if is_user_subscribed(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "🔄 تکایە وێنە یاخود فایلی پی دی ئێف بنێرە"
        )


# === Start ===
keep_alive()
threading.Thread(target=media_group_watcher, daemon=True).start()
bot.infinity_polling()
