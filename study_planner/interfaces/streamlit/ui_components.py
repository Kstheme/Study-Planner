from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any, Iterable

import altair as alt
import pandas as pd
import streamlit as st


STATUS_LABELS = {
    "todo": "未开始",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "已跳过",
}

STATUS_COLORS = {
    "未开始": "#cbd5e1",
    "进行中": "#7dd3fc",
    "已完成": "#86efac",
    "已跳过": "#fcd34d",
}


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --sp-bg: #f6f8fb;
            --sp-panel: #ffffff;
            --sp-ink: #172033;
            --sp-muted: #64748b;
            --sp-line: #e2e8f0;
            --sp-blue: #2563eb;
            --sp-green: #16a34a;
            --sp-amber: #f59e0b;
            --sp-rose: #e11d48;
        }
        .stApp { background: var(--sp-bg); color: var(--sp-ink); }
        [data-testid="stSidebar"] { background: #111827; }
        [data-testid="stSidebar"] * { color: #f8fafc !important; }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--sp-line);
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }
        .sp-hero {
            border-radius: 8px;
            padding: 30px 32px;
            color: #ffffff;
            background:
                linear-gradient(120deg, rgba(17, 24, 39, 0.96), rgba(37, 99, 235, 0.86)),
                radial-gradient(circle at 85% 10%, rgba(22, 163, 74, 0.36), transparent 30%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
            margin: 6px 0 18px;
        }
        .sp-hero h1 {
            font-size: 42px;
            line-height: 1.12;
            margin: 8px 0 10px;
            color: #ffffff;
        }
        .sp-hero p {
            max-width: 760px;
            font-size: 17px;
            line-height: 1.7;
            color: #dbeafe;
            margin: 0;
        }
        .sp-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 5px 10px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.14);
            color: #f8fafc;
            font-size: 13px;
            font-weight: 600;
        }
        .sp-section {
            margin: 22px 0 10px;
            font-size: 18px;
            font-weight: 700;
            color: var(--sp-ink);
        }
        .sp-card {
            background: #ffffff;
            border: 1px solid var(--sp-line);
            border-radius: 8px;
            padding: 16px 18px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
            min-height: 118px;
        }
        .sp-card-title {
            font-size: 14px;
            font-weight: 700;
            color: var(--sp-ink);
            margin-bottom: 6px;
        }
        .sp-card-body {
            color: var(--sp-muted);
            font-size: 13px;
            line-height: 1.55;
        }
        .sp-step {
            border-left: 3px solid var(--sp-blue);
            padding: 8px 12px;
            background: #ffffff;
            border-radius: 0 8px 8px 0;
            min-height: 84px;
        }
        .sp-step strong { color: var(--sp-ink); }
        .sp-step span {
            display: block;
            margin-top: 5px;
            color: var(--sp-muted);
            font-size: 13px;
            line-height: 1.45;
        }
        .sp-note {
            background: #eef6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 12px 14px;
            color: #1e3a8a;
            margin: 10px 0;
        }
        .sp-pill {
            display: inline-block;
            padding: 4px 9px;
            margin: 0 6px 6px 0;
            border-radius: 999px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #334155;
            font-size: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, kicker: str = "Study Planner") -> None:
    st.markdown(
        f"""
        <section class="sp-hero">
            <span class="sp-kicker">{_escape(kicker)}</span>
            <h1>{_escape(title)}</h1>
            <p>{_escape(subtitle)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_title(title: str) -> None:
    st.markdown(f'<div class="sp-section">{_escape(title)}</div>', unsafe_allow_html=True)


def render_info_cards(cards: Iterable[tuple[str, str]]) -> None:
    cards = list(cards)
    if not cards:
        return
    columns = st.columns(min(4, len(cards)))
    for index, (title, body) in enumerate(cards):
        with columns[index % len(columns)]:
            st.markdown(
                f"""
                <div class="sp-card">
                    <div class="sp-card-title">{_escape(title)}</div>
                    <div class="sp-card-body">{_escape(body)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_workflow_steps(active_index: int = 0) -> None:
    steps = [
        ("1. 配置目标", "输入主题、时间和偏好，生成可执行学习计划。"),
        ("2. 管理计划", "查看今日、本周、阶段任务并保存进度。"),
        ("3. 资料问答", "上传笔记或资料，生成摘要、卡片和引用答案。"),
        ("4. 复盘调整", "基于真实完成情况生成复盘，并预览重排结果。"),
        ("5. 导出报告", "下载 Markdown 或专业 HTML 学习报告。"),
    ]
    columns = st.columns(len(steps))
    for index, (title, body) in enumerate(steps):
        border = "#16a34a" if index <= active_index else "#2563eb"
        with columns[index]:
            st.markdown(
                f"""
                <div class="sp-step" style="border-left-color:{border}">
                    <strong>{_escape(title)}</strong>
                    <span>{_escape(body)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_dashboard_charts(plan: Any, today: date | None = None) -> None:
    tasks = _tasks(plan)
    if not tasks:
        st.info("暂无任务数据，生成计划后会显示学习分析。")
        return

    df = pd.DataFrame(
        [
            {
                "日期": task.date,
                "任务": task.title,
                "时长": task.duration_minutes,
                "状态": STATUS_LABELS.get(task.status, task.status),
                "类型": task.task_type or "未分类",
                "知识点": "、".join(task.related_topics) if task.related_topics else "未标注",
            }
            for task in tasks
        ]
    )

    daily = df.groupby("日期", as_index=False)["时长"].sum().sort_values("日期")
    status = df.groupby("状态", as_index=False).size().rename(columns={"size": "任务数"})
    task_type = df.groupby(["类型", "状态"], as_index=False).size().rename(columns={"size": "任务数"})
    topics = Counter(topic for task in tasks for topic in (task.related_topics or ["未标注"]))
    topic_df = pd.DataFrame([{"知识点": key, "任务数": value} for key, value in topics.most_common(10)])

    left, right = st.columns([1.15, 0.85])
    with left:
        st.altair_chart(_daily_minutes_chart(daily), use_container_width=True)
    with right:
        st.altair_chart(_status_arc_chart(status), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.altair_chart(_task_type_chart(task_type), use_container_width=True)
    with right:
        st.altair_chart(_topic_chart(topic_df), use_container_width=True)


def render_review_charts(view: Any, report: Any | None = None) -> None:
    rows = list(getattr(view, "progress_rows", []) or [])
    if not rows:
        st.info("暂无复盘数据。")
        return

    progress_df = pd.DataFrame(
        [
            {
                "任务": row.title,
                "日期": row.date,
                "时长": row.duration_minutes,
                "状态": STATUS_LABELS.get(row.status, row.status),
                "类型": row.task_type or "未分类",
                "知识点": "、".join(row.related_topics) if row.related_topics else "未标注",
            }
            for row in rows
        ]
    )
    status = progress_df.groupby("状态", as_index=False).size().rename(columns={"size": "任务数"})
    daily = progress_df.groupby(["日期", "状态"], as_index=False)["时长"].sum()

    left, right = st.columns(2)
    with left:
        st.altair_chart(_status_arc_chart(status, title="本轮任务状态"), use_container_width=True)
    with right:
        st.altair_chart(_review_timeline_chart(daily), use_container_width=True)

    if report is not None:
        weak_points = list(getattr(report, "weak_points", []) or [])
        overdue = list(getattr(report, "overdue_tasks", []) or [])
        insight_df = pd.DataFrame(
            [
                {"类别": "薄弱点", "数量": len(weak_points)},
                {"类别": "延期任务", "数量": len(overdue)},
                {"类别": "已完成", "数量": getattr(report, "completed_task_count", 0)},
            ]
        )
        st.altair_chart(_review_summary_chart(insight_df), use_container_width=True)


def render_material_charts(materials: Iterable[Any], latest_answer: Any | None = None) -> None:
    materials = list(materials)
    if not materials:
        st.info("上传资料后会显示资料处理状态、切片规模和引用质量。")
        return

    material_df = pd.DataFrame(
        [
            {
                "资料": material.filename,
                "状态": material.status,
                "类型": material.file_type,
                "切片数": material.chunk_count,
            }
            for material in materials
        ]
    )
    status_df = material_df.groupby("状态", as_index=False).size().rename(columns={"size": "资料数"})
    citations = len(getattr(latest_answer, "citations", []) or [])
    quality_df = pd.DataFrame(
        [
            {"指标": "资料数", "数量": len(materials)},
            {"指标": "总切片", "数量": int(material_df["切片数"].sum())},
            {"指标": "最近引用", "数量": citations},
        ]
    )

    left, right = st.columns(2)
    with left:
        st.altair_chart(_material_status_chart(status_df), use_container_width=True)
    with right:
        st.altair_chart(_review_summary_chart(quality_df, x="指标", y="数量", title="资料问答质量"), use_container_width=True)


def render_export_format_cards() -> None:
    render_info_cards(
        [
            ("Markdown", "适合继续编辑、放进笔记系统，结构清晰。"),
            ("HTML", "适合直接打开、打印和分享，包含完整视觉报告。"),
            ("PDF", "已预留能力，后续接入打印或服务端渲染。"),
        ]
    )


def _daily_minutes_chart(daily: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(daily)
        .mark_area(line={"color": "#2563eb"}, color={"x1": 1, "y1": 1, "x2": 1, "y2": 0, "gradient": "linear", "stops": [{"offset": 0, "color": "#dbeafe"}, {"offset": 1, "color": "#2563eb"}]})
        .encode(
            x=alt.X("日期:T", title="日期"),
            y=alt.Y("时长:Q", title="计划分钟"),
            tooltip=["日期:T", "时长:Q"],
        )
        .properties(title="每日学习负载趋势", height=260)
    )


def _status_arc_chart(status: pd.DataFrame, title: str = "任务状态分布") -> alt.Chart:
    return (
        alt.Chart(status)
        .mark_arc(innerRadius=54, outerRadius=94, stroke="#ffffff", strokeWidth=2)
        .encode(
            theta=alt.Theta("任务数:Q"),
            color=alt.Color("状态:N", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))),
            tooltip=["状态:N", "任务数:Q"],
        )
        .properties(title=title, height=300)
        .configure_title(anchor="middle", dy=-8, fontSize=15, color="#334155")
    )


def _task_type_chart(task_type: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(task_type)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("类型:N", title="任务类型"),
            y=alt.Y("任务数:Q", title="任务数"),
            color=alt.Color("状态:N", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))),
            tooltip=["类型:N", "状态:N", "任务数:Q"],
        )
        .properties(title="任务类型与状态", height=260)
    )


def _topic_chart(topic_df: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(topic_df)
        .mark_bar(cornerRadiusEnd=4, color="#16a34a")
        .encode(
            x=alt.X("任务数:Q", title="任务数"),
            y=alt.Y("知识点:N", title="", sort="-x"),
            tooltip=["知识点:N", "任务数:Q"],
        )
        .properties(title="高频知识点", height=260)
    )


def _review_timeline_chart(daily: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(daily)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("日期:T", title="日期"),
            y=alt.Y("时长:Q", title="分钟"),
            color=alt.Color("状态:N", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))),
            tooltip=["日期:T", "状态:N", "时长:Q"],
        )
        .properties(title="复盘周期内学习负载", height=260)
    )


def _review_summary_chart(data: pd.DataFrame, x: str = "类别", y: str = "数量", title: str = "复盘风险概览") -> alt.Chart:
    return (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#2563eb")
        .encode(
            x=alt.X(f"{x}:N", title=""),
            y=alt.Y(f"{y}:Q", title="数量"),
            tooltip=[f"{x}:N", f"{y}:Q"],
        )
        .properties(title=title, height=220)
    )


def _material_status_chart(status_df: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(status_df)
        .mark_arc(innerRadius=50, outerRadius=95)
        .encode(
            theta=alt.Theta("资料数:Q"),
            color=alt.Color("状态:N", scale=alt.Scale(range=["#16a34a", "#f59e0b", "#e11d48", "#2563eb"])),
            tooltip=["状态:N", "资料数:Q"],
        )
        .properties(title="资料处理状态", height=230)
    )


def _tasks(plan: Any) -> list[Any]:
    return [
        task
        for phase in getattr(plan, "phases", []) or []
        for week in getattr(phase, "weekly_plans", []) or []
        for task in getattr(week, "tasks", []) or []
    ]


def _escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
