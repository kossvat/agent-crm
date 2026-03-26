# Agent CRM 🤖

CRM для управления командой AI-агентов — Telegram Mini App.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License](https://img.shields.io/badge/license-private-red)

## Что это

Панель управления AI-агентами через Telegram Mini App:
- **Dashboard** — статус системы, бюджет, графики расходов, алерты
- **Task Board** — канбан-доска с drag & drop (SortableJS)
- **Agents** — карточки агентов, смена моделей, статусы
- **Crons** — управление cron-задачами (вкл/выкл)
- **Journal** — ежедневный журнал работы агентов (Markdown)
- **Files** — просмотр файлов агентов (MEMORY.md, SOUL.md и т.д.)
- **Alerts** — система оповещений с приоритетами

## Стек

| Layer | Tech |
|-------|------|
| Backend | **FastAPI** + SQLAlchemy + SQLite |
| Frontend | Vanilla JS/CSS (Telegram Mini App SDK) |
| Auth | Telegram WebApp `initData` validation |
| Charts | Chart.js |
| Drag & Drop | SortableJS |
| Deploy | Cloudflare Tunnel → localhost |

## Структура

```
agent-crm/
├── backend/
│   ├── main.py           # FastAPI app, uvicorn entry
│   ├── config.py          # env config
│   ├── database.py        # SQLAlchemy setup
│   ├── models.py          # ORM models
│   ├── schemas.py         # Pydantic schemas
│   ├── auth.py            # Telegram auth middleware
│   ├── routers/           # API endpoints
│   │   ├── agents.py
│   │   ├── alerts.py
│   │   ├── costs.py
│   │   ├── crons.py
│   │   ├── dashboard.py
│   │   ├── files.py
│   │   ├── journal.py
│   │   ├── spending.py
│   │   ├── system.py
│   │   └── tasks.py
│   └── services/          # Business logic
│       ├── openclaw.py    # OpenClaw gateway integration
│       ├── sync.py        # Agent/cron sync
│       └── watchdog.py    # Spending watchdog
├── frontend/
│   ├── index.html         # SPA shell
│   ├── style.css          # Telegram theme-aware styles
│   └── app.js             # Router, views, API client
├── bot/                   # Telegram bot (Mini App launcher)
├── data/                  # SQLite DB (gitignored)
├── scripts/               # Utility scripts
└── requirements.txt
```

## Запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить .env
cp .env.example .env
# BOT_TOKEN=... SECRET_KEY=...

# 3. Запустить
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8100
```

Frontend раздаётся FastAPI как статика на `/`.

## API

Все эндпоинты: `GET /docs` (Swagger UI).

Основные:
- `GET /api/dashboard` — сводка
- `GET/POST/PATCH/DELETE /api/tasks` — задачи
- `GET /api/agents` — список агентов
- `GET /api/spending/current` — расходы
- `GET /api/alerts` — оповещения
- `POST /api/system/stop|resume|fix` — управление gateway

## Авторизация

В продакшене: Telegram Mini App `initData` валидируется через HMAC.
`DEV_MODE=true` отключает проверку для локальной разработки.

---

Built for [OpenClaw](https://openclaw.ai) agent teams.
