# AgentCRM

Self-hosted CRM for managing AI agent teams — Telegram Mini App.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

## What is this

A control panel for AI agent teams, delivered as a Telegram Mini App:

- **Dashboard** — system status, budget tracking, spend charts, alerts
- **Task Board** — kanban with drag & drop
- **Agents** — agent cards, model switching, status tracking
- **Costs** — per-agent spend tracking with rate limits
- **Crons** — manage scheduled jobs
- **Journal** — daily agent work logs (Markdown)
- **Files** — view agent files (MEMORY.md, SOUL.md, etc.)
- **Alerts** — notification system with priorities
- **Connect** — magic link flow to onboard remote agents
- **Invite System** — closed beta with invite codes

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + SQLAlchemy |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Frontend | Vanilla JS/CSS (Telegram Mini App SDK) |
| Auth | Telegram WebApp initData HMAC + JWT |
| Charts | Chart.js |
| Drag & Drop | SortableJS |
| Deploy | Docker Compose or systemd + Cloudflare Tunnel |

## Quick Start

### Option A: Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env with your values (BOT_TOKEN, SECRET_KEY, OWNER_TELEGRAM_ID)

docker compose up -d
```

### Option B: Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — at minimum set BOT_TOKEN, SECRET_KEY, OWNER_TELEGRAM_ID

# Run
uvicorn backend.main:app --host 127.0.0.1 --port 8100
```

Frontend is served by FastAPI as static files on `/`.

### Option C: PostgreSQL (production)

```bash
# Set DATABASE_URL in .env
DATABASE_URL=postgresql://agentcrm:yourpassword@localhost:5432/agentcrm

# Run with systemd, Docker, or directly
uvicorn backend.main:app --host 127.0.0.1 --port 8100
```

## Configuration

All config is via environment variables. See `.env.example` for the full list.

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `SECRET_KEY` | Yes | Random string for JWT signing (32+ bytes) |
| `OWNER_TELEGRAM_ID` | Yes | Your Telegram user ID (superadmin) |
| `DATABASE_URL` | No | PostgreSQL or SQLite connection string |
| `WEB_APP_URL` | No | Public URL for the Mini App |
| `DEV_MODE` | No | Set `true` to skip Telegram auth locally |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |
| `REQUIRE_INVITE` | No | Set `true` for closed beta mode |

## Project Structure

```
agent-crm/
  backend/
    main.py              # FastAPI app + startup
    config.py            # Environment config
    database.py          # SQLAlchemy setup (SQLite/PostgreSQL)
    models.py            # ORM models
    schemas.py           # Pydantic schemas
    auth.py              # Telegram auth + JWT
    plan_limits.py       # Tier-based rate limiting
    routers/             # API endpoints (19 routers)
    services/            # Business logic (sync, watchdog)
    middleware/           # Rate limiting
  frontend/
    index.html           # SPA shell
    style.css            # Telegram theme-aware styles
    app.js               # Router, views, API client
  bot/
    bot.py               # Telegram bot (Mini App launcher)
  scripts/               # Utility scripts
  tests/                 # 60+ tests
  alembic/               # Database migrations
  docker-compose.yml     # Full stack with PostgreSQL
  Dockerfile
```

## API

Interactive docs at `GET /docs` (Swagger UI).

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard` | System overview |
| GET/POST/PATCH/DELETE | `/api/tasks` | Task management |
| GET/POST | `/api/agents` | Agent registry |
| POST | `/api/ingest` | Push usage data (agent → CRM) |
| GET | `/api/spending/current` | Cost analytics |
| GET | `/api/alerts` | Notifications |
| POST | `/api/connect/generate` | Magic link for remote agents |
| GET | `/api/journal` | Agent work logs |

## Architecture

**Push-based**: agents push data to CRM via `/api/ingest`, CRM doesn't poll agents.

**Multi-tenant**: workspace isolation via JWT. Each user gets their own workspace with tier-based limits.

**Auth flow**: Telegram Mini App → initData HMAC validation → JWT → workspace-scoped access.

**Cost tracking**: per-model pricing with session and weekly rate limits.

## Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Set the bot token in `.env`
3. Configure the Mini App URL in BotFather (your public domain)
4. Set `OWNER_TELEGRAM_ID` to your Telegram user ID
5. Start the app — bot will set up the menu button automatically

## License

MIT License. See [LICENSE](LICENSE).

## Credits

Built by [AgentForgeAI](https://agent-forge-ai.com).
