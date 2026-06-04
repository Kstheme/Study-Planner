from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.interfaces.streamlit.persistence_state import render_storage_status, restore_persistent_state

st.set_page_config(
    page_title="学习规划助手",
    page_icon="📚",
    layout="wide",
)

st.title("📚 学习规划助手")
restore_persistent_state()
st.markdown(
    """
把学习目标拆成可执行计划，并在执行过程中持续追踪、复盘和导出。

### 使用流程

1. **学习目标配置**：填写学习主题、目标、截止日期和时间约束。
2. **学习计划看板**：查看阶段、周、日任务，编辑日期、时长、状态和备注。
3. **资料问答**：上传资料，基于资料提问、摘要和生成复习卡片。
4. **复盘与动态调整**：根据完成情况生成复盘报告，并确认是否保存调整后的计划。
5. **学习计划导出**：下载当前已确认计划的 Markdown 或 HTML 文件，可附带最近复盘报告。
6. **持久化恢复**：页面刷新后自动恢复最近学习计划、任务状态和复盘报告。

请从左侧页面导航开始。建议先进入 **01 Goal Setup** 配置目标并生成计划。
"""
)

render_storage_status()

plan = st.session_state.get("study_plan")
report = st.session_state.get("last_review_report")

status_cols = st.columns(3)
status_cols[0].metric("当前计划", "已生成" if plan else "未生成")
status_cols[1].metric("复盘报告", "已有" if report else "暂无")
status_cols[2].metric("持久化", "可用" if st.session_state.get("storage_available", True) else "不可用")

if plan:
    st.success("当前已有学习计划，可以进入学习计划看板编辑，或进入学习计划导出页面下载文件。")
else:
    st.info("还没有学习计划。请先在左侧打开 01 Goal Setup，完成目标配置并生成计划。")
