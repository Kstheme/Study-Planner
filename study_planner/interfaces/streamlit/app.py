from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.interfaces.streamlit.persistence_state import render_storage_status, restore_persistent_state
from study_planner.interfaces.streamlit.ui_components import (
    inject_global_styles,
    render_dashboard_charts,
    render_info_cards,
    render_page_header,
    render_section_title,
    render_workflow_steps,
)


st.set_page_config(page_title="学习规划助手", page_icon="📚", layout="wide")


def show_home() -> None:
    inject_global_styles()
    restore_persistent_state()

    plan = st.session_state.get("study_plan")
    report = st.session_state.get("last_review_report")
    storage_available = st.session_state.get("storage_available", True)

    render_page_header(
        "学习规划助手",
        "把目标拆成计划，把执行沉淀成复盘，再把结果导出成可以分享和继续迭代的学习报告。",
        "从目标到复盘的一站式学习工作台",
    )

    status_cols = st.columns(4)
    status_cols[0].metric("当前计划", "已生成" if plan else "未生成")
    status_cols[1].metric("复盘报告", "已有" if report else "暂无")
    status_cols[2].metric("持久化", "可用" if storage_available else "不可用")
    status_cols[3].metric("下一步", "看板复盘" if plan else "配置目标")

    render_storage_status()

    render_section_title("推荐路径")
    render_workflow_steps(active_index=1 if plan else 0)

    if plan:
        render_section_title("当前计划概览")
        summary = plan.goal
        cards = [
            ("学习主题", summary.subject),
            ("目标结果", summary.target),
            ("时间约束", f"{summary.deadline.isoformat()} 截止，每日 {summary.daily_available_minutes} 分钟"),
            ("学习偏好", "、".join(summary.preferred_methods) if summary.preferred_methods else "未设置"),
        ]
        render_info_cards(cards)

        render_section_title("计划分析")
        render_dashboard_charts(plan)

        st.markdown(
            '<div class="sp-note">建议先进入「计划看板」处理今日任务；完成一轮后进入「复盘与调整」生成复盘。</div>',
            unsafe_allow_html=True,
        )
    else:
        render_section_title("开始之前")
        render_info_cards(
            [
                ("目标要具体", "写清楚要掌握什么、产出什么，计划会更可执行。"),
                ("时间要真实", "每日分钟数和每周天数会直接影响任务密度。"),
                ("薄弱点要坦诚", "复盘和重排会优先照顾你明确标记的薄弱主题。"),
                ("资料可后补", "生成计划后再上传笔记、PDF 或课程资料也可以。"),
            ]
        )
        st.markdown(
            '<div class="sp-note">请从左侧进入「配置学习目标」，生成第一版学习计划。</div>',
            unsafe_allow_html=True,
        )


pages = [
    st.Page(show_home, title="学习首页", icon="📚", default=True),
    st.Page("pages/01_Goal_Setup.py", title="配置学习目标", icon="🎯"),
    st.Page("pages/02_Plan_Dashboard.py", title="计划看板", icon="📋"),
    st.Page("pages/03_Material_QA.py", title="资料问答", icon="📎"),
    st.Page("pages/04_Review_Replan.py", title="复盘与调整", icon="🧭"),
    st.Page("pages/05_Plan_Export.py", title="导出学习报告", icon="📤"),
]

selected_page = st.navigation(pages, expanded=True)
selected_page.run()
