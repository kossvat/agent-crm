"""Application configuration from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Telegram bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")

# Database
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'crm.db'}")

# OpenClaw
OPENCLAW_BIN: str = os.getenv("OPENCLAW_BIN", "/home/caramel/.npm-global/bin/openclaw")
OPENCLAW_DIR: str = os.getenv("OPENCLAW_DIR", str(Path.home() / ".openclaw"))

# Server
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8100"))
