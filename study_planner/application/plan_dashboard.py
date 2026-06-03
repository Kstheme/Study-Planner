from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta

from study_planner.domain.models import ReviewSchedule, StudyPhase, StudyPlan, StudyTask, WeeklyPlan


VALID_TASK_STATUSES = {"todo", "doing", "done", "skipped"}


class DashboardValidationError(ValueError):
    pass


@dataclass
class PhaseTab:
    phase_index: int
    title: str
    objective: str
    start_date: date
    end_date: date
    milestone: str
    weekly_plans: list[WeeklyPlan] = field(default_factory=list)


@dataclass
class ProgressSummary:
    total_tasks: int
    done_tasks: int
    completion_rate: int
    daily_minutes: dict[date, int] = field(default_factory=dict)
    weekly_minutes: dict[int, int] = field(default_factory=dict)


@dataclass
class DashboardView:
    is_empty: bool
    empty_message: str = ""
    can_edit: bool = False
    goal_summary: dict = field(default_factory=dict)
    overall_route: str = ""
    phase_tabs: list[PhaseTab] = field(default_factory=list)
    task_rows: list[StudyTask] = field(default_factory=list)
    today_tasks: list[StudyTask] = field(default_factory=list)
    today_empty_message: str = ""
    risks: list[str] = field(default_factory=list)
    review_schedule: ReviewSchedule | None = None
    methods: list[str] = field(default_factory=list)
    progress: ProgressSummary | None = None
    progress_chart_data: dict = field(default_factory=dict)
    daily_minutes_chart_data: dict = field(default_factory=dict)
    weekly_minutes_chart_data: dict = field(default_factory=dict)


@dataclass
class DashboardState:
    study_plan: StudyPlan | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_session(cls, session: dict) -> "DashboardState":
        return cls(study_plan=session.get("study_plan"), errors=list(session.get("errors", [])))

    def save_to_session(self, session: dict) -> None:
        session["study_plan"] = self.study_plan
        session["errors"] = self.errors


def build_dashboard_view(study_plan: StudyPlan | None, today: date | None = None) -> DashboardView:
    today = today or date.today()
    if study_plan is None:
        return DashboardView(
            is_empty=True,
            empty_message="还没有学习计划，请先配置学习目标并生成学习计划。",
            can_edit=False,
        )

    progress = calculate_progress(study_plan)
    today_tasks = get_today_tasks(study_plan, today=today)
    phase_tabs = [
        PhaseTab(
            phase_index=phase.phase_index,
            title=phase.title,
            objective=phase.objective,
            start_date=phase.start_date,
            end_date=phase.end_date,
            milestone=phase.milestone,
            weekly_plans=phase.weekly_plans,
        )
        for phase in study_plan.phases
    ]

    return DashboardView(
        is_empty=False,
        can_edit=True,
        goal_summary={
            "subject": study_plan.goal.subject,
            "target": study_plan.goal.target,
            "deadline": study_plan.goal.deadline,
            "current_level": study_plan.goal.current_level,
            "daily_available_minutes": study_plan.goal.daily_available_minutes,
            "weekly_available_days": study_plan.goal.weekly_available_days,
        },
        overall_route=study_plan.overall_route,
        phase_tabs=phase_tabs,
        task_rows=list(_iter_tasks(study_plan)),
        today_tasks=today_tasks,
        today_empty_message="" if today_tasks else "今天没有学习任务。",
        risks=study_plan.risks,
        review_schedule=study_plan.review_schedule,
        methods=study_plan.methods,
        progress=progress,
        progress_chart_data={
            "total_tasks": progress.total_tasks,
            "done_tasks": progress.done_tasks,
            "completion_rate": progress.completion_rate,
        },
        daily_minutes_chart_data=progress.daily_minutes,
        weekly_minutes_chart_data=progress.weekly_minutes,
    )


def get_today_tasks(plan: StudyPlan, today: date | None = None) -> list[StudyTask]:
    today = today or date.today()
    return [task for task in _iter_tasks(plan) if task.date == today]


def get_current_week_tasks(plan: StudyPlan, today: date | None = None) -> list[StudyTask]:
    today = today or date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return [task for task in _iter_tasks(plan) if week_start <= task.date <= week_end]


def calculate_progress(plan: StudyPlan) -> ProgressSummary:
    tasks = list(_iter_tasks(plan))
    total_tasks = len(tasks)
    done_tasks = sum(1 for task in tasks if task.status == "done")
    completion_rate = int(done_tasks / total_tasks * 100) if total_tasks else 0
    daily_minutes: dict[date, int] = {}
    weekly_minutes: dict[int, int] = {}

    for phase in plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                daily_minutes[task.date] = daily_minutes.get(task.date, 0) + task.duration_minutes
                weekly_minutes[weekly_plan.week_index] = (
                    weekly_minutes.get(weekly_plan.week_index, 0) + task.duration_minutes
                )

    return ProgressSummary(
        total_tasks=total_tasks,
        done_tasks=done_tasks,
        completion_rate=completion_rate,
        daily_minutes=daily_minutes,
        weekly_minutes=weekly_minutes,
    )


def update_task_status(plan: StudyPlan, task_id: str, status: str) -> StudyPlan:
    if status not in VALID_TASK_STATUSES:
        raise DashboardValidationError("任务状态非法")
    updated = deepcopy(plan)
    task = _find_task(updated, task_id)
    task.status = status
    return updated


def update_task_date(plan: StudyPlan, task_id: str, new_date: date, today: date | None = None) -> StudyPlan:
    today = today or date.today()
    if new_date < today:
        raise DashboardValidationError("任务日期不能早于今天")
    if new_date > plan.goal.deadline:
        raise DashboardValidationError("任务日期不能超过截止日期")
    updated = deepcopy(plan)
    task = _find_task(updated, task_id)
    task.date = new_date
    _validate_daily_load(updated)
    return updated


def update_task_duration(plan: StudyPlan, task_id: str, duration_minutes: int) -> StudyPlan:
    if duration_minutes <= 0:
        raise DashboardValidationError("任务时长必须大于 0")
    updated = deepcopy(plan)
    task = _find_task(updated, task_id)
    task.duration_minutes = duration_minutes
    _validate_daily_load(updated)
    return updated


def update_task_notes(plan: StudyPlan, task_id: str, notes: str) -> StudyPlan:
    updated = deepcopy(plan)
    task = _find_task(updated, task_id)
    task.notes = notes
    return updated


def update_task(
    plan: StudyPlan,
    task_id: str,
    status: str,
    new_date: date,
    duration_minutes: int,
    notes: str,
    today: date | None = None,
) -> StudyPlan:
    today = today or date.today()
    if status not in VALID_TASK_STATUSES:
        raise DashboardValidationError("任务状态非法")
    if new_date < today:
        raise DashboardValidationError("任务日期不能早于今天")
    if new_date > plan.goal.deadline:
        raise DashboardValidationError("任务日期不能超过截止日期")
    if duration_minutes <= 0:
        raise DashboardValidationError("任务时长必须大于 0")

    updated = deepcopy(plan)
    task = _find_task(updated, task_id)
    task.status = status
    task.date = new_date
    task.duration_minutes = duration_minutes
    task.notes = notes
    _validate_daily_load(updated)
    return updated


def _find_task(plan: StudyPlan, task_id: str) -> StudyTask:
    for task in _iter_tasks(plan):
        if task.id == task_id:
            return task
    raise DashboardValidationError("任务不存在")


def _iter_tasks(plan: StudyPlan):
    for phase in plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                yield task


def _validate_daily_load(plan: StudyPlan) -> None:
    minutes_by_date: dict[date, int] = {}
    for task in _iter_tasks(plan):
        minutes_by_date[task.date] = minutes_by_date.get(task.date, 0) + task.duration_minutes
    if any(minutes > plan.goal.daily_available_minutes for minutes in minutes_by_date.values()):
        raise DashboardValidationError("当日任务总时长超过每日可学习时间")
