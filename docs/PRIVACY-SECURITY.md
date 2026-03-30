# Privacy & Security

AgentCRM is designed with a **zero-knowledge architecture** for your agent conversations. We never see, store, or transmit the content of your AI conversations.

## What We Collect

The sync script running on your machine sends **only usage metrics** to the CRM server:

| Data | Example | Purpose |
|------|---------|---------|
| Agent name | `caramel` | Display in dashboard |
| Model used | `claude-opus-4-6` | Cost breakdown |
| Token counts | `input: 5000, output: 2000` | Usage tracking |
| Cost (USD) | `$0.45` | Budget monitoring |
| Session ID | `a1b2c3d4` (random UUID) | Dedup only, not linked to content |
| Timestamp | `2026-03-30T04:00:00Z` | Timeline charts |

## What We NEVER Collect

- ❌ **Conversation content** — prompts, responses, thinking — never leaves your machine
- ❌ **Files** — your documents, code, images stay local
- ❌ **API keys or tokens** — your Anthropic/OpenAI keys are never transmitted
- ❌ **OpenClaw config** — your `openclaw.json` is not read or sent
- ❌ **System files** — no access to your filesystem beyond OpenClaw session logs
- ❌ **Browsing history, contacts, or personal data**

## How It Works

```
YOUR MACHINE                          CRM SERVER
─────────────                         ──────────
OpenClaw agents ──► JSONL session logs
                         │
                    collect.py reads ONLY:
                    • token counts
                    • model name
                    • cost
                         │
                    ┌────▼─────┐
                    │ Ingest   │──► HTTPS ──► /api/ingest
                    │ payload: │              (token counts
                    │ numbers  │               + cost only)
                    │ only     │
                    └──────────┘

Conversation text is NEVER parsed, extracted, or transmitted.
```

## Data Isolation

- **Workspace isolation**: Every user's data is stored in a separate workspace. Database queries are always scoped to `workspace_id`. One user cannot see another user's data.
- **JWT authentication**: All API calls require a valid JWT token tied to your Telegram account and workspace.
- **Workspace tokens**: The sync script uses a dedicated `workspace_token` (not your personal JWT) with write-only access to the ingest endpoint.

## Your Data, Your Control

- **Open source**: The sync script (`agentcrm-sync`) is fully open source. You can audit every line of code that runs on your machine.
- **Self-hosted option**: You can run the entire CRM server on your own infrastructure. Same Docker image, full control.
- **Data deletion**: Request full data deletion at any time. We remove all usage records, agent configs, and workspace data.
- **No third-party sharing**: We do not sell, share, or provide your data to any third party.

## Security Measures

### Transport
- All data transmitted over **HTTPS/TLS** (encrypted in transit)
- Workspace tokens are signed JWTs with expiration

### Storage
- Database: PostgreSQL with workspace-level row isolation
- No plaintext secrets in the database
- Server access restricted to admin only

### Authentication
- Telegram Login Widget (cryptographic verification of `initData`)
- JWT tokens with configurable expiration
- No password storage (Telegram-only auth)

### Sync Script
- Runs **on your machine** — we don't have SSH or remote access
- Read-only access to OpenClaw session logs (`.jsonl` files)
- Write-only access to CRM ingest API (can push data, cannot read other data)
- Token stored with `chmod 600` (owner-read only)

## FAQ

**Q: Can AgentCRM read my AI conversations?**
A: No. The sync script only extracts numeric usage data (tokens, cost). Conversation content is never read or transmitted.

**Q: Can you access my machine?**
A: No. The sync script runs locally on your machine. We have no remote access, SSH, or backdoor.

**Q: What if I stop using AgentCRM?**
A: Uninstall the sync script, and no more data is sent. Request data deletion and we wipe everything.

**Q: Is the sync script open source?**
A: Yes. Full source code available for audit. You can see exactly what data is collected and sent.

**Q: Can other users see my data?**
A: No. Strict workspace isolation in the database. All queries are scoped by workspace_id.
