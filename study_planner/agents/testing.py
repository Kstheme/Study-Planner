from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from study_planner.agents.nodes.critic import CriticReview
from study_planner.agents.planner_state import PlannerState, WorkflowError
from study_planner.domain.models import StudyPlan


class FakeRAG:
    def __init__(self, results: list[dict[str, Any]] | None = None, fail: bool = False):
        self.results = results or []
        self.fail = fail
        self.queries: list[str] = []

    def search(self, query: str) -> list[dict[str, Any]]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("RAG unavailable")
        return self.results


class FakePlannerAgent:
    def __init__(self, outputs: list[StudyPlan] | None = None, always: StudyPlan | None = None):
        self.outputs = list(outputs or [])
        self.always = always
        self.call_count = 0

    def run(self, goal, learner_profile=None, knowledge_points=None, resources=None) -> StudyPlan:
        self.call_count += 1
        if self.always is not None:
            return self.always
        if self.outputs:
            return self.outputs.pop(0)
        from study_planner.agents.nodes.planner import PlannerAgent

        return PlannerAgent().run(goal, learner_profile, knowledge_points, resources)


class FakeCriticAgent:
    def __init__(self, fail_first: bool = False, always_fail: bool = False, always_pass: bool = False):
        self.fail_first = fail_first
        self.always_fail = always_fail
        self.always_pass = always_pass
        self.call_count = 0

    def run(self, plan: StudyPlan) -> CriticReview:
        self.call_count += 1
        if self.always_pass:
            return CriticReview(passed=True)
        if self.always_fail or (self.fail_first and self.call_count == 1):
            return CriticReview(passed=False)
        return CriticReview(passed=True)


class FakePlannerWorkflow:
    def __init__(self, plan: StudyPlan | None = None, errors: list[str] | None = None):
        self.plan = plan
        self.errors = errors or []

    def run(self, goal) -> PlannerState:
        return PlannerState(
            goal=goal,
            final_plan=self.plan,
            errors=[WorkflowError(node="workflow", message=message) for message in self.errors],
        )


class ExplodingLLM:
    def generate(self, *_args, **_kwargs):
        raise RuntimeError("LLM should not be called")


class TimeoutLLM:
    pass


@dataclass
class FakeLLM:
    response: Any = None


@dataclass
class LeakyLLM:
    secret: str


class FlakyLLM:
    def __init__(self, failures_before_success: int = 0, always_fail: bool = False):
        self.failures_before_success = failures_before_success
        self.always_fail = always_fail
        self.calls = 0

    def should_fail(self) -> bool:
        self.calls += 1
        return self.always_fail or self.calls <= self.failures_before_success
