from datetime import date, datetime, timedelta
import os
from pathlib import Path

import pytest

from study_planner.application.persistence import ExportRecord, StorageError, StorageService
from study_planner.domain.models import (
    LearningMaterial,
    ReviewReport,
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TaskProgress,
    TimeBudget,
    WeeklyPlan,
)
from study_planner.infrastructure.db import repositories as db_repositories


pytestmark = pytest.mark.integration

CURRENT_DATE = date(2026, 6, 4)
NOW = datetime(2026, 6, 4, 9, 30)


def _postgres_class(name: str):
    try:
        return getattr(db_repositories, name)
    except AttributeError as exc:
        raise AssertionError(f"{name} is required for the real PostgreSQL F7 implementation") from exc


def _database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or _database_url_from_env_file()
    if not value:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to run real PostgreSQL repository tests.")
    return value


def _database_url_from_env_file() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in {"TEST_DATABASE_URL", "DATABASE_URL"}:
            return value.strip().strip('"').strip("'")
    return ""


def valid_goal(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法并完成一个小项目",
        "deadline": date(2026, 6, 30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["视频教程", "项目实践"],
        "weak_points": ["递归", "面向对象"],
        "extra_requirements": "多安排练习任务",
    }
    data.update(overrides)
    return StudyGoal(**data)


def make_task(task_id="task-1", **overrides):
    data = {
        "id": task_id,
        "title": f"学习任务 {task_id}",
        "date": CURRENT_DATE,
        "duration_minutes": 60,
        "task_type": "study",
        "related_topics": ["Python 基础"],
        "learning_method": "阅读文档 + 练习",
        "expected_output": "完成练习并整理笔记",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(tasks=None, goal=None, **overrides):
    goal = goal or valid_goal()
    tasks = tasks if tasks is not None else [
        make_task("task-1", title="学习变量与数据类型"),
        make_task("task-2", title="完成基础语法复习", duration_minutes=30, task_type="review", status="done"),
        make_task("task-3", title="函数练习", date=CURRENT_DATE + timedelta(days=1), task_type="practice"),
    ]
    data = {
        "goal": goal,
        "overall_route": "先学基础语法，再完成练习，最后做小项目。",
        "phases": [
            StudyPhase(
                phase_index=1,
                title="基础入门阶段",
                objective="掌握变量、条件、循环和函数",
                start_date=CURRENT_DATE,
                end_date=CURRENT_DATE + timedelta(days=13),
                milestone="能完成基础语法练习",
                weekly_plans=[
                    WeeklyPlan(
                        week_index=1,
                        start_date=CURRENT_DATE,
                        end_date=CURRENT_DATE + timedelta(days=6),
                        objective="完成基础语法学习",
                        review_focus="变量、条件、循环、函数",
                        tasks=tasks,
                    )
                ],
            )
        ],
        "methods": ["视频教程", "阅读文档", "项目实践"],
        "time_budget": TimeBudget(
            total_days=27,
            total_weeks=4,
            total_available_minutes=2400,
            planned_minutes=sum(task.duration_minutes for task in tasks),
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        "risks": ["每日时间不足可能导致延期"],
        "review_schedule": ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="周日",
            review_strategy="每天复习当天知识点，每周整理薄弱点",
        ),
        "suggestions": "每天完成一个可检查产出",
    }
    data.update(overrides)
    return StudyPlan(**data)


def valid_review_report(**overrides):
    data = {
        "period_start": date(2026, 6, 1),
        "period_end": date(2026, 6, 7),
        "completion_rate": 0.6,
        "completed_task_count": 3,
        "total_task_count": 5,
        "overdue_tasks": ["task-1"],
        "consecutive_unfinished_topics": ["递归"],
        "weak_points": ["递归", "练习时间不足"],
        "summary": "本周完成率一般，需要优先处理延期任务",
        "suggestions": ["降低任务粒度", "增加递归专项练习"],
    }
    data.update(overrides)
    return ReviewReport(**data)


def valid_material(**overrides):
    data = {
        "id": "material-1",
        "filename": "python-basics.pdf",
        "file_type": "pdf",
        "source_path": "uploads/python-basics.pdf",
        "uploaded_at": NOW,
        "status": "ready",
        "chunk_count": 12,
        "error_message": "",
        "raw_text": "",
    }
    data.update(overrides)
    return LearningMaterial(**data)


def all_tasks(plan):
    return [
        task
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    ]


@pytest.fixture()
def postgres_repositories():
    database_url = _database_url()
    initializer_cls = _postgres_class("PostgresDatabaseInitializer")
    initializer = initializer_cls(database_url=database_url, schema="study_planner_test")
    initializer.drop_all()
    initializer.initialize()

    repos = {
        "initializer": initializer,
        "goal": _postgres_class("PostgresStudyGoalRepository")(database_url=database_url, schema="study_planner_test"),
        "plan": _postgres_class("PostgresStudyPlanRepository")(database_url=database_url, schema="study_planner_test"),
        "progress": _postgres_class("PostgresTaskProgressRepository")(database_url=database_url, schema="study_planner_test"),
        "review": _postgres_class("PostgresReviewReportRepository")(database_url=database_url, schema="study_planner_test"),
        "material": _postgres_class("PostgresMaterialRepository")(database_url=database_url, schema="study_planner_test"),
        "export": _postgres_class("PostgresExportRecordRepository")(database_url=database_url, schema="study_planner_test"),
    }
    yield repos
    initializer.drop_all()


def test_postgres_repository_classes_are_complete_and_in_infrastructure_db():
    required = [
        "PostgresDatabaseInitializer",
        "PostgresStudyGoalRepository",
        "PostgresStudyPlanRepository",
        "PostgresTaskProgressRepository",
        "PostgresReviewReportRepository",
        "PostgresMaterialRepository",
        "PostgresExportRecordRepository",
    ]

    for class_name in required:
        cls = _postgres_class(class_name)
        assert "infrastructure.db" in cls.__module__


def test_postgres_initializer_creates_required_tables(postgres_repositories):
    initializer = postgres_repositories["initializer"]

    assert initializer.has_table("study_goals")
    assert initializer.has_table("study_plans")
    assert initializer.has_table("task_progress")
    assert initializer.has_table("review_reports")
    assert initializer.has_table("materials")
    assert initializer.has_table("export_records")


def test_postgres_study_goal_repository_round_trips_chinese_data(postgres_repositories):
    repo = postgres_repositories["goal"]
    goal = valid_goal(subject="机器学习", target="理解监督学习并完成分类项目", weak_points=["数学基础"])

    goal_id = repo.save(goal)
    restored = repo.get_by_id(goal_id)

    assert restored == goal
    assert repo.get_latest() == goal
    assert repo.metadata(goal_id)["created_at"] <= repo.metadata(goal_id)["updated_at"]


def test_postgres_study_plan_repository_saves_jsonb_payload_and_metadata(postgres_repositories):
    goal_repo = postgres_repositories["goal"]
    plan_repo = postgres_repositories["plan"]
    goal = valid_goal(subject="Python 数据分析")
    goal_id = goal_repo.save(goal)
    plan = valid_plan(goal=goal)

    plan_id = plan_repo.save(plan, goal_id=goal_id)
    restored = plan_repo.get_by_id(plan_id)
    metadata = plan_repo.metadata(plan_id)

    assert restored == plan
    assert metadata["goal_id"] == goal_id
    assert metadata["schema_version"] == 1
    assert all_tasks(restored)[0].id == "task-1"
    assert isinstance(restored.goal.deadline, date)


def test_postgres_study_plan_repository_get_latest_uses_updated_at(postgres_repositories):
    plan_repo = postgres_repositories["plan"]
    first_id = plan_repo.save(valid_plan(goal=valid_goal(subject="first")))
    plan_repo.save(valid_plan(goal=valid_goal(subject="second")))

    plan_repo.update_task(first_id, "task-1", status="done")

    assert plan_repo.get_latest().goal.subject == "first"
    assert plan_repo.metadata_latest()["id"] == first_id


def test_postgres_study_plan_repository_updates_task_without_touching_other_tasks(postgres_repositories):
    plan_repo = postgres_repositories["plan"]
    plan_id = plan_repo.save(valid_plan())

    updated = plan_repo.update_task(
        plan_id,
        "task-1",
        status="done",
        new_date=date(2026, 6, 6),
        duration_minutes=45,
        notes="已复习",
    )
    tasks = {task.id: task for task in all_tasks(updated)}

    assert tasks["task-1"].status == "done"
    assert tasks["task-1"].date == date(2026, 6, 6)
    assert tasks["task-1"].duration_minutes == 45
    assert tasks["task-1"].notes == "已复习"
    assert tasks["task-2"].status == "done"
    assert tasks["task-3"].status == "todo"


def test_postgres_study_plan_repository_update_unknown_task_is_clear_error(postgres_repositories):
    plan_repo = postgres_repositories["plan"]
    plan_id = plan_repo.save(valid_plan())

    with pytest.raises(KeyError):
        plan_repo.update_task(plan_id, "missing-task", status="done")


def test_postgres_task_progress_repository_round_trips_progress(postgres_repositories):
    repo = postgres_repositories["progress"]
    progress = TaskProgress(
        task_id="task-1",
        status="done",
        planned_date=CURRENT_DATE,
        actual_completed_at=NOW,
        duration_minutes=50,
        related_topics=["变量"],
        notes="完成练习",
    )

    progress_id = repo.save_progress(progress)

    assert repo.get_by_id(progress_id) == progress
    assert repo.list_by_task_id("task-1") == [progress]


def test_postgres_review_report_repository_binds_reports_to_plan(postgres_repositories):
    repo = postgres_repositories["review"]
    repo.save(valid_review_report(summary="计划 A 报告"), plan_id="plan-a")
    repo.save(valid_review_report(summary="计划 B 报告"), plan_id="plan-b")

    assert repo.get_latest(plan_id="plan-a").summary == "计划 A 报告"
    assert repo.get_latest(plan_id="plan-b").summary == "计划 B 报告"
    assert repo.get_latest().summary == "计划 B 报告"


def test_postgres_material_repository_saves_and_updates_metadata(postgres_repositories):
    repo = postgres_repositories["material"]
    material_id = repo.save(valid_material(status="processing", chunk_count=0))

    repo.update_status(material_id, status="ready", chunk_count=12)
    restored = repo.get_by_id(material_id)

    assert restored.filename == "python-basics.pdf"
    assert restored.uploaded_at == NOW
    assert restored.status == "ready"
    assert restored.chunk_count == 12
    assert [material.id for material in repo.list_all()] == [material_id]


def test_postgres_export_record_repository_saves_optional_export_record(postgres_repositories):
    repo = postgres_repositories["export"]
    record = ExportRecord(
        plan_id="plan-1",
        format="html",
        filename="Python-2026-06-04.html",
        exported_at=NOW,
    )

    record_id = repo.save(record)

    assert repo.get_by_id(record_id) == record


def test_postgres_storage_service_integrates_all_repositories(postgres_repositories):
    service = StorageService(
        goal_repository=postgres_repositories["goal"],
        plan_repository=postgres_repositories["plan"],
        task_progress_repository=postgres_repositories["progress"],
        review_report_repository=postgres_repositories["review"],
        material_repository=postgres_repositories["material"],
        export_record_repository=postgres_repositories["export"],
    )
    goal = valid_goal()
    plan = valid_plan(goal=goal)

    goal_id, plan_id = service.save_goal_and_plan(goal, plan)
    service.update_task(plan_id, "task-1", status="done", notes="数据库保存")
    service.save_review_report(valid_review_report(summary="PostgreSQL 复盘报告"), plan_id=plan_id)

    restored = service.get_latest_study_plan()

    assert goal_id
    assert restored.goal == goal
    assert all_tasks(restored)[0].status == "done"
    assert service.get_latest_review_report(plan_id=plan_id).summary == "PostgreSQL 复盘报告"


def test_postgres_storage_service_transaction_rolls_back_goal_when_plan_save_fails(postgres_repositories):
    service = StorageService(
        goal_repository=postgres_repositories["goal"],
        plan_repository=postgres_repositories["plan"],
        task_progress_repository=postgres_repositories["progress"],
        review_report_repository=postgres_repositories["review"],
        material_repository=postgres_repositories["material"],
        export_record_repository=postgres_repositories["export"],
    )
    invalid_plan = valid_plan(tasks=[make_task("late", date=date(2026, 7, 1))])

    with pytest.raises(StorageError):
        service.save_goal_and_plan(valid_goal(), invalid_plan)

    assert service.get_latest_study_goal() is None
    assert service.get_latest_study_plan() is None


def test_postgres_errors_do_not_leak_credentials():
    repo_cls = _postgres_class("PostgresStudyPlanRepository")
    repo = repo_cls(database_url="postgresql://user:secret-password@127.0.0.1:1/missing")

    with pytest.raises(StorageError) as exc_info:
        repo.get_latest()

    message = str(exc_info.value).lower()
    assert "secret-password" not in message
    assert "postgresql://" not in message
