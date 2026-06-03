from datetime import date, timedelta

import pytest

from study_planner.application.plan_dashboard import (
    DashboardState,
    DashboardValidationError,
    build_dashboard_view,
    calculate_progress,
    get_current_week_tasks,
    get_today_tasks,
    update_task_date,
    update_task_duration,
    update_task_notes,
    update_task_status,
)
from study_planner.domain.models import (
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TimeBudget,
    WeeklyPlan,
)


def valid_goal(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法，并能独立完成一个小型项目",
        "deadline": date.today() + timedelta(days=30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["视频教程", "实践项目"],
        "weak_points": ["缺乏编程经验"],
        "extra_requirements": "希望多安排练习任务",
    }
    data.update(overrides)
    return StudyGoal(**data)


def make_task(task_id="task-1", **overrides):
    data = {
        "id": task_id,
        "title": "学习变量与数据类型",
        "date": date.today(),
        "duration_minutes": 60,
        "task_type": "学习",
        "related_topics": ["变量", "数据类型"],
        "learning_method": "视频教程 + 练习",
        "expected_output": "完成 10 道变量和数据类型练习。",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(**overrides):
    goal = overrides.pop("goal", valid_goal())
    today = date.today()
    tasks = overrides.pop(
        "tasks",
        [
            make_task("task-1", date=today, duration_minutes=60, status="todo"),
            make_task(
                "task-2",
                title="完成基础语法复习",
                date=today,
                duration_minutes=30,
                task_type="复习",
                expected_output="整理 3 条易错点。",
                status="todo",
            ),
        ],
    )
    phase = StudyPhase(
        phase_index=1,
        title="基础入门阶段",
        objective="掌握 Python 基础语法和基本编程思维。",
        start_date=today,
        end_date=today + timedelta(days=13),
        milestone="能够完成变量、条件、循环和函数相关练习。",
        weekly_plans=[
            WeeklyPlan(
                week_index=1,
                start_date=today,
                end_date=today + timedelta(days=6),
                objective="完成 Python 基础语法学习。",
                review_focus="复习变量、条件、循环和函数。",
                tasks=tasks,
            )
        ],
    )
    data = {
        "goal": goal,
        "overall_route": "先学习 Python 基础语法，再完成练习，最后实现一个小型项目。",
        "phases": [phase],
        "methods": ["视频教程", "实践项目", "每日复习"],
        "time_budget": TimeBudget(
            total_days=31,
            total_weeks=5,
            total_available_minutes=3000,
            planned_minutes=sum(task.duration_minutes for task in tasks),
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        "risks": ["零基础学习容易卡在语法细节，需要保持每日练习。"],
        "review_schedule": ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="周日",
            review_strategy="每天复习当天知识点，每周整理一次薄弱点。",
        ),
        "suggestions": "保持小步快跑，每天完成一个可检查的学习产出。",
    }
    data.update(overrides)
    return StudyPlan(**data)


class FakeSessionState(dict):
    pass


def all_tasks(plan):
    return [
        task
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    ]


class TestF3Stage1EmptyStateAndPageBasics:
    def test_f3_1_01_empty_plan_shows_empty_state(self):
        """原因：用户可能直接进入看板页，系统必须优雅处理空状态。"""
        view = build_dashboard_view(study_plan=None)

        assert view.is_empty is True
        assert "学习计划" in view.empty_message

    def test_f3_1_02_empty_plan_hides_edit_controls(self):
        """原因：没有计划时编辑控件没有意义，避免用户误操作。"""
        view = build_dashboard_view(study_plan=None)

        assert view.can_edit is False
        assert view.task_rows == []

    def test_f3_1_03_dashboard_state_can_initialize_without_plan(self):
        """原因：先保证页面基础状态稳定，再测试复杂展示。"""
        state = DashboardState.from_session(FakeSessionState())

        assert state.study_plan is None
        assert state.errors == []


class TestF3Stage2PlanDisplay:
    def test_f3_2_01_displays_goal_summary(self):
        """原因：用户需要确认当前看板对应的是哪个学习目标。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert view.goal_summary["subject"] == "Python 编程"
        assert view.goal_summary["target"] == plan.goal.target
        assert view.goal_summary["deadline"] == plan.goal.deadline
        assert view.goal_summary["current_level"] == "零基础"
        assert view.goal_summary["daily_available_minutes"] == 120
        assert view.goal_summary["weekly_available_days"] == 5

    def test_f3_2_02_displays_overall_route(self):
        """原因：PRD 要求展示总体学习路线。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert view.overall_route == plan.overall_route

    def test_f3_2_03_displays_phase_tabs(self):
        """原因：F2 生成阶段结构，F3 必须能按阶段展示。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert len(view.phase_tabs) == 1
        assert view.phase_tabs[0].title == "基础入门阶段"
        assert view.phase_tabs[0].objective == "掌握 Python 基础语法和基本编程思维。"
        assert view.phase_tabs[0].start_date == date.today()
        assert view.phase_tabs[0].milestone

    def test_f3_2_04_displays_weekly_plans(self):
        """原因：周计划是阶段和每日任务之间的中间层。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)
        weekly_plan = view.phase_tabs[0].weekly_plans[0]

        assert weekly_plan.week_index == 1
        assert weekly_plan.objective == "完成 Python 基础语法学习。"
        assert weekly_plan.review_focus == "复习变量、条件、循环和函数。"

    def test_f3_2_05_displays_daily_tasks(self):
        """原因：每日任务是用户实际执行计划的最小单位。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)
        task_row = view.task_rows[0]

        assert task_row.title == "学习变量与数据类型"
        assert task_row.date == date.today()
        assert task_row.duration_minutes == 60
        assert task_row.task_type == "学习"
        assert task_row.related_topics == ["变量", "数据类型"]
        assert task_row.learning_method == "视频教程 + 练习"
        assert task_row.expected_output
        assert task_row.status == "todo"

    def test_f3_2_06_displays_today_tasks(self):
        """原因：今日任务是用户进入看板后最重要的信息。"""
        plan = valid_plan()

        today_tasks = get_today_tasks(plan, today=date.today())

        assert len(today_tasks) == 2
        assert all(task.date == date.today() for task in today_tasks)

    def test_f3_2_07_today_without_tasks_shows_hint(self):
        """原因：不是每天都有任务，今日空状态需要正常处理。"""
        plan = valid_plan(tasks=[make_task("task-1", date=date.today() + timedelta(days=1))])

        view = build_dashboard_view(plan, today=date.today())

        assert view.today_tasks == []
        assert view.today_empty_message

    def test_f3_2_08_displays_current_week_tasks(self):
        """原因：PRD 明确要求展示本周任务表格。"""
        plan = valid_plan()

        week_tasks = get_current_week_tasks(plan, today=date.today())

        assert len(week_tasks) == 2
        assert all(task.title for task in week_tasks)

    def test_f3_2_09_displays_risks(self):
        """原因：用户需要看到计划执行风险。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert view.risks == plan.risks

    def test_f3_2_10_displays_review_schedule(self):
        """原因：PRD 要求展示复习安排。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert view.review_schedule.daily_review_minutes == 15
        assert view.review_schedule.weekly_review_day == "周日"
        assert view.review_schedule.review_strategy

    def test_f3_2_11_displays_learning_methods(self):
        """原因：用户需要知道用什么方式执行计划。"""
        plan = valid_plan()

        view = build_dashboard_view(plan)

        assert view.methods == ["视频教程", "实践项目", "每日复习"]


class TestF3Stage3TaskEditing:
    def test_f3_3_01_marks_task_done(self):
        """原因：标记完成是 F3 的核心编辑能力。"""
        plan = valid_plan()

        updated = update_task_status(plan, "task-1", "done")

        assert all_tasks(updated)[0].status == "done"

    def test_f3_3_02_marks_task_doing(self):
        """原因：用户可能需要标记当前正在学习的任务。"""
        plan = valid_plan()

        updated = update_task_status(plan, "task-1", "doing")

        assert all_tasks(updated)[0].status == "doing"

    def test_f3_3_03_marks_task_skipped(self):
        """原因：跳过任务会影响 F5 复盘，需要被记录。"""
        plan = valid_plan()

        updated = update_task_status(plan, "task-1", "skipped")

        assert all_tasks(updated)[0].status == "skipped"

    def test_f3_3_04_updates_task_date(self):
        """原因：用户需要调整学习安排。"""
        plan = valid_plan()
        new_date = date.today() + timedelta(days=2)

        updated = update_task_date(plan, "task-1", new_date, today=date.today())

        assert all_tasks(updated)[0].date == new_date

    def test_f3_3_05_updates_task_duration(self):
        """原因：用户需要根据实际情况调整任务负载。"""
        plan = valid_plan()

        updated = update_task_duration(plan, "task-1", 45)

        assert all_tasks(updated)[0].duration_minutes == 45

    def test_f3_3_06_updates_task_notes(self):
        """原因：备注可以帮助用户记录执行细节。"""
        plan = valid_plan()

        updated = update_task_notes(plan, "task-1", "今天先看前两节")

        assert all_tasks(updated)[0].notes == "今天先看前两节"

    def test_f3_3_07_updates_multiple_task_statuses(self):
        """原因：用户可能一次性更新一天或一周的完成情况。"""
        plan = valid_plan()

        updated = update_task_status(plan, "task-1", "done")
        updated = update_task_status(updated, "task-2", "done")

        statuses = [task.status for task in all_tasks(updated)]
        assert statuses == ["done", "done"]


class TestF3Stage4EditValidation:
    def test_f3_4_01_rejects_invalid_task_status(self):
        """原因：F5 依赖任务状态枚举，不能出现未知状态。"""
        with pytest.raises(DashboardValidationError, match="状态"):
            update_task_status(valid_plan(), "task-1", "invalid_status")

    def test_f3_4_02_rejects_task_date_after_deadline(self):
        """原因：计划必须在用户截止日期内完成。"""
        plan = valid_plan()

        with pytest.raises(DashboardValidationError, match="截止日期"):
            update_task_date(plan, "task-1", plan.goal.deadline + timedelta(days=1), today=date.today())

    def test_f3_4_03_rejects_task_date_before_today(self):
        """原因：不应把未来计划编辑成过去任务。"""
        with pytest.raises(DashboardValidationError, match="今天"):
            update_task_date(valid_plan(), "task-1", date.today() - timedelta(days=1), today=date.today())

    def test_f3_4_04_rejects_non_positive_duration(self):
        """原因：任务必须有实际学习时间。"""
        with pytest.raises(DashboardValidationError, match="时长"):
            update_task_duration(valid_plan(), "task-1", 0)

    def test_f3_4_05_rejects_daily_minutes_over_goal_limit(self):
        """原因：防止用户编辑后破坏计划可执行性。"""
        plan = valid_plan()

        with pytest.raises(DashboardValidationError, match="每日可学习时间"):
            update_task_duration(plan, "task-1", 100)

    def test_f3_4_06_rejects_missing_task_id(self):
        """原因：更新不存在的任务应给出明确错误，而不是静默失败。"""
        with pytest.raises(DashboardValidationError, match="任务"):
            update_task_status(valid_plan(), "missing-task", "done")

    def test_f3_4_07_long_notes_are_saved_without_truncation(self):
        """原因：用户可能记录较详细的学习情况。"""
        long_notes = "今天学习时遇到的问题：" + "递归理解不够。" * 80

        updated = update_task_notes(valid_plan(), "task-1", long_notes)

        assert all_tasks(updated)[0].notes == long_notes


class TestF3Stage5ProgressAndCharts:
    def test_f3_5_01_counts_total_tasks(self):
        """原因：总任务数是完成率计算基础。"""
        progress = calculate_progress(valid_plan())

        assert progress.total_tasks == 2

    def test_f3_5_02_counts_done_tasks(self):
        """原因：用户需要看到完成进度。"""
        plan = valid_plan(tasks=[make_task("task-1", status="done"), make_task("task-2", status="todo")])

        progress = calculate_progress(plan)

        assert progress.done_tasks == 1

    def test_f3_5_03_calculates_completion_rate(self):
        """原因：完成率是学习进度最重要指标之一。"""
        plan = valid_plan(
            tasks=[
                make_task("task-1", status="done"),
                make_task("task-2", status="todo"),
                make_task("task-3", status="todo"),
                make_task("task-4", status="todo"),
            ]
        )

        progress = calculate_progress(plan)

        assert progress.completion_rate == 25

    def test_f3_5_04_empty_tasks_completion_rate_is_zero(self):
        """原因：防止边界情况导致除零错误。"""
        plan = valid_plan(tasks=[])

        progress = calculate_progress(plan)

        assert progress.total_tasks == 0
        assert progress.completion_rate == 0

    def test_f3_5_05_calculates_daily_minutes(self):
        """原因：图表需要展示每日学习负载。"""
        tomorrow = date.today() + timedelta(days=1)
        plan = valid_plan(
            tasks=[
                make_task("task-1", date=date.today(), duration_minutes=60),
                make_task("task-2", date=tomorrow, duration_minutes=45),
            ]
        )

        progress = calculate_progress(plan)

        assert progress.daily_minutes[date.today()] == 60
        assert progress.daily_minutes[tomorrow] == 45

    def test_f3_5_06_calculates_weekly_minutes(self):
        """原因：用户需要看到不同周的学习负载。"""
        plan = valid_plan()

        progress = calculate_progress(plan)

        assert progress.weekly_minutes[1] == 90

    def test_f3_5_07_completion_rate_changes_after_status_update(self):
        """原因：编辑操作必须反映到进度统计。"""
        plan = valid_plan(tasks=[make_task("task-1"), make_task("task-2")])

        updated = update_task_status(plan, "task-1", "done")
        progress = calculate_progress(updated)

        assert progress.completion_rate == 50

    def test_f3_5_08_dashboard_view_contains_chart_data(self):
        """原因：PRD 要求图表能直观反映学习进度。"""
        view = build_dashboard_view(valid_plan())

        assert view.progress_chart_data
        assert view.daily_minutes_chart_data
        assert view.weekly_minutes_chart_data


class TestF3Stage6StateAndFlowIntegration:
    def test_f3_6_01_edit_updates_session_state_plan(self):
        """原因：F5 需要读取最新计划做复盘。"""
        session = FakeSessionState(study_plan=valid_plan())

        state = DashboardState.from_session(session)
        state.study_plan = update_task_status(state.study_plan, "task-1", "done")
        state.save_to_session(session)

        assert all_tasks(session["study_plan"])[0].status == "done"

    def test_f3_6_02_session_state_preserves_edit_result(self):
        """原因：用户不应因为重新进入看板丢失刚刚编辑的进度。"""
        session = FakeSessionState(study_plan=valid_plan())
        session["study_plan"] = update_task_status(session["study_plan"], "task-1", "done")

        restored = DashboardState.from_session(session)

        assert all_tasks(restored.study_plan)[0].status == "done"

    def test_f3_6_03_updated_plan_can_be_read_by_review_flow(self):
        """原因：F3 是 F5 复盘数据来源。"""
        session = FakeSessionState(study_plan=valid_plan())
        session["study_plan"] = update_task_status(session["study_plan"], "task-1", "skipped")

        f5_input_plan = session["study_plan"]

        assert all_tasks(f5_input_plan)[0].status == "skipped"

    def test_f3_6_04_updated_plan_can_be_exported_later(self):
        """原因：导出必须反映当前计划，而不是旧计划。"""
        session = FakeSessionState(study_plan=valid_plan())
        session["study_plan"] = update_task_notes(session["study_plan"], "task-1", "导出时应包含这条备注")

        f6_input_plan = session["study_plan"]

        assert all_tasks(f6_input_plan)[0].notes == "导出时应包含这条备注"
