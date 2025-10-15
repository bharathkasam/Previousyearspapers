"""
CBIT Previous Question Paper Telegram Bot
------------------------------------------
Searches and sends CBIT previous-year papers when students send "Subject Year".
Hosting: works perfectly on Render / Railway / Replit.

To run:
1. pip install -r requirements.txt
2. python cbit_paper_bot.py
"""

import re
import io
import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ------------------ CONFIG ------------------
BOT_TOKEN = "PASTE_YOUR_TOKEN_HERE"  # <--- replace this with your full token

BASE_URL = "https://www.cbit.ac.in/current_students/previous-question-papers/"
INDEX_PAGES = [
    BASE_URL,
    "https://www.cbit.ac.in/current_students/academic-year-2023-2024-question-papers/",
]
SPDC_ROOT = "https://spdc.cbit.org.in/"
MAX_STREAM_BYTES = 45 * 1024 * 1024
# --------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "CBITPaperBot/1.0"})

def normalize(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')

def attempt_direct_patterns(subject, year):
    s_norm = normalize(subject)
    candidates = [
        f"{BASE_URL.rstrip('/')}/{year}/{s_norm}.pdf",
        f"{BASE_URL.rstrip('/')}/{s_norm}_{year}.pdf",
        f"{SPDC_ROOT}{s_norm}_{year}.pdf",
        f"{SPDC_ROOT}{year}/{s_norm}.pdf"
    ]
    for url in candidates:
        try:
            r = session.head(url, allow_redirects=True, timeout=5)
            if r.status_code == 200 and 'pdf' in r.headers.get('Content-Type', '').lower():
                return url
        except Exception:
            continue
    return None

def scrape_for_pdf(subject, year):
    keywords = [normalize(subject), subject.lower(), year]
    for page in INDEX_PAGES:
        try:
            r = session.get(page, timeout=10)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all("a", href=True):
                href = a['href']
                if ".pdf" in href.lower():
                    full = urljoin(page, href)
                    low = full.lower()
                    if year in low and any(k in low for k in [normalize(subject), subject.lower()]):
                        return full
        except Exception:
            continue
    return None

def safe_get_pdf_stream(url):
    try:
        r = session.get(url, stream=True, timeout=15)
        if r.status_code != 200:
            return None, None
        total = int(r.headers.get("Content-Length", 0))
        if total and total > MAX_STREAM_BYTES:
            return None, None
        bio = io.BytesIO()
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                bio.write(chunk)
                if bio.tell() > MAX_STREAM_BYTES:
                    return None, None
        bio.seek(0)
        fname = urlparse(url).path.split("/")[-1]
        return bio, fname
    except Exception:
        return None, None

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Hi! Send me the *subject name* and *year* (e.g. `DBMS 2023`) "
        "to get the CBIT previous question paper.",
        parse_mode="Markdown"
    )

def handle(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    year_match = re.search(r'(20\d{2}|19\d{2})', text)
    year = year_match.group(1) if year_match else ""
    subject = text.replace(year, "").strip() if year else text
    if not subject:
        update.message.reply_text("Please use format: `Subject Year` (e.g. DBMS 2022)", parse_mode="Markdown")
        return

    update.message.reply_text(f"🔍 Searching for *{subject}* ({year or 'any year'})...", parse_mode="Markdown")
    url = attempt_direct_patterns(subject, year) or scrape_for_pdf(subject, year)

    if not url:
        update.message.reply_text("❌ Paper not found! It may not be uploaded yet.")
        return

    bio, fname = safe_get_pdf_stream(url)
    if bio:
        try:
            update.message.reply_chat_action("upload_document")
            update.message.reply_document(document=bio, filename=fname)
            return
        except Exception:
            pass

    update.message.reply_text(f"✅ Found paper link:\n{url}")

def main():
    bot = Bot(token=BOT_TOKEN)
    updater = Updater(bot=bot, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
