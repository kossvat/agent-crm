# Platform Support

AgentCRM works anywhere OpenClaw runs. The CRM itself is a web app (Telegram Mini App) — no install needed. The **agent-side sync** (spending tracker + task sync) runs on the same machine as your OpenClaw instance.

## Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| **Linux** (Ubuntu, Debian, etc.) | ✅ Full support | Native. Recommended for servers/VPS. |
| **macOS** (Intel & Apple Silicon) | ✅ Full support | Mac Mini as always-on server works great. Disable sleep in System Settings → Energy. |
| **Windows (WSL2)** | ✅ Works | OpenClaw requires WSL2. CRM sync runs inside WSL2 alongside OpenClaw. |
| **Windows (native)** | ❌ Not supported | OpenClaw doesn't run natively on Windows. Use WSL2. |
| **Docker** | ✅ Full support | CRM server runs in Docker. Agent sync can also run in a container. |

## Setup by Platform

### Linux / macOS

Standard setup — everything works out of the box:

```bash
# Install sync (via magic link from CRM)
# The agent handles setup automatically

# Manual cron (if needed):
crontab -e
# */5 * * * * cd ~/projects/agentcrm-sync && python3 sync.py >> /tmp/crm-sync.log 2>&1
```

### macOS — Prevent Sleep

If using Mac Mini as a server, ensure it doesn't sleep:

```
System Settings → Energy → Prevent automatic sleeping when the display is off → ON
```

Alternatively, use `caffeinate` or a launchd plist for guaranteed execution.

### Windows (WSL2)

OpenClaw runs inside WSL2, so CRM sync must also run inside WSL2:

```powershell
# From PowerShell — ensure WSL2 is set up:
wsl --install
wsl --set-default-version 2
```

```bash
# Inside WSL2 terminal — everything is standard Linux:
# OpenClaw is here, sync runs here, cron works here.

# Enable systemd (for cron reliability):
# Edit /etc/wsl.conf:
[boot]
systemd=true

# Then restart WSL:
# (from PowerShell) wsl --shutdown
```

**Important:** Do NOT run the sync from Windows CMD/PowerShell directly. It must run inside WSL2 where OpenClaw lives.

#### WSL2 Gotchas

1. **WSL may stop** when all terminals are closed. Enable systemd (above) or use `wsl --exec` from Task Scheduler for persistent cron.
2. **Paths:** `~/.openclaw/` inside WSL = `/home/username/.openclaw/`. This is different from the Windows filesystem. The sync script handles this automatically when run inside WSL.
3. **Memory:** WSL2 defaults to 50% of system RAM. For OpenClaw + CRM sync, 4GB is plenty. Adjust in `%UserProfile%\.wslconfig` if needed.

## Architecture

```
┌─────────────────────────────┐
│  Your Machine               │
│  (Linux / macOS / WSL2)     │
│                             │
│  OpenClaw ← agents run here │
│  agentcrm-sync ← collects   │
│    spending data + pushes    │
│    to CRM server             │
└──────────┬──────────────────┘
           │ HTTPS (Ingest API)
           ▼
┌─────────────────────────────┐
│  CRM Server (our infra)     │
│  Docker: FastAPI + PostgreSQL│
│                             │
│  Dashboard, Kanban, Alerts  │
│  via Telegram Mini App      │
└─────────────────────────────┘
```

The CRM server is platform-independent (Docker). Only the agent-side sync needs to match where OpenClaw runs.
