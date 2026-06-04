from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgePoint:
    name: str
    description: str = ""
    prerequisites: list[str] = field(default_factory=list)
    difficulty: int = 1
    importance: int = 1
    mastery_level: int = 0


class KnowledgeAgent:
    def __init__(self, llm: Any | None = None):
        self.llm = llm

    def run(self, goal, learner_profile=None) -> list[KnowledgePoint]:
        payload = self._payload(goal)
        points = payload.get("knowledge_points", [])
        if not isinstance(points, list):
            raise ValueError("knowledge points must be structured JSON")
        if not points:
            raise ValueError("knowledge points cannot be empty / 知识点不能为空")
        result: list[KnowledgePoint] = []
        seen: set[str] = set()
        for item in points:
            if isinstance(item, str):
                item = {"name": item}
            name = str(item.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            result.append(
                KnowledgePoint(
                    name=name,
                    description=str(item.get("description", "")),
                    prerequisites=list(item.get("prerequisites", [])),
                    difficulty=_clamp_int(item.get("difficulty", 1)),
                    importance=_clamp_int(item.get("importance", 3)),
                    mastery_level=_clamp_int(item.get("mastery_level", 0), 0, 5),
                )
            )
        for weak_point in getattr(goal, "weak_points", []):
            if weak_point not in seen:
                result.append(KnowledgePoint(name=weak_point, description="用户薄弱点", difficulty=3, importance=5))
        return result

    def _payload(self, goal) -> dict:
        if self.llm is None:
            if "机器学习" in goal.subject:
                return {
                    "knowledge_points": [
                        {"name": "数学基础", "difficulty": 3, "importance": 5},
                        {"name": "监督学习", "prerequisites": ["数学基础"], "difficulty": 4, "importance": 5},
                    ]
                }
            return {
                "knowledge_points": [
                    {"name": "变量", "description": "基础语法", "difficulty": 1, "importance": 5},
                    {"name": "函数", "description": "代码组织", "difficulty": 2, "importance": 5},
                ]
            }
        if isinstance(self.llm, dict):
            return self.llm
        raise ValueError("LLM response is not JSON / 结构化解析失败")


def _clamp_int(value, min_value: int = 1, max_value: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = min_value
    return max(min_value, min(max_value, parsed))
