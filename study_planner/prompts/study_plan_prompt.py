from datetime import date

from study_planner.domain.models import StudyGoal


def build_study_plan_prompt(goal: StudyGoal) -> str:
    today = date.today().isoformat()
    return f"""
你是学习规划专家。请根据用户信息生成智能学习计划。

用户信息：
- 今天日期：{today}
- 学习主题：{goal.subject}
- 学习目标：{goal.target}
- 截止日期：{goal.deadline.isoformat()}
- 当前水平：{goal.current_level}
- 每日可学习时间：{goal.daily_available_minutes} 分钟
- 每周学习天数：{goal.weekly_available_days} 天
- 学习偏好：{", ".join(goal.preferred_methods)}
- 薄弱点：{", ".join(goal.weak_points)}
- 额外要求：{goal.extra_requirements}

生成要求：
1. 必须包含阶段、周、日三级结构。
2. 每日任务总时长不能超过每日可学习时间。
3. 每周安排学习任务的天数不能超过每周学习天数。
4. 所有阶段、周计划和任务日期不能超过截止日期，也不能早于今天日期 {today}。
5. 必须包含总体路线、阶段目标、周计划、每日任务、学习方法、风险提示和复习安排。

只输出合法 JSON，不要输出 Markdown，不要输出解释文字。JSON 顶层必须是对象，字段如下：
{{
  "overall_route": "总体学习路线",
  "phases": [
    {{
      "phase_index": 1,
      "title": "阶段标题",
      "objective": "阶段目标",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "milestone": "阶段里程碑",
      "weekly_plans": [
        {{
          "week_index": 1,
          "start_date": "YYYY-MM-DD",
          "end_date": "YYYY-MM-DD",
          "objective": "周目标",
          "review_focus": "复习重点",
          "tasks": [
            {{
              "title": "任务标题",
              "date": "YYYY-MM-DD",
              "duration_minutes": 60,
              "task_type": "学习/练习/复习/项目",
              "related_topics": ["知识点"],
              "learning_method": "学习方法",
              "expected_output": "预期产出",
              "review_required": true,
              "status": "todo"
            }}
          ]
        }}
      ]
    }}
  ],
  "methods": ["学习方法"],
  "risks": ["风险提示"],
  "review_schedule": {{
    "daily_review_minutes": 15,
    "weekly_review_day": "周日",
    "review_strategy": "复习安排"
  }},
  "suggestions": "整体建议"
}}
""".strip()
