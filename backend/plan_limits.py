"""
Anthropic plan limits — dual rate limit system.

Two separate limits:
1. Weekly session: resets every Saturday ~8pm EST (Sunday 01:00 UTC)
2. Current session: 5-hour rolling window

Limits are in OUTPUT tokens. Calibrated from real usage data (March 2026).
"""

PLANS = {
    "pro_20": {
        "name": "Pro",
        "monthly_cost": 20,
        "weekly_reset_utc_hour": 1,  # Sunday 01:00 UTC = Saturday 8pm EST
        "weekly_reset_day": 6,       # 6 = Sunday
        "session_hours": 5,
        "weekly_limits": {
            "_all": 230_000,
            "claude-sonnet-4-6": 200_000,
            "claude-opus-4-6": 60_000,
        },
        "session_limits": {
            "_all": 160_000,
            "claude-sonnet-4-6": 140_000,
            "claude-opus-4-6": 45_000,
        },
    },
    "max_100": {
        "name": "Max 5x",
        "monthly_cost": 100,
        "weekly_reset_utc_hour": 1,
        "weekly_reset_day": 6,
        "session_hours": 5,
        "weekly_limits": {
            "_all": 1_150_000,
            "claude-sonnet-4-6": 1_000_000,
            "claude-opus-4-6": 300_000,
        },
        "session_limits": {
            "_all": 806_000,
            "claude-sonnet-4-6": 700_000,
            "claude-opus-4-6": 200_000,
        },
    },
    "max_200": {
        "name": "Max 20x",
        "monthly_cost": 200,
        "weekly_reset_utc_hour": 1,
        "weekly_reset_day": 6,
        "session_hours": 5,
        "weekly_limits": {
            "_all": 4_600_000,
            "claude-sonnet-4-6": 4_000_000,
            "claude-opus-4-6": 1_200_000,
        },
        "session_limits": {
            "_all": 3_200_000,
            "claude-sonnet-4-6": 2_800_000,
            "claude-opus-4-6": 800_000,
        },
    },
}


def get_plan_by_budget(monthly_budget: float) -> dict:
    """Match a plan by monthly budget amount."""
    if monthly_budget >= 200:
        return PLANS["max_200"]
    elif monthly_budget >= 100:
        return PLANS["max_100"]
    else:
        return PLANS["pro_20"]
