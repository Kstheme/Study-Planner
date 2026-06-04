from datetime import date
from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.agent_workflow import build_plan_workflow_use_case, workflow_trace_rows
from study_planner.application.generate_study_plan import StudyPlanGenerationError
from study_planner.application.persistence import StorageError
from study_planner.application.study_goal_input import collect_study_goal
from study_planner.interfaces.streamlit.persistence_state import (
    render_storage_status,
    restore_persistent_state,
    save_goal_and_plan_to_storage,
)
from study_planner.interfaces.streamlit.ui_components import (
    inject_global_styles,
    render_info_cards,
    render_page_header,
    render_workflow_steps,
)


st.set_page_config(page_title="学习目标配置", page_icon="🎯", layout="wide")
inject_global_styles()
render_page_header(
    "学习目标配置",
    "把主题、目标、时间和偏好整理成清晰输入，生成后续看板、资料问答、复盘和导出的基础计划。",
    "F1 · Goal Setup",
)
storage_service = restore_persistent_state()
render_storage_status()
render_workflow_steps(active_index=0)
render_info_cards(
    [
        ("输入质量决定计划质量", "目标越具体，阶段、周计划和每日任务越容易落地。"),
        ("时间预算影响任务密度", "每日学习时长和每周学习天数会被用于排程和复盘。"),
        ("薄弱点会进入后续调整", "复盘和自动重排会优先关注你标记的薄弱主题。"),
    ]
)

with st.form("learning_goal_form"):
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("基本信息")
        learning_topic = st.text_input(
            "学习主题",
            placeholder="例如：Python 编程、机器学习、英语四级",
            help="输入你想学习的主题或技能。",
        )
        learning_goal = st.text_area(
            "学习目标",
            placeholder="例如：掌握 Python 基础语法，并独立完成一个小项目。",
            help="尽量写清楚希望达到的结果。",
        )
        deadline = st.date_input("截止日期", min_value=date.today())
        current_level = st.selectbox("当前水平", options=["零基础", "入门", "初级", "中级", "高级"])

    with col2:
        st.subheader("时间安排")
        daily_study_time = st.number_input(
            "每日学习时间（小时）",
            min_value=0.5,
            max_value=12.0,
            value=2.0,
            step=0.5,
        )
        weekly_study_days = st.slider("每周学习天数", min_value=1, max_value=7, value=5)
        learning_preference = st.multiselect(
            "学习偏好",
            options=["视频教程", "文字教程", "实践项目", "理论学习", "互动练习", "阅读书籍"],
            default=["视频教程", "实践项目"],
        )

    st.subheader("补充信息")
    weak_points = st.text_area(
        "薄弱点",
        placeholder="例如：数学基础较弱、缺少实践经验、递归理解不稳定",
    )
    additional_requirements = st.text_area(
        "额外要求",
        placeholder="例如：希望侧重实战、需要备考证书、希望快速入门",
    )

    submitted = st.form_submit_button("生成学习计划", type="primary", use_container_width=True)

if submitted:
    form_data = {
        "subject": learning_topic,
        "target": learning_goal,
        "deadline": deadline,
        "current_level": current_level,
        "daily_available_minutes": int(daily_study_time * 60),
        "weekly_available_days": int(weekly_study_days),
        "preferred_methods": learning_preference,
        "weak_points": weak_points,
        "extra_requirements": additional_requirements,
    }

    try:
        study_goal = collect_study_goal(form_data)
        st.session_state["study_goal"] = study_goal

        st.markdown("### 配置摘要")
        summary_col1, summary_col2 = st.columns(2)
        with summary_col1:
            st.markdown(f"**学习主题**：{study_goal.subject}")
            st.markdown(f"**学习目标**：{study_goal.target}")
            st.markdown(f"**截止日期**：{study_goal.deadline.isoformat()}")
            st.markdown(f"**当前水平**：{study_goal.current_level}")
        with summary_col2:
            st.markdown(f"**每日学习时间**：{study_goal.daily_available_minutes} 分钟")
            st.markdown(f"**每周学习天数**：{study_goal.weekly_available_days} 天")
            st.markdown(
                f"**学习偏好**：{'、'.join(study_goal.preferred_methods) if study_goal.preferred_methods else '未选择'}"
            )
            st.markdown(f"**薄弱点**：{'、'.join(study_goal.weak_points) if study_goal.weak_points else '无'}")

        with st.spinner("正在生成个性化学习计划..."):
            use_case = build_plan_workflow_use_case(PROJECT_ROOT / ".env", debug=True)
            study_plan = use_case.execute(study_goal)
            st.session_state["study_plan"] = study_plan
            st.session_state["last_workflow_trace"] = workflow_trace_rows(use_case.last_workflow_state.trace)

        try:
            plan_id = save_goal_and_plan_to_storage(storage_service, study_goal, study_plan)
            st.success(f"学习计划生成并保存成功，计划 ID：{plan_id}")
        except StorageError as exc:
            st.warning(f"学习计划已生成，但持久化保存失败：{exc}")

        st.info("下一步进入 02 Plan Dashboard 查看和编辑学习计划。")

        if st.session_state.get("last_workflow_trace"):
            with st.expander("Agent 工作流执行链路", expanded=False):
                st.dataframe(st.session_state["last_workflow_trace"], use_container_width=True, hide_index=True)

    except (ValueError, StudyPlanGenerationError) as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"学习计划生成失败：{exc}")
