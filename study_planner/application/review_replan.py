from __future__ import annotations

from copy import deepcopy
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from study_planner.domain.models import (
    AdjustedStudyPlan,
    ReplanRequest,
    ReviewReport,
    StudyPlan,
    StudyTask,
    TaskProgress,
)
from study_planner.infrastructure.settings import load_app_settings


VALID_TASK_STATUSES = {"todo", "doing", "done", "skipped"}


class ReviewReplanError(ValueError):
    pass


@dataclass
class ReviewLLMRequest:
    study_plan: StudyPlan
    current_date: date
    user_review_text: str
    period_start: date
    period_end: date
    progress: "PeriodProgress"
    overdue_tasks: list[StudyTask]
    consecutive_unfinished_topics: list[str]


@dataclass
class PeriodProgress:
    period_start: date
    period_end: date
    period_tasks: list[StudyTask]
    total_task_count: int
    completed_task_count: int
    completion_rate: float


@dataclass
class ReviewRiskAnalysis:
    unfinished_tasks: list[TaskProgress] = field(default_factory=list)
    overdue_tasks: list[StudyTask] = field(default_factory=list)
    consecutive_unfinished_topics: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class PlanValidationResult:
    is_valid: bool
    warnings: list[str] = field(default_factory=list)
    daily_minutes: dict[date, int] = field(default_factory=dict)


@dataclass
class PlanDiffItem:
    task_id: str
    title: str
    before_date: date | None = None
    after_date: date | None = None
    before_duration_minutes: int | None = None
    after_duration_minutes: int | None = None


@dataclass
class PlanDiff:
    moved_tasks: list[PlanDiffItem] = field(default_factory=list)
    new_tasks: list[PlanDiffItem] = field(default_factory=list)
    compressed_or_split_tasks: list[PlanDiffItem] = field(default_factory=list)

    @property
    def rows(self) -> list[PlanDiffItem]:
        return self.moved_tasks + self.new_tasks + self.compressed_or_split_tasks


@dataclass
class ReviewProgressRow:
    task_id: str
    title: str
    date: date
    duration_minutes: int
    status: str
    related_topics: list[str]
    task_type: str


@dataclass
class ReviewPageView:
    is_empty: bool = False
    empty_message: str = ""
    can_generate_review: bool = False
    can_auto_replan: bool = False
    can_save_adjustment: bool = False
    progress_rows: list[ReviewProgressRow] = field(default_factory=list)
    has_review_text_input: bool = True
    review_text_input_type: str = "textarea"
    auto_replan_button_label: str = "自动重排"
    save_adjustment_button_label: str = "保存调整"
    has_adjustment_preview: bool = False
    before_rows: list[ReviewProgressRow] = field(default_factory=list)
    after_rows: list[ReviewProgressRow] = field(default_factory=list)
    diff_rows: list[PlanDiffItem] = field(default_factory=list)


class GenerateReviewReportUseCase:
    def __init__(self, llm: Any):
        self.llm = llm

    def execute(self, study_plan: StudyPlan | None, current_date: date, user_review_text: str = "") -> ReviewReport:
        if study_plan is None:
            raise ReviewReplanError("需要先生成学习计划")

        period_start, period_end = _week_bounds(current_date)
        progress = calculate_plan_progress(study_plan, period_start, period_end)
        plan_tasks = list(iter_tasks(study_plan))
        overdue_tasks = identify_overdue_tasks(plan_tasks, current_date)
        consecutive_topics = identify_consecutive_unfinished_topics(plan_tasks)
        request = ReviewLLMRequest(
            study_plan=study_plan,
            current_date=current_date,
            user_review_text=user_review_text,
            period_start=period_start,
            period_end=period_end,
            progress=progress,
            overdue_tasks=overdue_tasks,
            consecutive_unfinished_topics=consecutive_topics,
        )
        payload = self.llm.generate_review_report(request)
        report = _review_report_from_payload(payload)
        return _normalize_review_report(report, request)


class LocalReviewLLM:
    def generate_review_report(self, request: ReviewLLMRequest) -> dict[str, Any]:
        weak_points = list(request.consecutive_unfinished_topics or request.study_plan.goal.weak_points)
        if request.user_review_text:
            weak_points.extend(_extract_known_topics(request.user_review_text, request.study_plan))
        return {
            "period_start": request.period_start,
            "period_end": request.period_end,
            "completion_rate": request.progress.completion_rate,
            "completed_task_count": request.progress.completed_task_count,
            "total_task_count": request.progress.total_task_count,
            "overdue_tasks": [task.id for task in request.overdue_tasks],
            "consecutive_unfinished_topics": request.consecutive_unfinished_topics,
            "weak_points": _dedupe(weak_points),
            "summary": "本周完成情况已统计，请优先处理延期任务和薄弱知识点。",
            "suggestions": ["降低任务粒度", "为薄弱点增加专项练习"],
        }


class DeepSeekReviewLLM:
    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required when USE_REAL_LLM=true.")
        if not model:
            raise ValueError("DEEPSEEK_MODEL is required when USE_REAL_LLM=true.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate_review_report(self, request: ReviewLLMRequest) -> dict[str, Any]:
        prompt = _build_review_prompt(request)
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ReviewReplanError(f"DeepSeek review request failed: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ReviewReplanError(f"DeepSeek review network error: {exc}") from exc
        return json.loads(_extract_json_text(payload["choices"][0]["message"]["content"]))


class SimpleReplanPlanner:
    def __init__(self, current_date: date):
        self.current_date = current_date

    def replan(self, request: ReplanRequest) -> StudyPlan:
        adjusted = deepcopy(request.original_plan)
        remaining_by_id = {stable_task_id(task) for task in request.remaining_tasks}
        scheduled_minutes = _locked_daily_minutes(adjusted, remaining_by_id)

        for task in iter_tasks(adjusted):
            if stable_task_id(task) not in remaining_by_id:
                continue
            task.status = "todo"
            task.date = _next_available_date(
                task.duration_minutes,
                scheduled_minutes,
                start_date=self.current_date,
                deadline=adjusted.goal.deadline,
                daily_limit=adjusted.goal.daily_available_minutes,
            )
            scheduled_minutes[task.date] = scheduled_minutes.get(task.date, 0) + task.duration_minutes

        _append_reinforcement_tasks(adjusted, request.review_report.weak_points, scheduled_minutes, self.current_date)
        adjusted.time_budget.planned_minutes = sum(task.duration_minutes for task in iter_tasks(adjusted))
        return adjusted


def build_f5_llm_from_env(env_path: str | Path = ".env"):
    settings = load_app_settings(env_path)
    if settings.use_real_llm:
        return DeepSeekReviewLLM(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    return LocalReviewLLM()


def calculate_period_progress(study_plan: StudyPlan, period_start: date, period_end: date) -> PeriodProgress:
    tasks = []
    for task in iter_tasks(study_plan):
        _validate_task_status(task.status)
        if period_start <= task.date <= period_end:
            tasks.append(task)
    completed = sum(1 for task in tasks if task.status == "done")
    total = len(tasks)
    return PeriodProgress(
        period_start=period_start,
        period_end=period_end,
        period_tasks=tasks,
        total_task_count=total,
        completed_task_count=completed,
        completion_rate=completed / total if total else 0,
    )


def calculate_plan_progress(study_plan: StudyPlan, period_start: date, period_end: date) -> PeriodProgress:
    tasks = list(iter_tasks(study_plan))
    for task in tasks:
        _validate_task_status(task.status)
    completed = sum(1 for task in tasks if task.status == "done")
    total = len(tasks)
    return PeriodProgress(
        period_start=period_start,
        period_end=period_end,
        period_tasks=tasks,
        total_task_count=total,
        completed_task_count=completed,
        completion_rate=completed / total if total else 0,
    )


def identify_overdue_tasks(tasks: list[StudyTask], current_date: date) -> list[StudyTask]:
    return [task for task in tasks if task.date < current_date and task.status != "done"]


def analyze_review_risks(tasks: list[StudyTask], current_date: date) -> ReviewRiskAnalysis:
    unfinished = [
        TaskProgress(
            task_id=stable_task_id(task),
            status=task.status,
            planned_date=task.date,
            duration_minutes=task.duration_minutes,
            related_topics=task.related_topics,
            notes=task.notes,
        )
        for task in tasks
        if task.status != "done"
    ]
    overdue = identify_overdue_tasks(tasks, current_date)
    topics = identify_consecutive_unfinished_topics(tasks)
    suggestions = []
    if unfinished:
        suggestions.append("为未完成任务安排补救时间")
    if overdue:
        suggestions.append("优先处理延期任务")
    if topics:
        suggestions.append("针对连续未完成知识点安排强化练习")
    return ReviewRiskAnalysis(
        unfinished_tasks=unfinished,
        overdue_tasks=overdue,
        consecutive_unfinished_topics=topics,
        suggestions=suggestions,
    )


def identify_consecutive_unfinished_topics(tasks: list[StudyTask], threshold: int = 3) -> list[str]:
    counts: dict[str, int] = {}
    for task in tasks:
        if task.status == "done":
            continue
        for topic in task.related_topics:
            counts[topic] = counts.get(topic, 0) + 1
    return [topic for topic, count in counts.items() if count >= threshold]


def build_replan_request(study_plan: StudyPlan, review_report: ReviewReport, current_date: date) -> ReplanRequest:
    if current_date > study_plan.goal.deadline:
        raise ReviewReplanError("目标已过期，请调整 deadline 后重新生成计划")

    unfinished = [task for task in iter_tasks(study_plan) if task.status != "done"]
    overdue_ids = set(review_report.overdue_tasks)
    overdue_remaining = [task for task in unfinished if task.id in overdue_ids]
    remaining = overdue_remaining if overdue_remaining else unfinished
    need_replan = bool(remaining) and (bool(overdue_remaining) or review_report.completion_rate < 1)
    return ReplanRequest(
        original_plan=study_plan,
        review_report=review_report,
        remaining_tasks=remaining,
        remaining_days=max(0, (study_plan.goal.deadline - current_date).days + 1),
        daily_available_minutes=study_plan.goal.daily_available_minutes,
        need_replan=need_replan,
        replan_type="major" if need_replan else "minor",
    )


def validate_adjusted_plan(
    study_plan: StudyPlan,
    current_date: date,
    prerequisites: dict[str, list[str]] | None = None,
) -> PlanValidationResult:
    warnings: list[str] = []
    daily_minutes: dict[date, int] = {}
    tasks = list(iter_tasks(study_plan))
    task_by_id = {stable_task_id(task): task for task in tasks}

    for task in tasks:
        _validate_task_status(task.status)
        daily_minutes[task.date] = daily_minutes.get(task.date, 0) + task.duration_minutes
        if task.date < current_date:
            warnings.append(f"任务 {stable_task_id(task)} 被安排在过去日期")
        if task.date > study_plan.goal.deadline:
            warnings.append(f"任务 {stable_task_id(task)} 超过 deadline")

    for task_date, minutes in daily_minutes.items():
        if minutes > study_plan.goal.daily_available_minutes:
            warnings.append(f"时间超限: {task_date} 安排 {minutes} 分钟")

    for task_id, dependency_ids in (prerequisites or {}).items():
        task = task_by_id.get(task_id)
        if task is None:
            continue
        for dependency_id in dependency_ids:
            dependency = task_by_id.get(dependency_id)
            if dependency and dependency.date > task.date:
                warnings.append(f"知识依赖顺序错误: {dependency_id} 晚于 {task_id}")

    return PlanValidationResult(is_valid=not warnings, warnings=warnings, daily_minutes=daily_minutes)


def generate_adjustment_preview(
    request: ReplanRequest,
    planner: Any,
    session_state: dict | None = None,
) -> AdjustedStudyPlan:
    adjusted_plan = planner.replan(request)
    diff = calculate_plan_diff(request.original_plan, adjusted_plan)
    preview = AdjustedStudyPlan(
        original_plan=request.original_plan,
        adjusted_plan=adjusted_plan,
        review_report=request.review_report,
        changed_tasks=[item.__dict__ for item in diff.rows],
        warnings=[],
        saved=False,
    )
    if session_state is not None:
        session_state["pending_adjusted_plan"] = adjusted_plan
        session_state["pending_review_report"] = request.review_report
    return preview


def calculate_plan_diff(original_plan: StudyPlan, adjusted_plan: StudyPlan) -> PlanDiff:
    original_by_id = {stable_task_id(task): task for task in iter_tasks(original_plan)}
    adjusted_by_id = {stable_task_id(task): task for task in iter_tasks(adjusted_plan)}
    diff = PlanDiff()

    for task_id, adjusted in adjusted_by_id.items():
        original = original_by_id.get(task_id)
        if original is None:
            diff.new_tasks.append(
                PlanDiffItem(
                    task_id=task_id,
                    title=adjusted.title,
                    after_date=adjusted.date,
                    after_duration_minutes=adjusted.duration_minutes,
                )
            )
            root_id = _split_root_task_id(task_id)
            if root_id in original_by_id:
                diff.compressed_or_split_tasks.append(
                    PlanDiffItem(task_id=root_id, title=original_by_id[root_id].title)
                )
            continue
        if original.date != adjusted.date:
            diff.moved_tasks.append(
                PlanDiffItem(task_id=task_id, title=adjusted.title, before_date=original.date, after_date=adjusted.date)
            )
        if original.duration_minutes != adjusted.duration_minutes:
            diff.compressed_or_split_tasks.append(
                PlanDiffItem(
                    task_id=task_id,
                    title=adjusted.title,
                    before_duration_minutes=original.duration_minutes,
                    after_duration_minutes=adjusted.duration_minutes,
                )
            )
    return diff


def cancel_adjustment_preview(session_state: dict) -> None:
    session_state.pop("pending_adjusted_plan", None)
    session_state.pop("pending_review_report", None)


def save_adjusted_plan(session_state: dict, repository: Any, current_date: date) -> StudyPlan:
    original = session_state.get("study_plan")
    adjusted = session_state.get("pending_adjusted_plan")
    report = session_state.get("pending_review_report")
    if adjusted is None:
        raise ReviewReplanError("没有待保存的调整计划")

    validation = validate_adjusted_plan(adjusted, current_date=current_date)
    if not validation.is_valid:
        raise ReviewReplanError("; ".join(validation.warnings))

    try:
        if report is not None and hasattr(repository, "save_review_report"):
            repository.save_review_report(report)
        if hasattr(repository, "save_study_plan"):
            repository.save_study_plan(adjusted)
    except Exception as exc:
        session_state["study_plan"] = original
        raise ReviewReplanError(f"保存失败: {exc}") from exc

    session_state["study_plan"] = adjusted
    if report is not None:
        session_state["last_review_report"] = report
    cancel_adjustment_preview(session_state)
    return adjusted


def build_review_page_view(
    study_plan: StudyPlan | None,
    pending_adjusted_plan: StudyPlan | None = None,
) -> ReviewPageView:
    if study_plan is None:
        return ReviewPageView(
            is_empty=True,
            empty_message="请先生成学习计划",
            can_generate_review=False,
            can_auto_replan=False,
        )

    before_rows = _progress_rows(study_plan)
    view = ReviewPageView(
        is_empty=False,
        can_generate_review=True,
        can_auto_replan=True,
        progress_rows=before_rows,
        before_rows=before_rows,
    )
    if pending_adjusted_plan is not None:
        view.has_adjustment_preview = True
        view.can_save_adjustment = True
        view.after_rows = _progress_rows(pending_adjusted_plan)
        view.diff_rows = calculate_plan_diff(study_plan, pending_adjusted_plan).rows
    return view


def stable_task_id(task: StudyTask) -> str:
    if task.id:
        return task.id
    topics = ",".join(task.related_topics)
    return f"task-{task.title}-{task.date.isoformat()}-{task.duration_minutes}-{topics}"


def iter_tasks(study_plan: StudyPlan):
    for phase in study_plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                yield task


def _review_report_from_payload(payload: Any) -> ReviewReport:
    if isinstance(payload, str):
        try:
            payload = json.loads(_extract_json_text(payload))
        except json.JSONDecodeError as exc:
            raise ReviewReplanError("LLM 复盘结果不是 JSON，解析失败") from exc
    if not isinstance(payload, dict):
        raise ReviewReplanError("复盘结果必须是结构化对象")

    required = [
        "period_start",
        "period_end",
        "completion_rate",
        "completed_task_count",
        "total_task_count",
        "overdue_tasks",
        "consecutive_unfinished_topics",
        "weak_points",
        "summary",
        "suggestions",
    ]
    missing = [field_name for field_name in required if field_name not in payload]
    if missing:
        raise ReviewReplanError(f"复盘结果缺少字段: {', '.join(missing)}")

    return ReviewReport(
        period_start=_coerce_date(payload["period_start"]),
        period_end=_coerce_date(payload["period_end"]),
        completion_rate=float(payload["completion_rate"]),
        completed_task_count=int(payload["completed_task_count"]),
        total_task_count=int(payload["total_task_count"]),
        overdue_tasks=_coerce_string_list(payload["overdue_tasks"]),
        consecutive_unfinished_topics=_coerce_string_list(payload["consecutive_unfinished_topics"]),
        weak_points=_coerce_string_list(payload["weak_points"]),
        summary=str(payload["summary"]),
        suggestions=_coerce_suggestion_list(payload["suggestions"]),
    )


def _normalize_review_report(report: ReviewReport, request: ReviewLLMRequest) -> ReviewReport:
    return ReviewReport(
        period_start=request.period_start,
        period_end=request.period_end,
        completion_rate=request.progress.completion_rate,
        completed_task_count=request.progress.completed_task_count,
        total_task_count=request.progress.total_task_count,
        overdue_tasks=[stable_task_id(task) for task in request.overdue_tasks],
        consecutive_unfinished_topics=request.consecutive_unfinished_topics,
        weak_points=_dedupe(report.weak_points or request.consecutive_unfinished_topics or request.study_plan.goal.weak_points),
        summary=report.summary,
        suggestions=_dedupe(_coerce_suggestion_list(report.suggestions)),
    )


def _progress_rows(study_plan: StudyPlan) -> list[ReviewProgressRow]:
    return [
        ReviewProgressRow(
            task_id=stable_task_id(task),
            title=task.title,
            date=task.date,
            duration_minutes=task.duration_minutes,
            status=task.status,
            related_topics=task.related_topics,
            task_type=task.task_type,
        )
        for task in iter_tasks(study_plan)
    ]


def _validate_task_status(status: str) -> None:
    if status not in VALID_TASK_STATUSES:
        raise ReviewReplanError(f"invalid task status: {status}")


def _week_bounds(current_date: date) -> tuple[date, date]:
    start = current_date - timedelta(days=current_date.weekday())
    return start, start + timedelta(days=6)


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ReviewReplanError(f"invalid date value: {value}")


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item).strip() for item in value.values() if str(item).strip()]
    text = str(value).strip()
    if not text or text == "0":
        return []
    return [part.strip() for part in re.split(r"[,，、\n]", text) if part.strip()]


def _coerce_suggestion_list(value: Any) -> list[str]:
    raw_items = _coerce_string_list(value)
    suggestions: list[str] = []
    for item in raw_items:
        parts = re.split(r"(?:^|\s|[;；。])\d+[\.、)]\s*", item)
        for part in parts:
            cleaned = re.sub(r"^\s*[-•]\s*", "", part).strip(" ;；。")
            if cleaned:
                suggestions.append(cleaned)
    return suggestions


def _extract_json_text(response: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", response, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    stripped = response.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and start < end:
        return stripped[start : end + 1]
    return stripped


def _build_review_prompt(request: ReviewLLMRequest) -> str:
    return (
        "请生成学习复盘报告，只返回 JSON。\n"
        "字段: period_start, period_end, completion_rate, completed_task_count, total_task_count, "
        "overdue_tasks, consecutive_unfinished_topics, weak_points, summary, suggestions。\n"
        f"用户复盘: {request.user_review_text}\n"
        f"完成率: {request.progress.completion_rate}\n"
    )


def _extract_known_topics(text: str, study_plan: StudyPlan) -> list[str]:
    topics = []
    for task in iter_tasks(study_plan):
        for topic in task.related_topics:
            if topic in text:
                topics.append(topic)
    for weak_point in study_plan.goal.weak_points:
        if weak_point in text:
            topics.append(weak_point)
    return _dedupe(topics)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _split_root_task_id(task_id: str) -> str:
    for marker in ("-part-", "-split-"):
        if marker in task_id:
            return task_id.split(marker, 1)[0]
    return task_id


def _locked_daily_minutes(study_plan: StudyPlan, remaining_ids: set[str]) -> dict[date, int]:
    daily_minutes: dict[date, int] = {}
    for task in iter_tasks(study_plan):
        if stable_task_id(task) in remaining_ids:
            continue
        daily_minutes[task.date] = daily_minutes.get(task.date, 0) + task.duration_minutes
    return daily_minutes


def _next_available_date(
    duration_minutes: int,
    scheduled_minutes: dict[date, int],
    start_date: date,
    deadline: date,
    daily_limit: int,
) -> date:
    current = start_date
    while current <= deadline:
        if scheduled_minutes.get(current, 0) + duration_minutes <= daily_limit:
            return current
        current += timedelta(days=1)
    return deadline


def _append_reinforcement_tasks(
    study_plan: StudyPlan,
    weak_points: list[str],
    scheduled_minutes: dict[date, int],
    current_date: date,
) -> None:
    if not study_plan.phases or not study_plan.phases[0].weekly_plans:
        return
    target_week = study_plan.phases[0].weekly_plans[0]
    existing_titles = {task.title for task in iter_tasks(study_plan)}
    for index, weak_point in enumerate(weak_points, start=1):
        title = f"{weak_point} 强化练习"
        if title in existing_titles:
            continue
        duration = min(45, study_plan.goal.daily_available_minutes)
        task_date = _next_available_date(
            duration,
            scheduled_minutes,
            start_date=current_date,
            deadline=study_plan.goal.deadline,
            daily_limit=study_plan.goal.daily_available_minutes,
        )
        scheduled_minutes[task_date] = scheduled_minutes.get(task_date, 0) + duration
        target_week.tasks.append(
            StudyTask(
                id=f"reinforcement-{index}-{weak_point}",
                title=title,
                date=task_date,
                duration_minutes=duration,
                task_type="reinforcement",
                related_topics=[weak_point],
                learning_method="专项复习 + 练习",
                expected_output=f"完成 {weak_point} 强化练习并整理错因",
                review_required=True,
                status="todo",
            )
        )
