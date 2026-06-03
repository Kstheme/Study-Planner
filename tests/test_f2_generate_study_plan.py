from datetime import date, timedelta

import pytest

from study_planner.application.generate_study_plan import (
    GenerateStudyPlanUseCase,
    StudyPlanGenerationError,
)
from study_planner.domain.models import StudyGoal, StudyPlan


def valid_goal(**overrides):
    """
    创建有效的学习目标对象用于测试。

    构建一个默认的 StudyGoal 实例，包含 Python 编程学习的完整信息，
    允许通过 overrides 参数覆盖任意字段以适配不同测试场景。

    Args:
        **overrides: 可变关键字参数，用于覆盖默认的学习目标字段值。
                     可覆盖的字段包括 subject、target、deadline、current_level、
                     daily_available_minutes、weekly_available_days、
                     preferred_methods、weak_points、extra_requirements。

    Returns:
        StudyGoal: 配置好的学习目标实例，包含完整的字段信息。
    """
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


class FakeStudyPlanLLM:
    """
    模拟学习计划生成的 LLM（大语言模型）服务。

    用于测试环境中替代真实的 LLM 调用，直接返回预设的响应数据，
    避免依赖外部服务和网络请求，提高测试执行速度和稳定性。
    """

    def __init__(self, response):
        """
        初始化模拟 LLM 实例。

        Args:
            response: 预设的响应数据，将在 generate_study_plan 方法中直接返回。
                      通常为包含完整学习计划结构的字典或 StudyPlan 对象。
        """
        self.response = response

    def generate_study_plan(self, goal: StudyGoal):
        """
        生成学习计划（模拟实现）。

        不进行实际的 AI 推理，直接返回构造时预设的响应数据。

        Args:
            goal: 学习目标对象，包含学习主题、目标、截止日期等信息。
                  在此模拟实现中该参数不被使用，仅为保持接口一致性。

        Returns:
            构造时传入的 response 数据，通常为学习计划的有效载荷字典。
        """
        return self.response

def valid_plan_payload(goal=None, **overrides):
    """
    创建有效的学习计划 payload 数据用于测试。

    构建一个完整的学习计划数据结构，包含阶段划分、周计划、任务列表、
    时间预算、复习安排等完整信息，允许通过 overrides 参数自定义任意字段。

    Args:
        goal: 学习目标对象，默认为 None，此时会自动调用 valid_goal() 创建默认目标。
              如果提供，则使用该目标对象作为计划的 goal 字段。
        **overrides: 可变关键字参数，用于覆盖默认 payload 中的字段值。
                     可覆盖的字段包括 goal、overall_route、phases、methods、
                     time_budget、risks、review_schedule、suggestions 等。

    Returns:
        dict: 包含完整学习计划结构的数据字典，可直接用于 GenerateStudyPlanUseCase 的测试。
              字典包含 phases（阶段列表）、time_budget（时间预算）、
              review_schedule（复习计划）等关键信息。
    """
    goal = goal or valid_goal()
    today = date.today()
    payload = {
        "goal": goal,
        "overall_route": "先学习 Python 基础语法，再完成练习，最后实现一个小型项目。",
        "phases": [
            {
                "phase_index": 1,
                "title": "基础入门阶段",
                "objective": "掌握 Python 基础语法和基本编程思维。",
                "start_date": today,
                "end_date": today + timedelta(days=13),
                "milestone": "能够完成变量、条件、循环和函数相关练习。",
                "weekly_plans": [
                    {
                        "week_index": 1,
                        "start_date": today,
                        "end_date": today + timedelta(days=6),
                        "objective": "完成 Python 基础语法学习。",
                        "review_focus": "复习变量、条件、循环和函数。",
                        "tasks": [
                            {
                                "title": "学习变量与数据类型",
                                "date": today,
                                "duration_minutes": 60,
                                "task_type": "学习",
                                "related_topics": ["变量", "数据类型"],
                                "learning_method": "视频教程 + 练习",
                                "expected_output": "完成 10 道变量和数据类型练习。",
                                "review_required": True,
                                "status": "todo",
                            },
                            {
                                "title": "完成基础语法复习",
                                "date": today,
                                "duration_minutes": 30,
                                "task_type": "复习",
                                "related_topics": ["变量", "数据类型"],
                                "learning_method": "错题回顾",
                                "expected_output": "整理 3 条易错点。",
                                "review_required": True,
                                "status": "todo",
                            },
                        ],
                    }
                ],
            }
        ],
        "methods": ["视频教程", "实践项目", "每日复习"],
        "time_budget": {
            "total_days": 31,
            "total_weeks": 5,
            "total_available_minutes": 3000,
            "planned_minutes": 90,
            "daily_available_minutes": goal.daily_available_minutes,
            "weekly_available_days": goal.weekly_available_days,
        },
        "risks": ["零基础学习容易卡在语法细节，需要保持每日练习。"],
        "review_schedule": {
            "daily_review_minutes": 15,
            "weekly_review_day": "周日",
            "review_strategy": "每天复习当天知识点，每周整理一次薄弱点。",
        },
        "suggestions": "保持小步快跑，每天完成一个可检查的学习产出。",
    }
    payload.update(overrides)
    return payload

def generate_plan_with_payload(payload):
    """
    使用给定的 payload 数据生成学习计划。

    创建带有模拟 LLM 的 GenerateStudyPlanUseCase 实例并执行，
    用于在测试中快速生成学习计划对象。

    Args:
        payload: 学习计划的有效载荷字典，必须包含 'goal' 键，
                 其值为 StudyGoal 对象或其他可作为 LLM 响应的数据。

    Returns:
        StudyPlan: 生成的学习计划对象，由 use_case.execute() 方法返回。
    """
    use_case = GenerateStudyPlanUseCase(llm=FakeStudyPlanLLM(payload))
    return use_case.execute(payload["goal"])

def iter_tasks(plan):
    """
    遍历学习计划中的所有任务。

    通过三层嵌套循环依次访问计划中的每个阶段、每周计划和任务，
    以生成器方式逐个产出任务对象，便于测试中对任务进行验证和统计。

    Args:
        plan: StudyPlan 对象，包含 phases 属性，每个 phase 包含 weekly_plans，
              每个 weekly_plan 包含 tasks 列表。

    Yields:
        Task: 学习计划中的单个任务对象，按阶段和周的顺序依次产出。
    """
    for phase in plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                yield task


class TestF2Stage1BasicStructure:
    def test_f2_1_01_generates_study_plan(self):
        """原因：验证 F2 主流程存在，输入 StudyGoal 后能返回 StudyPlan。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert isinstance(plan, StudyPlan)

    def test_f2_1_02_plan_keeps_original_goal(self):
        """原因：计划需要追溯原始学习目标，方便后续展示、保存和复盘。"""
        goal = valid_goal(subject="机器学习")
        plan = generate_plan_with_payload(valid_plan_payload(goal=goal))

        assert plan.goal == goal

    def test_f2_1_03_plan_has_overall_route(self):
        """原因：PRD 要求生成总体学习路线，不能只有每日任务。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.overall_route.strip()

    def test_f2_1_04_plan_has_suggestions(self):
        """原因：计划需要给用户整体执行建议，帮助理解如何开始。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.suggestions.strip()

    def test_f2_1_05_rejects_empty_llm_response(self):
        """原因：LLM 无输出时不能被误认为生成了有效计划。"""
        use_case = GenerateStudyPlanUseCase(llm=FakeStudyPlanLLM(None))

        with pytest.raises(StudyPlanGenerationError):
            use_case.execute(valid_goal())


class TestF2Stage2PlanHierarchy:
    def test_f2_2_01_plan_has_at_least_one_phase(self):
        """原因：验收要求计划必须包含阶段结构。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert len(plan.phases) > 0

    def test_f2_2_02_each_phase_has_objective(self):
        """原因：阶段不能只是时间容器，必须有明确阶段目标。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(phase.objective.strip() for phase in plan.phases)

    def test_f2_2_03_each_phase_has_valid_date_range(self):
        """原因：阶段计划需要能落到时间线上，开始日期不能晚于结束日期。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for phase in plan.phases:
            assert phase.start_date <= phase.end_date

    def test_f2_2_04_each_phase_has_weekly_plans(self):
        """原因：验收要求计划必须包含周计划结构。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(len(phase.weekly_plans) > 0 for phase in plan.phases)

    def test_f2_2_05_each_weekly_plan_has_objective(self):
        """原因：周计划需要有本周目标，而不只是任务列表。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for phase in plan.phases:
            assert all(weekly_plan.objective.strip() for weekly_plan in phase.weekly_plans)

    def test_f2_2_06_each_weekly_plan_has_daily_tasks(self):
        """原因：验收要求计划必须包含每日任务。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for phase in plan.phases:
            assert all(len(weekly_plan.tasks) > 0 for weekly_plan in phase.weekly_plans)

    def test_f2_2_07_each_task_has_date(self):
        """原因：日计划必须落到具体日期，后续看板和复盘都依赖日期。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(task.date for task in iter_tasks(plan))

    def test_f2_2_08_each_task_has_title_and_expected_output(self):
        """原因：任务需要可执行、可验收，不能是泛泛描述。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for task in iter_tasks(plan):
            assert task.title.strip()
            assert task.expected_output.strip()


class TestF2Stage3ContentCompleteness:
    def test_f2_3_01_plan_has_learning_methods(self):
        """原因：PRD 要求生成学习方法。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert len(plan.methods) > 0
        assert all(method.strip() for method in plan.methods)

    def test_f2_3_02_each_task_has_learning_method(self):
        """原因：学习方法需要落到每日任务层，用户才知道怎么执行。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(task.learning_method.strip() for task in iter_tasks(plan))

    def test_f2_3_03_plan_has_time_budget(self):
        """原因：PRD 要求生成时间预算。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.time_budget is not None

    def test_f2_3_04_time_budget_has_available_minutes(self):
        """原因：用户需要知道总共可投入多少学习时间。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.time_budget.total_available_minutes > 0

    def test_f2_3_05_time_budget_has_planned_minutes(self):
        """原因：计划时间用于判断生成的学习计划是否过载。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.time_budget.planned_minutes > 0

    def test_f2_3_06_plan_has_risks(self):
        """原因：PRD 要求生成风险提示。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert len(plan.risks) > 0

    def test_f2_3_07_risks_are_specific(self):
        """原因：风险提示不能是空字符串或占位符。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(risk.strip() and risk.strip() not in {"无", "暂无", "N/A"} for risk in plan.risks)

    def test_f2_3_08_plan_has_review_schedule(self):
        """原因：PRD 要求生成复习安排。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.review_schedule is not None

    def test_f2_3_09_review_schedule_has_executable_strategy(self):
        """原因：复习安排必须能指导用户执行，而不能只是空壳。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert plan.review_schedule.review_strategy.strip()
        assert plan.review_schedule.daily_review_minutes > 0 or plan.review_schedule.weekly_review_day.strip()

    def test_f2_3_10_each_phase_has_milestone(self):
        """原因：阶段目标需要有可验收的里程碑。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(phase.milestone.strip() for phase in plan.phases)

    def test_f2_3_11_each_task_has_related_topics(self):
        """原因：每日任务应关联知识点，保证计划是学习路径而不是单纯时间表。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(len(task.related_topics) > 0 for task in iter_tasks(plan))


class TestF2Stage4ScheduleConstraints:
    def test_f2_4_01_each_task_duration_is_positive(self):
        """原因：任务必须有实际时间投入。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(task.duration_minutes > 0 for task in iter_tasks(plan))

    def test_f2_4_02_daily_task_minutes_do_not_exceed_goal_limit(self):
        """原因：防止生成超过用户每日可学习时间的过载计划。"""
        plan = generate_plan_with_payload(valid_plan_payload())
        minutes_by_date = {}

        for task in iter_tasks(plan):
            minutes_by_date[task.date] = minutes_by_date.get(task.date, 0) + task.duration_minutes

        assert all(minutes <= plan.goal.daily_available_minutes for minutes in minutes_by_date.values())

    def test_f2_4_03_task_dates_are_not_before_today(self):
        """原因：不能生成过去日期的学习任务。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(task.date >= date.today() for task in iter_tasks(plan))

    def test_f2_4_04_task_dates_are_not_after_deadline(self):
        """原因：计划必须在用户截止日期内完成。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        assert all(task.date <= plan.goal.deadline for task in iter_tasks(plan))

    def test_f2_4_05_phase_dates_are_inside_goal_range(self):
        """原因：阶段时间范围不能超出整体目标周期。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for phase in plan.phases:
            assert date.today() <= phase.start_date <= plan.goal.deadline
            assert date.today() <= phase.end_date <= plan.goal.deadline

    def test_f2_4_06_weekly_dates_are_inside_phase_range(self):
        """原因：周计划日期需要和所属阶段保持一致。"""
        plan = generate_plan_with_payload(valid_plan_payload())

        for phase in plan.phases:
            for weekly_plan in phase.weekly_plans:
                assert phase.start_date <= weekly_plan.start_date <= phase.end_date
                assert phase.start_date <= weekly_plan.end_date <= phase.end_date

    def test_f2_4_07_planned_minutes_match_task_duration_sum(self):
        """原因：时间预算应与实际任务时长一致。"""
        plan = generate_plan_with_payload(valid_plan_payload())
        total_task_minutes = sum(task.duration_minutes for task in iter_tasks(plan))

        assert plan.time_budget.planned_minutes == total_task_minutes

    def test_f2_4_08_total_available_minutes_is_calculated_from_goal(self):
        """原因：总可用时间最好由系统兜底计算，不能完全依赖 LLM 乱填。"""
        goal = valid_goal(deadline=date.today() + timedelta(days=13), daily_available_minutes=120, weekly_available_days=5)
        plan = generate_plan_with_payload(valid_plan_payload(goal=goal))

        assert plan.time_budget.total_available_minutes == 10 * 120

    def test_f2_4_09_weekly_study_days_do_not_exceed_goal_limit(self):
        """原因：生成计划必须尊重用户每周可学习天数。"""
        goal = valid_goal(weekly_available_days=1)
        payload = valid_plan_payload(goal=goal)
        payload["phases"][0]["weekly_plans"][0]["tasks"] = [
            {
                **payload["phases"][0]["weekly_plans"][0]["tasks"][0],
                "date": date.today(),
                "duration_minutes": 60,
            }
        ]
        plan = generate_plan_with_payload(payload)

        for phase in plan.phases:
            for weekly_plan in phase.weekly_plans:
                active_days = {task.date for task in weekly_plan.tasks}
                assert len(active_days) <= plan.goal.weekly_available_days

    def test_f2_4_10_review_tasks_count_toward_daily_minutes(self):
        """原因：复习任务也占用学习时间，不能形成隐形过载。"""
        plan = generate_plan_with_payload(valid_plan_payload())
        today_minutes = sum(task.duration_minutes for task in iter_tasks(plan) if task.date == date.today())

        assert today_minutes <= plan.goal.daily_available_minutes


class TestF2Stage5InvalidOutputs:
    def test_f2_5_01_rejects_invalid_json_response(self):
        """原因：LLM 可能返回破损 JSON，系统必须能防守。"""
        use_case = GenerateStudyPlanUseCase(llm=FakeStudyPlanLLM("{ invalid json"))

        with pytest.raises(StudyPlanGenerationError):
            use_case.execute(valid_goal())

    def test_f2_5_02_rejects_payload_without_phases(self):
        """原因：阶段结构是 F2 验收要求，不能缺失。"""
        payload = valid_plan_payload()
        payload["phases"] = []

        with pytest.raises(StudyPlanGenerationError):
            generate_plan_with_payload(payload)

    def test_f2_5_03_rejects_phase_without_weekly_plans(self):
        """原因：周计划结构是 F2 验收要求，不能缺失。"""
        payload = valid_plan_payload()
        payload["phases"][0]["weekly_plans"] = []

        with pytest.raises(StudyPlanGenerationError):
            generate_plan_with_payload(payload)

    def test_f2_5_04_rejects_weekly_plan_without_tasks(self):
        """原因：每日任务结构是 F2 验收要求，不能缺失。"""
        payload = valid_plan_payload()
        payload["phases"][0]["weekly_plans"][0]["tasks"] = []

        with pytest.raises(StudyPlanGenerationError):
            generate_plan_with_payload(payload)

    def test_f2_5_05_rejects_daily_tasks_that_exceed_daily_limit(self):
        """原因：坏的 LLM 输出不能生成过载计划。"""
        payload = valid_plan_payload()
        payload["phases"][0]["weekly_plans"][0]["tasks"][0]["duration_minutes"] = 180

        with pytest.raises(StudyPlanGenerationError):
            generate_plan_with_payload(payload)

    def test_f2_5_06_near_deadline_plan_contains_risk(self):
        """原因：截止日期很近时，系统应给出冲刺风险提示。"""
        goal = valid_goal(deadline=date.today())
        payload = valid_plan_payload(goal=goal, risks=["截止日期很近，需要压缩学习范围并优先完成核心任务。"])
        plan = generate_plan_with_payload(payload)

        assert any("截止日期" in risk or "冲刺" in risk for risk in plan.risks)

    def test_f2_5_07_low_daily_minutes_plan_contains_lightweight_tasks_or_risk(self):
        """原因：每日学习时间很少时，计划需要轻量化或提示风险。"""
        goal = valid_goal(daily_available_minutes=30)
        payload = valid_plan_payload(goal=goal, risks=["每日学习时间较少，需要延长周期或降低目标范围。"])
        payload["phases"][0]["weekly_plans"][0]["tasks"] = [
            {
                **payload["phases"][0]["weekly_plans"][0]["tasks"][0],
                "duration_minutes": 30,
            }
        ]
        plan = generate_plan_with_payload(payload)

        assert all(task.duration_minutes <= 30 for task in iter_tasks(plan))
        assert plan.risks

    def test_f2_5_08_one_day_per_week_goal_gets_one_active_day_per_week(self):
        """原因：每周只学 1 天时，计划必须尊重该约束。"""
        goal = valid_goal(weekly_available_days=1)
        payload = valid_plan_payload(goal=goal)
        payload["phases"][0]["weekly_plans"][0]["tasks"] = [
            payload["phases"][0]["weekly_plans"][0]["tasks"][0]
        ]
        plan = generate_plan_with_payload(payload)

        for phase in plan.phases:
            for weekly_plan in phase.weekly_plans:
                assert len({task.date for task in weekly_plan.tasks}) <= 1

    def test_f2_5_09_empty_preferred_methods_still_generates_methods(self):
        """原因：F1 允许学习偏好为空，F2 需要提供默认学习方法。"""
        goal = valid_goal(preferred_methods=[])
        plan = generate_plan_with_payload(valid_plan_payload(goal=goal, methods=["阅读教程", "基础练习"]))

        assert plan.methods

    def test_f2_5_10_empty_weak_points_still_generates_plan(self):
        """原因：薄弱点是可选字段，不能为空阻断计划生成。"""
        goal = valid_goal(weak_points=[])
        plan = generate_plan_with_payload(valid_plan_payload(goal=goal))

        assert isinstance(plan, StudyPlan)

    def test_f2_5_11_long_target_still_generates_plan_or_clear_error(self):
        """原因：用户可能输入较长目标，系统不能静默失败。"""
        goal = valid_goal(target="我要系统学习 Python。" * 80)
        plan = generate_plan_with_payload(valid_plan_payload(goal=goal))

        assert isinstance(plan, StudyPlan)

    def test_f2_5_12_chinese_goal_generates_chinese_plan(self):
        """原因：产品面向中文用户，输出计划关键内容应保持中文可读。"""
        goal = valid_goal(subject="机器学习", target="理解监督学习，并完成分类项目")
        plan = generate_plan_with_payload(
            valid_plan_payload(
                goal=goal,
                overall_route="先学习基础概念，再完成分类项目。",
                methods=["阅读中文教程", "项目实践"],
            )
        )

        assert "学习" in plan.overall_route or "项目" in plan.overall_route
        assert any("教程" in method or "实践" in method for method in plan.methods)
