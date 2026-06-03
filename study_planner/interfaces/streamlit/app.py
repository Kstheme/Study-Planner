from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="学习规划助手",
    page_icon="📚",
    layout="wide"
)

st.title("📚 学习规划助手")
st.markdown("""
欢迎使用学习规划助手！这是一个智能学习计划生成工具。

### 功能说明
- **学习目标配置**：设置您的学习目标、时间安排和学习偏好
- **智能规划**：根据您的目标自动生成个性化学习计划
- **进度跟踪**：实时监控学习进度

### 开始使用
请在左侧导航栏选择相应功能开始使用。
""")

st.info("💡 提示：请点击左侧边栏的'01 Goal Setup'开始设置您的学习计划")
