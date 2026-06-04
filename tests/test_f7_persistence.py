from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from study_planner.application.persistence import (
    ExportRecord,
    InvalidTaskUpdateError,
    StorageError,
    StorageService,
    build_persistent_app_state,
)
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
from study_planner.infrastructure.db.repositories import (
    DatabaseInitializer,
    InMemoryExportRecordRepository,
    InMemoryMaterialRepository,
    InMemoryReviewReportRepository,
    InMemoryStudyGoalRepository,
    InMemoryStudyPlanRepository,
    InMemoryTaskProgressRepository,
    JsonPayloadCodec,
    PostgresStudyPlanRepository,
)


CURRENT_DATE = date(2026, 6, 4)
NOW = datetime(2026, 6, 4, 9, 30)


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


def valid_plan(tasks=None, goal=None, phases=None, **overrides):
    goal = goal or valid_goal()
    tasks = tasks if tasks is not None else [
        make_task("task-1", title="学习变量与数据类型", status="todo"),
        make_task("task-2", title="完成基础语法复习", duration_minutes=30, task_type="review", status="done"),
        make_task("task-3", title="函数练习", date=CURRENT_DATE + timedelta(days=1), task_type="practice", status="doing"),
    ]
    if phases is None:
        phases = [
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
        ]
    data = {
        "goal": goal,
        "overall_route": "先学基础语法，再完成练习，最后做小项目",
        "phases": phases,
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


def make_storage_service(**overrides):
    defaults = {
        "goal_repository": InMemoryStudyGoalRepository(clock=lambda: NOW),
        "plan_repository": InMemoryStudyPlanRepository(clock=lambda: NOW),
        "task_progress_repository": InMemoryTaskProgressRepository(clock=lambda: NOW),
        "review_report_repository": InMemoryReviewReportRepository(clock=lambda: NOW),
        "material_repository": InMemoryMaterialRepository(clock=lambda: NOW),
        "export_record_repository": InMemoryExportRecordRepository(clock=lambda: NOW),
    }
    defaults.update(overrides)
    return StorageService(**defaults)


class FailingRepository:
    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise RuntimeError("database unavailable")

        return _fail


class FakeSessionState(dict):
    pass


class TestF7Stage1RepositoryContracts:
    def test_f7_001_business_layer_depends_on_repository_abstractions(self):
        """原因：业务代码只应依赖 repository 接口，不直接依赖 PostgreSQL。"""
        service = make_storage_service()

        goal_id = service.save_study_goal(valid_goal())

        assert goal_id
        assert service.get_latest_study_goal() == valid_goal()

    def test_f7_002_postgres_implementation_lives_under_infrastructure_db(self):
        """原因：PostgreSQL 实现应放在 infrastructure/db，避免页面和应用层耦合数据库。"""
        module_name = PostgresStudyPlanRepository.__module__

        assert "infrastructure.db" in module_name

    def test_f7_003_repository_can_be_replaced_by_fake_repository(self):
        """原因：自动化测试和离线开发需要可替换依赖。"""
        fake_plan_repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        service = make_storage_service(plan_repository=fake_plan_repo)

        plan_id = service.save_study_plan(valid_plan())

        assert plan_id
        assert service.get_latest_study_plan().goal.subject == "Python 编程"

    def test_f7_004_repository_errors_are_converted_to_storage_error(self):
        """原因：数据库异常不能直接泄露给页面。"""
        service = make_storage_service(plan_repository=FailingRepository())

        with pytest.raises(StorageError, match="数据库|storage|unavailable"):
            service.save_study_plan(valid_plan())


class TestF7Stage2StudyGoalPersistence:
    def test_f7_005_saves_study_goal(self):
        """原因：F1 输入的学习目标是后续计划生成和恢复的基础。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)

        goal_id = repo.save(valid_goal())

        assert goal_id
        assert repo.get_by_id(goal_id) == valid_goal()
        assert repo.metadata(goal_id)["created_at"] == NOW

    def test_f7_006_reads_latest_study_goal(self):
        """原因：页面刷新或重启后需要恢复最近配置。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)
        repo.save(valid_goal(subject="旧目标"))
        repo.save(valid_goal(subject="最新目标"))

        latest = repo.get_latest()

        assert latest.subject == "最新目标"

    def test_f7_007_reads_study_goal_by_id(self):
        """原因：学习计划需要关联原始目标。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)
        first_id = repo.save(valid_goal(subject="目标 A"))
        second_id = repo.save(valid_goal(subject="目标 B"))

        assert repo.get_by_id(first_id).subject == "目标 A"
        assert repo.get_by_id(second_id).subject == "目标 B"

    def test_f7_008_preserves_chinese_study_goal(self):
        """原因：产品面向中文学习场景，持久化必须使用正确编码。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)
        goal = valid_goal(subject="机器学习", target="理解监督学习并完成分类项目", weak_points=["数学基础"])

        goal_id = repo.save(goal)
        restored = repo.get_by_id(goal_id)

        assert restored.subject == "机器学习"
        assert restored.target == "理解监督学习并完成分类项目"
        assert restored.weak_points == ["数学基础"]

    def test_f7_009_saves_goal_with_empty_optional_fields(self):
        """原因：F1 允许部分输入为空，F7 不能阻断。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)
        goal = valid_goal(preferred_methods=[], weak_points=[], extra_requirements="")

        goal_id = repo.save(goal)
        restored = repo.get_by_id(goal_id)

        assert restored.preferred_methods == []
        assert restored.weak_points == []
        assert restored.extra_requirements == ""


class TestF7Stage3StudyPlanPersistence:
    def test_f7_010_saves_complete_study_plan(self):
        """原因：F2 生成的完整计划必须可保存。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)

        plan_id = repo.save(valid_plan())

        assert plan_id
        assert repo.get_by_id(plan_id).phases[0].weekly_plans[0].tasks

    def test_f7_011_reads_latest_study_plan(self):
        """原因：刷新后需要恢复最近学习计划。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        repo.save(valid_plan(goal=valid_goal(subject="旧计划")))
        repo.save(valid_plan(goal=valid_goal(subject="最新计划")))

        latest = repo.get_latest()

        assert latest.goal.subject == "最新计划"

    def test_f7_012_reads_study_plan_by_id(self):
        """原因：历史计划和复盘关联需要稳定 ID。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        first_id = repo.save(valid_plan(goal=valid_goal(subject="计划 A")))
        second_id = repo.save(valid_plan(goal=valid_goal(subject="计划 B")))

        assert repo.get_by_id(first_id).goal.subject == "计划 A"
        assert repo.get_by_id(second_id).goal.subject == "计划 B"

    def test_f7_013_plan_keeps_original_goal_reference(self):
        """原因：计划必须追溯到用户原始目标。"""
        service = make_storage_service()
        goal = valid_goal(subject="原始目标")
        goal_id = service.save_study_goal(goal)
        plan_id = service.save_study_plan(valid_plan(goal=goal), goal_id=goal_id)

        restored = service.get_study_plan(plan_id)

        assert restored.goal == goal
        assert service.get_plan_metadata(plan_id)["goal_id"] == goal_id

    def test_f7_014_jsonb_payload_round_trips_nested_plan(self):
        """原因：MVP 可以先使用 JSONB 保存复杂计划。"""
        codec = JsonPayloadCodec()
        plan = valid_plan()

        payload = codec.to_jsonable(plan)
        restored = codec.study_plan_from_jsonable(payload)

        assert restored == plan
        assert payload["phases"][0]["weekly_plans"][0]["tasks"][0]["id"] == "task-1"

    def test_f7_015_preserves_task_ids(self):
        """原因：F3、F5、F6 都依赖稳定任务 ID。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)

        plan_id = repo.save(valid_plan())

        assert all_tasks(repo.get_by_id(plan_id))[0].id == "task-1"

    def test_f7_016_preserves_task_notes(self):
        """原因：F3 支持任务备注编辑，必须持久化。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        plan = valid_plan(tasks=[make_task("task-1", notes="复习时重点看类型转换")])

        plan_id = repo.save(plan)

        assert all_tasks(repo.get_by_id(plan_id))[0].notes == "复习时重点看类型转换"

    def test_f7_017_preserves_review_schedule(self):
        """原因：复习安排是 F2/F6 的关键内容。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)

        plan_id = repo.save(valid_plan())
        schedule = repo.get_by_id(plan_id).review_schedule

        assert schedule.daily_review_minutes == 15
        assert schedule.weekly_review_day == "周日"

    def test_f7_018_preserves_time_budget(self):
        """原因：时间预算用于看板展示和导出。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)

        plan_id = repo.save(valid_plan())
        budget = repo.get_by_id(plan_id).time_budget

        assert budget.total_days == 27
        assert budget.total_available_minutes == 2400


class TestF7Stage4TaskProgressPersistence:
    def test_f7_019_updates_task_status_to_done(self):
        """原因：完成定义要求任务完成状态能持久保存。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", status="done")

        assert all_tasks(service.get_study_plan(plan_id))[0].status == "done"

    def test_f7_020_updates_task_status_to_doing(self):
        """原因：任务状态至少包含 doing。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", status="doing")

        assert all_tasks(service.get_study_plan(plan_id))[0].status == "doing"

    def test_f7_021_updates_task_status_to_skipped(self):
        """原因：skipped 代表未完成风险，必须正确持久化。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", status="skipped")

        assert all_tasks(service.get_study_plan(plan_id))[0].status == "skipped"

    def test_f7_022_updates_task_date(self):
        """原因：F3 支持编辑任务日期。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", new_date=date(2026, 6, 6))

        assert all_tasks(service.get_study_plan(plan_id))[0].date == date(2026, 6, 6)

    def test_f7_023_updates_task_duration(self):
        """原因：F3 支持编辑任务时长。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", duration_minutes=45)

        assert all_tasks(service.get_study_plan(plan_id))[0].duration_minutes == 45

    def test_f7_024_updates_task_notes(self):
        """原因：备注是用户执行计划的重要补充信息。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", notes="复习时重点看类型转换")

        assert all_tasks(service.get_study_plan(plan_id))[0].notes == "复习时重点看类型转换"

    def test_f7_025_updating_unknown_task_returns_clear_error(self):
        """原因：防止错误 task_id 污染计划数据。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        with pytest.raises(InvalidTaskUpdateError, match="不存在|not found"):
            service.update_task(plan_id, "task-not-exists", status="done")

    def test_f7_026_invalid_task_status_cannot_be_saved(self):
        """原因：F3/F5 对状态枚举有约束。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        with pytest.raises(InvalidTaskUpdateError, match="status|状态"):
            service.update_task(plan_id, "task-1", status="unknown")


class TestF7Stage5ReviewReportPersistence:
    def test_f7_027_saves_review_report(self):
        """原因：F5 生成的复盘报告需要保存。"""
        repo = InMemoryReviewReportRepository(clock=lambda: NOW)

        report_id = repo.save(valid_review_report(), plan_id="plan-1")

        assert report_id
        assert repo.get_by_id(report_id).summary

    def test_f7_028_reads_latest_review_report(self):
        """原因：F6 导出需要读取最近复盘报告。"""
        repo = InMemoryReviewReportRepository(clock=lambda: NOW)
        repo.save(valid_review_report(summary="旧报告"), plan_id="plan-1")
        repo.save(valid_review_report(summary="最新报告"), plan_id="plan-1")

        assert repo.get_latest(plan_id="plan-1").summary == "最新报告"

    def test_f7_029_review_report_is_bound_to_plan(self):
        """原因：多计划场景下复盘报告不能串读。"""
        repo = InMemoryReviewReportRepository(clock=lambda: NOW)
        repo.save(valid_review_report(summary="计划 A 报告"), plan_id="plan-a")
        repo.save(valid_review_report(summary="计划 B 报告"), plan_id="plan-b")

        assert repo.get_latest(plan_id="plan-a").summary == "计划 A 报告"
        assert repo.get_latest(plan_id="plan-b").summary == "计划 B 报告"

    def test_f7_030_preserves_chinese_review_report(self):
        """原因：F5 复盘内容面向中文用户。"""
        repo = InMemoryReviewReportRepository(clock=lambda: NOW)
        report = valid_review_report(summary="递归理解不稳，需要专项练习", weak_points=["递归"])

        report_id = repo.save(report, plan_id="plan-1")

        assert repo.get_by_id(report_id).summary == "递归理解不稳，需要专项练习"
        assert repo.get_by_id(report_id).weak_points == ["递归"]

    def test_f7_031_saves_review_report_with_empty_lists(self):
        """原因：完成率较好时可能没有延期任务或薄弱点。"""
        repo = InMemoryReviewReportRepository(clock=lambda: NOW)
        report = valid_review_report(overdue_tasks=[], weak_points=[], suggestions=[])

        report_id = repo.save(report, plan_id="plan-1")
        restored = repo.get_by_id(report_id)

        assert restored.overdue_tasks == []
        assert restored.weak_points == []
        assert restored.suggestions == []


class TestF7Stage6MaterialMetadataPersistence:
    def test_f7_032_saves_material_metadata(self):
        """原因：F4 资料上传需要保存资料状态和索引信息。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)

        material_id = repo.save(valid_material())

        assert material_id == "material-1"
        assert repo.get_by_id(material_id).filename == "python-basics.pdf"

    def test_f7_033_reads_material_metadata_by_id(self):
        """原因：资料问答需要定位资料来源。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)
        repo.save(valid_material(id="material-1", filename="a.pdf"))
        repo.save(valid_material(id="material-2", filename="b.md"))

        assert repo.get_by_id("material-2").filename == "b.md"

    def test_f7_034_lists_all_material_metadata(self):
        """原因：F4 页面需要展示资料列表。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)
        repo.save(valid_material(id="material-1", filename="a.pdf"))
        repo.save(valid_material(id="material-2", filename="b.md"))

        materials = repo.list_all()

        assert [material.id for material in materials] == ["material-1", "material-2"]

    def test_f7_035_updates_material_processing_status(self):
        """原因：资料解析是异步或多步骤过程，状态必须保存。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)
        repo.save(valid_material(status="processing", chunk_count=0))

        repo.update_status("material-1", status="ready", chunk_count=12)

        restored = repo.get_by_id("material-1")
        assert restored.status == "ready"
        assert restored.chunk_count == 12

    def test_f7_036_saves_material_error_message(self):
        """原因：F4 要处理上传或解析失败场景。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)
        repo.save(valid_material(status="processing"))

        repo.update_status("material-1", status="failed", error_message="PDF parse failed")

        restored = repo.get_by_id("material-1")
        assert restored.status == "failed"
        assert restored.error_message == "PDF parse failed"


class TestF7Stage7OptionalExportRecordPersistence:
    def test_f7_037_saves_export_record(self):
        """原因：features.md 将导出记录列为可选数据范围。"""
        repo = InMemoryExportRecordRepository(clock=lambda: NOW)
        record = ExportRecord(plan_id="plan-1", format="html", filename="Python-2026-06-04.html", exported_at=NOW)

        record_id = repo.save(record)

        assert record_id
        assert repo.get_by_id(record_id).filename == "Python-2026-06-04.html"

    def test_f7_038_missing_export_record_repository_does_not_block_export(self):
        """原因：导出记录是可选能力，不应影响 F6 主流程。"""
        service = make_storage_service(export_record_repository=None)
        plan_id = service.save_study_plan(valid_plan())

        result = service.record_export_if_available(plan_id, format="html", filename="plan.html", exported_at=NOW)

        assert result is None


class TestF7Stage8StreamlitRefreshRecovery:
    def test_f7_039_refresh_recovers_latest_study_plan(self):
        """原因：刷新后应恢复最近学习计划。"""
        service = make_storage_service()
        service.save_study_plan(valid_plan())
        state = FakeSessionState()

        app_state = build_persistent_app_state(state, service)

        assert app_state.study_plan.goal.subject == "Python 编程"
        assert state["study_plan"].goal.subject == "Python 编程"

    def test_f7_040_refresh_recovers_task_done_status(self):
        """原因：任务完成状态需要持久保存。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())
        service.update_task(plan_id, "task-1", status="done")
        state = FakeSessionState()

        app_state = build_persistent_app_state(state, service)

        assert all_tasks(app_state.study_plan)[0].status == "done"

    def test_f7_041_refresh_recovers_latest_review_report(self):
        """原因：F5/F6 需要共享复盘状态。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())
        service.save_review_report(valid_review_report(summary="刷新后恢复报告"), plan_id=plan_id)
        state = FakeSessionState()

        app_state = build_persistent_app_state(state, service)

        assert app_state.review_report.summary == "刷新后恢复报告"

    def test_f7_042_empty_database_shows_empty_state(self):
        """原因：新用户或清空数据库后必须有友好空状态。"""
        service = make_storage_service()
        state = FakeSessionState()

        app_state = build_persistent_app_state(state, service)

        assert app_state.study_plan is None
        assert app_state.empty_message


class TestF7Stage9F3Integration:
    def test_f7_043_f3_reads_persisted_plan_on_open(self):
        """原因：F3 是计划执行主页面，必须接入持久化。"""
        service = make_storage_service()
        service.save_study_plan(valid_plan(goal=valid_goal(subject="持久化计划")))

        state = build_persistent_app_state(FakeSessionState(), service)

        assert state.study_plan.goal.subject == "持久化计划"

    def test_f7_044_f3_task_edit_is_saved_to_database(self):
        """原因：用户在 F3 的编辑不能只存在于内存。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", status="done", new_date=date(2026, 6, 6), duration_minutes=45, notes="已复习")
        restored = service.get_study_plan(plan_id)

        task = all_tasks(restored)[0]
        assert task.status == "done"
        assert task.date == date(2026, 6, 6)
        assert task.duration_minutes == 45
        assert task.notes == "已复习"

    def test_f7_045_f3_save_failure_shows_error(self):
        """原因：保存失败时页面需要明确反馈。"""
        service = make_storage_service(plan_repository=FailingRepository())

        with pytest.raises(StorageError, match="保存失败|storage|unavailable"):
            service.update_task("plan-1", "task-1", status="done")


class TestF7Stage10F5Integration:
    def test_f7_046_f5_reads_persisted_plan_for_review(self):
        """原因：F5 依赖 F3 更新后的进度。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())
        service.update_task(plan_id, "task-1", status="done")

        plan = service.get_latest_study_plan()

        assert all_tasks(plan)[0].status == "done"

    def test_f7_047_f5_saves_review_report_to_database(self):
        """原因：复盘报告是 F7 数据范围。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        report_id = service.save_review_report(valid_review_report(), plan_id=plan_id)

        assert report_id
        assert service.get_latest_review_report(plan_id=plan_id).summary

    def test_f7_048_f5_saves_adjusted_plan_to_database(self):
        """原因：F5 调整结果需要回流到看板和持久化层。"""
        service = make_storage_service()
        service.save_study_plan(valid_plan(tasks=[make_task("task-1", title="旧任务")]))
        adjusted = valid_plan(tasks=[make_task("task-1", title="调整后任务")])

        new_plan_id = service.save_adjusted_plan(adjusted, review_report=valid_review_report())

        assert service.get_study_plan(new_plan_id).phases[0].weekly_plans[0].tasks[0].title == "调整后任务"
        assert service.get_latest_study_plan().phases[0].weekly_plans[0].tasks[0].title == "调整后任务"

    def test_f7_049_f5_adjusted_plan_save_failure_rolls_back(self):
        """原因：调整计划不能在失败时造成计划丢失。"""
        plan_repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        service = make_storage_service(plan_repository=plan_repo)
        original_id = service.save_study_plan(valid_plan(tasks=[make_task("task-1", title="原计划")]))
        service.plan_repository.fail_next_save = True

        with pytest.raises(StorageError):
            service.save_adjusted_plan(valid_plan(tasks=[make_task("task-1", title="调整计划")]), review_report=valid_review_report())

        assert service.get_study_plan(original_id).phases[0].weekly_plans[0].tasks[0].title == "原计划"


class TestF7Stage11F6Integration:
    def test_f7_050_f6_exports_from_persisted_plan(self):
        """原因：F7 完成定义要求 F6 可以读取持久化数据。"""
        service = make_storage_service()
        service.save_study_plan(valid_plan(tasks=[make_task("task-1", title="持久化导出任务")]))

        result = service.export_latest_plan(format="markdown", exported_at=NOW)

        assert "持久化导出任务" in result.content

    def test_f7_051_f6_exports_persisted_task_status(self):
        """原因：导出必须反映当前持久化状态。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())
        service.update_task(plan_id, "task-1", status="done")

        result = service.export_latest_plan(format="markdown", exported_at=NOW)

        assert "done" in result.content or "已完成" in result.content

    def test_f7_052_f6_exports_persisted_review_report(self):
        """原因：F6 导出学习计划和复盘报告。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())
        service.save_review_report(valid_review_report(summary="持久化复盘报告"), plan_id=plan_id)

        result = service.export_latest_plan(format="html", exported_at=NOW)

        assert "持久化复盘报告" in result.content


class TestF7Stage12DatabaseUnavailableAndErrors:
    def test_f7_053_app_start_survives_database_unavailable(self):
        """原因：读取失败时不应影响应用启动。"""
        service = make_storage_service(plan_repository=FailingRepository())

        app_state = build_persistent_app_state(FakeSessionState(), service)

        assert app_state.storage_available is False
        assert app_state.startup_error

    def test_f7_054_plan_read_failure_has_clear_error(self):
        """原因：数据库不可用时错误必须清晰。"""
        service = make_storage_service(plan_repository=FailingRepository())

        with pytest.raises(StorageError, match="读取失败|storage|unavailable"):
            service.get_latest_study_plan()

    def test_f7_055_plan_save_failure_has_clear_error(self):
        """原因：保存失败时页面需要明确反馈。"""
        service = make_storage_service(plan_repository=FailingRepository())

        with pytest.raises(StorageError, match="保存失败|storage|unavailable"):
            service.save_study_plan(valid_plan())

    def test_f7_056_task_progress_save_failure_has_clear_error(self):
        """原因：避免用户误以为进度已保存。"""
        service = make_storage_service(task_progress_repository=FailingRepository())

        with pytest.raises(StorageError, match="进度|progress|unavailable"):
            service.save_task_progress(TaskProgress(task_id="task-1", status="done", planned_date=CURRENT_DATE))

    def test_f7_057_review_report_save_failure_has_clear_error(self):
        """原因：F5 输出不能因保存失败无提示丢失。"""
        service = make_storage_service(review_report_repository=FailingRepository())

        with pytest.raises(StorageError, match="复盘|review|unavailable"):
            service.save_review_report(valid_review_report(), plan_id="plan-1")


class TestF7Stage13TransactionsAndConsistency:
    def test_f7_058_goal_and_plan_save_uses_consistent_transaction(self):
        """原因：目标和计划是强关联数据。"""
        service = make_storage_service()
        service.plan_repository.fail_next_save = True

        with pytest.raises(StorageError):
            service.save_goal_and_plan(valid_goal(), valid_plan())

        assert service.get_latest_study_goal() is None
        assert service.get_latest_study_plan() is None

    def test_f7_059_adjusted_plan_and_review_report_save_are_consistent(self):
        """原因：F5 保存涉及多实体一致性。"""
        service = make_storage_service()
        service.save_study_plan(valid_plan(tasks=[make_task("task-1", title="原计划")]))
        service.plan_repository.fail_next_save = True

        with pytest.raises(StorageError):
            service.save_adjusted_plan(valid_plan(tasks=[make_task("task-1", title="调整计划")]), valid_review_report())

        assert service.get_latest_review_report() is None
        assert "原计划" in all_tasks(service.get_latest_study_plan())[0].title

    def test_f7_060_task_status_update_does_not_touch_other_tasks(self):
        """原因：局部更新必须避免误改其他任务。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", status="done")
        tasks = {task.id: task for task in all_tasks(service.get_study_plan(plan_id))}

        assert tasks["task-1"].status == "done"
        assert tasks["task-2"].status == "done"
        assert tasks["task-3"].status == "doing"

    def test_f7_061_concurrent_saves_use_defined_strategy(self):
        """原因：多窗口或刷新可能导致并发写入。"""
        service = make_storage_service()
        plan_id = service.save_study_plan(valid_plan())

        service.update_task(plan_id, "task-1", notes="窗口 A")
        service.update_task(plan_id, "task-1", status="done")
        task = all_tasks(service.get_study_plan(plan_id))[0]

        assert task.notes == "窗口 A"
        assert task.status == "done"


class TestF7Stage14ValidationAndSecurity:
    def test_f7_062_validates_task_status_before_save(self):
        """原因：避免非法状态污染 F3/F5/F6。"""
        service = make_storage_service()

        with pytest.raises(StorageError, match="status|状态"):
            service.save_study_plan(valid_plan(tasks=[make_task("bad", status="unknown")]))

    def test_f7_063_validates_task_date_before_deadline(self):
        """原因：不应持久化不可执行计划。"""
        service = make_storage_service()
        goal = valid_goal(deadline=date(2026, 6, 10))

        with pytest.raises(StorageError, match="deadline|截止"):
            service.save_study_plan(valid_plan(goal=goal, tasks=[make_task("late", date=date(2026, 6, 11))]))

    def test_f7_064_validates_daily_minutes_before_save(self):
        """原因：防止持久化绕过业务约束。"""
        service = make_storage_service()
        tasks = [make_task("a", duration_minutes=90), make_task("b", duration_minutes=90)]

        with pytest.raises(StorageError, match="时长|minutes|过载"):
            service.save_study_plan(valid_plan(tasks=tasks))

    def test_f7_065_sql_injection_string_is_saved_as_plain_text(self):
        """原因：用户输入必须通过参数化查询或 JSON 序列化安全保存。"""
        repo = InMemoryStudyGoalRepository(clock=lambda: NOW)
        goal = valid_goal(subject="'); DROP TABLE study_plans; --")

        goal_id = repo.save(goal)

        assert repo.get_by_id(goal_id).subject == "'); DROP TABLE study_plans; --"
        assert repo.table_exists("study_goals") is True

    def test_f7_066_errors_do_not_leak_database_credentials(self):
        """原因：配置和凭据不能暴露给用户。"""
        service = make_storage_service(plan_repository=FailingRepository())

        with pytest.raises(StorageError) as exc_info:
            service.save_study_plan(valid_plan())

        message = str(exc_info.value)
        assert "password" not in message.lower()
        assert "postgres://" not in message.lower()


class TestF7Stage15TimeAndOrdering:
    def test_f7_067_created_at_and_updated_at_are_maintained(self):
        """原因：最近计划和历史记录依赖时间字段。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        plan_id = repo.save(valid_plan())
        later = NOW + timedelta(minutes=5)
        repo.clock = lambda: later

        repo.update_task(plan_id, "task-1", status="done")
        metadata = repo.metadata(plan_id)

        assert metadata["created_at"] == NOW
        assert metadata["updated_at"] == later

    def test_f7_068_get_latest_uses_updated_at_ordering(self):
        """原因：“最近计划”必须定义清楚。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)
        first_id = repo.save(valid_plan(goal=valid_goal(subject="first")))
        repo.clock = lambda: NOW + timedelta(minutes=1)
        repo.save(valid_plan(goal=valid_goal(subject="second")))
        repo.clock = lambda: NOW + timedelta(minutes=2)
        repo.update_task(first_id, "task-1", status="done")

        assert repo.get_latest().goal.subject == "first"

    def test_f7_069_date_fields_round_trip_as_date(self):
        """原因：F3/F5 依赖日期比较。"""
        repo = InMemoryStudyPlanRepository(clock=lambda: NOW)

        plan_id = repo.save(valid_plan())
        restored = repo.get_by_id(plan_id)

        assert isinstance(restored.goal.deadline, date)
        assert isinstance(all_tasks(restored)[0].date, date)

    def test_f7_070_datetime_fields_round_trip_stably(self):
        """原因：上传记录和复盘记录需要稳定排序。"""
        repo = InMemoryMaterialRepository(clock=lambda: NOW)

        material_id = repo.save(valid_material(uploaded_at=NOW))

        assert repo.get_by_id(material_id).uploaded_at == NOW


class TestF7Stage16MigrationAndInitialization:
    def test_f7_071_first_start_initializes_database_tables(self):
        """原因：MVP 需要可部署、可重复初始化。"""
        initializer = DatabaseInitializer()

        initializer.initialize()
        initializer.initialize()

        assert initializer.has_table("study_goals")
        assert initializer.has_table("study_plans")
        assert initializer.has_table("task_progress")
        assert initializer.has_table("review_reports")
        assert initializer.has_table("materials")

    def test_f7_072_missing_table_returns_clear_error(self):
        """原因：部署阶段常见数据库未初始化。"""
        initializer = DatabaseInitializer()
        repo = PostgresStudyPlanRepository(initializer=initializer)

        with pytest.raises(StorageError, match="初始化|table|study_plans"):
            repo.get_latest()

    def test_f7_073_jsonb_schema_version_is_recognized(self):
        """原因：后续从 JSONB 迁移到规范化表时需要版本信息。"""
        codec = JsonPayloadCodec(schema_version=1)

        payload = codec.to_jsonable(valid_plan())
        restored = codec.study_plan_from_jsonable(payload)

        assert payload["schema_version"] == 1
        assert restored.goal.subject == "Python 编程"
