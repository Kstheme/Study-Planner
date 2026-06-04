from __future__ import annotations

from datetime import date, timedelta

import pytest

from study_planner.application.agent_workflow import build_plan_workflow_use_case, build_replan_workflow_planner
from study_planner.agents.planner_workflow import PlannerWorkflow, WorkflowReplanPlanner
from study_planner.domain.models import (
    ReviewReport,
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TimeBudget,
    WeeklyPlan,
)


def write_env(path, *, use_real_llm: bool = True, api_key: str = "sk-test", model: str = "deepseek-chat"):
    path.write_text(
        "\n".join(
            [
                f"USE_REAL_LLM={'true' if use_real_llm else 'false'}",
                f"DEEPSEEK_API_KEY={api_key}",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                f"DEEPSEEK_MODEL={model}",
            ]
        ),
        encoding="utf-8",
    )
    return path


def valid_goal(**overrides):
    data = {
        "subject": "Python programming",
        "target": "Build a small project with Python basics",
        "deadline": date.today() + timedelta(days=21),
        "current_level": "beginner",
        "daily_available_minutes": 90,
        "weekly_available_days": 5,
        "preferred_methods": ["project practice"],
        "weak_points": ["functions"],
        "extra_requirements": "Use short daily tasks.",
    }
    data.update(overrides)
    return StudyGoal(**data)


def make_task(task_id: str = "task-1", **overrides):
    data = {
        "id": task_id,
        "title": f"Task {task_id}",
        "date": date.today(),
        "duration_minutes": 45,
        "task_type": "study",
        "related_topics": ["Python"],
        "learning_method": "Read and practice",
        "expected_output": "Notes and exercise",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(goal=None, tasks=None):
    goal = goal or valid_goal()
    tasks = tasks or [make_task("task-1"), make_task("task-2", date=date.today() + timedelta(days=1))]
    planned_minutes = sum(task.duration_minutes for task in tasks)
    return StudyPlan(
        goal=goal,
        overall_route="Learn basics, practice, then build.",
        phases=[
            StudyPhase(
                phase_index=1,
                title="Foundation",
                objective="Learn core Python concepts",
                start_date=date.today(),
                end_date=min(goal.deadline, date.today() + timedelta(days=6)),
                milestone="Complete core exercises",
                weekly_plans=[
                    WeeklyPlan(
                        week_index=1,
                        start_date=date.today(),
                        end_date=min(goal.deadline, date.today() + timedelta(days=6)),
                        objective="Complete first week",
                        review_focus="Python basics",
                        tasks=tasks,
                    )
                ],
            )
        ],
        methods=["practice"],
        time_budget=TimeBudget(
            total_days=max(1, (goal.deadline - date.today()).days + 1),
            total_weeks=3,
            total_available_minutes=goal.daily_available_minutes * goal.weekly_available_days * 3,
            planned_minutes=planned_minutes,
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        risks=[],
        review_schedule=ReviewSchedule(
            daily_review_minutes=10,
            weekly_review_day="Sunday",
            review_strategy="Review mistakes weekly.",
        ),
        suggestions="Keep tasks small.",
    )


def valid_review_report():
    return ReviewReport(
        period_start=date.today() - timedelta(days=3),
        period_end=date.today(),
        completion_rate=0.5,
        completed_task_count=1,
        total_task_count=2,
        overdue_tasks=[],
        consecutive_unfinished_topics=[],
        weak_points=["functions"],
        summary="Needs more practice.",
        suggestions=["Add function exercises."],
    )


def all_tasks(plan: StudyPlan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


class RecordingRealPlanLLM:
    calls = 0

    def __init__(self, plan: StudyPlan | None = None):
        self.plan = plan

    @classmethod
    def from_env(cls, env_path):
        cls.calls += 1
        return cls()

    def generate_study_plan(self, goal: StudyGoal):
        self.plan = valid_plan(goal=goal)
        return self.plan


class BrokenRealPlanLLM:
    @classmethod
    def from_env(cls, env_path):
        return cls()

    def generate_study_plan(self, goal: StudyGoal):
        raise RuntimeError("real provider failed")


class RecordingRealReplanLLM:
    calls = 0

    @classmethod
    def from_env(cls, env_path):
        cls.calls += 1
        return cls()

    def replan(self, request):
        adjusted = valid_plan(goal=request.original_plan.goal, tasks=request.remaining_tasks)
        for task in all_tasks(adjusted):
            task.date = date.today() + timedelta(days=2)
        return adjusted


class TestF8RealWorkflowConfiguration:
    def test_f8_real_001_from_env_reads_use_real_llm_switch(self, tmp_path):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)

        workflow = PlannerWorkflow.from_env(env_path)

        assert getattr(workflow, "use_real_llm") is True

    def test_f8_real_002_real_switch_builds_real_plan_llm(self, tmp_path, monkeypatch):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)
        monkeypatch.setattr(
            "study_planner.infrastructure.llm.real_study_plan_llm.RealStudyPlanLLM",
            RecordingRealPlanLLM,
        )

        workflow = PlannerWorkflow.from_env(env_path)

        assert RecordingRealPlanLLM.calls == 1
        assert getattr(workflow.planner_agent, "llm", None).__class__ is RecordingRealPlanLLM

    def test_f8_real_003_fake_switch_keeps_local_planner(self, tmp_path):
        env_path = write_env(tmp_path / ".env", use_real_llm=False)

        workflow = PlannerWorkflow.from_env(env_path)

        assert getattr(workflow, "use_real_llm") is False
        assert getattr(workflow.planner_agent, "llm", None) is None

    def test_f8_real_004_missing_deepseek_config_fails_fast(self, tmp_path):
        env_path = write_env(tmp_path / ".env", use_real_llm=True, api_key="", model="")

        with pytest.raises(ValueError, match="DEEPSEEK|API|model|key"):
            PlannerWorkflow.from_env(env_path)


class TestF8RealPlanGeneration:
    def test_f8_real_005_workflow_calls_real_plan_llm_when_enabled(self, tmp_path, monkeypatch):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)
        monkeypatch.setattr(
            "study_planner.infrastructure.llm.real_study_plan_llm.RealStudyPlanLLM",
            RecordingRealPlanLLM,
        )

        result = PlannerWorkflow.from_env(env_path).run(valid_goal())

        assert result.final_plan is not None
        assert result.final_plan.overall_route == "Learn basics, practice, then build."

    def test_f8_real_006_application_factory_uses_real_workflow(self, tmp_path, monkeypatch):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)
        monkeypatch.setattr(
            "study_planner.infrastructure.llm.real_study_plan_llm.RealStudyPlanLLM",
            RecordingRealPlanLLM,
        )

        use_case = build_plan_workflow_use_case(env_path, debug=True)
        plan = use_case.execute(valid_goal())

        assert isinstance(plan, StudyPlan)
        assert use_case.last_workflow_state.trace
        assert getattr(use_case.workflow.planner_agent, "llm", None).__class__ is RecordingRealPlanLLM

    def test_f8_real_007_real_generation_error_enters_workflow_errors(self, tmp_path, monkeypatch):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)
        monkeypatch.setattr(
            "study_planner.infrastructure.llm.real_study_plan_llm.RealStudyPlanLLM",
            BrokenRealPlanLLM,
        )

        result = PlannerWorkflow.from_env(env_path).run(valid_goal())

        assert result.errors
        assert result.final_plan is None
        assert "provider failed" in result.errors[0].message


class TestF8RealReplanWorkflow:
    def test_f8_real_008_replan_from_env_reads_real_switch(self, tmp_path):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)

        planner = WorkflowReplanPlanner.from_env(env_path)

        assert getattr(planner, "use_real_llm") is True

    def test_f8_real_009_replan_factory_uses_workflow_planner(self, tmp_path):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)

        planner = build_replan_workflow_planner(env_path, debug=True)

        assert isinstance(planner, WorkflowReplanPlanner)
        assert getattr(planner, "debug") is True

    def test_f8_real_010_real_replan_keeps_completed_tasks_locked(self, tmp_path, monkeypatch):
        env_path = write_env(tmp_path / ".env", use_real_llm=True)
        monkeypatch.setattr(
            "study_planner.infrastructure.llm.real_study_plan_llm.RealStudyPlanLLM",
            RecordingRealPlanLLM,
        )
        original = valid_plan(tasks=[make_task("done", status="done"), make_task("todo", status="todo")])
        request = type(
            "Request",
            (),
            {
                "original_plan": original,
                "review_report": valid_review_report(),
                "remaining_tasks": [all_tasks(original)[1]],
            },
        )()

        adjusted = WorkflowReplanPlanner.from_env(env_path).replan(request)

        assert all_tasks(adjusted)[0].status == "done"
        assert all_tasks(adjusted)[0].date == all_tasks(original)[0].date


class TestF8RealPageIntegrationContracts:
    def test_f8_real_011_goal_page_uses_application_workflow_factory(self):
        page_source = (
            __import__("pathlib")
            .Path("study_planner/interfaces/streamlit/pages/01_Goal_Setup.py")
            .read_text(encoding="utf-8")
        )

        assert "build_plan_workflow_use_case" in page_source
        assert "RealStudyPlanLLM.from_env" not in page_source
        assert "PlannerWorkflow.from_env" not in page_source

    def test_f8_real_012_replan_page_uses_application_workflow_factory(self):
        page_source = (
            __import__("pathlib")
            .Path("study_planner/interfaces/streamlit/pages/04_Review_Replan.py")
            .read_text(encoding="utf-8")
        )

        assert "build_replan_workflow_planner" in page_source
        assert "SimpleReplanPlanner(" not in page_source
        assert "WorkflowReplanPlanner.from_env" not in page_source
