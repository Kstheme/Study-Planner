from __future__ import annotations

from pathlib import Path
from typing import Any

from study_planner.agents.planner_workflow import PlannerWorkflow, WorkflowReplanPlanner
from study_planner.application.generate_study_plan import GenerateStudyPlanUseCase


def build_plan_workflow_use_case(env_path: str | Path = ".env", debug: bool = False) -> GenerateStudyPlanUseCase:
    workflow = PlannerWorkflow.from_env(str(env_path), debug=debug)
    return GenerateStudyPlanUseCase(workflow=workflow)


def build_replan_workflow_planner(env_path: str | Path = ".env", debug: bool = False) -> WorkflowReplanPlanner:
    return WorkflowReplanPlanner.from_env(str(env_path), debug=debug)


def workflow_trace_rows(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [{"节点": item.get("node", ""), "耗时(ms)": item.get("duration_ms", 0)} for item in trace or []]
