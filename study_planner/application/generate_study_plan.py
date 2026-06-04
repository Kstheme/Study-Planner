import json
from datetime import date
from math import ceil
from typing import Any

from study_planner.domain.models import (
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TimeBudget,
    WeeklyPlan,
)


class StudyPlanGenerationError(ValueError):
    pass


class GenerateStudyPlanUseCase:
    def __init__(self, llm: Any | None = None, workflow: Any | None = None):
        if llm is None and workflow is None:
            raise TypeError("llm or workflow is required")
        self.llm = llm
        self.workflow = workflow

    def execute(self, goal: StudyGoal) -> StudyPlan:
        if self.workflow is not None:
            state = self.workflow.run(goal)
            self.last_workflow_state = state
            if getattr(state, "errors", None):
                detail = "; ".join(getattr(error, "message", str(error)) for error in state.errors)
                raise StudyPlanGenerationError(f"workflow study plan generation failed: {detail}")
            if state.final_plan is None:
                raise StudyPlanGenerationError("workflow did not generate a study plan")
            plan = state.final_plan
            self._normalize_plan_dates(plan)
            self._validate(plan)
            return plan

        payload = self.llm.generate_study_plan(goal)
        if not payload:
            raise StudyPlanGenerationError("学习计划生成结果为空")
        if isinstance(payload, StudyPlan):
            plan = payload
        else:
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise StudyPlanGenerationError("学习计划不是合法 JSON") from exc
            if not isinstance(payload, dict):
                raise StudyPlanGenerationError("学习计划格式无效")
            plan = self._build_plan(payload, goal)

        self._normalize_plan_dates(plan)
        self._validate(plan)
        return plan

    def _build_plan(self, payload: dict[str, Any], fallback_goal: StudyGoal) -> StudyPlan:
        goal = payload.get("goal") or fallback_goal
        phases = [self._build_phase(item) for item in payload.get("phases", [])]
        planned_minutes = sum(
            task.duration_minutes
            for phase in phases
            for weekly_plan in phase.weekly_plans
            for task in weekly_plan.tasks
        )
        total_days = (goal.deadline - date.today()).days + 1
        total_weeks = max(1, ceil(total_days / 7))
        time_budget = TimeBudget(
            total_days=total_days,
            total_weeks=total_weeks,
            total_available_minutes=total_weeks * goal.weekly_available_days * goal.daily_available_minutes,
            planned_minutes=planned_minutes,
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        )
        review_payload = payload.get("review_schedule", {})

        return StudyPlan(
            goal=goal,
            overall_route=payload.get("overall_route", ""),
            phases=phases,
            methods=list(payload.get("methods", [])),
            time_budget=time_budget,
            risks=list(payload.get("risks", [])),
            review_schedule=ReviewSchedule(
                daily_review_minutes=review_payload.get("daily_review_minutes", 0),
                weekly_review_day=review_payload.get("weekly_review_day", ""),
                review_strategy=review_payload.get("review_strategy", ""),
            ),
            suggestions=payload.get("suggestions", ""),
        )

    def _build_phase(self, payload: dict[str, Any]) -> StudyPhase:
        return StudyPhase(
            phase_index=payload["phase_index"],
            title=payload["title"],
            objective=payload["objective"],
            start_date=self._parse_date(payload["start_date"]),
            end_date=self._parse_date(payload["end_date"]),
            milestone=payload.get("milestone", ""),
            weekly_plans=[self._build_weekly_plan(item) for item in payload.get("weekly_plans", [])],
        )

    def _build_weekly_plan(self, payload: dict[str, Any]) -> WeeklyPlan:
        return WeeklyPlan(
            week_index=payload["week_index"],
            start_date=self._parse_date(payload["start_date"]),
            end_date=self._parse_date(payload["end_date"]),
            objective=payload["objective"],
            review_focus=payload.get("review_focus", ""),
            tasks=[self._build_task(item) for item in payload.get("tasks", [])],
        )

    def _build_task(self, payload: dict[str, Any]) -> StudyTask:
        return StudyTask(
            id=payload.get("id", ""),
            title=payload["title"],
            date=self._parse_date(payload["date"]),
            duration_minutes=payload["duration_minutes"],
            task_type=payload["task_type"],
            related_topics=list(payload.get("related_topics", [])),
            learning_method=payload.get("learning_method", ""),
            expected_output=payload.get("expected_output", ""),
            review_required=payload.get("review_required", False),
            status=payload.get("status", "todo"),
            notes=payload.get("notes", ""),
        )

    def _parse_date(self, value: Any) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise StudyPlanGenerationError("日期格式无效")

    def _normalize_plan_dates(self, plan: StudyPlan) -> None:
        today = date.today()
        for phase in plan.phases:
            if phase.start_date < today:
                phase.start_date = today
            if phase.end_date > plan.goal.deadline:
                phase.end_date = plan.goal.deadline

            for weekly_plan in phase.weekly_plans:
                if weekly_plan.start_date < phase.start_date:
                    weekly_plan.start_date = phase.start_date
                if weekly_plan.end_date > phase.end_date:
                    weekly_plan.end_date = phase.end_date

                for task in weekly_plan.tasks:
                    if task.date < weekly_plan.start_date:
                        task.date = weekly_plan.start_date
                    if task.date > weekly_plan.end_date:
                        task.date = weekly_plan.end_date

    def _validate(self, plan: StudyPlan) -> None:
        if not plan.phases:
            raise StudyPlanGenerationError("学习计划必须包含阶段")
        today = date.today()
        for phase in plan.phases:
            if phase.start_date < today or phase.end_date < today:
                raise StudyPlanGenerationError("阶段日期不能早于今天")
            if phase.start_date > phase.end_date:
                raise StudyPlanGenerationError("阶段开始日期不能晚于结束日期")
            if phase.end_date > plan.goal.deadline:
                raise StudyPlanGenerationError("阶段日期不能超过截止日期")
            if not phase.weekly_plans:
                raise StudyPlanGenerationError("阶段必须包含周计划")
            for weekly_plan in phase.weekly_plans:
                if weekly_plan.start_date < today or weekly_plan.end_date < today:
                    raise StudyPlanGenerationError("周计划日期不能早于今天")
                if weekly_plan.start_date > weekly_plan.end_date:
                    raise StudyPlanGenerationError("周计划开始日期不能晚于结束日期")
                if weekly_plan.start_date < phase.start_date or weekly_plan.end_date > phase.end_date:
                    raise StudyPlanGenerationError("周计划日期必须在所属阶段范围内")
                if not weekly_plan.tasks:
                    raise StudyPlanGenerationError("周计划必须包含每日任务")

        minutes_by_date: dict[date, int] = {}
        for phase in plan.phases:
            for weekly_plan in phase.weekly_plans:
                for task in weekly_plan.tasks:
                    minutes_by_date[task.date] = minutes_by_date.get(task.date, 0) + task.duration_minutes
                    if task.date < today:
                        raise StudyPlanGenerationError("任务日期不能早于今天")
                    if task.date > plan.goal.deadline:
                        raise StudyPlanGenerationError("任务日期不能超过截止日期")
                    if task.date < weekly_plan.start_date or task.date > weekly_plan.end_date:
                        raise StudyPlanGenerationError("任务日期必须在所属周计划范围内")

        if any(minutes > plan.goal.daily_available_minutes for minutes in minutes_by_date.values()):
            raise StudyPlanGenerationError("每日任务总时长不能超过每日学习时间")
