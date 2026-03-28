"""
Anthropic plan limits — 5-hour rolling window token budgets.

Based on public data (March 2026):
- Rate limits use 5-hour rolling windows
- Limits are in OUTPUT tokens (primary cost driver)
- Each model has its own limit + combined "all models" limit
- Plans: Pro ($20), Max 5x ($100), Max 20x ($200)

Token allocations are approximate — Anthropic doesn't publish exact numbers.
These are calibrated from community data and official hints.
"""

# Plan definitions: plan_id -> {name, monthly_cost, window_hours, limits}
# Limits are OUTPUT tokens per 5-hour rolling window
PLANS = {
    "pro_20": {
        "name": "Pro",
        "monthly_cost": 20,
        "window_hours": 5,
        "limits": {
            "_all": 200_000,
            "claude-sonnet-4-6": 180_000,
            "claude-opus-4-6": 50_000,
            "claude-haiku-35-20241022": 400_000,
        },
    },
    "max_100": {
        "name": "Max 5x",
        "monthly_cost": 100,
        "window_hours": 5,
        "limits": {
            "_all": 500_000,
            "claude-sonnet-4-6": 450_000,
            "claude-opus-4-6": 150_000,
            "claude-haiku-35-20241022": 1_000_000,
        },
    },
    "max_200": {
        "name": "Max 20x",
        "monthly_cost": 200,
        "window_hours": 5,
        "limits": {
            "_all": 1_000_000,
            "claude-sonnet-4-6": 900_000,
            "claude-opus-4-6": 300_000,
            "claude-haiku-35-20241022": 2_000_000,
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


def get_model_limit(plan: dict, model: str) -> int:
    """Get output token limit for a specific model in a plan."""
    return plan["limits"].get(model, plan["limits"]["_all"])


def get_all_limit(plan: dict) -> int:
    """Get combined all-models output token limit."""
    return plan["limits"]["_all"]
