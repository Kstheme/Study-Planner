from pathlib import Path
from datetime import date, timedelta

import pytest

from study_planner.application.generate_study_plan import (
    GenerateStudyPlanUseCase,
    StudyPlanGenerationError,
)
from study_planner.domain.models import StudyGoal, StudyPlan
from study_planner.infrastructure.llm.real_study_plan_llm import RealStudyPlanLLM
from study_planner.prompts.study_plan_prompt import build_study_plan_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
ENV_PATH = PROJECT_ROOT / ".env"


def valid_goal(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法，并能独立完成一个小型项目",
        "deadline": date.today() + timedelta(days=30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["视频教程", "实践项目"],
        "weak_points": ["缺乏编程经验"],
        "extra_requirements": "希望多安排练习任务",
    }
    data.update(overrides)
    return StudyGoal(**data)


def valid_llm_json():
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=6)).isoformat()
    phase_end = (date.today() + timedelta(days=13)).isoformat()
    return f"""
    {{
      "overall_route": "先学习 Python 基础语法，再完成练习，最后实现一个小型项目。",
      "phases": [
        {{
          "phase_index": 1,
          "title": "基础入门阶段",
          "objective": "掌握 Python 基础语法和基本编程思维。",
          "start_date": "{today}",
          "end_date": "{phase_end}",
          "milestone": "能够完成变量、条件、循环和函数相关练习。",
          "weekly_plans": [
            {{
              "week_index": 1,
              "start_date": "{today}",
              "end_date": "{week_end}",
              "objective": "完成 Python 基础语法学习。",
              "review_focus": "复习变量、条件、循环和函数。",
              "tasks": [
                {{
                  "title": "学习变量与数据类型",
                  "date": "{today}",
                  "duration_minutes": 60,
                  "task_type": "学习",
                  "related_topics": ["变量", "数据类型"],
                  "learning_method": "视频教程 + 练习",
                  "expected_output": "完成 10 道变量和数据类型练习。",
                  "review_required": true,
                  "status": "todo"
                }},
                {{
                  "title": "完成基础语法复习",
                  "date": "{today}",
                  "duration_minutes": 30,
                  "task_type": "复习",
                  "related_topics": ["变量", "数据类型"],
                  "learning_method": "错题回顾",
                  "expected_output": "整理 3 条易错点。",
                  "review_required": true,
                  "status": "todo"
                }}
              ]
            }}
          ]
        }}
      ],
      "methods": ["视频教程", "实践项目", "每日复习"],
      "risks": ["零基础学习容易卡在语法细节，需要保持每日练习。"],
      "review_schedule": {{
        "daily_review_minutes": 15,
        "weekly_review_day": "周日",
        "review_strategy": "每天复习当天知识点，每周整理一次薄弱点。"
      }},
      "suggestions": "保持小步快跑，每天完成一个可检查的学习产出。"
    }}
    """


class FakeChatModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            raise RuntimeError("no fake response left")
        return self.responses.pop(0)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class TestF2BPrompt:
    def test_f2b_01_prompt_contains_study_goal_fields(self):
        """原因：真实 LLM 必须收到完整 StudyGoal 信息，才能生成个性化计划。"""
        goal = valid_goal()

        prompt = build_study_plan_prompt(goal)

        assert "Python 编程" in prompt
        assert "掌握 Python 基础语法" in prompt
        assert "零基础" in prompt
        assert "120" in prompt
        assert "5" in prompt
        assert "视频教程" in prompt
        assert "缺乏编程经验" in prompt

    def test_f2b_02_prompt_requires_stage_week_day_hierarchy(self):
        """原因：F2 验收要求真实 LLM 输出阶段、周、日三级结构。"""
        prompt = build_study_plan_prompt(valid_goal())

        assert "phases" in prompt
        assert "weekly_plans" in prompt
        assert "tasks" in prompt

    def test_f2b_03_prompt_requires_all_f2_fields(self):
        """原因：真实 LLM 输出必须覆盖总体路线、方法、预算相关信息、风险和复习安排。"""
        prompt = build_study_plan_prompt(valid_goal())

        assert "overall_route" in prompt
        assert "methods" in prompt
        assert "risks" in prompt
        assert "review_schedule" in prompt
        assert "duration_minutes" in prompt

    def test_f2b_04_prompt_requires_json_only(self):
        """原因：真实 LLM 若混入说明文本，会增加 JSON 解析失败概率。"""
        prompt = build_study_plan_prompt(valid_goal())

        assert "JSON" in prompt
        assert "不要输出 Markdown" in prompt or "只输出" in prompt

    def test_f2b_05_prompt_contains_schedule_constraints(self):
        """原因：模型需要明确知道每日时长、每周天数和截止日期限制。"""
        prompt = build_study_plan_prompt(valid_goal())

        assert "每日" in prompt
        assert "每周" in prompt
        assert "截止日期" in prompt
        assert "不能超过" in prompt


class TestF2BLLMAdapter:
    def test_f2b_06_real_llm_calls_chat_model_with_prompt(self):
        """原因：适配器必须把 StudyGoal 转成 prompt 并调用底层 chat model。"""
        chat_model = FakeChatModel([FakeMessage(valid_llm_json())])
        llm = RealStudyPlanLLM(chat_model=chat_model)

        llm.generate_study_plan(valid_goal())

        assert len(chat_model.prompts) == 1
        assert "Python 编程" in chat_model.prompts[0]

    def test_f2b_07_real_llm_accepts_message_content_response(self):
        """原因：LangChain 模型通常返回带 content 字段的消息对象。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(valid_llm_json())]))

        payload = llm.generate_study_plan(valid_goal())

        assert payload["overall_route"]
        assert payload["phases"]

    def test_f2b_08_real_llm_accepts_plain_string_response(self):
        """原因：不同模型封装可能直接返回字符串，适配器需要兼容。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([valid_llm_json()]))

        payload = llm.generate_study_plan(valid_goal())

        assert payload["methods"]

    def test_f2b_09_real_llm_extracts_json_from_code_fence(self):
        """原因：模型常把 JSON 包在 ```json 代码块里，需要能提取。"""
        response = f"```json\n{valid_llm_json()}\n```"
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(response)]))

        payload = llm.generate_study_plan(valid_goal())

        assert payload["review_schedule"]["review_strategy"]

    def test_f2b_10_real_llm_rejects_non_json_text(self):
        """原因：模型返回普通说明文本时不能进入计划生成流程。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage("我建议你每天学习。")]))

        with pytest.raises(StudyPlanGenerationError):
            llm.generate_study_plan(valid_goal())

    def test_f2b_11_real_llm_rejects_json_array_root(self):
        """原因：StudyPlan 顶层必须是对象，不应接受数组根节点。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage("[]")]))

        with pytest.raises(StudyPlanGenerationError):
            llm.generate_study_plan(valid_goal())

    def test_f2b_12_real_llm_retries_once_after_invalid_json(self):
        """原因：真实模型偶尔格式错误，适配器应支持有限重试。"""
        chat_model = FakeChatModel([FakeMessage("not json"), FakeMessage(valid_llm_json())])
        llm = RealStudyPlanLLM(chat_model=chat_model, max_retries=1)

        payload = llm.generate_study_plan(valid_goal())

        assert payload["phases"]
        assert len(chat_model.prompts) == 2

    def test_f2b_13_real_llm_fails_after_retry_exhausted(self):
        """原因：重试耗尽后要给出明确错误，避免无限循环。"""
        chat_model = FakeChatModel([FakeMessage("bad"), FakeMessage("still bad")])
        llm = RealStudyPlanLLM(chat_model=chat_model, max_retries=1)

        with pytest.raises(StudyPlanGenerationError):
            llm.generate_study_plan(valid_goal())


class TestF2BUseCaseWithRealLLMAdapter:
    def test_f2b_14_use_case_generates_study_plan_from_real_llm_payload(self):
        """原因：真实 LLM 适配器输出的 payload 必须能进入 F2 用例并生成 StudyPlan。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(valid_llm_json())]))
        use_case = GenerateStudyPlanUseCase(llm=llm)

        plan = use_case.execute(valid_goal())
        
        print(plan)

        assert isinstance(plan, StudyPlan)
        assert plan.overall_route
        assert plan.phases[0].weekly_plans[0].tasks

    def test_f2b_15_use_case_parses_iso_date_strings_from_llm(self):
        """原因：真实 LLM JSON 中日期通常是字符串，需要转换为 date 对象。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(valid_llm_json())]))
        plan = GenerateStudyPlanUseCase(llm=llm).execute(valid_goal())

        first_task = plan.phases[0].weekly_plans[0].tasks[0]

        assert isinstance(first_task.date, date)

    def test_f2b_16_use_case_uses_original_goal_not_llm_goal(self):
        """原因：真实 LLM 不应该决定用户原始目标，计划应绑定调用方传入的 StudyGoal。"""
        goal = valid_goal(subject="机器学习")
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(valid_llm_json())]))

        plan = GenerateStudyPlanUseCase(llm=llm).execute(goal)

        assert plan.goal == goal
        assert plan.goal.subject == "机器学习"

    def test_f2b_17_use_case_computes_time_budget_even_if_llm_omits_it(self):
        """原因：时间预算应由系统兜底计算，不能完全依赖模型输出。"""
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(valid_llm_json())]))

        plan = GenerateStudyPlanUseCase(llm=llm).execute(valid_goal())

        assert plan.time_budget.total_available_minutes > 0
        assert plan.time_budget.planned_minutes == 90

    def test_f2b_18_use_case_rejects_real_llm_payload_missing_required_hierarchy(self):
        """原因：真实 LLM 若缺少阶段、周、日结构，不能通过 F2 验收。"""
        response = '{"overall_route": "学习 Python", "phases": []}'
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(response)]))

        with pytest.raises(StudyPlanGenerationError):
            GenerateStudyPlanUseCase(llm=llm).execute(valid_goal())

    def test_f2b_19_use_case_rejects_real_llm_payload_that_exceeds_daily_limit(self):
        """原因：真实 LLM 生成过载日程时，需要被业务校验拦截。"""
        response = valid_llm_json().replace('"duration_minutes": 60', '"duration_minutes": 180', 1)
        llm = RealStudyPlanLLM(chat_model=FakeChatModel([FakeMessage(response)]))

        with pytest.raises(StudyPlanGenerationError):
            GenerateStudyPlanUseCase(llm=llm).execute(valid_goal())


class TestF2BConfiguration:
    def test_f2b_20_env_example_documents_deepseek_config(self):
        """原因：项目指定 F2-B 基于 DeepSeek，.env.example 必须给出完整配置模板。"""
        content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

        assert "DEEPSEEK_API_KEY=" in content
        assert "DEEPSEEK_BASE_URL=" in content
        assert "DEEPSEEK_MODEL=" in content
        assert "USE_REAL_LLM=" in content

    def test_f2b_21_real_llm_can_be_constructed_from_deepseek_config(self):
        """原因：真实 LLM 配置应以 DeepSeek 为默认供应商。"""
        config = {
            "provider": "deepseek",
            "api_key": "test-key",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        }

        llm = RealStudyPlanLLM.from_config(config)

        assert isinstance(llm, RealStudyPlanLLM)

    def test_f2b_22_real_llm_loads_deepseek_config_from_env_file(self):
        """原因：实际调用时应读取 .env，而不是在代码或测试中硬编码密钥。"""
        llm = RealStudyPlanLLM.from_env(ENV_PATH)

        assert isinstance(llm, RealStudyPlanLLM)
        assert llm.config["provider"] == "deepseek"
        assert llm.config["api_key"]
        assert llm.config["base_url"] == "https://api.deepseek.com"
        assert llm.config["model"]
        assert isinstance(llm.config["use_real_llm"], bool)

    def test_f2b_23_missing_deepseek_api_key_raises_clear_error(self):
        """原因：DeepSeek 缺少 API Key 时，应给开发者明确配置错误。"""
        config = {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        }

        with pytest.raises(ValueError, match="API"):
            RealStudyPlanLLM.from_config(config)

    def test_f2b_24_unsupported_provider_raises_clear_error(self):
        """原因：不支持的模型供应商不能静默失败。"""
        config = {
            "provider": "unknown",
            "api_key": "test-key",
            "model": "test-model",
        }

        with pytest.raises(ValueError, match="provider|供应商|模型"):
            RealStudyPlanLLM.from_config(config)


class TestF2BRealDeepSeekModel:
    def test_f2b_25_calls_real_deepseek_model_from_env(self):
        """原因：F2-B 必须验证 .env 中的 DeepSeek 配置能真实调用模型并生成 StudyPlan。"""
        goal = valid_goal(
            deadline=date.today() + timedelta(days=14),
            daily_available_minutes=240,
            weekly_available_days=7,
        )
        llm = RealStudyPlanLLM.from_env(ENV_PATH)
        if not llm.config["use_real_llm"]:
            pytest.skip("USE_REAL_LLM=false，跳过真实 DeepSeek 调用")

        plan = GenerateStudyPlanUseCase(llm=llm).execute(goal)

        assert isinstance(plan, StudyPlan)
        assert plan.overall_route
        assert plan.phases
        assert plan.phases[0].weekly_plans
        assert plan.phases[0].weekly_plans[0].tasks
