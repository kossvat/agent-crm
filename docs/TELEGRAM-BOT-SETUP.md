# Telegram Bot & Mini App Setup

## 1. Create Bot (if not done)

```
/newbot → AgentCRM Bot → @agentcrm_bot
```

Save the bot token → `.env` as `BOT_TOKEN`.

## 2. Configure Mini App via BotFather

```
/mybots → @agentcrm_bot → Bot Settings → Menu Button
```

Set:
- **Menu button text:** `Open CRM`
- **Menu button URL:** `https://your-crm-domain.com`

This adds the "Open CRM" button in the bot chat that launches the Mini App.

## 3. Configure Web App URL

```
/mybots → @agentcrm_bot → Bot Settings → Web App
```

Set the Web App URL to: `https://your-crm-domain.com`

## 4. Bot Commands

```
/mybots → @agentcrm_bot → Edit Bot → Edit Commands
```

```
start - Open AgentCRM dashboard
help - How to use AgentCRM
invite - Check your invite code
status - Quick system status
```

## 5. Bot Welcome Message

The bot should handle `/start` with a welcome message + inline button to open the Mini App.

Add to backend — `bot_handler.py`:

```python
# POST /api/bot/webhook — Telegram webhook handler
# On /start:
#   - Send welcome message with InlineKeyboardButton(text="Open CRM", web_app=WebAppInfo(url=...))
# On /start <invite_code>:
#   - Deep link with invite code pre-filled
```

## 6. Webhook Setup (after deploy)

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://your-crm-domain.com/api/bot/webhook" \
  -d "allowed_updates=[\"message\",\"callback_query\"]"
```

Verify:
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

## 7. Deep Links for Invite Codes

Format: `https://t.me/agentcrm_bot?start=INVITE_A3F7B2C1`

The bot parses the start parameter, extracts the invite code, and opens the Mini App with it pre-filled.

This way you can share invite links like:
```
https://t.me/agentcrm_bot?start=A3F7B2C1
```

User clicks → bot opens → Mini App launches with invite code ready.

## 8. Bot Description & About

```
/mybots → @agentcrm_bot → Edit Bot
```

- **About:** `AI Agent Management Platform — track costs, manage tasks, monitor your agent team.`
- **Description:** `AgentCRM helps you manage your AI agent team. Track spending, organize tasks, monitor performance — all in Telegram.`
- **Description Picture:** Upload a branded image (1280x720)

## Checklist

- [ ] Bot created on BotFather
- [ ] BOT_TOKEN in `.env`
- [ ] Menu Button → `https://your-crm-domain.com`
- [ ] Web App URL set
- [ ] Bot commands registered
- [ ] Webhook configured (after deploy)
- [ ] Deep link invite flow tested
- [ ] Bot profile picture & description set
