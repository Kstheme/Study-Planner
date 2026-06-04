from __future__ import annotations

from dataclasses import asdict, dataclass, field

from study_planner.domain.models import StudyPlan


@dataclass
class CriticIssue:
    code: str
    message: str


@dataclass
class CriticReview:
    passed: bool
    issues: list[CriticIssue] = field(default_factory=list)


class CriticAgent:
    def __init__(self, prerequisites: dict[str, list[str]] | None = None, max_single_task_minutes: int = 180):
        self.prerequisites = prerequisites or {}
        self.max_single_task_minutes = max_single_task_minutes

    def run(self, plan: StudyPlan) -> CriticReview:
        issues: list[CriticIssue] = []
        daily_minutes: dict = {}
        task_by_id = {}
        for task in _all_tasks(plan):
            task_by_id[task.id] = task
            daily_minutes[task.date] = daily_minutes.get(task.date, 0) + task.duration_minutes
            if task.date > plan.goal.deadline:
                issues.append(CriticIssue("deadline", f"任务 {task.id} 超过截止日期"))
            if task.duration_minutes > self.max_single_task_minutes:
                issues.append(CriticIssue("split_task", f"任务 {task.id} 需要拆分"))
        for task_date, minutes in daily_minutes.items():
            if minutes > plan.goal.daily_available_minutes:
                issues.append(CriticIssue("daily_overload", f"{task_date} 安排 {minutes} 分钟，超过每日限制"))
        for task_id, dependencies in self.prerequisites.items():
            task = task_by_id.get(task_id)
            for dependency_id in dependencies:
                dependency = task_by_id.get(dependency_id)
                if task and dependency and dependency.date > task.date:
                    issues.append(CriticIssue("prerequisite_order", f"先修任务 {dependency_id} 晚于 {task_id}"))
        return CriticReview(passed=not issues, issues=issues)


def serialize_critic_review(review: CriticReview) -> dict:
    return asdict(review)


def _all_tasks(plan: StudyPlan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]
