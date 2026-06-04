from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from study_planner.domain.models import ReviewSchedule, StudyPhase, StudyPlan, StudyTask, TimeBudget, WeeklyPlan


class PlannerAgent:
    def __init__(self, llm: Any | None = None):
        self.llm = llm

    def run(self, goal, learner_profile=None, knowledge_points=None, resources=None) -> StudyPlan:
        if self.llm is not None and hasattr(self.llm, "generate_study_plan"):
            payload = self.llm.generate_study_plan(goal)
            if isinstance(payload, StudyPlan):
                return payload
            from study_planner.application.generate_study_plan import GenerateStudyPlanUseCase

            return GenerateStudyPlanUseCase(llm=_PayloadLLM(payload)).execute(goal)
        if isinstance(self.llm, dict) and "phases" not in self.llm:
            raise ValueError("draft plan missing phases / 草案结构缺少字段")
        topics = [point.name for point in knowledge_points or []] or ["Python 基础"]
        resource_text = ""
        if resources:
            first = resources[0]
            resource_text = f"；参考 {first.title} {first.source}"
        today = date.today()
        start = max(today, today)
        task_date = start
        tasks = [
            StudyTask(
                id=f"task-{index}",
                title=f"学习{topic}",
                date=task_date + timedelta(days=index - 1),
                duration_minutes=min(60, goal.daily_available_minutes),
                task_type="study",
                related_topics=[topic],
                learning_method=f"阅读文档 + 练习{resource_text}",
                expected_output=f"完成{topic}练习",
                review_required=True,
                status="todo",
            )
            for index, topic in enumerate(topics[: max(1, min(3, len(topics)))], start=1)
        ]
        return _build_plan(goal, tasks)

    def replan(self, request) -> StudyPlan:
        adjusted = deepcopy(request.original_plan)
        remaining_ids = {task.id for task in request.remaining_tasks}
        for index, task in enumerate(_all_tasks(adjusted), start=1):
            if task.id in remaining_ids:
                task.status = "todo"
                task.date = date.today() + timedelta(days=index)
        return adjusted


def _build_plan(goal, tasks: list[StudyTask]) -> StudyPlan:
    start = min(task.date for task in tasks)
    end = min(goal.deadline, max(task.date for task in tasks) + timedelta(days=6))
    planned_minutes = sum(task.duration_minutes for task in tasks)
    return StudyPlan(
        goal=goal,
        overall_route="按知识点逐步学习并完成练习。",
        phases=[
            StudyPhase(
                phase_index=1,
                title="基础阶段",
                objective="完成核心知识点学习",
                start_date=start,
                end_date=end,
                milestone="能独立完成练习",
                weekly_plans=[
                    WeeklyPlan(
                        week_index=1,
                        start_date=start,
                        end_date=end,
                        objective="完成第一阶段学习",
                        review_focus="核心知识点",
                        tasks=tasks,
                    )
                ],
            )
        ],
        methods=["阅读文档", "练习", "项目实践"],
        time_budget=TimeBudget(
            total_days=max(1, (goal.deadline - start).days + 1),
            total_weeks=1,
            total_available_minutes=goal.daily_available_minutes * goal.weekly_available_days,
            planned_minutes=planned_minutes,
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        risks=[],
        review_schedule=ReviewSchedule(daily_review_minutes=15, weekly_review_day="周日", review_strategy="每日复习"),
        suggestions="保持每日小步推进",
    )


def _all_tasks(plan: StudyPlan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


class _PayloadLLM:
    def __init__(self, payload):
        self.payload = payload

    def generate_study_plan(self, _goal):
        return self.payload
