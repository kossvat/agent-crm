# AgentCRM Sync

Syncs pending commands from your AgentCRM dashboard to your local OpenClaw instance.
Enables remote model changes, gateway stop/resume/fix from the CRM web UI.

## Setup
This skill was auto-configured during installation. No manual setup needed.

## What it does
- Runs every minute via cron
- Checks for pending commands (model changes, stop/resume/fix)  
- Applies changes to local openclaw.json
- Acknowledges commands back to CRM
- OpenClaw hot-reload picks up config changes automatically

## Commands handled
- `change_model` — changes agent model in openclaw.json
- `stop_gateway` — stops gateway + disables all crons
- `resume_gateway` — starts gateway + enables all crons
- `fix_system` — clears large sessions + disables crons

## Files
- `apply_commands.py` — sync script (runs via cron)
- `config.json` — connection settings (URL + token)
