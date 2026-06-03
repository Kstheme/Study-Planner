from datetime import date, timedelta

import pytest

from study_planner.application.study_goal_input import (
    collect_study_goal,
    submit_study_goal,
)
from study_planner.domain.models import StudyGoal


def valid_form_data(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法，并能独立完成一个小型项目",
        "deadline": date.today() + timedelta(days=30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["视频教程", "实践项目"],
        "weak_points": ["缺乏编程经验", "英语文档阅读慢"],
        "extra_requirements": "希望多安排练习任务",
    }
    data.update(overrides)
    return data


class FakeNextFlow:
    def __init__(self):
        self.received_goal = None

    def receive_study_goal(self, goal: StudyGoal):
        self.received_goal = goal


def test_f1_01_collects_complete_study_goal_data():
    """原因：覆盖 F1 主路径，保证完整表单可以转换成 StudyGoal。"""
    goal = collect_study_goal(valid_form_data())

    assert isinstance(goal, StudyGoal)
    assert goal.subject == "Python 编程"
    assert goal.target == "掌握 Python 基础语法，并能独立完成一个小型项目"
    assert goal.current_level == "零基础"
    assert goal.daily_available_minutes == 120
    assert goal.weekly_available_days == 5
    assert goal.preferred_methods == ["视频教程", "实践项目"]
    assert goal.weak_points == ["缺乏编程经验", "英语文档阅读慢"]
    assert goal.extra_requirements == "希望多安排练习任务"


def test_f1_02_rejects_empty_subject():
    """原因：学习主题是后续 Agent 判断学习领域的核心输入，不能为空。"""
    with pytest.raises(ValueError, match="学习主题"):
        collect_study_goal(valid_form_data(subject=""))


def test_f1_03_rejects_blank_subject_after_stripping():
    """原因：用户可能输入空格，系统应去除前后空格后再校验。"""
    with pytest.raises(ValueError, match="学习主题"):
        collect_study_goal(valid_form_data(subject="   "))


def test_f1_04_rejects_empty_target():
    """原因：学习目标为空时，后续流程无法生成有方向的学习计划。"""
    with pytest.raises(ValueError, match="学习目标"):
        collect_study_goal(valid_form_data(target=""))


def test_f1_05_rejects_past_deadline():
    """原因：截止日期决定学习周期，早于今天的日期不可用于生成未来计划。"""
    with pytest.raises(ValueError, match="截止日期"):
        collect_study_goal(valid_form_data(deadline=date.today() - timedelta(days=1)))


def test_f1_06_accepts_today_as_deadline():
    """原因：用户可能需要当天冲刺计划，今天应视为有效截止日期。"""
    goal = collect_study_goal(valid_form_data(deadline=date.today()))

    assert goal.deadline == date.today()


def test_f1_07_rejects_missing_current_level():
    """原因：当前水平会影响计划难度和起点，必须提供。"""
    with pytest.raises(ValueError, match="当前水平"):
        collect_study_goal(valid_form_data(current_level=""))


def test_f1_08_rejects_invalid_current_level():
    """原因：当前水平应来自固定选项，避免后续计划难度不可控。"""
    with pytest.raises(ValueError, match="当前水平"):
        collect_study_goal(valid_form_data(current_level="未知水平"))


def test_f1_09_rejects_zero_daily_available_minutes():
    """原因：每日学习时间为 0 时无法生成可执行的每日任务。"""
    with pytest.raises(ValueError, match="每日学习时间"):
        collect_study_goal(valid_form_data(daily_available_minutes=0))


def test_f1_10_rejects_too_large_daily_available_minutes():
    """原因：每日学习时间过大通常不现实，应防止生成过载计划。"""
    with pytest.raises(ValueError, match="每日学习时间"):
        collect_study_goal(valid_form_data(daily_available_minutes=13 * 60))


def test_f1_11_rejects_zero_weekly_available_days():
    """原因：每周学习天数为 0 时无法排出有效学习计划。"""
    with pytest.raises(ValueError, match="每周学习天数"):
        collect_study_goal(valid_form_data(weekly_available_days=0))


def test_f1_12_rejects_weekly_available_days_greater_than_seven():
    """原因：每周学习天数必须符合自然周范围。"""
    with pytest.raises(ValueError, match="每周学习天数"):
        collect_study_goal(valid_form_data(weekly_available_days=8))


def test_f1_13_allows_empty_preferred_methods():
    """原因：学习偏好是辅助信息，用户不选时不应阻断主流程。"""
    goal = collect_study_goal(valid_form_data(preferred_methods=[]))

    assert goal.preferred_methods == []


def test_f1_14_allows_empty_weak_points():
    """原因：薄弱点是可选信息，用户不填写时应使用空列表。"""
    goal = collect_study_goal(valid_form_data(weak_points=[]))

    assert goal.weak_points == []


def test_f1_15_allows_empty_extra_requirements():
    """原因：额外要求是补充信息，不填写时应使用空字符串。"""
    goal = collect_study_goal(valid_form_data(extra_requirements=""))

    assert goal.extra_requirements == ""


def test_f1_16_converts_comma_separated_weak_points_to_list():
    """原因：页面可能用文本框收集薄弱点，需要能转换成结构化列表。"""
    goal = collect_study_goal(valid_form_data(weak_points="函数, 递归，动态规划"))

    assert goal.weak_points == ["函数", "递归", "动态规划"]


def test_f1_17_strips_text_fields_before_saving():
    """原因：去除前后空格可以减少后续 prompt 和数据库中的脏数据。"""
    goal = collect_study_goal(
        valid_form_data(
            subject="  Python 编程  ",
            target="  掌握基础语法  ",
            extra_requirements="  多做练习  ",
        )
    )

    assert goal.subject == "Python 编程"
    assert goal.target == "掌握基础语法"
    assert goal.extra_requirements == "多做练习"


def test_f1_18_preserves_chinese_input_without_garbled_text():
    """原因：产品主要面向中文用户，中文字段必须被完整保存。"""
    goal = collect_study_goal(
        valid_form_data(
            subject="机器学习",
            target="理解监督学习、无监督学习，并完成一个分类项目",
            weak_points=["线性代数", "概率论"],
        )
    )

    assert goal.subject == "机器学习"
    assert "监督学习" in goal.target
    assert goal.weak_points == ["线性代数", "概率论"]


def test_f1_19_submit_sends_study_goal_to_next_flow():
    """原因：F1 的验收关键是能把完整 StudyGoal 提交给后续流程。"""
    goal = collect_study_goal(valid_form_data())
    next_flow = FakeNextFlow()

    submit_study_goal(goal, next_flow)

    assert next_flow.received_goal == goal


def test_f1_20_repeated_submit_uses_latest_study_goal():
    """原因：用户修改后重新提交时，后续流程应接收最新目标。"""
    next_flow = FakeNextFlow()
    first_goal = collect_study_goal(valid_form_data(subject="Python 编程"))
    second_goal = collect_study_goal(valid_form_data(subject="机器学习"))

    submit_study_goal(first_goal, next_flow)
    submit_study_goal(second_goal, next_flow)

    assert next_flow.received_goal == second_goal
    assert next_flow.received_goal.subject == "机器学习"
