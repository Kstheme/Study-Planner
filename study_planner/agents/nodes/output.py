from __future__ import annotations

from datetime import date

from study_planner.domain.models import StudyPlan


STATUS_MAP = {"未开始": "todo", "进行中": "doing", "已完成": "done", "已跳过": "skipped"}
VALID_STATUSES = {"todo", "doing", "done", "skipped"}


class OutputAgent:
    def __init__(self, llm=None):
        self.llm = llm

    def run(self, draft) -> StudyPlan:
        if not isinstance(draft, StudyPlan):
            raise ValueError("final plan missing required field: time_budget")
        _normalize_dates(draft)
        _ensure_task_ids(draft)
        for task in _all_tasks(draft):
            task.status = STATUS_MAP.get(task.status, task.status)
            if task.status not in VALID_STATUSES:
                raise ValueError(f"invalid task status 状态: {task.status}")
        return draft


def _normalize_dates(plan: StudyPlan) -> None:
    if isinstance(plan.goal.deadline, str):
        plan.goal.deadline = date.fromisoformat(plan.goal.deadline)
    for phase in plan.phases:
        if isinstance(phase.start_date, str):
            phase.start_date = date.fromisoformat(phase.start_date)
        if isinstance(phase.end_date, str):
            phase.end_date = date.fromisoformat(phase.end_date)
        for week in phase.weekly_plans:
            if isinstance(week.start_date, str):
                week.start_date = date.fromisoformat(week.start_date)
            if isinstance(week.end_date, str):
                week.end_date = date.fromisoformat(week.end_date)
            for task in week.tasks:
                if isinstance(task.date, str):
                    task.date = date.fromisoformat(task.date)


def _ensure_task_ids(plan: StudyPlan) -> None:
    used = set()
    counter = 1
    for task in _all_tasks(plan):
        if not task.id or task.id in used:
            while f"task-{counter}" in used:
                counter += 1
            task.id = f"task-{counter}"
        used.add(task.id)
        counter += 1


def _all_tasks(plan: StudyPlan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]
