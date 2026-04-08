#!/home/caramel/.caldav-env/bin/python3
"""Telegram bot for Agent CRM — WebApp button."""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update, WebAppInfo, MenuButtonWebApp, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from backend.config import BOT_TOKEN

# Load dotenv explicitly before reading WEB_APP_URL
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
WEB_APP_URL = os.getenv("WEB_APP_URL", "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEB_APP_URL:
        await update.message.reply_text("⚠️ WEB_APP_URL not set. Run with WEB_APP_URL=https://...")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open Mission Control", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await update.message.reply_text(
        "**🤖 Agent CRM — Mission Control**\n\n"
        "Управляй командой AI агентов из Telegram.\n"
        "Нажми кнопку ниже:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def setup_menu_button(app: Application):
    """Set the bot's menu button to open the web app."""
    if WEB_APP_URL:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Mission Control", web_app=WebAppInfo(url=WEB_APP_URL))
        )


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set in .env")
        sys.exit(1)
    if not WEB_APP_URL:
        print("ERROR: WEB_APP_URL not set. Run with WEB_APP_URL=https://your-url")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.post_init = setup_menu_button

    print(f"Bot starting... WebApp URL: {WEB_APP_URL}")
    app.run_polling()


if __name__ == "__main__":
    main()
