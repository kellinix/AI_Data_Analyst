from __future__ import annotations

PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free":         {"analyses": 5,   "ai_queries": 20,   "storage": 100 * 1024 * 1024},
    "starter":      {"analyses": 20,  "ai_queries": 100,  "storage": 1 * 1024 * 1024 * 1024},
    "professional": {"analyses": 100, "ai_queries": 500,  "storage": 10 * 1024 * 1024 * 1024},
    "enterprise":   {"analyses": 9999,"ai_queries": 9999, "storage": 100 * 1024 * 1024 * 1024},
}


def plan_limits_for(plan: str) -> dict[str, int]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
