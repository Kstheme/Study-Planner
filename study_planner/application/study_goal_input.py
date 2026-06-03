from datetime import date
import re
from typing import Any

from study_planner.domain.models import StudyGoal


VALID_CURRENT_LEVELS = {"零基础", "入门", "初级", "中级", "高级"}


def collect_study_goal(form_data: dict[str, Any]) -> StudyGoal:
    subject = _clean_text(form_data.get("subject", ""))
    target = _clean_text(form_data.get("target", ""))
    deadline = form_data.get("deadline")
    current_level = _clean_text(form_data.get("current_level", ""))
    daily_available_minutes = form_data.get("daily_available_minutes")
    weekly_available_days = form_data.get("weekly_available_days")
    preferred_methods = _clean_list(form_data.get("preferred_methods", []))
    weak_points = _clean_list(form_data.get("weak_points", []))
    extra_requirements = _clean_text(form_data.get("extra_requirements", ""))

    if not subject:
        raise ValueError("学习主题不能为空")
    if not target:
        raise ValueError("学习目标不能为空")
    if not isinstance(deadline, date) or deadline < date.today():
        raise ValueError("截止日期无效")
    if not current_level or current_level not in VALID_CURRENT_LEVELS:
        raise ValueError("当前水平无效")
    if not isinstance(daily_available_minutes, int) or not 1 <= daily_available_minutes <= 12 * 60:
        raise ValueError("每日学习时间必须在合理范围内")
    if not isinstance(weekly_available_days, int) or not 1 <= weekly_available_days <= 7:
        raise ValueError("每周学习天数必须在 1-7 天之间")

    return StudyGoal(
        subject=subject,
        target=target,
        deadline=deadline,
        current_level=current_level,
        daily_available_minutes=daily_available_minutes,
        weekly_available_days=weekly_available_days,
        preferred_methods=preferred_methods,
        weak_points=weak_points,
        extra_requirements=extra_requirements,
    )


def submit_study_goal(goal: StudyGoal, next_flow: Any) -> None:
    next_flow.receive_study_goal(goal)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = re.split(r"[,，]", value)
    else:
        items = value
    return [_clean_text(item) for item in items if _clean_text(item)]
