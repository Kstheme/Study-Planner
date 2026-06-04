from datetime import datetime
from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.plan_export import (
    ExportPlanError,
    ExportRequest,
    ExportStudyPlanUseCase,
    build_download_payload,
    build_export_page_view,
)
from study_planner.interfaces.streamlit.persistence_state import render_storage_status, restore_persistent_state


st.set_page_config(page_title="学习计划导出", page_icon="📤", layout="wide")
st.title("学习计划导出")
restore_persistent_state()
render_storage_status()


def _render_workflow_hint() -> None:
    steps = st.columns(4)
    steps[0].caption("1. 配置目标")
    steps[1].caption("2. 查看和编辑计划")
    steps[2].caption("3. 复盘并确认调整")
    steps[3].caption("4. 导出当前计划")


def _render_summary(view) -> None:
    summary = view.summary
    cols = st.columns(4)
    cols[0].metric("学习主题", summary["subject"])
    cols[1].metric("截止日期", summary["deadline"].isoformat())
    cols[2].metric("阶段数", summary["phase_count"])
    cols[3].metric("任务数", summary["task_count"])


def _render_report_summary(report) -> None:
    if report is None:
        st.caption("当前没有复盘报告，导出文件会保留“暂无复盘报告”占位。")
        return

    cols = st.columns(4)
    cols[0].metric("复盘周期", f"{report.period_start.isoformat()} 至 {report.period_end.isoformat()}")
    cols[1].metric("完成率", f"{report.completion_rate * 100:.0f}%")
    cols[2].metric("已完成任务", report.completed_task_count)
    cols[3].metric("延期任务", len(report.overdue_tasks))


def _build_export(format_name: str):
    use_case = ExportStudyPlanUseCase.from_session(st.session_state)
    return use_case.execute(ExportRequest(format=format_name, exported_at=datetime.now()))


_render_workflow_hint()

plan = st.session_state.get("study_plan")
report = st.session_state.get("last_review_report")
view = build_export_page_view(plan)

if not view.can_export:
    st.info(view.empty_message)
    st.stop()

if st.session_state.get("pending_adjusted_plan") is not None:
    st.warning("检测到尚未保存的调整预览。导出默认使用当前已确认计划；如需导出调整结果，请先在复盘与动态调整页面保存。")

st.subheader("导出对象")
_render_summary(view)

st.subheader("复盘报告")
_render_report_summary(report)

st.subheader("下载文件")
try:
    markdown_result = _build_export("markdown")
    html_result = _build_export("html")
    markdown_payload = build_download_payload(markdown_result)
    html_payload = build_download_payload(html_result)
except (ExportPlanError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

download_cols = st.columns(3)
with download_cols[0]:
    st.download_button(
        label="下载 Markdown",
        data=markdown_payload["data"],
        file_name=markdown_payload["file_name"],
        mime=markdown_payload["mime"],
        use_container_width=True,
    )
with download_cols[1]:
    st.download_button(
        label="下载 HTML",
        data=html_payload["data"],
        file_name=html_payload["file_name"],
        mime=html_payload["mime"],
        use_container_width=True,
    )
with download_cols[2]:
    st.button("PDF 后续支持", disabled=True, use_container_width=True)

with st.expander("预览 Markdown 内容", expanded=False):
    st.code(markdown_result.content, language="markdown")
