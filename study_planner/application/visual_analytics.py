from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ChartSpec:
    name: str
    title: str
    data: Any = field(default_factory=dict)


def _tasks(plan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


def build_dashboard_charts(plan, today: date | None = None) -> list[ChartSpec]:
    tasks = _tasks(plan)
    status_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    daily_minutes: dict[str, int] = {}
    weekly_load: dict[int, int] = {}
    for phase in plan.phases:
        for week in phase.weekly_plans:
            for task in week.tasks:
                status_counts[task.status] = status_counts.get(task.status, 0) + 1
                daily_minutes[task.date.isoformat()] = daily_minutes.get(task.date.isoformat(), 0) + task.duration_minutes
                weekly_load[week.week_index] = weekly_load.get(week.week_index, 0) + task.duration_minutes
                for topic in task.related_topics:
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1
    done = sum(1 for task in tasks if task.status == "done")
    return [
        ChartSpec("daily_minutes", "每日学习分钟趋势", daily_minutes),
        ChartSpec("weekly_load", "每周学习负载", weekly_load),
        ChartSpec("task_status", "任务状态分布", status_counts),
        ChartSpec("topic_distribution", "主题任务占比", topic_counts),
        ChartSpec("completion_trend", "完成率趋势", {"completion_rate": done / len(tasks) if tasks else 0}),
    ]


def build_review_charts(plan, report, today: date | None = None) -> list[ChartSpec]:
    return [
        ChartSpec(
            "completion_distribution",
            "完成分布",
            {"completed": report.completed_task_count, "remaining": report.total_task_count - report.completed_task_count},
        ),
        ChartSpec("weak_points", "薄弱点排行", {point: 1 for point in report.weak_points}),
        ChartSpec("overdue_timeline", "延期任务时间轴", list(report.overdue_tasks)),
        ChartSpec("before_after_dates", "调整前后日期对比", {"task_count": len(_tasks(plan))}),
    ]


def build_material_charts(materials, latest_answer=None) -> list[ChartSpec]:
    return [
        ChartSpec("material_status", "资料状态", {material.status: 1 for material in materials}),
        ChartSpec("citation_quality", "引用质量", {"citations": len(getattr(latest_answer, "citations", []) or [])}),
    ]
