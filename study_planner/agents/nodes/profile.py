from __future__ import annotations

from dataclasses import dataclass, field

from study_planner.domain.models import StudyGoal


@dataclass
class LearnerProfile:
    level: str
    risk_level: str = "low"
    preferences: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)
    summary: str = ""


class ProfileAgent:
    def run(self, goal: StudyGoal) -> LearnerProfile:
        risks: list[str] = []
        risk_level = "low"
        if "零" in goal.current_level or "基础" in goal.current_level:
            risks.append("基础薄弱，需要更细任务粒度")
            risk_level = "medium"
        if goal.daily_available_minutes < 60 or (goal.deadline.day if hasattr(goal.deadline, "day") else 30) <= 7:
            risks.append("时间紧张，需要控制范围")
            risk_level = "high" if risk_level == "medium" else "medium"
        summary = f"{goal.subject} / {goal.current_level} / 薄弱点: {'、'.join(goal.weak_points)}"
        return LearnerProfile(
            level=goal.current_level,
            risk_level=risk_level,
            preferences=list(goal.preferred_methods),
            risks=risks,
            weak_points=list(goal.weak_points),
            summary=summary,
        )
