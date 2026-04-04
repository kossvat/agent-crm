# agentcrm CLI

Universal CLI for [AI Agent CRM](https://myaiagentscrm.com) — works with **any** agent framework (OpenClaw, Hermes, LangChain, custom).

## Install

```bash
pip install agentcrm
# or from source:
pip install -e .
```

## Quick Start

### 1. Get your API key

Open CRM → Settings → Generate API Key (or ask your admin).

### 2. Login

```bash
agentcrm login
# Enter your CRM URL and API key
```

### 3. Sync agents

Create `~/.agentcrm/agents.json`:

```json
[
  {"name": "MyAgent", "emoji": "🤖", "role": "Assistant", "model": "gpt-4o"},
  {"name": "Coder", "emoji": "💻", "role": "Developer", "model": "claude-sonnet-4"}
]
```

```bash
agentcrm agents sync
```

### 4. Sync files

Organize files as `<dir>/<AgentName>/SOUL.md`:

```
agent-files/
├── MyAgent/
│   ├── SOUL.md
│   ├── IDENTITY.md
│   └── MEMORY.md
└── Coder/
    ├── SOUL.md
    └── IDENTITY.md
```

```bash
agentcrm files sync --dir ./agent-files
```

### 5. Push costs

```bash
agentcrm costs push --file costs.json
```

## Environment Variables

| Variable | Description |
|---|---|
| `AGENTCRM_API_KEY` | API key (overrides config file) |
| `AGENTCRM_URL` | CRM URL (default: https://myaiagentscrm.com) |

## Commands

| Command | Description |
|---|---|
| `agentcrm login` | Interactive login |
| `agentcrm status` | Check connection |
| `agentcrm agents list` | List agents |
| `agentcrm agents sync` | Sync agents from config |
| `agentcrm files sync` | Sync agent files |
| `agentcrm costs push` | Push spending data |
