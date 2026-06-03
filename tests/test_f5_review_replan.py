from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from study_planner.application.review_replan import (
    GenerateReviewReportUseCase,
    ReviewReplanError,
    analyze_review_risks,
    build_f5_llm_from_env,
    build_replan_request,
    build_review_page_view,
    calculate_period_progress,
    calculate_plan_diff,
    cancel_adjustment_preview,
    generate_adjustment_preview,
    identify_consecutive_unfinished_topics,
    identify_overdue_tasks,
    save_adjusted_plan,
    stable_task_id,
    validate_adjusted_plan,
)
from study_planner.domain.models import (
    AdjustedStudyPlan,
    ReplanRequest,
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


CURRENT_DATE = date(2026, 6, 3)


def valid_goal(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法并完成一个小项目",
        "deadline": date(2026, 6, 30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["项目实践", "刷题练习"],
        "weak_points": ["递归"],
        "extra_requirements": "希望多安排练习任务",
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
        "learning_method": "阅读 + 练习",
        "expected_output": "完成练习并整理笔记",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(tasks=None, goal=None, **overrides):
    goal = goal or valid_goal()
    tasks = tasks if tasks is not None else [make_task("task-1"), make_task("task-2", status="done")]
    phase = StudyPhase(
        phase_index=1,
        title="基础阶段",
        objective="掌握 Python 基础语法",
        start_date=CURRENT_DATE - timedelta(days=2),
        end_date=CURRENT_DATE + timedelta(days=13),
        milestone="完成基础语法练习",
        weekly_plans=[
            WeeklyPlan(
                week_index=1,
                start_date=CURRENT_DATE - timedelta(days=2),
                end_date=CURRENT_DATE + timedelta(days=4),
                objective="完成第一周学习",
                review_focus="复习变量、条件、函数",
                tasks=tasks,
            )
        ],
    )
    data = {
        "goal": goal,
        "overall_route": "先学基础，再做练习，最后完成项目",
        "phases": [phase],
        "methods": ["阅读", "练习", "项目实践"],
        "time_budget": TimeBudget(
            total_days=31,
            total_weeks=5,
            total_available_minutes=3000,
            planned_minutes=sum(task.duration_minutes for task in tasks),
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        "risks": ["任务延期会影响项目实践时间"],
        "review_schedule": ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="周日",
            review_strategy="每天复习当天知识点，每周做一次总结",
        ),
        "suggestions": "保持每天小步推进",
    }
    data.update(overrides)
    return StudyPlan(**data)


def all_tasks(plan):
    return [
        task
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    ]


def review_payload(**overrides):
    data = {
        "period_start": date(2026, 6, 1),
        "period_end": date(2026, 6, 7),
        "completion_rate": 0.6,
        "completed_task_count": 3,
        "total_task_count": 5,
        "overdue_tasks": ["task-1"],
        "consecutive_unfinished_topics": ["递归"],
        "weak_points": ["递归", "练习时间不足"],
        "summary": "本周完成率一般，递归理解不稳定。",
        "suggestions": ["降低任务粒度", "增加递归专项练习"],
    }
    data.update(overrides)
    return data


class FakeReviewLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_review_report(self, request):
        self.calls.append(request)
        return self.response


class FakePlanner:
    def __init__(self, adjusted_plan):
        self.adjusted_plan = adjusted_plan
        self.calls = []

    def replan(self, request):
        self.calls.append(request)
        return self.adjusted_plan


class FakeRepository:
    def __init__(self, fail=False):
        self.fail = fail
        self.saved_reports = []
        self.saved_plans = []

    def save_review_report(self, report):
        if self.fail:
            raise RuntimeError("database unavailable")
        self.saved_reports.append(report)

    def save_study_plan(self, plan):
        if self.fail:
            raise RuntimeError("database unavailable")
        self.saved_plans.append(plan)


class FakeSessionState(dict):
    pass


class TestF5Stage1ProgressStats:
    def test_f5_1_01_empty_plan_cannot_generate_review(self):
        """原因：F5 依赖 F3 的计划和任务状态，空计划时必须有保护。"""
        view = build_review_page_view(study_plan=None)

        assert view.is_empty is True
        assert view.can_generate_review is False
        assert "学习计划" in view.empty_message

    def test_f5_1_02_completion_rate_counts_done_only(self):
        """原因：完成率是复盘报告和是否重排的基础指标。"""
        statuses = ["done"] * 6 + ["todo"] * 2 + ["doing", "skipped"]
        tasks = [make_task(f"task-{index}", status=status) for index, status in enumerate(statuses, start=1)]
        plan = valid_plan(tasks=tasks)

        progress = calculate_period_progress(plan, date(2026, 6, 1), date(2026, 6, 7))

        assert progress.total_task_count == 10
        assert progress.completed_task_count == 6
        assert progress.completion_rate == pytest.approx(0.6)

    def test_f5_1_03_only_counts_tasks_in_current_period(self):
        """原因：本周复盘必须按周期计算，不能被全计划任务污染。"""
        tasks = [
            make_task("last-week", date=date(2026, 5, 28), status="done"),
            make_task("this-week-1", date=date(2026, 6, 2), status="done"),
            make_task("this-week-2", date=date(2026, 6, 3), status="todo"),
            make_task("next-week", date=date(2026, 6, 10), status="todo"),
        ]
        plan = valid_plan(tasks=tasks)

        progress = calculate_period_progress(plan, date(2026, 6, 1), date(2026, 6, 7))

        assert progress.total_task_count == 2
        assert progress.completed_task_count == 1
        assert {task.id for task in progress.period_tasks} == {"this-week-1", "this-week-2"}

    def test_f5_1_04_user_review_text_can_be_empty(self):
        """原因：复盘输入框是增强信息，不应阻塞自动复盘。"""
        plan = valid_plan()
        use_case = GenerateReviewReportUseCase(llm=FakeReviewLLM(review_payload()))

        report = use_case.execute(plan, current_date=CURRENT_DATE, user_review_text="")

        assert isinstance(report, ReviewReport)
        assert report.summary

    def test_f5_1_05_user_review_text_enters_report_context(self):
        """原因：用户主观反馈是动态调整的重要输入。"""
        plan = valid_plan()
        llm = FakeReviewLLM(review_payload(weak_points=["递归"], summary="递归理解不好，练习时间不够。"))
        use_case = GenerateReviewReportUseCase(llm=llm)

        report = use_case.execute(plan, current_date=CURRENT_DATE, user_review_text="这周递归部分理解不好，练习时间不够。")

        assert "递归" in report.summary
        assert "递归" in report.weak_points
        assert "递归" in llm.calls[0].user_review_text


class TestF5Stage2RiskDetection:
    def test_f5_2_01_identifies_overdue_tasks(self):
        """原因：延期判断必须基于任务日期和当前日期。"""
        tasks = [
            make_task("task-a", date=date(2026, 6, 1), status="todo"),
            make_task("task-b", date=date(2026, 6, 2), status="doing"),
            make_task("task-c", date=date(2026, 6, 3), status="todo"),
        ]

        overdue = identify_overdue_tasks(tasks, current_date=CURRENT_DATE)

        assert {task.id for task in overdue} == {"task-a", "task-b"}

    def test_f5_2_02_done_past_tasks_are_not_overdue(self):
        """原因：已完成任务不应触发重排压力。"""
        task = make_task("done-past", date=date(2026, 6, 1), status="done")

        overdue = identify_overdue_tasks([task], current_date=CURRENT_DATE)

        assert overdue == []

    def test_f5_2_03_skipped_tasks_enter_risk_analysis(self):
        """原因：跳过任务不是完成，可能代表时间不足或难度过高。"""
        task = make_task("skipped-task", date=date(2026, 6, 1), status="skipped")

        risks = analyze_review_risks([task], current_date=CURRENT_DATE)

        assert "skipped-task" in [item.task_id for item in risks.unfinished_tasks]
        assert risks.suggestions

    def test_f5_2_04_identifies_consecutive_unfinished_topics(self):
        """原因：连续失败比单个延期更能说明学习阻塞。"""
        tasks = [
            make_task("dp-1", related_topics=["动态规划"], status="todo"),
            make_task("dp-2", related_topics=["动态规划"], status="skipped"),
            make_task("dp-3", related_topics=["动态规划"], status="todo"),
        ]

        topics = identify_consecutive_unfinished_topics(tasks, threshold=3)

        assert "动态规划" in topics

    def test_f5_2_05_single_unfinished_task_is_not_consecutive_risk(self):
        """原因：避免过度诊断，减少错误重排。"""
        tasks = [
            make_task("recursion-1", related_topics=["递归"], status="todo"),
            make_task("recursion-2", related_topics=["递归"], status="done"),
            make_task("recursion-3", related_topics=["递归"], status="done"),
        ]

        topics = identify_consecutive_unfinished_topics(tasks, threshold=3)

        assert "递归" not in topics


class TestF5Stage3ReviewReport:
    def test_f5_3_01_fake_llm_generates_structured_review_report(self):
        """原因：自动化测试默认不依赖真实 LLM。"""
        plan = valid_plan()
        use_case = GenerateReviewReportUseCase(llm=FakeReviewLLM(review_payload()))

        report = use_case.execute(plan, current_date=CURRENT_DATE, user_review_text="递归理解不稳定")

        assert isinstance(report, ReviewReport)
        assert report.completion_rate == pytest.approx(0.6)
        assert report.overdue_tasks
        assert report.weak_points
        assert report.suggestions

    def test_f5_3_02_real_llm_switch_uses_deepseek_adapter(self, tmp_path):
        """原因：所有涉及 LLM 的功能都必须服从统一 USE_REAL_LLM 开关。"""
        env_path = tmp_path / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "USE_REAL_LLM=true",
                    "DEEPSEEK_API_KEY=test-key",
                    "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                    "DEEPSEEK_MODEL=deepseek-chat",
                ]
            ),
            encoding="utf-8",
        )

        llm = build_f5_llm_from_env(env_path)

        assert llm.__class__.__name__ == "DeepSeekReviewLLM"

    def test_f5_3_03_review_report_has_required_fields(self):
        """原因：F5 页面和重排逻辑依赖这些字段。"""
        report = GenerateReviewReportUseCase(llm=FakeReviewLLM(review_payload())).execute(
            valid_plan(),
            current_date=CURRENT_DATE,
            user_review_text="",
        )

        assert report.summary
        assert report.completion_rate is not None
        assert isinstance(report.overdue_tasks, list)
        assert isinstance(report.weak_points, list)
        assert report.suggestions

    def test_f5_3_04_non_json_llm_response_fails_cleanly(self):
        """原因：防止 LLM 输出格式不稳定导致页面崩溃。"""
        use_case = GenerateReviewReportUseCase(llm=FakeReviewLLM("这周整体还可以。"))

        with pytest.raises(ReviewReplanError, match="JSON|结构化|解析"):
            use_case.execute(valid_plan(), current_date=CURRENT_DATE, user_review_text="")

    def test_f5_3_05_missing_report_fields_fail_validation(self):
        """原因：结构化输出必须严格校验。"""
        payload = review_payload()
        payload.pop("suggestions")
        use_case = GenerateReviewReportUseCase(llm=FakeReviewLLM(payload))

        with pytest.raises(ReviewReplanError, match="suggestions|字段"):
            use_case.execute(valid_plan(), current_date=CURRENT_DATE, user_review_text="")


class TestF5Stage4ReplanRequest:
    def test_f5_4_01_all_done_needs_only_minor_or_no_replan(self):
        """原因：全部完成时应鼓励继续执行，而不是制造不必要变化。"""
        tasks = [make_task("task-1", status="done"), make_task("task-2", status="done")]
        plan = valid_plan(tasks=tasks)
        report = ReviewReport(**review_payload(completion_rate=1.0, completed_task_count=2, total_task_count=2, overdue_tasks=[]))

        request = build_replan_request(plan, report, current_date=CURRENT_DATE)

        assert request.need_replan is False or request.replan_type == "minor"
        assert request.remaining_tasks == []

    def test_f5_4_02_overdue_tasks_trigger_replan(self):
        """原因：延期任务是动态调整的核心触发条件。"""
        tasks = [
            make_task("late-1", date=date(2026, 6, 1), status="todo"),
            make_task("late-2", date=date(2026, 6, 2), status="doing"),
        ]
        plan = valid_plan(tasks=tasks)
        report = ReviewReport(**review_payload(overdue_tasks=["late-1", "late-2"]))

        request = build_replan_request(plan, report, current_date=CURRENT_DATE)

        assert request.need_replan is True
        assert {task.id for task in request.remaining_tasks} == {"late-1", "late-2"}
        assert request.remaining_days > 0
        assert request.daily_available_minutes == 120

    def test_f5_4_03_replan_request_contains_only_unfinished_tasks(self):
        """原因：已完成任务不应被重新安排。"""
        tasks = [
            make_task("done-task", status="done"),
            make_task("todo-task", status="todo"),
            make_task("doing-task", status="doing"),
            make_task("skipped-task", status="skipped"),
        ]
        plan = valid_plan(tasks=tasks)
        report = ReviewReport(**review_payload())

        request = build_replan_request(plan, report, current_date=CURRENT_DATE)

        assert {task.id for task in request.remaining_tasks} == {"todo-task", "doing-task", "skipped-task"}

    def test_f5_4_04_replan_request_keeps_original_plan_reference(self):
        """原因：页面需要展示调整前后差异，保存前也要防止覆盖。"""
        plan = valid_plan()
        report = ReviewReport(**review_payload())

        request = build_replan_request(plan, report, current_date=CURRENT_DATE)

        assert isinstance(request, ReplanRequest)
        assert request.original_plan is plan


class TestF5Stage5AdjustedPlanConstraints:
    def test_f5_5_01_adjusted_tasks_are_not_scheduled_before_today(self):
        """原因：新计划不能继续安排在过去。"""
        adjusted = valid_plan(
            tasks=[
                make_task("late-1", date=CURRENT_DATE, status="todo"),
                make_task("late-2", date=CURRENT_DATE + timedelta(days=1), status="todo"),
            ]
        )

        validation = validate_adjusted_plan(adjusted, current_date=CURRENT_DATE)

        assert validation.is_valid is True
        assert all(task.date >= CURRENT_DATE for task in all_tasks(adjusted))

    def test_f5_5_02_adjusted_tasks_do_not_exceed_deadline(self):
        """原因：F5 必须遵守用户目标约束。"""
        adjusted = valid_plan(tasks=[make_task("task-1", date=date(2026, 6, 30))])

        validation = validate_adjusted_plan(adjusted, current_date=CURRENT_DATE)

        assert validation.is_valid is True
        assert all(task.date <= adjusted.goal.deadline for task in all_tasks(adjusted))

    def test_f5_5_03_adjusted_daily_minutes_do_not_exceed_limit(self):
        """原因：防止动态调整生成不可执行计划。"""
        adjusted = valid_plan(
            tasks=[
                make_task("task-1", date=CURRENT_DATE, duration_minutes=60),
                make_task("task-2", date=CURRENT_DATE, duration_minutes=60),
                make_task("task-3", date=CURRENT_DATE + timedelta(days=1), duration_minutes=90),
            ]
        )

        validation = validate_adjusted_plan(adjusted, current_date=CURRENT_DATE)

        assert validation.is_valid is True
        assert validation.daily_minutes[CURRENT_DATE] == 120

    def test_f5_5_04_insufficient_time_returns_warning(self):
        """原因：当约束不可满足时，应暴露冲突，而不是伪造可行计划。"""
        goal = valid_goal(deadline=CURRENT_DATE, daily_available_minutes=60)
        overloaded = valid_plan(
            goal=goal,
            tasks=[
                make_task("task-1", date=CURRENT_DATE, duration_minutes=60),
                make_task("task-2", date=CURRENT_DATE, duration_minutes=60),
            ],
        )

        validation = validate_adjusted_plan(overloaded, current_date=CURRENT_DATE)

        assert validation.is_valid is False
        assert validation.warnings
        assert any("时间" in warning or "超" in warning for warning in validation.warnings)

    def test_f5_5_05_adjusted_plan_keeps_phase_week_task_hierarchy(self):
        """原因：F5 输出必须能回到 F3 展示。"""
        adjusted = valid_plan()

        validation = validate_adjusted_plan(adjusted, current_date=CURRENT_DATE)

        assert validation.is_valid is True
        assert adjusted.phases
        assert adjusted.phases[0].weekly_plans
        assert adjusted.phases[0].weekly_plans[0].tasks

    def test_f5_5_06_reinforcement_task_is_inserted_for_weak_point(self):
        """原因：F5 不能只移动日期，还要对学习问题做补救。"""
        plan = valid_plan(tasks=[make_task("recursion-task", related_topics=["递归"], status="todo")])
        report = ReviewReport(**review_payload(weak_points=["递归"]))
        request = build_replan_request(plan, report, current_date=CURRENT_DATE)
        adjusted = deepcopy(plan)
        adjusted.phases[0].weekly_plans[0].tasks.append(
            make_task("recursion-reinforcement", title="递归专项强化练习", task_type="reinforcement", related_topics=["递归"])
        )

        preview = generate_adjustment_preview(request, planner=FakePlanner(adjusted))

        assert any("递归" in task.title for task in all_tasks(preview.adjusted_plan))
        assert any(task.task_type in {"review", "practice", "reinforcement"} for task in all_tasks(preview.adjusted_plan))


class TestF5Stage6PreviewAndSave:
    def test_f5_6_01_preview_does_not_overwrite_original_plan(self):
        """原因：PRD 要求用户确认后才保存。"""
        original = valid_plan()
        adjusted = deepcopy(original)
        adjusted.phases[0].weekly_plans[0].tasks[0].date = CURRENT_DATE + timedelta(days=2)
        state = FakeSessionState(study_plan=original)

        preview = generate_adjustment_preview(
            build_replan_request(original, ReviewReport(**review_payload()), current_date=CURRENT_DATE),
            planner=FakePlanner(adjusted),
            session_state=state,
        )

        assert state["study_plan"] is original
        assert state["pending_adjusted_plan"] == preview.adjusted_plan

    def test_f5_6_02_plan_diff_lists_moved_new_and_compressed_tasks(self):
        """原因：页面需要展示调整前后对比，帮助用户决定是否保存。"""
        original = valid_plan(tasks=[make_task("task-1", date=CURRENT_DATE, duration_minutes=90)])
        adjusted = valid_plan(
            tasks=[
                make_task("task-1", date=CURRENT_DATE + timedelta(days=1), duration_minutes=60),
                make_task("task-1-part-2", title="学习任务 task-1 拆分练习", date=CURRENT_DATE + timedelta(days=2)),
                make_task("reinforcement", title="递归强化任务", task_type="reinforcement"),
            ]
        )

        diff = calculate_plan_diff(original, adjusted)

        assert "task-1" in [item.task_id for item in diff.moved_tasks]
        assert "reinforcement" in [item.task_id for item in diff.new_tasks]
        assert "task-1" in [item.task_id for item in diff.compressed_or_split_tasks]

    def test_f5_6_03_cancel_adjustment_keeps_original_plan(self):
        """原因：用户必须拥有最终控制权。"""
        original = valid_plan()
        adjusted = deepcopy(original)
        state = FakeSessionState(study_plan=original, pending_adjusted_plan=adjusted)

        cancel_adjustment_preview(state)

        assert state["study_plan"] is original
        assert "pending_adjusted_plan" not in state

    def test_f5_6_04_confirm_adjustment_saves_new_plan(self):
        """原因：F5 的最终结果必须回流到 F3。"""
        original = valid_plan()
        adjusted = deepcopy(original)
        adjusted.phases[0].weekly_plans[0].tasks[0].date = CURRENT_DATE + timedelta(days=1)
        report = ReviewReport(**review_payload())
        state = FakeSessionState(study_plan=original, pending_adjusted_plan=adjusted, pending_review_report=report)

        save_adjusted_plan(state, repository=FakeRepository(), current_date=CURRENT_DATE)

        assert state["study_plan"] == adjusted
        assert state["last_review_report"] == report
        assert "pending_adjusted_plan" not in state

    def test_f5_6_05_invalid_adjustment_cannot_be_saved(self):
        """原因：保存前必须再次校验，防止异常结果进入主状态。"""
        original = valid_plan()
        invalid = valid_plan(tasks=[make_task("invalid", date=date(2026, 7, 1))])
        state = FakeSessionState(study_plan=original, pending_adjusted_plan=invalid, pending_review_report=ReviewReport(**review_payload()))

        with pytest.raises(ReviewReplanError):
            save_adjusted_plan(state, repository=FakeRepository(), current_date=CURRENT_DATE)

        assert state["study_plan"] is original


class TestF5Stage7PageRequirements:
    def test_f5_7_01_empty_page_view_shows_empty_state(self):
        """原因：页面必须处理新用户或刷新后的空状态。"""
        view = build_review_page_view(None)

        assert view.is_empty is True
        assert view.can_auto_replan is False

    def test_f5_7_02_page_view_displays_progress_table(self):
        """原因：PRD 明确要求展示完成情况表格。"""
        plan = valid_plan()

        view = build_review_page_view(plan)

        assert view.progress_rows
        first = view.progress_rows[0]
        assert first.title
        assert first.date
        assert first.duration_minutes
        assert first.status
        assert first.related_topics

    def test_f5_7_03_page_view_has_review_input(self):
        """原因：用户主观反馈是 F5 输入之一。"""
        view = build_review_page_view(valid_plan())

        assert view.has_review_text_input is True
        assert view.review_text_input_type == "textarea"

    def test_f5_7_04_page_view_has_auto_replan_button(self):
        """原因：PRD 明确要求自动重排按钮。"""
        view = build_review_page_view(valid_plan())

        assert view.can_auto_replan is True
        assert view.auto_replan_button_label

    def test_f5_7_05_page_view_displays_before_after_preview(self):
        """原因：用户保存前必须能理解系统改了什么。"""
        original = valid_plan()
        adjusted = deepcopy(original)
        adjusted.phases[0].weekly_plans[0].tasks[0].date = CURRENT_DATE + timedelta(days=1)

        view = build_review_page_view(original, pending_adjusted_plan=adjusted)

        assert view.has_adjustment_preview is True
        assert view.before_rows
        assert view.after_rows
        assert view.diff_rows

    def test_f5_7_06_page_view_has_save_adjustment_button(self):
        """原因：PRD 要求确认后保存。"""
        original = valid_plan()
        adjusted = deepcopy(original)

        view = build_review_page_view(original, pending_adjusted_plan=adjusted)

        assert view.can_save_adjustment is True
        assert view.save_adjustment_button_label


class TestF5Stage8PersistenceIntegration:
    def test_f5_8_01_saves_review_report_to_repository(self):
        """原因：F7 要求 PostgreSQL 保存复盘报告。"""
        repository = FakeRepository()
        report = ReviewReport(**review_payload())

        repository.save_review_report(report)

        assert repository.saved_reports == [report]

    def test_f5_8_02_saves_adjusted_plan_to_repository(self):
        """原因：刷新应用后不能丢失调整结果。"""
        repository = FakeRepository()
        adjusted = valid_plan()
        state = FakeSessionState(study_plan=valid_plan(), pending_adjusted_plan=adjusted, pending_review_report=ReviewReport(**review_payload()))

        save_adjusted_plan(state, repository=repository, current_date=CURRENT_DATE)

        assert repository.saved_plans == [adjusted]

    def test_f5_8_03_f3_can_display_adjusted_plan_after_save(self):
        """原因：F5 必须闭环回到计划执行页面。"""
        adjusted = valid_plan(tasks=[make_task("reinforcement", title="递归强化任务", task_type="reinforcement")])
        state = FakeSessionState(study_plan=valid_plan(), pending_adjusted_plan=adjusted, pending_review_report=ReviewReport(**review_payload()))

        save_adjusted_plan(state, repository=FakeRepository(), current_date=CURRENT_DATE)
        view = build_review_page_view(state["study_plan"])

        assert any(row.task_type == "reinforcement" for row in view.progress_rows)

    def test_f5_8_04_repository_failure_keeps_original_plan(self):
        """原因：真实数据库异常不能导致计划丢失。"""
        original = valid_plan()
        adjusted = deepcopy(original)
        adjusted.phases[0].weekly_plans[0].tasks[0].date = CURRENT_DATE + timedelta(days=1)
        state = FakeSessionState(study_plan=original, pending_adjusted_plan=adjusted, pending_review_report=ReviewReport(**review_payload()))

        with pytest.raises(ReviewReplanError, match="database|保存"):
            save_adjusted_plan(state, repository=FakeRepository(fail=True), current_date=CURRENT_DATE)

        assert state["study_plan"] is original


class TestF5Stage9EdgeCases:
    def test_f5_9_01_empty_task_list_does_not_divide_by_zero(self):
        """原因：防止空计划结构导致崩溃。"""
        plan = valid_plan(tasks=[])

        progress = calculate_period_progress(plan, date(2026, 6, 1), date(2026, 6, 7))

        assert progress.total_task_count == 0
        assert progress.completion_rate == 0

    def test_f5_9_02_invalid_task_status_fails_validation(self):
        """原因：F3/F5 状态枚举必须一致。"""
        plan = valid_plan(tasks=[make_task("bad-status", status="unknown")])

        with pytest.raises(ReviewReplanError, match="status|状态"):
            calculate_period_progress(plan, date(2026, 6, 1), date(2026, 6, 7))

    def test_f5_9_03_missing_task_id_can_generate_stable_id(self):
        """原因：F3 早期任务可能没有 ID，F5 需要处理迁移状态。"""
        task = make_task("", id="", title="学习递归", date=CURRENT_DATE, related_topics=["递归"])

        first = stable_task_id(task)
        second = stable_task_id(task)

        assert first
        assert first == second

    def test_f5_9_04_expired_goal_blocks_replan(self):
        """原因：过期目标需要用户修改截止日期或重新生成计划。"""
        goal = valid_goal(deadline=date(2026, 6, 1))
        plan = valid_plan(goal=goal)
        report = ReviewReport(**review_payload())

        with pytest.raises(ReviewReplanError, match="过期|deadline"):
            build_replan_request(plan, report, current_date=CURRENT_DATE)

    def test_f5_9_05_replan_keeps_prerequisite_order(self):
        """原因：动态调整不能破坏学习路径。"""
        adjusted = valid_plan(
            tasks=[
                make_task("task-a", title="学习递归基础", date=CURRENT_DATE, related_topics=["递归基础"]),
                make_task("task-b", title="递归项目练习", date=CURRENT_DATE + timedelta(days=1), related_topics=["递归项目"]),
            ]
        )

        validation = validate_adjusted_plan(
            adjusted,
            current_date=CURRENT_DATE,
            prerequisites={"task-b": ["task-a"]},
        )

        assert validation.is_valid is True
        dates = {task.id: task.date for task in all_tasks(adjusted)}
        assert dates["task-a"] <= dates["task-b"]
