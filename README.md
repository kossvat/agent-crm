# Agent CRM

CRM for AI agent teams — Telegram Mini App.

## Quick Start

```bash
cd ~/projects/agent-crm

# Install deps
/home/caramel/.caldav-env/bin/pip install -r requirements.txt

# Copy and edit config
cp .env.example .env
# Set BOT_TOKEN from @BotFather

# Run (dev mode)
/home/caramel/.caldav-env/bin/python3 -m backend.main
```

Server starts on `http://127.0.0.1:8100`

## Architecture

```
Backend:  FastAPI + SQLAlchemy + SQLite
Frontend: Telegram Mini App (TWA), vanilla JS
Auth:     Telegram initData HMAC-SHA256
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/dashboard | Summary: agents, tasks, costs, alerts |
| GET | /api/agents | List agents |
| POST | /api/agents | Create agent |
| GET/POST/PATCH/DELETE | /api/tasks | Task CRUD |
| GET | /api/crons | List cron jobs |
| GET | /api/costs | Cost history |
| GET | /api/costs/summary | Cost summary by agent |
| GET | /api/alerts | Alert feed |
| PATCH | /api/alerts/{id}/read | Mark alert read |
| POST | /api/sync | Trigger OpenClaw sync |

## OpenClaw Integration

On startup, syncs:
- Agent configs from `~/.openclaw/agents/`
- Agent sessions (status, model, last active)
- Crontab entries

## Dev Mode

Set `DEV_MODE=true` in `.env` to skip Telegram auth (uses mock user).

## Telegram Mini App Setup

1. Talk to @BotFather, create a bot
2. `/newapp` → set Web App URL to your server
3. Set `BOT_TOKEN` in `.env`
4. Users open the bot → click "Open App" → TWA loads
