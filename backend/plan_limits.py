"""
Anthropic plan limits — dual rate limit system (cost-based).

Two separate limits:
1. Weekly session: resets every Saturday 8pm EDT (Sunday 00:00 UTC)
2. Current session: 5-hour rolling window

IMPORTANT — Cost accuracy notes:
- Costs in spending.db use REAL Anthropic API pricing ($15/$75 per M for Opus,
  $3/$15 for Sonnet), recalculated from raw token counts.
- OpenClaw internally uses Vercel AI Gateway prices (3x lower) — we correct this.
- Anthropic's session/weekly % on claude.ai includes THINKING tokens that are
  NOT reported in OpenClaw's usage data (summarized thinking only). This means
  our visible cost underestimates real Anthropic billing, especially for Opus.
- Limits are empirically calibrated from Anthropic UI screenshot comparisons.

Calibration data (2026-03-29, Max 5x $100 plan):
  Point 1: 2:03 AM UTC — our visible cost $70.04, Anthropic 100% session
  Point 2: 14:53 UTC — our visible cost $68.37 weekly, Anthropic 17% weekly
  → session limit ≈ $70 (Max 5x), weekly limit ≈ $402 (Max 5x)

Plans scale proportionally: Pro=1x, Max5x=5x, Max20x=20x.
"""

# Base cost limits (Pro $20 = 1x)
# Empirically calibrated from Anthropic UI comparisons:
# Max 5x ($100): session ≈$70, weekly ≈$402
BASE_WEEKLY_COST = 80.4    # $402 / 5x
BASE_SESSION_COST = 14.0   # $70 / 5x

PLAN_TIERS = [
    {"name": "Pro", "cost": 20, "multiplier": 1},
    {"name": "Max 5x", "cost": 100, "multiplier": 5},
    {"name": "Max 20x", "cost": 200, "multiplier": 20},
]

WEEKLY_RESET_UTC_HOUR = 0   # Sunday 00:00 UTC = Saturday 8pm EDT
WEEKLY_RESET_DAY = 6        # 6 = Sunday
SESSION_HOURS = 5


def get_plan_by_budget(monthly_budget: float) -> dict:
    """Build plan config for a budget amount."""
    tier = PLAN_TIERS[0]
    for t in PLAN_TIERS:
        if monthly_budget >= t["cost"]:
            tier = t

    m = tier["multiplier"]
    return {
        "name": tier["name"],
        "monthly_cost": monthly_budget,
        "weekly_reset_utc_hour": WEEKLY_RESET_UTC_HOUR,
        "weekly_reset_day": WEEKLY_RESET_DAY,
        "session_hours": SESSION_HOURS,
        "weekly_cost_limit": round(BASE_WEEKLY_COST * m, 2),
        "session_cost_limit": round(BASE_SESSION_COST * m, 2),
    }
