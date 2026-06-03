from pathlib import Path
import sys

import streamlit as st
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.generate_study_plan import GenerateStudyPlanUseCase, StudyPlanGenerationError
from study_planner.application.study_goal_input import collect_study_goal
from study_planner.infrastructure.llm.real_study_plan_llm import RealStudyPlanLLM

st.set_page_config(
    page_title="学习目标配置",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 学习目标配置")
st.markdown("请填写以下信息，我们将为您生成个性化的学习计划")

with st.form("learning_goal_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("基本信息")
        
        learning_topic = st.text_input(
            "学习主题",
            placeholder="例如：Python编程、机器学习、英语等",
            help="请输入您想要学习的主题或技能"
        )
        
        learning_goal = st.text_area(
            "学习目标",
            placeholder="例如：掌握Python基础语法，能够独立开发小型项目",
            help="请详细描述您的学习目标"
        )
        
        deadline = st.date_input(
            "截止日期",
            min_value=date.today(),
            help="请选择您希望完成学习目标的日期"
        )
        
        current_level = st.selectbox(
            "当前水平",
            options=["零基础", "入门", "初级", "中级", "高级"],
            help="请选择您当前的学习水平"
        )
    
    with col2:
        st.subheader("时间安排")
        
        daily_study_time = st.number_input(
            "每日学习时间（小时）",
            min_value=0.5,
            max_value=12.0,
            value=2.0,
            step=0.5,
            help="您每天可以投入的学习时间"
        )
        
        weekly_study_days = st.slider(
            "每周学习天数",
            min_value=1,
            max_value=7,
            value=5,
            help="您每周计划学习几天"
        )
        
        learning_preference = st.multiselect(
            "学习偏好",
            options=["视频教程", "文字教程", "实践项目", "理论学习", "互动练习", "阅读书籍"],
            default=["视频教程", "实践项目"],
            help="请选择您偏好的学习方式（可多选）"
        )
    
    st.subheader("其他信息")
    
    weak_points = st.text_area(
        "薄弱点",
        placeholder="例如：数学基础较弱、缺乏实践经验、记忆力不好等",
        help="请描述您在学习过程中遇到的困难或薄弱环节"
    )
    
    additional_requirements = st.text_area(
        "额外要求",
        placeholder="例如：希望侧重实战、需要备考证书、希望快速入门等",
        help="请输入其他特殊要求或期望"
    )
    
    st.markdown("---")
    
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

        st.markdown("### 📋 配置摘要")
        summary_col1, summary_col2 = st.columns(2)
        
        with summary_col1:
            st.markdown(f"**学习主题**：{study_goal.subject}")
            st.markdown(f"**学习目标**：{study_goal.target}")
            st.markdown(f"**截止日期**：{study_goal.deadline.strftime('%Y年%m月%d日')}")
            st.markdown(f"**当前水平**：{study_goal.current_level}")
        
        with summary_col2:
            st.markdown(f"**每日学习时间**：{study_goal.daily_available_minutes} 分钟")
            st.markdown(f"**每周学习天数**：{study_goal.weekly_available_days} 天")
            st.markdown(f"**学习偏好**：{'、'.join(study_goal.preferred_methods) if study_goal.preferred_methods else '未选择'}")
            st.markdown(f"**薄弱点**：{'、'.join(study_goal.weak_points) if study_goal.weak_points else '无'}")
            st.markdown(f"**额外要求**：{study_goal.extra_requirements if study_goal.extra_requirements else '无'}")

        with st.spinner("正在生成个性化学习计划..."):
            llm = RealStudyPlanLLM.from_env(PROJECT_ROOT / ".env")
            study_plan = GenerateStudyPlanUseCase(llm=llm).execute(study_goal)
            st.session_state["study_plan"] = study_plan

        st.success("✅ 学习计划生成成功！")
        st.info("请进入左侧导航的“02 Plan Dashboard”查看和编辑学习计划。")

    except (ValueError, StudyPlanGenerationError) as exc:
        st.error(f"❌ {exc}")
    except Exception as exc:
        st.error(f"❌ 学习计划生成失败：{exc}")
