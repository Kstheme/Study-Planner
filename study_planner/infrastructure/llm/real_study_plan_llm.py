import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from study_planner.application.generate_study_plan import StudyPlanGenerationError
from study_planner.domain.models import StudyGoal
from study_planner.infrastructure.settings import load_app_settings
from study_planner.prompts.study_plan_prompt import build_study_plan_prompt


class _ConfiguredChatModel:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def invoke(self, prompt: str):
        base_url = self.config.get("base_url", "").rstrip("/")
        url = f"{base_url}/chat/completions"
        request_body = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if self.config.get("provider") == "deepseek":
            request_body["response_format"] = {"type": "json_object"}
        body = json.dumps(request_body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StudyPlanGenerationError(f"DeepSeek API 调用失败: {detail}") from exc
        except urllib.error.URLError as exc:
            raise StudyPlanGenerationError(f"DeepSeek API 网络错误: {exc}") from exc

        return payload["choices"][0]["message"]["content"]


class _FakeConfiguredChatModel:
    def invoke(self, prompt: str):
        from datetime import date, timedelta

        today = date.today()
        return json.dumps(
            {
                "overall_route": "先学习基础知识，再完成练习，最后做一个小项目。",
                "phases": [
                    {
                        "phase_index": 1,
                        "title": "基础阶段",
                        "objective": "掌握核心基础知识。",
                        "start_date": today.isoformat(),
                        "end_date": (today + timedelta(days=6)).isoformat(),
                        "milestone": "完成基础练习。",
                        "weekly_plans": [
                            {
                                "week_index": 1,
                                "start_date": today.isoformat(),
                                "end_date": (today + timedelta(days=6)).isoformat(),
                                "objective": "完成第一周基础学习。",
                                "review_focus": "复习核心概念。",
                                "tasks": [
                                    {
                                        "title": "学习基础概念",
                                        "date": today.isoformat(),
                                        "duration_minutes": 60,
                                        "task_type": "学习",
                                        "related_topics": ["基础概念"],
                                        "learning_method": "阅读教程 + 练习",
                                        "expected_output": "完成基础概念笔记。",
                                        "review_required": True,
                                        "status": "todo",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "methods": ["阅读教程", "实践练习", "每日复习"],
                "risks": ["需要保持稳定学习节奏。"],
                "review_schedule": {
                    "daily_review_minutes": 15,
                    "weekly_review_day": "周日",
                    "review_strategy": "每天复习当天内容，每周整理薄弱点。",
                },
                "suggestions": "先完成基础任务，再逐步增加项目实践。",
            },
            ensure_ascii=False,
        )


class RealStudyPlanLLM:
    def __init__(self, chat_model: Any, max_retries: int = 0, config: dict[str, Any] | None = None):
        self.chat_model = chat_model
        self.max_retries = max_retries
        self.config = config or {}

    @classmethod
    def from_config(cls, config: dict[str, Any]):
        provider = config.get("provider")
        api_key = config.get("api_key")
        if provider not in {"openai", "deepseek", "qwen"}:
            raise ValueError("不支持的 provider")
        if not api_key:
            raise ValueError("API Key 缺失")
        return cls(chat_model=_ConfiguredChatModel(config), config=config)

    @classmethod
    def from_env(cls, env_path: str | Path = ".env"):
        settings = load_app_settings(env_path)
        config = {
            "provider": "deepseek",
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
            "model": settings.deepseek_model,
            "use_real_llm": settings.use_real_llm,
        }
        if not settings.use_real_llm:
            return cls(chat_model=_FakeConfiguredChatModel(), config=config)
        return cls.from_config(config)

    @staticmethod
    def _read_env(env_path: str | Path) -> dict[str, str]:
        path = Path(env_path)
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def generate_study_plan(self, goal: StudyGoal) -> dict[str, Any]:
        prompt = build_study_plan_prompt(goal)
        last_error: Exception | None = None
        last_content = ""

        for _ in range(self.max_retries + 1):
            response = self.chat_model.invoke(prompt)
            content = self._content_from_response(response)
            last_content = content
            try:
                payload = json.loads(self._extract_json(content))
                if not isinstance(payload, dict):
                    raise StudyPlanGenerationError("学习计划 JSON 顶层必须是对象")
                return payload
            except (json.JSONDecodeError, StudyPlanGenerationError) as exc:
                last_error = exc

        if self.config.get("use_real_llm"):
            try:
                repaired = self._repair_json_response(last_content, goal)
                payload = json.loads(self._extract_json(repaired))
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:
                last_error = exc

        snippet = self._safe_snippet(last_content)
        raise StudyPlanGenerationError(f"真实 LLM 返回内容无法解析为学习计划。返回片段: {snippet}") from last_error

    def _content_from_response(self, response: Any) -> str:
        if hasattr(response, "content"):
            return str(response.content)
        return str(response)

    def _extract_json(self, content: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and start < end:
            return stripped[start : end + 1]
        return stripped

    def _repair_json_response(self, content: str, goal: StudyGoal) -> str:
        from datetime import date

        repair_prompt = (
            "请把下面内容转换成合法 JSON 对象，且只能输出 JSON。\n"
            "必须包含字段 overall_route, phases, methods, risks, review_schedule, suggestions。\n"
            "phases[].weekly_plans[].tasks[] 必须存在。\n"
            f"今天日期不能早于: {date.today().isoformat()}\n"
            f"截止日期不能晚于: {goal.deadline.isoformat()}\n"
            f"原始内容:\n{content}"
        )
        return self._content_from_response(self.chat_model.invoke(repair_prompt))

    def _safe_snippet(self, content: str, limit: int = 300) -> str:
        text = re.sub(r"\s+", " ", content or "").strip()
        return text[:limit] if text else "<empty>"
