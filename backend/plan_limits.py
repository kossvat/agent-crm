"""
Anthropic plan limits — dual rate limit system.

Two separate limits:
1. Weekly session: resets every Saturday 8pm EDT (Sunday 00:00 UTC)
2. Current session: 5-hour rolling window

Base unit = Pro ($20). All other plans scale proportionally.
Max 5x ($100) = 5× Pro. Max 20x ($200) = 20× Pro (but 10× relative to $100).

Limits are OUTPUT tokens per window. Calibrated March 2026.
"""

# === Base limits (Pro $20 plan = 1x multiplier) ===
BASE_WEEKLY = {
    "_all": 230_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 60_000,
    "claude-haiku-35-20241022": 400_000,
}

BASE_SESSION = {
    "_all": 161_000,
    "claude-sonnet-4-6": 140_000,
    "claude-opus-4-6": 40_000,
    "claude-haiku-35-20241022": 280_000,
}

# === Plan multipliers ===
# $20 = 1x, $100 = 5x, $200 = 10x (relative to $20)
PLAN_TIERS = [
    {"name": "Pro", "cost": 20, "multiplier": 1},
    {"name": "Max 5x", "cost": 100, "multiplier": 5},
    {"name": "Max 20x", "cost": 200, "multiplier": 10},
]

# Common config
WEEKLY_RESET_UTC_HOUR = 0   # Sunday 00:00 UTC = Saturday 8pm EDT
WEEKLY_RESET_DAY = 6        # 6 = Sunday (Python weekday)
SESSION_HOURS = 5


def _scale_limits(base: dict, multiplier: float) -> dict:
    """Scale base limits by multiplier."""
    return {k: int(v * multiplier) for k, v in base.items()}


def get_plan_by_budget(monthly_budget: float) -> dict:
    """
    Build plan config for any budget amount.
    
    Known tiers: $20 (1x), $100 (5x), $200 (10x).
    Unknown amounts: interpolate multiplier linearly ($20=1x baseline).
    """
    # Find matching tier or interpolate
    tier = PLAN_TIERS[0]  # default Pro
    for t in PLAN_TIERS:
        if monthly_budget >= t["cost"]:
            tier = t

    # For exact matches use tier multiplier, otherwise interpolate
    if monthly_budget == tier["cost"]:
        multiplier = tier["multiplier"]
        name = tier["name"]
    elif monthly_budget > tier["cost"]:
        # Above highest tier — extrapolate
        multiplier = tier["multiplier"] * (monthly_budget / tier["cost"])
        name = f"Custom ${int(monthly_budget)}"
    else:
        # Below Pro — scale down proportionally
        multiplier = max(0.1, monthly_budget / 20.0)
        name = f"Custom ${int(monthly_budget)}"

    return {
        "name": name,
        "monthly_cost": monthly_budget,
        "weekly_reset_utc_hour": WEEKLY_RESET_UTC_HOUR,
        "weekly_reset_day": WEEKLY_RESET_DAY,
        "session_hours": SESSION_HOURS,
        "weekly_limits": _scale_limits(BASE_WEEKLY, multiplier),
        "session_limits": _scale_limits(BASE_SESSION, multiplier),
    }
