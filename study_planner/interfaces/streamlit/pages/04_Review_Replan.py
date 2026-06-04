from datetime import date
from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.review_replan import (
    GenerateReviewReportUseCase,
    ReviewReplanError,
    SimpleReplanPlanner,
    build_f5_llm_from_env,
    build_replan_request,
    build_review_page_view,
    cancel_adjustment_preview,
    generate_adjustment_preview,
    save_adjusted_plan,
    validate_adjusted_plan,
)
from study_planner.application.persistence import StorageError
from study_planner.interfaces.streamlit.persistence_state import render_storage_status, restore_persistent_state


st.set_page_config(page_title="复盘与动态调整", page_icon="🧭", layout="wide")
st.title("复盘与动态调整")
storage_service = restore_persistent_state()
render_storage_status()


class SessionPlanRepository:
    def __init__(self, service):
        self.service = service
        self.pending_report = None

    def save_review_report(self, report):
        st.session_state["last_review_report"] = report
        self.pending_report = report

    def save_study_plan(self, plan):
        st.session_state["study_plan"] = plan
        if self.pending_report is not None:
            plan_id = self.service.save_adjusted_plan(plan, self.pending_report)
        else:
            plan_id = self.service.save_study_plan(plan, goal_id=st.session_state.get("selected_goal_id"))
        st.session_state["selected_plan_id"] = plan_id


STATUS_LABELS = {
    "todo": "未开始",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "已跳过",
}


def _row_to_dict(row):
    return {
        "任务ID": row.task_id,
        "任务": row.title,
        "日期": row.date.isoformat(),
        "时长(分钟)": row.duration_minutes,
        "类型": row.task_type,
        "状态": STATUS_LABELS.get(row.status, row.status),
        "知识点": ", ".join(row.related_topics),
    }


def _optional_int_text(value):
    return str(value) if value is not None else ""


def _diff_to_dict(row):
    return {
        "任务ID": row.task_id,
        "任务": row.title,
        "原日期": row.before_date.isoformat() if row.before_date else "",
        "新日期": row.after_date.isoformat() if row.after_date else "",
        "原时长": _optional_int_text(row.before_duration_minutes),
        "新时长": _optional_int_text(row.after_duration_minutes),
    }


def _report_to_metrics(report):
    cols = st.columns(4)
    cols[0].metric("完成率", f"{report.completion_rate * 100:.0f}%")
    cols[1].metric("已完成任务", report.completed_task_count)
    cols[2].metric("总任务数", report.total_task_count)
    cols[3].metric("延期任务", len(report.overdue_tasks))


plan = st.session_state.get("study_plan")
pending_plan = st.session_state.get("pending_adjusted_plan")
view = build_review_page_view(plan, pending_adjusted_plan=pending_plan)

if view.is_empty:
    st.info(view.empty_message)
    st.stop()

st.subheader("完成情况")
st.dataframe([_row_to_dict(row) for row in view.progress_rows], use_container_width=True)

review_text = st.text_area("本周复盘", value=st.session_state.get("review_text", ""), height=160)
st.session_state["review_text"] = review_text

action_col1, action_col2, action_col3 = st.columns(3)

with action_col1:
    generate_clicked = st.button("生成复盘", disabled=not view.can_generate_review)
with action_col2:
    replan_clicked = st.button(view.auto_replan_button_label, disabled=not view.can_auto_replan)
with action_col3:
    cancel_clicked = st.button("取消调整", disabled=not view.has_adjustment_preview)

if generate_clicked:
    try:
        llm = build_f5_llm_from_env(PROJECT_ROOT / ".env")
        report = GenerateReviewReportUseCase(llm=llm).execute(
            plan,
            current_date=date.today(),
            user_review_text=review_text,
        )
        st.session_state["last_review_report"] = report
        plan_id = st.session_state.get("selected_plan_id")
        if plan_id:
            storage_service.save_review_report(report, plan_id=plan_id)
        st.success("复盘已生成")
        st.rerun()
    except (ReviewReplanError, ValueError, StorageError) as exc:
        st.error(str(exc))

if replan_clicked:
    try:
        llm = build_f5_llm_from_env(PROJECT_ROOT / ".env")
        report = GenerateReviewReportUseCase(llm=llm).execute(
            plan,
            current_date=date.today(),
            user_review_text=review_text,
        )
        request = build_replan_request(plan, report, current_date=date.today())
        preview = generate_adjustment_preview(
            request,
            planner=SimpleReplanPlanner(current_date=date.today()),
            session_state=st.session_state,
        )
        validation = validate_adjusted_plan(preview.adjusted_plan, current_date=date.today())
        st.session_state["last_review_report"] = report
        st.session_state["pending_review_report"] = report
        st.session_state["adjustment_warnings"] = validation.warnings
        st.success("调整预览已生成")
        st.rerun()
    except (ReviewReplanError, ValueError, StorageError) as exc:
        st.error(str(exc))

if cancel_clicked:
    cancel_adjustment_preview(st.session_state)
    st.session_state.pop("adjustment_warnings", None)
    st.success("已取消调整")
    st.rerun()

report = st.session_state.get("last_review_report")
if report:
    st.subheader("复盘报告")
    _report_to_metrics(report)
    st.write(report.summary)

    report_col1, report_col2, report_col3 = st.columns(3)
    with report_col1:
        st.markdown("**延期任务**")
        if report.overdue_tasks:
            for task_id in report.overdue_tasks:
                st.write(f"- {task_id}")
        else:
            st.caption("暂无延期任务")
    with report_col2:
        st.markdown("**薄弱点**")
        if report.weak_points:
            for point in report.weak_points:
                st.write(f"- {point}")
        else:
            st.caption("暂无薄弱点")
    with report_col3:
        st.markdown("**建议**")
        for suggestion in report.suggestions:
            st.write(f"- {suggestion}")

if pending_plan:
    preview_view = build_review_page_view(plan, pending_adjusted_plan=pending_plan)
    st.subheader("调整前后对比")

    before_col, after_col = st.columns(2)
    with before_col:
        st.markdown("**调整前**")
        st.dataframe([_row_to_dict(row) for row in preview_view.before_rows], use_container_width=True)
    with after_col:
        st.markdown("**调整后**")
        st.dataframe([_row_to_dict(row) for row in preview_view.after_rows], use_container_width=True)

    st.markdown("**变化明细**")
    if preview_view.diff_rows:
        st.dataframe([_diff_to_dict(row) for row in preview_view.diff_rows], use_container_width=True)
    else:
        st.info("暂无任务变化")

    warnings = st.session_state.get("adjustment_warnings", [])
    if warnings:
        for warning in warnings:
            st.warning(warning)

    if st.button(preview_view.save_adjustment_button_label, disabled=bool(warnings)):
        try:
            save_adjusted_plan(
                st.session_state,
                repository=SessionPlanRepository(storage_service),
                current_date=date.today(),
            )
            st.session_state.pop("adjustment_warnings", None)
            st.success("调整已保存，学习计划看板会显示新计划")
            st.rerun()
        except ReviewReplanError as exc:
            st.error(str(exc))
