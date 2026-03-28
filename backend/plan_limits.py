"""
Anthropic plan limits — dual rate limit system (cost-based).

Two separate limits:
1. Weekly session: resets every Saturday 8pm EDT (Sunday 00:00 UTC)
2. Current session: 5-hour rolling window

Anthropic tracks usage by equivalent API cost, not raw tokens.
Limits calibrated from real Max $100 data (March 2026):
  - Weekly: $231 used = 95% → limit ≈ $243
  - Session: $58.6 used = 33% → limit ≈ $177

Plans scale proportionally: Pro=1x, Max5x=5x, Max20x=20x.
"""

# Base cost limits (Pro $20 = 1x)
# Max $100: weekly $243 (95%), session $177 (33%)
# Pro = Max/5
BASE_WEEKLY_COST = 48.6    # dollars per week
BASE_SESSION_COST = 35.4   # dollars per 5hr session

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
