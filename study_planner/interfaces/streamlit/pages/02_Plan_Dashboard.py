from datetime import date, timedelta
from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.persistence import InvalidTaskUpdateError, StorageError
from study_planner.application.plan_dashboard import (
    DashboardValidationError,
    build_dashboard_view,
    get_current_week_tasks,
    update_task,
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
from study_planner.interfaces.streamlit.persistence_state import (
    ensure_stable_task_ids,
    render_storage_status,
    restore_persistent_state,
    save_plan_to_storage,
)


STATUS_LABELS = {
    "todo": "未开始",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "已跳过",
}


st.set_page_config(page_title="学习计划看板", page_icon="📋", layout="wide")
st.title("📋 学习计划看板")
storage_service = restore_persistent_state()
render_storage_status()


def _ensure_task_ids(plan: StudyPlan) -> StudyPlan:
    return ensure_stable_task_ids(plan)


def _has_missing_task_ids(plan: StudyPlan) -> bool:
    return any(
        not task.id
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    )


def _save_plan(plan: StudyPlan) -> None:
    plan = _ensure_task_ids(plan)
    try:
        plan_id = save_plan_to_storage(
            storage_service,
            plan,
            goal_id=st.session_state.get("selected_goal_id"),
        )
        st.session_state["selected_plan_id"] = plan_id
    except StorageError as exc:
        st.session_state["study_plan"] = plan
        st.warning(f"计划已更新到当前页面，但持久化保存失败：{exc}")


def _load_demo_plan() -> StudyPlan:
    today = date.today()
    goal = StudyGoal(
        subject="Python 编程",
        target="掌握 Python 基础语法，并能独立完成一个小型项目",
        deadline=today + timedelta(days=30),
        current_level="零基础",
        daily_available_minutes=120,
        weekly_available_days=5,
        preferred_methods=["视频教程", "实践项目"],
        weak_points=["缺少编程经验"],
        extra_requirements="多安排练习任务",
    )
    tasks = [
        StudyTask(
            id="task-1",
            title="学习变量与数据类型",
            date=today,
            duration_minutes=60,
            task_type="study",
            related_topics=["变量", "数据类型"],
            learning_method="视频教程 + 练习",
            expected_output="完成 10 道变量和数据类型练习",
            review_required=True,
            status="todo",
        ),
        StudyTask(
            id="task-2",
            title="完成基础语法复习",
            date=today,
            duration_minutes=30,
            task_type="review",
            related_topics=["变量", "数据类型"],
            learning_method="错题回顾",
            expected_output="整理 3 条易错点",
            review_required=True,
            status="todo",
        ),
    ]
    return StudyPlan(
        goal=goal,
        overall_route="先学习 Python 基础语法，再完成练习，最后实现一个小型项目。",
        phases=[
            StudyPhase(
                phase_index=1,
                title="基础入门阶段",
                objective="掌握 Python 基础语法和基本编程思维。",
                start_date=today,
                end_date=today + timedelta(days=13),
                milestone="能完成变量、条件、循环和函数相关练习。",
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
        ],
        methods=["视频教程", "实践项目", "每日复习"],
        time_budget=TimeBudget(
            total_days=31,
            total_weeks=5,
            total_available_minutes=3000,
            planned_minutes=90,
            daily_available_minutes=120,
            weekly_available_days=5,
        ),
        risks=["零基础学习容易卡在语法细节，需要保持每日练习。"],
        review_schedule=ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="周日",
            review_strategy="每天复习当天知识点，每周整理一次薄弱点。",
        ),
        suggestions="保持小步快跑，每天完成一个可检查的学习产出。",
    )


def _format_task(task: StudyTask) -> dict:
    return {
        "日期": task.date.isoformat(),
        "任务": task.title,
        "时长(分钟)": task.duration_minutes,
        "类型": task.task_type,
        "状态": STATUS_LABELS.get(task.status, task.status),
        "预期产出": task.expected_output,
    }


def _render_task_editor(plan: StudyPlan, task: StudyTask) -> None:
    with st.expander(f"{task.title} | {STATUS_LABELS.get(task.status, task.status)}", expanded=False):
        st.caption(f"{task.date.isoformat()} | {task.duration_minutes} 分钟 | {task.task_type}")
        st.write(f"知识点：{', '.join(task.related_topics) if task.related_topics else '无'}")
        st.write(f"学习方法：{task.learning_method or '未设置'}")
        st.write(f"预期产出：{task.expected_output or '未设置'}")

        status_options = list(STATUS_LABELS.keys())
        current_status_index = status_options.index(task.status) if task.status in status_options else 0
        new_status = st.selectbox(
            "任务状态",
            options=status_options,
            format_func=lambda value: STATUS_LABELS[value],
            index=current_status_index,
            key=f"status_{task.id}",
        )
        new_date = st.date_input("任务日期", value=task.date, key=f"date_{task.id}")
        new_duration = st.number_input(
            "任务时长（分钟）",
            min_value=1,
            max_value=720,
            value=task.duration_minutes,
            step=5,
            key=f"duration_{task.id}",
        )
        new_notes = st.text_area("任务备注", value=task.notes, key=f"notes_{task.id}")

        if st.button("保存任务修改", key=f"save_{task.id}"):
            try:
                plan_id = st.session_state.get("selected_plan_id")
                if plan_id:
                    updated = storage_service.update_task(
                        plan_id,
                        task.id,
                        status=new_status,
                        new_date=new_date,
                        duration_minutes=int(new_duration),
                        notes=new_notes,
                    )
                    st.session_state["study_plan"] = updated
                else:
                    updated = update_task(
                        plan=plan,
                        task_id=task.id,
                        status=new_status,
                        new_date=new_date,
                        duration_minutes=int(new_duration),
                        notes=new_notes,
                        today=date.today(),
                    )
                    _save_plan(updated)
                st.success("任务已保存，刷新页面后仍会保留。")
                st.rerun()
            except (DashboardValidationError, InvalidTaskUpdateError, StorageError) as exc:
                st.error(f"保存失败：{exc}")


if "study_plan" in st.session_state and st.session_state["study_plan"] is not None:
    restored_plan = st.session_state["study_plan"]
    if _has_missing_task_ids(restored_plan):
        _save_plan(restored_plan)
    else:
        st.session_state["study_plan"] = _ensure_task_ids(restored_plan)

view = build_dashboard_view(st.session_state.get("study_plan"), today=date.today())

if view.is_empty:
    st.info(view.empty_message)
    if st.button("加载示例学习计划"):
        _save_plan(_load_demo_plan())
        st.rerun()
    st.stop()
    if "study_plan" not in st.session_state:
        st.session_state["study_plan"] = _load_demo_plan()
        view = build_dashboard_view(st.session_state["study_plan"], today=date.today())

plan = st.session_state.get("study_plan")

summary = view.goal_summary
st.subheader("目标摘要")
metric_cols = st.columns(4)
metric_cols[0].metric("学习主题", summary["subject"])
metric_cols[1].metric("当前水平", summary["current_level"])
metric_cols[2].metric("每日学习", f"{summary['daily_available_minutes']} 分钟")
metric_cols[3].metric("每周学习", f"{summary['weekly_available_days']} 天")
st.write(f"目标：{summary['target']}")
st.write(f"截止日期：{summary['deadline'].isoformat()}")

st.subheader("总体路线")
st.write(view.overall_route)

st.subheader("进度")
progress_cols = st.columns(3)
progress_cols[0].metric("总任务", view.progress.total_tasks)
progress_cols[1].metric("已完成", view.progress.done_tasks)
progress_cols[2].metric("完成率", f"{view.progress.completion_rate}%")
st.progress(view.progress.completion_rate / 100)

chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    st.caption("每日计划分钟数")
    if view.daily_minutes_chart_data:
        st.bar_chart({day.isoformat(): minutes for day, minutes in view.daily_minutes_chart_data.items()})
    else:
        st.info("暂无每日分钟数数据")
with chart_col2:
    st.caption("每周计划分钟数")
    if view.weekly_minutes_chart_data:
        st.bar_chart({f"第{week}周": minutes for week, minutes in view.weekly_minutes_chart_data.items()})
    else:
        st.info("暂无每周分钟数数据")

st.subheader("今日任务")
if view.today_tasks:
    st.table([_format_task(task) for task in view.today_tasks])
else:
    st.info(view.today_empty_message)

st.subheader("本周任务")
week_tasks = get_current_week_tasks(plan, today=date.today())
if week_tasks:
    st.table([_format_task(task) for task in week_tasks])
else:
    st.info("本周没有学习任务。")

st.subheader("阶段计划")
tabs = st.tabs([f"阶段 {phase.phase_index}：{phase.title}" for phase in view.phase_tabs])
for tab, phase in zip(tabs, view.phase_tabs):
    with tab:
        st.markdown(f"**阶段目标**：{phase.objective}")
        st.markdown(f"**阶段时间**：{phase.start_date.isoformat()} 至 {phase.end_date.isoformat()}")
        st.markdown(f"**里程碑**：{phase.milestone}")
        for weekly_plan in phase.weekly_plans:
            st.markdown("---")
            st.markdown(f"#### 第 {weekly_plan.week_index} 周")
            st.markdown(f"**周目标**：{weekly_plan.objective}")
            st.markdown(f"**周时间**：{weekly_plan.start_date.isoformat()} 至 {weekly_plan.end_date.isoformat()}")
            st.markdown(f"**复习重点**：{weekly_plan.review_focus}")
            for task in weekly_plan.tasks:
                _render_task_editor(plan, task)

info_col1, info_col2, info_col3 = st.columns(3)
with info_col1:
    st.subheader("学习方法")
    for method in view.methods:
        st.write(f"- {method}")
with info_col2:
    st.subheader("风险提示")
    for risk in view.risks:
        st.warning(risk)
with info_col3:
    st.subheader("复习安排")
    if view.review_schedule:
        st.write(f"每日复习：{view.review_schedule.daily_review_minutes} 分钟")
        st.write(f"每周复习日：{view.review_schedule.weekly_review_day}")
        st.write(view.review_schedule.review_strategy)
