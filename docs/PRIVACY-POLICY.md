# Privacy Policy

**AgentCRM** — AI Agent Management Platform
Last updated: March 30, 2026

This Privacy Policy describes how AgentCRM ("we", "us", "our") collects, uses, and protects your information when you use our Service.

## 1. Information We Collect

### 1.1 Account Information
- **Telegram ID** — used as your unique account identifier
- **Telegram display name** — shown in the dashboard
- **Workspace name** — chosen by you during onboarding

### 1.2 Usage Metrics (via Sync Script)
The sync script running on your machine sends the following data:
- **Agent names** — names of your AI agents (e.g., "caramel", "sixteen")
- **Model names** — AI models used (e.g., "claude-opus-4-6")
- **Token counts** — input/output token quantities (numbers only)
- **Cost in USD** — calculated spending amounts
- **Timestamps** — when activity occurred
- **Session IDs** — random UUIDs for deduplication (not linked to content)

### 1.3 Task & Configuration Data
- Task titles, descriptions, statuses, and assignments you create in the CRM
- Cron job configurations
- Journal entries you write

### 1.4 Technical Data
- IP address (for rate limiting, not stored long-term)
- Request timestamps (server logs, retained 30 days)

## 2. Information We NEVER Collect

We want to be explicit about what we do NOT have access to:

- ❌ **AI conversation content** — prompts, responses, thinking traces
- ❌ **Your files** — documents, code, images on your machine
- ❌ **API keys or tokens** — your Anthropic, OpenAI, or other provider credentials
- ❌ **OpenClaw configuration** — your `openclaw.json` or agent configs
- ❌ **Browsing history, contacts, location, or device identifiers**
- ❌ **Data from other apps on your device**

The sync script is auditable Python code on your machine. You can verify exactly what data is collected and transmitted.

## 3. How We Use Your Information

| Purpose | Data Used |
|---------|-----------|
| Display your dashboard | Agent names, costs, token counts |
| Budget tracking & alerts | Costs, model usage |
| Task management | Task data you create |
| Authentication | Telegram ID |
| Rate limiting & abuse prevention | IP address (not stored) |
| Service improvement | Aggregate, anonymized usage patterns |

We do **not** use your data for:
- Advertising or ad targeting
- Selling to third parties
- Training AI models
- Profiling or behavioral tracking

## 4. Data Storage & Security

- **Location**: Our servers are hosted on DigitalOcean (US data centers)
- **Database**: PostgreSQL with workspace-level row isolation
- **Transit**: All data encrypted via HTTPS/TLS
- **Access**: Server access restricted to administrators only
- **Backups**: Regular database backups, encrypted at rest

### Workspace Isolation
Every user's data is stored in a separate workspace. All database queries are scoped by `workspace_id`. One user cannot access, view, or modify another user's data.

## 5. Data Sharing

We do **not** sell, rent, or share your personal data with third parties, except:

- **Payment processor** (Lemon Squeezy) — receives only payment information you provide directly to them, not your CRM data
- **Law enforcement** — only if required by valid legal process (subpoena, court order)
- **Service providers** — hosting (DigitalOcean) has access to server infrastructure but not application-level data

## 6. Data Retention

- **Active accounts**: Data retained as long as your account is active
- **Deleted accounts**: All data permanently deleted within 30 days of account deletion
- **Server logs**: IP addresses and request logs retained for 30 days, then purged
- **Backups**: Deleted data may persist in encrypted backups for up to 90 days

## 7. Your Rights

You have the right to:

- **Access** — view all data we have about you (available in the dashboard)
- **Delete** — request full data deletion at any time
- **Export** — request a copy of your data in machine-readable format
- **Correct** — update your workspace name and agent configurations
- **Withdraw** — stop using the sync script at any time; no more data will be sent

### For EU/EEA Users (GDPR)
If you are in the European Union or European Economic Area, you additionally have the right to:
- Object to processing
- Restrict processing
- Data portability
- Lodge a complaint with your local data protection authority

Our legal basis for processing: legitimate interest (providing the service you signed up for) and consent (Telegram login).

### For California Users (CCPA)
We do not sell personal information. You have the right to know what data we collect, request deletion, and opt out of any future data sales (which we do not engage in).

## 8. Children's Privacy

AgentCRM is not intended for users under 18 years of age. We do not knowingly collect data from minors.

## 9. International Transfers

Your data is processed in the United States. By using AgentCRM, you consent to the transfer of your data to the US. We ensure appropriate safeguards for international data transfers.

## 10. Changes to This Policy

We may update this Privacy Policy from time to time. Material changes will be communicated via Telegram or in-app notification at least 14 days before taking effect.

## 11. Contact

For privacy questions, data requests, or concerns:
- Telegram: Contact us through the app
- Email: privacy@agentforgeai.com

For EU users, you may also contact your local data protection authority.
