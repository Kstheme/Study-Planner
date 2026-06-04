from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
from typing import Any

from study_planner.domain.models import StudyGoal, StudyPlan


@dataclass
class WorkflowError:
    node: str
    message: str


@dataclass
class PlannerState:
    goal: StudyGoal
    learner_profile: Any | None = None
    knowledge_points: list[Any] = field(default_factory=list)
    resources: list[Any] = field(default_factory=list)
    draft_plan: StudyPlan | None = None
    review: Any | None = None
    final_plan: StudyPlan | None = None
    errors: list[WorkflowError] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    debug_state: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0


def validate_state_serializable(state: PlannerState) -> None:
    def _default(value):
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"{type(value).__name__} is not serializable")

    try:
        json.dumps(state, default=_default, ensure_ascii=False)
    except TypeError as exc:
        raise ValueError("PlannerState must be JSON serializable / 状态必须可序列化") from exc
