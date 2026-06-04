from __future__ import annotations


def build_goal_summary_view(goal) -> dict:
    return {
        "subject": goal.subject,
        "target": goal.target,
        "deadline": goal.deadline,
        "current_level": goal.current_level,
        "daily_available_minutes": goal.daily_available_minutes,
        "weekly_available_days": goal.weekly_available_days,
        "preferred_methods": list(goal.preferred_methods),
        "weak_points": list(goal.weak_points),
    }
