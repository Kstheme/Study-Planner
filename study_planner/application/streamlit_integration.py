from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from study_planner.agents.planner_workflow import PlannerWorkflow, WorkflowReplanPlanner
from study_planner.application.material_rag import build_material_qa_view
from study_planner.application.plan_export import ExportRequest, ExportStudyPlanUseCase, MarkdownExporter
from study_planner.application.review_replan import GenerateReviewReportUseCase, LocalReviewLLM, build_replan_request


@dataclass
class MainFlowResult:
    plan: object
    review_report: object | None
    export_payload: object | None


@dataclass
class FakeServices:
    llm: object
    storage: object


@dataclass
class FakeMaterialFlowResult:
    answer: object


class _FakeFlag:
    is_fake = True


def run_fake_main_flow(goal) -> MainFlowResult:
    plan = PlannerWorkflow(use_resources=False).run(goal).final_plan
    report = GenerateReviewReportUseCase(LocalReviewLLM()).execute(plan, current_date=date.today())
    request = build_replan_request(plan, report, current_date=date.today())
    adjusted = WorkflowReplanPlanner().replan(request)
    export_payload = MarkdownExporter().export(ExportRequest(study_plan=adjusted, review_report=report, format="markdown")).content
    return MainFlowResult(plan=adjusted, review_report=report, export_payload=export_payload)


def build_fake_app_services() -> FakeServices:
    return FakeServices(llm=_FakeFlag(), storage=_FakeFlag())


def run_fake_material_flow(filename: str, question: str) -> FakeMaterialFlowResult:
    from study_planner.domain.models import Citation, MaterialAnswer

    answer = MaterialAnswer(
        question=question,
        answer="Recursion calls itself with a base case.",
        citations=[Citation(filename=filename, chunk_id="chunk-1", snippet="Recursion calls itself.", score=1.0)],
    )
    build_material_qa_view([], answer)
    return FakeMaterialFlowResult(answer=answer)


def export_current_plan(state: dict, format: str = "markdown") -> str:
    result = ExportStudyPlanUseCase().execute(
        ExportRequest(study_plan=state.get("study_plan"), review_report=state.get("last_review_report"), format=format)
    )
    return result.content


def simulate_page_navigation(plan) -> dict:
    return {"study_plan": plan, "materials": [], "last_review_report": None}


def regression_manifest() -> list[str]:
    return [
        "test_f1_study_goal_input.py",
        "test_f2_generate_study_plan.py",
        "test_f3_plan_dashboard_editing.py",
        "test_f4_material_upload_rag.py",
        "test_f5_review_replan.py",
        "test_f6_plan_export.py",
        "test_f7_persistence.py",
        "test_f8_agent_workflow.py",
    ]


def run_real_main_flow(goal) -> MainFlowResult:
    plan = PlannerWorkflow.from_env(".env").run(goal).final_plan
    export_payload = None
    if plan is not None:
        export_payload = MarkdownExporter().export(ExportRequest(study_plan=plan, format="markdown")).content
    return MainFlowResult(plan=plan, review_report=None, export_payload=export_payload)
