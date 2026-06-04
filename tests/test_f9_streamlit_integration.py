from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib import import_module
from pathlib import Path

import pytest

from study_planner.domain.models import (
    LearningMaterial,
    MaterialAnswer,
    Citation,
    ReviewReport,
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TimeBudget,
    WeeklyPlan,
)


CURRENT_DATE = date(2026, 6, 4)
STREAMLIT_ROOT = Path("study_planner/interfaces/streamlit")
PAGE_ROOT = STREAMLIT_ROOT / "pages"
PAGE_MODULES = [
    "study_planner.interfaces.streamlit.pages.01_Goal_Setup",
    "study_planner.interfaces.streamlit.pages.02_Plan_Dashboard",
    "study_planner.interfaces.streamlit.pages.03_Material_QA",
    "study_planner.interfaces.streamlit.pages.04_Review_Replan",
    "study_planner.interfaces.streamlit.pages.05_Plan_Export",
]


def f9_attr(module_name: str, attr_name: str):
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"F9 module is required: {module_name}") from exc
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise AssertionError(f"F9 attribute is required: {module_name}.{attr_name}") from exc


def page_source(filename: str) -> str:
    path = PAGE_ROOT / filename
    assert path.exists(), f"Streamlit page is required: {path}"
    return path.read_text(encoding="utf-8")


def valid_goal(**overrides) -> StudyGoal:
    data = {
        "subject": "Python programming",
        "target": "Master Python basics and build a small project",
        "deadline": CURRENT_DATE + timedelta(days=26),
        "current_level": "beginner",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["video", "project"],
        "weak_points": ["recursion", "oop"],
        "extra_requirements": "Add more practice tasks.",
    }
    data.update(overrides)
    return StudyGoal(**data)


def make_task(task_id: str = "task-1", **overrides) -> StudyTask:
    data = {
        "id": task_id,
        "title": f"Study task {task_id}",
        "date": CURRENT_DATE,
        "duration_minutes": 60,
        "task_type": "study",
        "related_topics": ["Python basics"],
        "learning_method": "Read and practice",
        "expected_output": "Notes and exercise",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(tasks: list[StudyTask] | None = None, goal: StudyGoal | None = None, **overrides) -> StudyPlan:
    goal = goal or valid_goal()
    tasks = tasks or [
        make_task("task-1", status="done"),
        make_task("task-2", date=CURRENT_DATE + timedelta(days=1)),
        make_task("task-3", date=CURRENT_DATE + timedelta(days=2), related_topics=["functions"]),
    ]
    data = {
        "goal": goal,
        "overall_route": "Learn basics, practice daily, then build a project.",
        "phases": [
            StudyPhase(
                phase_index=1,
                title="Foundation",
                objective="Learn core syntax and functions",
                start_date=CURRENT_DATE,
                end_date=CURRENT_DATE + timedelta(days=13),
                milestone="Complete basic exercises",
                weekly_plans=[
                    WeeklyPlan(
                        week_index=1,
                        start_date=CURRENT_DATE,
                        end_date=CURRENT_DATE + timedelta(days=6),
                        objective="Complete first week",
                        review_focus="variables, loops, functions",
                        tasks=tasks,
                    )
                ],
            )
        ],
        "methods": ["read", "practice", "project"],
        "time_budget": TimeBudget(
            total_days=27,
            total_weeks=4,
            total_available_minutes=2400,
            planned_minutes=sum(task.duration_minutes for task in tasks),
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        "risks": ["Daily time may be tight."],
        "review_schedule": ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="Sunday",
            review_strategy="Review daily notes and weekly weak points.",
        ),
        "suggestions": "Keep every task small and inspectable.",
    }
    data.update(overrides)
    return StudyPlan(**data)


def valid_review_report(**overrides) -> ReviewReport:
    data = {
        "period_start": CURRENT_DATE - timedelta(days=3),
        "period_end": CURRENT_DATE,
        "completion_rate": 1 / 3,
        "completed_task_count": 1,
        "total_task_count": 3,
        "overdue_tasks": ["task-2"],
        "consecutive_unfinished_topics": ["functions"],
        "weak_points": ["functions"],
        "summary": "Progress is behind schedule.",
        "suggestions": ["Reduce task size.", "Add function practice."],
    }
    data.update(overrides)
    return ReviewReport(**data)


def valid_material(**overrides) -> LearningMaterial:
    data = {
        "id": "material-1",
        "filename": "python_notes.txt",
        "file_type": "txt",
        "source_path": "uploads/python_notes.txt",
        "uploaded_at": __import__("datetime").datetime(2026, 6, 4, 9, 0),
        "status": "ready",
        "chunk_count": 2,
        "error_message": "",
        "raw_text": "Recursion calls itself.",
    }
    data.update(overrides)
    return LearningMaterial(**data)


def valid_answer() -> MaterialAnswer:
    return MaterialAnswer(
        question="What is recursion?",
        answer="Recursion is a function calling itself with a base case.",
        citations=[
            Citation(
                filename="python_notes.txt",
                chunk_id="chunk-1",
                snippet="Recursion calls itself.",
                score=0.9,
                material_id="material-1",
                page_number=1,
            )
        ],
    )


def all_tasks(plan: StudyPlan) -> list[StudyTask]:
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


class FakeSessionState(dict):
    pass


@dataclass
class FakeStorageService:
    fail: bool = False
    saved_plan: StudyPlan | None = None
    saved_report: ReviewReport | None = None
    plan_id: str = "plan-1"

    def save_study_plan(self, plan: StudyPlan, goal_id: str | None = None):
        if self.fail:
            raise RuntimeError("storage failed")
        self.saved_plan = plan
        return self.plan_id

    def save_review_report(self, report: ReviewReport, plan_id: str | None = None):
        if self.fail:
            raise RuntimeError("storage failed")
        self.saved_report = report
        return "review-1"

    def save_adjusted_plan(self, plan: StudyPlan, report: ReviewReport):
        if self.fail:
            raise RuntimeError("storage failed")
        self.saved_plan = plan
        self.saved_report = report
        return self.plan_id


class TestF9Stage1AppEntryAndPageStructure:
    def test_f9_001_streamlit_app_entry_exists(self):
        assert (STREAMLIT_ROOT / "app.py").exists()

    def test_f9_002_home_page_displays_product_entry(self):
        source = (STREAMLIT_ROOT / "app.py").read_text(encoding="utf-8")
        assert "set_page_config" in source
        assert "学习" in source or "Study" in source

    def test_f9_003_goal_setup_page_exists(self):
        assert (PAGE_ROOT / "01_Goal_Setup.py").exists()

    def test_f9_004_plan_dashboard_page_exists(self):
        assert (PAGE_ROOT / "02_Plan_Dashboard.py").exists()

    def test_f9_005_material_qa_page_exists(self):
        assert (PAGE_ROOT / "03_Material_QA.py").exists()

    def test_f9_006_review_replan_page_exists(self):
        assert (PAGE_ROOT / "04_Review_Replan.py").exists()

    def test_f9_007_plan_export_page_exists(self):
        assert (PAGE_ROOT / "05_Plan_Export.py").exists()

    def test_f9_008_page_order_matches_main_flow(self):
        names = [path.name for path in sorted(PAGE_ROOT.glob("*.py"))]
        assert names[:5] == [
            "01_Goal_Setup.py",
            "02_Plan_Dashboard.py",
            "03_Material_QA.py",
            "04_Review_Replan.py",
            "05_Plan_Export.py",
        ]


class TestF9Stage2PageDecoupling:
    def test_f9_009_pages_do_not_call_llm_sdk_directly(self):
        forbidden = ["openai", "langchain", "ChatOpenAI", "DeepSeek", "RealStudyPlanLLM.from_env"]
        for path in PAGE_ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not any(token in source for token in forbidden), path

    def test_f9_010_pages_do_not_write_sql_directly(self):
        forbidden = ["psycopg", "SELECT ", "INSERT ", "UPDATE ", "DELETE "]
        for path in PAGE_ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not any(token in source for token in forbidden), path

    def test_f9_011_pages_do_not_call_milvus_sdk_directly(self):
        for path in PAGE_ROOT.glob("*.py"):
            assert "pymilvus" not in path.read_text(encoding="utf-8")

    def test_f9_012_pages_do_not_depend_on_concrete_agent_nodes(self):
        for path in PAGE_ROOT.glob("*.py"):
            assert "study_planner.agents.nodes" not in path.read_text(encoding="utf-8")

    def test_f9_013_pages_depend_on_application_layer(self):
        for filename in ["01_Goal_Setup.py", "02_Plan_Dashboard.py", "03_Material_QA.py", "04_Review_Replan.py", "05_Plan_Export.py"]:
            source = page_source(filename)
            assert "study_planner.application" in source

    def test_f9_014_app_startup_does_not_force_external_service_connections(self):
        source = (STREAMLIT_ROOT / "app.py").read_text(encoding="utf-8")
        assert "RealStudyPlanLLM.from_env" not in source
        assert "psycopg.connect" not in source
        assert "MilvusClient" not in source

    def test_f9_015_page_errors_do_not_expose_sensitive_config(self):
        sanitize_error_message = f9_attr("study_planner.application.ui_errors", "sanitize_error_message")
        message = sanitize_error_message("failed with key sk-secret and password=abc")
        assert "sk-secret" not in message
        assert "password=abc" not in message

    def test_f9_016_pages_can_be_imported_by_pytest(self):
        for module_name in PAGE_MODULES:
            module = import_module(module_name)
            assert module is not None


class TestF9Stage3SessionStateAndPersistence:
    def test_f9_017_initializes_required_session_state_keys(self):
        initialize_session_state = f9_attr("study_planner.application.streamlit_state", "initialize_session_state")
        state = FakeSessionState()
        initialize_session_state(state)
        for key in ["study_goal", "study_plan", "selected_plan_id", "materials", "last_review_report", "errors"]:
            assert key in state

    def test_f9_018_goal_submit_writes_study_goal(self):
        set_study_goal = f9_attr("study_planner.application.streamlit_state", "set_study_goal")
        state = FakeSessionState()
        goal = valid_goal()
        set_study_goal(state, goal)
        assert state["study_goal"] == goal

    def test_f9_019_plan_generation_writes_study_plan(self):
        set_study_plan = f9_attr("study_planner.application.streamlit_state", "set_study_plan")
        state = FakeSessionState()
        plan = valid_plan()
        set_study_plan(state, plan)
        assert state["study_plan"] == plan

    def test_f9_020_plan_save_writes_selected_plan_id(self):
        save_plan_to_session = f9_attr("study_planner.application.streamlit_state", "save_plan_to_session")
        state = FakeSessionState()
        plan_id = save_plan_to_session(state, valid_plan(), plan_id="plan-1")
        assert plan_id == "plan-1"
        assert state["selected_plan_id"] == "plan-1"

    def test_f9_021_material_upload_updates_materials(self):
        add_material_to_session = f9_attr("study_planner.application.streamlit_state", "add_material_to_session")
        state = FakeSessionState(materials=[])
        material = valid_material()
        add_material_to_session(state, material)
        assert state["materials"] == [material]

    def test_f9_022_review_generation_writes_last_review_report(self):
        set_last_review_report = f9_attr("study_planner.application.streamlit_state", "set_last_review_report")
        state = FakeSessionState()
        report = valid_review_report()
        set_last_review_report(state, report)
        assert state["last_review_report"] == report

    def test_f9_023_adjustment_preview_does_not_override_study_plan(self):
        set_pending_adjusted_plan = f9_attr("study_planner.application.streamlit_state", "set_pending_adjusted_plan")
        original = valid_plan()
        pending = valid_plan(tasks=[make_task("future", date=CURRENT_DATE + timedelta(days=4))])
        state = FakeSessionState(study_plan=original)
        set_pending_adjusted_plan(state, pending, valid_review_report())
        assert state["study_plan"] == original
        assert state["pending_adjusted_plan"] == pending

    def test_f9_024_save_adjustment_overrides_study_plan(self):
        commit_pending_adjustment = f9_attr("study_planner.application.streamlit_state", "commit_pending_adjustment")
        pending = valid_plan(tasks=[make_task("future", date=CURRENT_DATE + timedelta(days=4))])
        state = FakeSessionState(study_plan=valid_plan(), pending_adjusted_plan=pending, pending_review_report=valid_review_report())
        commit_pending_adjustment(state)
        assert state["study_plan"] == pending
        assert "pending_adjusted_plan" not in state

    def test_f9_025_refresh_restores_latest_plan(self):
        restore_latest_plan = f9_attr("study_planner.application.streamlit_state", "restore_latest_plan")
        state = FakeSessionState()
        service = FakeStorageService()
        service.saved_plan = valid_plan()
        restore_latest_plan(state, service)
        assert state["study_plan"] == service.saved_plan

    def test_f9_026_refresh_keeps_task_status(self):
        restore_latest_plan = f9_attr("study_planner.application.streamlit_state", "restore_latest_plan")
        plan = valid_plan(tasks=[make_task("task-1", status="done")])
        service = FakeStorageService(saved_plan=plan)
        state = FakeSessionState()
        restore_latest_plan(state, service)
        assert all_tasks(state["study_plan"])[0].status == "done"


class TestF9Stage4GoalToPlanWorkflow:
    def test_f9_027_goal_form_contains_required_fields(self):
        source = page_source("01_Goal_Setup.py")
        for token in ["text_input", "text_area", "date_input", "selectbox", "number_input", "slider", "multiselect"]:
            assert token in source

    def test_f9_028_empty_required_fields_do_not_generate_plan(self):
        collect_study_goal = f9_attr("study_planner.application.study_goal_input", "collect_study_goal")
        with pytest.raises(ValueError):
            collect_study_goal({"subject": "", "target": "", "deadline": CURRENT_DATE})

    def test_f9_029_deadline_cannot_be_before_today(self):
        collect_study_goal = f9_attr("study_planner.application.study_goal_input", "collect_study_goal")
        with pytest.raises(ValueError):
            collect_study_goal(
                {
                    "subject": "Python",
                    "target": "Learn Python",
                    "deadline": CURRENT_DATE - timedelta(days=1),
                    "current_level": "beginner",
                    "daily_available_minutes": 60,
                    "weekly_available_days": 5,
                }
            )

    def test_f9_030_generate_plan_shows_loading_state(self):
        source = page_source("01_Goal_Setup.py")
        assert "st.spinner" in source

    def test_f9_031_fake_environment_generates_plan(self):
        PlannerWorkflow = f9_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        result = PlannerWorkflow.from_env(".env", use_real_llm=False).run(valid_goal())
        assert result.final_plan is not None

    @pytest.mark.manual
    def test_f9_032_real_environment_generates_plan(self):
        PlannerWorkflow = f9_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        result = PlannerWorkflow.from_env(".env").run(valid_goal(subject="Machine learning"))
        assert result.final_plan is not None
        assert "Machine" in result.final_plan.goal.subject or "machine" in repr(result.final_plan).lower()

    def test_f9_033_generation_failure_shows_error(self):
        render_user_error = f9_attr("study_planner.application.ui_errors", "render_user_error")
        message = render_user_error(RuntimeError("provider failed"))
        assert "provider failed" in message
        assert "Traceback" not in message

    def test_f9_034_generation_success_displays_goal_summary(self):
        build_goal_summary_view = f9_attr("study_planner.application.goal_page", "build_goal_summary_view")
        summary = build_goal_summary_view(valid_goal())
        assert summary["subject"] == "Python programming"
        assert "deadline" in summary

    def test_f9_035_agent_workflow_trace_is_visible(self):
        source = page_source("01_Goal_Setup.py")
        assert "last_workflow_trace" in source
        assert "dataframe" in source

    def test_f9_036_success_guides_user_to_dashboard(self):
        source = page_source("01_Goal_Setup.py")
        assert "Dashboard" in source or "看板" in source


class TestF9Stage5DashboardIntegration:
    def test_f9_037_dashboard_empty_state(self):
        build_dashboard_view = f9_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        view = build_dashboard_view(None, today=CURRENT_DATE)
        assert view.is_empty is True

    def test_f9_038_dashboard_displays_goal_summary(self):
        build_dashboard_view = f9_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        view = build_dashboard_view(valid_plan(), today=CURRENT_DATE)
        assert view.goal_summary["subject"] == "Python programming"

    def test_f9_039_dashboard_displays_three_level_plan(self):
        build_dashboard_view = f9_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        view = build_dashboard_view(valid_plan(), today=CURRENT_DATE)
        assert view.phase_sections
        assert view.phase_sections[0].weekly_sections
        assert view.phase_sections[0].weekly_sections[0].tasks

    def test_f9_040_dashboard_displays_today_and_week_tasks(self):
        build_dashboard_view = f9_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        view = build_dashboard_view(valid_plan(), today=CURRENT_DATE)
        assert view.today_tasks
        assert view.task_rows

    def test_f9_041_dashboard_displays_progress_charts(self):
        build_dashboard_view = f9_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        view = build_dashboard_view(valid_plan(), today=CURRENT_DATE)
        assert view.daily_minutes_chart_data
        assert view.weekly_minutes_chart_data

    def test_f9_042_task_status_update_persists_to_review(self):
        update_task_progress = f9_attr("study_planner.application.plan_dashboard", "update_task_progress")
        plan = valid_plan(tasks=[make_task("task-1", status="todo")])
        updated = update_task_progress(plan, task_id="task-1", status="done", today=CURRENT_DATE)
        assert all_tasks(updated)[0].status == "done"

    def test_f9_043_task_date_update_succeeds(self):
        update_task_progress = f9_attr("study_planner.application.plan_dashboard", "update_task_progress")
        new_date = CURRENT_DATE + timedelta(days=2)
        updated = update_task_progress(valid_plan(), task_id="task-2", new_date=new_date, today=CURRENT_DATE)
        assert any(task.id == "task-2" and task.date == new_date for task in all_tasks(updated))

    def test_f9_044_task_duration_update_succeeds(self):
        update_task_progress = f9_attr("study_planner.application.plan_dashboard", "update_task_progress")
        updated = update_task_progress(valid_plan(), task_id="task-2", duration_minutes=30, today=CURRENT_DATE)
        assert any(task.id == "task-2" and task.duration_minutes == 30 for task in all_tasks(updated))

    def test_f9_045_invalid_task_update_is_rejected(self):
        update_task_progress = f9_attr("study_planner.application.plan_dashboard", "update_task_progress")
        with pytest.raises(Exception):
            update_task_progress(valid_plan(), task_id="task-2", new_date=CURRENT_DATE + timedelta(days=60), today=CURRENT_DATE)

    def test_f9_046_save_failure_keeps_dashboard_state(self):
        save_dashboard_plan = f9_attr("study_planner.application.streamlit_state", "save_dashboard_plan")
        state = FakeSessionState(study_plan=valid_plan())
        with pytest.raises(Exception):
            save_dashboard_plan(state, valid_plan(), FakeStorageService(fail=True))
        assert state["study_plan"] is not None


class TestF9Stage6MaterialQAIntegration:
    def test_f9_047_material_page_empty_state(self):
        build_material_qa_view = f9_attr("study_planner.application.material_rag", "build_material_qa_view")
        view = build_material_qa_view(materials=[], latest_answer=None)
        assert view.is_empty is True

    def test_f9_048_upload_txt_material_succeeds(self, tmp_path):
        create_material_from_upload = f9_attr("study_planner.application.material_rag", "create_material_from_upload")
        upload = type("Upload", (), {"name": "notes.txt", "getvalue": lambda self: b"recursion"})()
        material = create_material_from_upload(upload, upload_dir=tmp_path)
        assert material.file_type == "txt"

    def test_f9_049_upload_markdown_material_succeeds(self, tmp_path):
        create_material_from_upload = f9_attr("study_planner.application.material_rag", "create_material_from_upload")
        upload = type("Upload", (), {"name": "notes.md", "getvalue": lambda self: b"# Recursion"})()
        material = create_material_from_upload(upload, upload_dir=tmp_path)
        assert material.file_type == "markdown"

    def test_f9_050_upload_pdf_material_succeeds(self, tmp_path):
        create_material_from_upload = f9_attr("study_planner.application.material_rag", "create_material_from_upload")
        upload = type("Upload", (), {"name": "course.pdf", "getvalue": lambda self: b"%PDF-1.4"})()
        material = create_material_from_upload(upload, upload_dir=tmp_path)
        assert material.file_type == "pdf"

    def test_f9_051_unsupported_file_type_is_rejected(self, tmp_path):
        create_material_from_upload = f9_attr("study_planner.application.material_rag", "create_material_from_upload")
        upload = type("Upload", (), {"name": "bad.exe", "getvalue": lambda self: b"x"})()
        with pytest.raises(Exception):
            create_material_from_upload(upload, upload_dir=tmp_path)

    def test_f9_052_can_ask_question_after_upload(self):
        build_material_qa_view = f9_attr("study_planner.application.material_rag", "build_material_qa_view")
        view = build_material_qa_view(materials=[valid_material()], latest_answer=None)
        assert view.can_ask_question is True

    def test_f9_053_qa_displays_citations(self):
        build_material_qa_view = f9_attr("study_planner.application.material_rag", "build_material_qa_view")
        view = build_material_qa_view(materials=[valid_material()], latest_answer=valid_answer())
        assert view.latest_answer.citations

    def test_f9_054_no_retrieval_result_shows_hint(self):
        answer_material_question = f9_attr("study_planner.application.material_rag", "answer_material_question")
        with pytest.raises(Exception, match="material|资料|source|retriev"):
            answer_material_question("unrelated question", retriever=type("Retriever", (), {"search": lambda self, q: []})())

    def test_f9_055_rag_service_failure_does_not_crash_page(self):
        render_user_error = f9_attr("study_planner.application.ui_errors", "render_user_error")
        message = render_user_error(RuntimeError("RAG unavailable"))
        assert "RAG unavailable" in message


class TestF9Stage7ReviewReplanIntegration:
    def test_f9_056_review_empty_state(self):
        build_review_page_view = f9_attr("study_planner.application.review_replan", "build_review_page_view")
        view = build_review_page_view(None)
        assert view.is_empty is True

    def test_f9_057_review_progress_table(self):
        build_review_page_view = f9_attr("study_planner.application.review_replan", "build_review_page_view")
        view = build_review_page_view(valid_plan())
        assert view.progress_rows

    def test_f9_058_review_text_persists_in_session(self):
        set_review_text = f9_attr("study_planner.application.streamlit_state", "set_review_text")
        state = FakeSessionState()
        set_review_text(state, "This week was hard.")
        assert state["review_text"] == "This week was hard."

    def test_f9_059_review_report_metrics_match_plan(self):
        GenerateReviewReportUseCase = f9_attr("study_planner.application.review_replan", "GenerateReviewReportUseCase")
        llm = type("LLM", (), {"generate_review_report": lambda self, req: valid_review_report().__dict__})()
        report = GenerateReviewReportUseCase(llm=llm).execute(valid_plan(), current_date=CURRENT_DATE)
        assert report.completed_task_count == 1
        assert report.total_task_count == 3

    def test_f9_060_review_suggestions_are_list_items(self):
        report = valid_review_report(suggestions=["A", "B"])
        assert isinstance(report.suggestions, list)
        assert len(report.suggestions) == 2

    def test_f9_061_auto_replan_generates_preview(self):
        generate_adjustment_preview = f9_attr("study_planner.application.review_replan", "generate_adjustment_preview")
        plan = valid_plan()
        request = type("Request", (), {"original_plan": plan, "review_report": valid_review_report(), "remaining_tasks": all_tasks(plan)[1:]})()
        planner = type("Planner", (), {"replan": lambda self, req: valid_plan(tasks=[make_task("task-1", status="done"), make_task("task-2", date=CURRENT_DATE + timedelta(days=3))])})()
        preview = generate_adjustment_preview(request, planner=planner, session_state=FakeSessionState())
        assert preview.adjusted_plan is not None

    def test_f9_062_auto_replan_keeps_completed_tasks(self):
        WorkflowReplanPlanner = f9_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        original = valid_plan()
        request = type("Request", (), {"original_plan": original, "review_report": valid_review_report(), "remaining_tasks": all_tasks(original)[1:]})()
        adjusted = WorkflowReplanPlanner().replan(request)
        assert all_tasks(adjusted)[0].status == "done"

    def test_f9_063_infeasible_adjustment_shows_error(self):
        validate_adjusted_plan = f9_attr("study_planner.application.review_replan", "validate_adjusted_plan")
        plan = valid_plan(tasks=[make_task("too-long", duration_minutes=999)])
        validation = validate_adjusted_plan(plan, current_date=CURRENT_DATE)
        assert validation.is_valid is False

    def test_f9_064_save_adjustment_updates_dashboard_plan(self):
        save_adjusted_plan = f9_attr("study_planner.application.review_replan", "save_adjusted_plan")
        adjusted = valid_plan(tasks=[make_task("task-1", status="done"), make_task("task-2", date=CURRENT_DATE + timedelta(days=4))])
        state = FakeSessionState(study_plan=valid_plan(), pending_adjusted_plan=adjusted, pending_review_report=valid_review_report())
        saved = save_adjusted_plan(state, repository=FakeStorageService(), current_date=CURRENT_DATE)
        assert saved == adjusted
        assert state["study_plan"] == adjusted

    def test_f9_065_cancel_adjustment_clears_preview(self):
        cancel_adjustment_preview = f9_attr("study_planner.application.review_replan", "cancel_adjustment_preview")
        state = FakeSessionState(pending_adjusted_plan=valid_plan(), pending_review_report=valid_review_report())
        cancel_adjustment_preview(state)
        assert "pending_adjusted_plan" not in state


class TestF9Stage8ExportIntegration:
    def test_f9_066_export_empty_state(self):
        build_export_page_view = f9_attr("study_planner.application.plan_export", "build_export_page_view")
        view = build_export_page_view(None)
        assert view.is_empty is True

    def test_f9_067_markdown_download_available(self):
        build_export_page_view = f9_attr("study_planner.application.plan_export", "build_export_page_view")
        view = build_export_page_view(valid_plan())
        assert view.can_export_markdown is True

    def test_f9_068_html_download_available(self):
        build_export_page_view = f9_attr("study_planner.application.plan_export", "build_export_page_view")
        view = build_export_page_view(valid_plan())
        assert view.can_export_html is True

    def test_f9_069_export_content_matches_current_plan(self):
        MarkdownExporter = f9_attr("study_planner.application.plan_export", "MarkdownExporter")
        plan = valid_plan(tasks=[make_task("done", status="done")])
        content = MarkdownExporter().export(plan)
        assert "done" in content

    def test_f9_070_export_contains_review_report(self):
        ExportRequest = f9_attr("study_planner.application.plan_export", "ExportRequest")
        ExportStudyPlanUseCase = f9_attr("study_planner.application.plan_export", "ExportStudyPlanUseCase")
        MarkdownExporter = f9_attr("study_planner.application.plan_export", "MarkdownExporter")
        content = ExportStudyPlanUseCase(MarkdownExporter()).execute(ExportRequest(study_plan=valid_plan(), review_report=valid_review_report()))
        assert "Progress is behind schedule" in content

    def test_f9_071_chinese_export_is_not_garbled(self):
        MarkdownExporter = f9_attr("study_planner.application.plan_export", "MarkdownExporter")
        content = MarkdownExporter().export(valid_plan(goal=valid_goal(subject="机器学习")))
        assert "机器学习" in content

    def test_f9_072_export_filename_contains_subject_and_date(self):
        generate_export_filename = f9_attr("study_planner.application.plan_export", "generate_export_filename")
        filename = generate_export_filename(valid_plan(), "html", exported_at=__import__("datetime").datetime(2026, 6, 4))
        assert "Python" in filename
        assert "2026" in filename

    def test_f9_073_export_failure_shows_error(self):
        render_user_error = f9_attr("study_planner.application.ui_errors", "render_user_error")
        assert "failed" in render_user_error(RuntimeError("export failed"))


class TestF9Stage9ErrorsLoadingAndEmptyStates:
    def test_f9_074_long_tasks_show_spinner(self):
        for filename in ["01_Goal_Setup.py", "03_Material_QA.py", "04_Review_Replan.py", "05_Plan_Export.py"]:
            assert "spinner" in page_source(filename)

    def test_f9_075_missing_llm_config_has_clear_message(self, tmp_path):
        PlannerWorkflow = f9_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        env_path = tmp_path / ".env"
        env_path.write_text("USE_REAL_LLM=true\n", encoding="utf-8")
        with pytest.raises(ValueError, match="DEEPSEEK|API|model"):
            PlannerWorkflow.from_env(env_path)

    def test_f9_076_postgres_unavailable_app_can_start(self):
        build_storage_service = f9_attr("study_planner.interfaces.streamlit.persistence_state", "build_storage_service")
        service = build_storage_service(env_path="missing.env")
        assert service is not None

    def test_f9_077_milvus_unavailable_material_page_shows_error(self):
        render_user_error = f9_attr("study_planner.application.ui_errors", "render_user_error")
        assert "Milvus" in render_user_error(RuntimeError("Milvus unavailable"))

    def test_f9_078_network_error_does_not_override_existing_plan(self):
        preserve_plan_on_error = f9_attr("study_planner.application.streamlit_state", "preserve_plan_on_error")
        plan = valid_plan()
        state = FakeSessionState(study_plan=plan)
        preserve_plan_on_error(state, RuntimeError("network"))
        assert state["study_plan"] == plan

    def test_f9_079_download_failure_does_not_clear_plan(self):
        preserve_plan_on_error = f9_attr("study_planner.application.streamlit_state", "preserve_plan_on_error")
        plan = valid_plan()
        state = FakeSessionState(study_plan=plan)
        preserve_plan_on_error(state, RuntimeError("download"))
        assert state["study_plan"] == plan

    def test_f9_080_empty_material_question_does_not_call_llm(self):
        validate_material_question_ready = f9_attr("study_planner.application.material_rag", "validate_material_question_ready")
        with pytest.raises(Exception):
            validate_material_question_ready(materials=[], question="What is recursion?")

    def test_f9_081_repeated_clicks_do_not_duplicate_dirty_data(self):
        dedupe_pending_actions = f9_attr("study_planner.application.streamlit_state", "dedupe_pending_actions")
        state = FakeSessionState(pending_actions=["save", "save", "generate"])
        dedupe_pending_actions(state)
        assert state["pending_actions"].count("save") == 1

    def test_f9_082_errors_enter_error_state(self):
        add_ui_error = f9_attr("study_planner.application.streamlit_state", "add_ui_error")
        state = FakeSessionState(errors=[])
        add_ui_error(state, RuntimeError("bad input"))
        assert state["errors"]

    def test_f9_083_raw_traceback_is_not_rendered(self):
        render_user_error = f9_attr("study_planner.application.ui_errors", "render_user_error")
        assert "Traceback" not in render_user_error(RuntimeError("Traceback: internal"))


class TestF9Stage10FakeEndToEnd:
    def test_f9_084_fake_main_flow_from_goal_to_export(self):
        run_fake_main_flow = f9_attr("study_planner.application.streamlit_integration", "run_fake_main_flow")
        result = run_fake_main_flow(valid_goal())
        assert result.plan is not None
        assert result.review_report is not None
        assert result.export_payload is not None

    def test_f9_085_fake_main_flow_does_not_require_external_services(self):
        build_fake_app_services = f9_attr("study_planner.application.streamlit_integration", "build_fake_app_services")
        services = build_fake_app_services()
        assert services.llm.is_fake is True
        assert services.storage.is_fake is True

    def test_f9_086_fake_plan_can_refresh_restore(self):
        restore_latest_plan = f9_attr("study_planner.application.streamlit_state", "restore_latest_plan")
        service = FakeStorageService(saved_plan=valid_plan())
        state = FakeSessionState()
        restore_latest_plan(state, service)
        assert state["study_plan"] is not None

    def test_f9_087_fake_material_upload_and_qa_available(self):
        run_fake_material_flow = f9_attr("study_planner.application.streamlit_integration", "run_fake_material_flow")
        result = run_fake_material_flow("notes.txt", "What is recursion?")
        assert result.answer.citations

    def test_f9_088_fake_task_status_affects_review_metrics(self):
        ProgressAgent = f9_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        tasks = [make_task(f"task-{i}", status="done" if i <= 2 else "todo") for i in range(1, 11)]
        context = ProgressAgent().run(valid_plan(tasks=tasks), current_date=CURRENT_DATE)
        assert context.completed_task_count == 2
        assert context.total_task_count == 10

    def test_f9_089_fake_replan_export_uses_latest_plan(self):
        export_current_plan = f9_attr("study_planner.application.streamlit_integration", "export_current_plan")
        adjusted = valid_plan(tasks=[make_task("adjusted", title="Adjusted task")])
        state = FakeSessionState(study_plan=adjusted)
        content = export_current_plan(state, format="markdown")
        assert "Adjusted task" in content

    def test_f9_090_fake_navigation_has_no_state_break(self):
        simulate_page_navigation = f9_attr("study_planner.application.streamlit_integration", "simulate_page_navigation")
        state = simulate_page_navigation(valid_plan())
        assert state["study_plan"] is not None
        assert "last_review_report" in state

    def test_f9_091_fake_page_imports_pass(self):
        for module_name in PAGE_MODULES:
            assert import_module(module_name)


class TestF9Stage11RealManualAcceptance:
    @pytest.mark.manual
    def test_f9_092_real_llm_generates_plan(self):
        PlannerWorkflow = f9_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        result = PlannerWorkflow.from_env(".env").run(valid_goal(subject="Machine learning"))
        assert result.final_plan is not None

    @pytest.mark.manual
    def test_f9_093_real_llm_failure_is_recoverable(self, tmp_path):
        PlannerWorkflow = f9_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        env_path = tmp_path / ".env"
        env_path.write_text("USE_REAL_LLM=true\nDEEPSEEK_API_KEY=bad\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")
        result = PlannerWorkflow.from_env(env_path).run(valid_goal())
        assert result.errors or result.final_plan is None

    @pytest.mark.manual
    def test_f9_094_real_postgres_refresh_restore(self):
        build_storage_service = f9_attr("study_planner.interfaces.streamlit.persistence_state", "build_storage_service")
        service = build_storage_service(".env")
        plan_id = service.save_study_plan(valid_plan())
        assert service.load_study_plan(plan_id) is not None

    @pytest.mark.manual
    def test_f9_095_real_postgres_saves_task_modification(self):
        build_storage_service = f9_attr("study_planner.interfaces.streamlit.persistence_state", "build_storage_service")
        service = build_storage_service(".env")
        plan = valid_plan(tasks=[make_task("task-1", status="done")])
        plan_id = service.save_study_plan(plan)
        assert all_tasks(service.load_study_plan(plan_id))[0].status == "done"

    @pytest.mark.manual
    def test_f9_096_real_rag_upload_material(self):
        build_real_rag_services = f9_attr("study_planner.infrastructure.rag.factory", "build_real_rag_services")
        services = build_real_rag_services(".env")
        assert services.vector_store is not None

    @pytest.mark.manual
    def test_f9_097_real_rag_material_qa(self):
        answer_material_question = f9_attr("study_planner.application.material_rag", "answer_material_question")
        answer = answer_material_question("What is recursion?")
        assert answer.citations

    @pytest.mark.manual
    def test_f9_098_real_review_metrics_use_real_plan_state(self):
        ProgressAgent = f9_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        context = ProgressAgent().run(valid_plan(), current_date=CURRENT_DATE)
        assert context.completed_task_count == 1
        assert context.total_task_count == 3

    @pytest.mark.manual
    def test_f9_099_real_replan_does_not_override_done_tasks(self):
        WorkflowReplanPlanner = f9_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        plan = valid_plan()
        request = type("Request", (), {"original_plan": plan, "review_report": valid_review_report(), "remaining_tasks": all_tasks(plan)[1:]})()
        adjusted = WorkflowReplanPlanner.from_env(".env").replan(request)
        assert all_tasks(adjusted)[0].status == "done"

    @pytest.mark.manual
    def test_f9_100_real_html_export_can_open(self):
        HTMLExporter = f9_attr("study_planner.application.plan_export", "HTMLExporter")
        html = HTMLExporter().export(valid_plan())
        assert "<html" in html.lower()

    @pytest.mark.manual
    def test_f9_101_real_full_flow_acceptance(self):
        run_real_main_flow = f9_attr("study_planner.application.streamlit_integration", "run_real_main_flow")
        result = run_real_main_flow(valid_goal(subject="Machine learning"))
        assert result.plan is not None
        assert result.export_payload is not None


class TestF9Stage12UsabilityAndRegression:
    def test_f9_102_page_copy_guides_next_step(self):
        for filename in ["01_Goal_Setup.py", "02_Plan_Dashboard.py", "04_Review_Replan.py", "05_Plan_Export.py"]:
            source = page_source(filename)
            assert "st.info" in source or "st.success" in source or "caption" in source

    def test_f9_103_critical_buttons_have_reasonable_states(self):
        for filename in ["04_Review_Replan.py", "05_Plan_Export.py"]:
            source = page_source(filename)
            assert "disabled=" in source

    def test_f9_104_long_text_does_not_overflow_contract(self):
        build_responsive_text = f9_attr("study_planner.application.ui_design", "build_responsive_text")
        rendered = build_responsive_text("x" * 300)
        assert "overflow-wrap" in rendered or "word-break" in rendered

    def test_f9_105_chinese_content_full_flow_not_garbled(self):
        plan = valid_plan(goal=valid_goal(subject="机器学习", target="掌握监督学习"))
        HTMLExporter = f9_attr("study_planner.application.plan_export", "HTMLExporter")
        assert "机器学习" in HTMLExporter().export(plan)

    def test_f9_106_cross_page_state_consistency(self):
        assert_same_current_plan = f9_attr("study_planner.application.streamlit_state", "assert_same_current_plan")
        state = FakeSessionState(study_plan=valid_plan())
        assert_same_current_plan(state, pages=["dashboard", "review", "export"])

    def test_f9_107_regresses_f1_to_f8_core_tests(self):
        regression_manifest = f9_attr("study_planner.application.streamlit_integration", "regression_manifest")
        tests = regression_manifest()
        assert "test_f8_agent_workflow.py" in tests
        assert "test_f6_plan_export.py" in tests

    def test_f9_108_browser_refresh_has_no_key_error(self):
        for module_name in PAGE_MODULES:
            module = import_module(module_name)
            assert module is not None

    def test_f9_109_page_startup_does_not_run_long_tasks(self):
        app_source = (STREAMLIT_ROOT / "app.py").read_text(encoding="utf-8")
        assert "generate_study_plan(" not in app_source
        assert "urlopen(" not in app_source

    def test_f9_110_main_flow_can_restart_with_new_plan(self):
        reset_for_new_plan = f9_attr("study_planner.application.streamlit_state", "reset_for_new_plan")
        state = FakeSessionState(study_plan=valid_plan(), pending_adjusted_plan=valid_plan(), last_review_report=valid_review_report())
        reset_for_new_plan(state)
        assert "pending_adjusted_plan" not in state
        assert state.get("last_review_report") is None


class TestF9Stage13VisualDesignChartsAndInformationArchitecture:
    def test_f9_111_all_pages_have_unified_professional_design(self):
        get_design_tokens = f9_attr("study_planner.application.ui_design", "get_design_tokens")
        tokens = get_design_tokens()
        assert tokens.primary_color
        assert tokens.spacing_scale
        assert tokens.card_radius <= 8

    def test_f9_112_home_page_is_high_quality_and_guiding(self):
        build_home_view = f9_attr("study_planner.application.home_page", "build_home_view")
        view = build_home_view(state=FakeSessionState())
        assert view.hero_title
        assert view.primary_action
        assert view.flow_steps

    def test_f9_113_home_page_handles_empty_and_existing_plan_states(self):
        build_home_view = f9_attr("study_planner.application.home_page", "build_home_view")
        empty = build_home_view(state=FakeSessionState())
        existing = build_home_view(state=FakeSessionState(study_plan=valid_plan()))
        assert empty.primary_action != existing.primary_action

    def test_f9_114_dashboard_charts_provide_insight_beyond_basic_metrics(self):
        build_dashboard_charts = f9_attr("study_planner.application.visual_analytics", "build_dashboard_charts")
        charts = build_dashboard_charts(valid_plan(), today=CURRENT_DATE)
        chart_names = {chart.name for chart in charts}
        assert {"daily_minutes", "weekly_load", "task_status", "topic_distribution"} <= chart_names

    def test_f9_115_review_charts_explain_progress_risk(self):
        build_review_charts = f9_attr("study_planner.application.visual_analytics", "build_review_charts")
        charts = build_review_charts(valid_plan(), valid_review_report(), today=CURRENT_DATE)
        chart_names = {chart.name for chart in charts}
        assert {"completion_distribution", "weak_points", "before_after_dates"} <= chart_names

    def test_f9_116_material_page_visualizes_material_status_and_citation_quality(self):
        build_material_charts = f9_attr("study_planner.application.visual_analytics", "build_material_charts")
        charts = build_material_charts([valid_material()], latest_answer=valid_answer())
        chart_names = {chart.name for chart in charts}
        assert "material_status" in chart_names
        assert "citation_quality" in chart_names

    def test_f9_117_export_page_has_preview_and_format_guidance(self):
        build_export_experience_view = f9_attr("study_planner.application.plan_export", "build_export_experience_view")
        view = build_export_experience_view(valid_plan())
        assert view.preview_html
        assert view.format_guidance

    def test_f9_118_page_integration_decision_is_explicit(self):
        analyze_page_information_architecture = f9_attr("study_planner.application.information_architecture", "analyze_page_information_architecture")
        decision = analyze_page_information_architecture(PAGE_MODULES)
        assert decision.should_merge_pages in {True, False}
        assert decision.reason

    def test_f9_119_page_merging_does_not_break_boundaries(self):
        validate_page_architecture = f9_attr("study_planner.application.information_architecture", "validate_page_architecture")
        result = validate_page_architecture(PAGE_MODULES)
        assert result.uses_application_layer_only is True
        assert result.has_all_f1_to_f8_entrypoints is True

    def test_f9_120_visual_optimization_keeps_accessibility_and_stability(self):
        audit_visual_accessibility = f9_attr("study_planner.application.ui_design", "audit_visual_accessibility")
        result = audit_visual_accessibility(PAGE_MODULES)
        assert result.has_sufficient_contrast is True
        assert result.has_no_text_overlap is True
        assert result.responsive_layout is True
