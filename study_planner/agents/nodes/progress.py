from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ProgressContext:
    total_task_count: int
    completed_task_count: int
    completion_rate: float
    overdue_task_ids: list[str] = field(default_factory=list)
    consecutive_unfinished_topics: list[str] = field(default_factory=list)


@dataclass
class WorkflowReplanRequest:
    original_plan: object
    review_report: object
    remaining_tasks: list
    remaining_days: int = 0
    daily_available_minutes: int = 0


class ProgressAgent:
    def run(self, study_plan, current_date: date) -> ProgressContext:
        tasks = _all_tasks(study_plan)
        completed = sum(1 for task in tasks if task.status == "done")
        overdue = [task.id for task in tasks if task.date < current_date and task.status != "done"]
        topic_counts: dict[str, int] = {}
        for task in tasks:
            if task.status == "done":
                continue
            for topic in task.related_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        return ProgressContext(
            total_task_count=len(tasks),
            completed_task_count=completed,
            completion_rate=completed / len(tasks) if tasks else 0,
            overdue_task_ids=overdue,
            consecutive_unfinished_topics=[topic for topic, count in topic_counts.items() if count >= 3],
        )

    def build_replan_request(self, study_plan, review_report, current_date: date) -> WorkflowReplanRequest:
        if current_date > study_plan.goal.deadline:
            raise ValueError("目标已过期，请调整 deadline")
        remaining = [task for task in _all_tasks(study_plan) if task.status != "done"]
        return WorkflowReplanRequest(
            original_plan=study_plan,
            review_report=review_report,
            remaining_tasks=remaining,
            remaining_days=max(0, (study_plan.goal.deadline - current_date).days + 1),
            daily_available_minutes=study_plan.goal.daily_available_minutes,
        )


def _all_tasks(plan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]
