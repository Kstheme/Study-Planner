from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from study_planner.application.plan_export import ExportRequest, ExportStudyPlanUseCase
from study_planner.application.plan_dashboard import VALID_TASK_STATUSES
from study_planner.domain.models import ReviewReport, StudyPlan, StudyTask


class StorageError(RuntimeError):
    pass


class InvalidTaskUpdateError(StorageError):
    pass


@dataclass
class ExportRecord:
    plan_id: str
    format: str
    filename: str
    exported_at: datetime


@dataclass
class PersistentAppState:
    study_plan: StudyPlan | None = None
    review_report: ReviewReport | None = None
    empty_message: str = ""
    storage_available: bool = True
    startup_error: str = ""


class StorageService:
    def __init__(
        self,
        goal_repository: Any,
        plan_repository: Any,
        task_progress_repository: Any,
        review_report_repository: Any,
        material_repository: Any,
        export_record_repository: Any | None = None,
    ):
        self.goal_repository = goal_repository
        self.plan_repository = plan_repository
        self.task_progress_repository = task_progress_repository
        self.review_report_repository = review_report_repository
        self.material_repository = material_repository
        self.export_record_repository = export_record_repository

    def save_study_goal(self, goal: Any) -> str:
        try:
            return self.goal_repository.save(goal)
        except Exception as exc:
            raise _storage_error("storage save failed: database unavailable", exc) from exc

    def get_latest_study_goal(self) -> Any | None:
        try:
            return self.goal_repository.get_latest()
        except Exception as exc:
            raise _storage_error("storage read failed: database unavailable", exc) from exc

    def save_study_plan(self, plan: StudyPlan, goal_id: str | None = None) -> str:
        self._validate_plan(plan)
        try:
            return self.plan_repository.save(plan, goal_id=goal_id)
        except Exception as exc:
            raise _storage_error("storage save failed: database unavailable", exc) from exc

    def get_latest_study_plan(self) -> StudyPlan | None:
        try:
            return self.plan_repository.get_latest()
        except Exception as exc:
            raise _storage_error("storage read failed: database unavailable", exc) from exc

    def get_study_plan(self, plan_id: str) -> StudyPlan | None:
        try:
            return self.plan_repository.get_by_id(plan_id)
        except Exception as exc:
            raise _storage_error("storage read failed: database unavailable", exc) from exc

    def get_plan_metadata(self, plan_id: str) -> dict[str, Any]:
        try:
            return self.plan_repository.metadata(plan_id)
        except Exception as exc:
            raise _storage_error("storage read failed: database unavailable", exc) from exc

    def update_task(
        self,
        plan_id: str,
        task_id: str,
        status: str | None = None,
        new_date: date | None = None,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> StudyPlan:
        if status is not None and status not in VALID_TASK_STATUSES:
            raise InvalidTaskUpdateError("invalid task status 状态")
        try:
            updated = self.plan_repository.update_task(
                plan_id,
                task_id,
                status=status,
                new_date=new_date,
                duration_minutes=duration_minutes,
                notes=notes,
            )
        except KeyError as exc:
            raise InvalidTaskUpdateError("task not found 不存在") from exc
        except ValueError as exc:
            raise InvalidTaskUpdateError(str(exc)) from exc
        except Exception as exc:
            raise _storage_error("storage save failed: database unavailable", exc) from exc
        self._validate_plan(updated)
        return updated

    def save_task_progress(self, progress: Any) -> str:
        try:
            if hasattr(self.task_progress_repository, "save_progress"):
                return self.task_progress_repository.save_progress(progress)
            return self.task_progress_repository.save(progress)
        except Exception as exc:
            raise _storage_error("progress save failed: database unavailable", exc) from exc

    def save_review_report(self, report: ReviewReport, plan_id: str | None = None) -> str:
        try:
            return self.review_report_repository.save(report, plan_id=plan_id)
        except Exception as exc:
            raise _storage_error("review save failed: database unavailable", exc) from exc

    def get_latest_review_report(self, plan_id: str | None = None) -> ReviewReport | None:
        try:
            return self.review_report_repository.get_latest(plan_id=plan_id)
        except Exception as exc:
            raise _storage_error("review read failed: database unavailable", exc) from exc

    def record_export_if_available(
        self,
        plan_id: str,
        format: str,
        filename: str,
        exported_at: datetime,
    ) -> str | None:
        if self.export_record_repository is None:
            return None
        try:
            return self.export_record_repository.save(
                ExportRecord(plan_id=plan_id, format=format, filename=filename, exported_at=exported_at)
            )
        except Exception as exc:
            raise _storage_error("export record save failed: database unavailable", exc) from exc

    def save_goal_and_plan(self, goal: Any, plan: StudyPlan) -> tuple[str, str]:
        goal_id: str | None = None
        try:
            goal_id = self.save_study_goal(goal)
            plan_id = self.save_study_plan(plan, goal_id=goal_id)
            return goal_id, plan_id
        except Exception:
            if goal_id and hasattr(self.goal_repository, "delete"):
                self.goal_repository.delete(goal_id)
            raise

    def save_adjusted_plan(self, adjusted_plan: StudyPlan, review_report: ReviewReport) -> str:
        plan_id: str | None = None
        try:
            plan_id = self.save_study_plan(adjusted_plan)
            self.save_review_report(review_report, plan_id=plan_id)
            return plan_id
        except Exception:
            if plan_id and hasattr(self.plan_repository, "delete"):
                self.plan_repository.delete(plan_id)
            raise

    def export_latest_plan(self, format: str, exported_at: datetime | None = None):
        result = ExportStudyPlanUseCase.from_repository(self).execute(
            ExportRequest(format=format, exported_at=exported_at)
        )
        plan_id = None
        try:
            metadata = self.plan_repository.metadata_latest()
            plan_id = metadata.get("id")
        except Exception:
            pass
        if plan_id is not None:
            self.record_export_if_available(plan_id, format=format, filename=result.filename, exported_at=exported_at or datetime.now())
        return result

    def _validate_plan(self, plan: StudyPlan) -> None:
        minutes_by_date: dict[date, int] = {}
        for task in _iter_tasks(plan):
            if task.status not in VALID_TASK_STATUSES:
                raise StorageError("invalid task status 状态")
            if task.date > plan.goal.deadline:
                raise StorageError("task date exceeds deadline 截止")
            minutes_by_date[task.date] = minutes_by_date.get(task.date, 0) + task.duration_minutes
        for minutes in minutes_by_date.values():
            if minutes > plan.goal.daily_available_minutes:
                raise StorageError("daily minutes overloaded 时长 过载")


def build_persistent_app_state(session_state: dict, service: StorageService) -> PersistentAppState:
    try:
        plan = session_state.get("study_plan") or service.get_latest_study_plan()
        report = (
            session_state.get("last_review_report")
            or session_state.get("pending_review_report")
            or service.get_latest_review_report()
        )
    except StorageError as exc:
        return PersistentAppState(
            storage_available=False,
            startup_error=str(exc),
            empty_message="暂无可恢复的学习计划",
        )

    if plan is not None:
        session_state["study_plan"] = plan
    if report is not None:
        session_state["last_review_report"] = report

    return PersistentAppState(
        study_plan=plan,
        review_report=report,
        empty_message="" if plan is not None else "暂无学习计划，请先配置目标并生成计划",
    )


def _iter_tasks(plan: StudyPlan):
    for phase in plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                yield task


def _storage_error(message: str, exc: Exception) -> StorageError:
    if isinstance(exc, StorageError):
        return exc
    return StorageError(message)
