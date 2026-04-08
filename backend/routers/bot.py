"""Telegram Bot webhook handler — /start, deep links, Mini App launcher."""

import logging
import os
from fastapi import APIRouter, Request
import requests as http_requests

from backend.config import BOT_TOKEN

router = APIRouter(prefix="/api/bot", tags=["bot"])
log = logging.getLogger("agent-crm.bot")

CRM_URL = os.getenv("WEB_APP_URL", "http://localhost:8100")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))


def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    """Send a Telegram message."""
    if not BOT_TOKEN:
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10,
        )
    except Exception as e:
        log.error(f"Send message failed: {e}")


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates."""
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id", 0)
    text = message.get("text", "")

    # Only allow owner to use the bot
    if OWNER_TELEGRAM_ID and user_id != OWNER_TELEGRAM_ID:
        send_message(chat_id, "🔒 This is a private CRM instance.\n\nDeploy your own: github.com/kossvat/agent-crm")
        return {"ok": True}

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        invite_code = parts[1] if len(parts) > 1 else None

        if invite_code:
            # Deep link with invite code
            welcome = (
                f"🎉 <b>Welcome to AgentCRM!</b>\n\n"
                f"Your invite code: <code>{invite_code}</code>\n\n"
                f"Tap the button below to get started."
            )
            # Mini App URL with invite hint (will be read by frontend)
            app_url = f"{CRM_URL}#invite={invite_code}"
        else:
            welcome = (
                "🤖 <b>AgentCRM</b> — AI Agent Management Platform\n\n"
                "Track costs, manage tasks, and monitor your AI agent team — all in Telegram.\n\n"
                "Tap the button below to open the dashboard."
            )
            app_url = CRM_URL

        reply_markup = {
            "inline_keyboard": [[
                {
                    "text": "🚀 Open AgentCRM",
                    "web_app": {"url": app_url},
                }
            ]]
        }
        send_message(chat_id, welcome, reply_markup)

    elif text == "/help":
        help_text = (
            "📖 <b>AgentCRM Help</b>\n\n"
            "• /start — Open the CRM dashboard\n"
            "• /help — This message\n"
            "• /status — Quick system overview\n\n"
            "💡 Use the <b>Open CRM</b> menu button to launch the full app."
        )
        send_message(chat_id, help_text)

    elif text == "/status":
        status_text = (
            "📊 <b>Quick Status</b>\n\n"
            "Open the dashboard for full details:"
        )
        reply_markup = {
            "inline_keyboard": [[
                {
                    "text": "📊 Open Dashboard",
                    "web_app": {"url": CRM_URL},
                }
            ]]
        }
        send_message(chat_id, status_text, reply_markup)

    return {"ok": True}
