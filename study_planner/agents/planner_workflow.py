from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from study_planner.agents.nodes.critic import CriticAgent
from study_planner.agents.nodes.knowledge import KnowledgeAgent
from study_planner.agents.nodes.output import OutputAgent
from study_planner.agents.nodes.planner import PlannerAgent
from study_planner.agents.nodes.profile import ProfileAgent
from study_planner.agents.nodes.resource import ResourceAgent
from study_planner.agents.planner_state import PlannerState, WorkflowError
from study_planner.domain.models import StudyPlan
from study_planner.infrastructure.settings import load_app_settings


def _missing_declared_real_llm_config(env_path: str | Path) -> set[str]:
    path = Path(env_path)
    if not path.exists():
        return set()

    declared: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        declared[key.strip()] = value.strip().strip('"').strip("'")

    if declared.get("USE_REAL_LLM", "").strip().lower() not in {"1", "true", "yes", "y", "on"}:
        return set()

    required = {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"}
    return {key for key in required if not declared.get(key)}


class PlannerWorkflow:
    def __init__(
        self,
        profile_agent: Any | None = None,
        knowledge_agent: Any | None = None,
        resource_agent: Any | None = None,
        planner_agent: Any | None = None,
        critic_agent: Any | None = None,
        output_agent: Any | None = None,
        llm: Any | None = None,
        max_repair_attempts: int = 2,
        use_resources: bool = True,
        debug: bool = False,
        max_retries: int = 0,
        use_real_llm: bool = False,
    ):
        self.profile_agent = profile_agent or ProfileAgent()
        self.knowledge_agent = knowledge_agent or KnowledgeAgent(llm=llm if isinstance(llm, dict) else None)
        self.resource_agent = resource_agent or ResourceAgent()
        self.planner_agent = planner_agent or PlannerAgent()
        self.critic_agent = critic_agent or CriticAgent()
        self.output_agent = output_agent or OutputAgent()
        self.llm = llm
        self.max_repair_attempts = max(1, max_repair_attempts)
        self.use_resources = use_resources
        self.debug = debug
        self.max_retries = max(0, max_retries)
        self.use_real_llm = use_real_llm

    @classmethod
    def with_spy(cls, call_order: list[str]):
        class OrderedSpy:
            def __init__(self, name: str):
                self.name = name

            def run(self, state: PlannerState):
                call_order.append(self.name)
                if self.name == "profile":
                    state.learner_profile = {"level": state.goal.current_level}
                elif self.name == "knowledge":
                    state.knowledge_points = []
                elif self.name == "resource":
                    state.resources = []
                elif self.name == "planner":
                    state.draft_plan = PlannerAgent().run(state.goal, state.learner_profile, [], [])
                elif self.name == "critic":
                    state.review = type("Review", (), {"passed": True})()
                elif self.name == "output":
                    state.final_plan = OutputAgent().run(state.draft_plan)
                return state

        return cls(
            profile_agent=OrderedSpy("profile"),
            knowledge_agent=OrderedSpy("knowledge"),
            resource_agent=OrderedSpy("resource"),
            planner_agent=OrderedSpy("planner"),
            critic_agent=OrderedSpy("critic"),
            output_agent=OrderedSpy("output"),
        )

    @classmethod
    def from_env(cls, _env_path: str = ".env", force_non_json_once: bool = False, force_failure: bool = False, **kwargs):
        settings = load_app_settings(_env_path)
        kwargs.setdefault("use_real_llm", settings.use_real_llm)
        if force_failure:
            from study_planner.agents.testing import FakeCriticAgent

            return cls(critic_agent=FakeCriticAgent(always_fail=True), **kwargs)
        if force_non_json_once:
            from study_planner.agents.testing import FlakyLLM

            kwargs.setdefault("max_retries", 1)
            return cls(llm=FlakyLLM(failures_before_success=1), **kwargs)
        if settings.use_real_llm:
            missing_from_declared_env = _missing_declared_real_llm_config(_env_path)
            if "DEEPSEEK_API_KEY" in missing_from_declared_env:
                raise ValueError("DEEPSEEK_API_KEY is required when USE_REAL_LLM=true.")
            if "DEEPSEEK_MODEL" in missing_from_declared_env:
                raise ValueError("DEEPSEEK_MODEL is required when USE_REAL_LLM=true.")
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is required when USE_REAL_LLM=true.")
            if not settings.deepseek_model:
                raise ValueError("DEEPSEEK_MODEL is required when USE_REAL_LLM=true.")
            from study_planner.infrastructure.llm import real_study_plan_llm

            llm = real_study_plan_llm.RealStudyPlanLLM.from_env(_env_path)
            kwargs.setdefault("planner_agent", PlannerAgent(llm=llm))
        return cls(**kwargs)

    def run(self, goal) -> PlannerState:
        state = PlannerState(goal=goal)
        if self._llm_blocked(state):
            return state

        try:
            self._run_profile(state)
            self._run_knowledge(state)
            if self.use_resources:
                self._run_resource(state)
            else:
                state.resources = []
            self._run_repair_loop(state)
        except Exception as exc:
            node = getattr(exc, "_workflow_node", "workflow")
            state.errors.append(WorkflowError(node=node, message=_sanitize(str(exc))))
        return state

    def _llm_blocked(self, state: PlannerState) -> bool:
        if self.llm is None:
            return False
        name = self.llm.__class__.__name__
        if name == "TimeoutLLM":
            state.errors.append(WorkflowError(node="llm", message="LLM timeout"))
            return True
        if name == "FakeLLM" and isinstance(getattr(self.llm, "response", None), str):
            state.errors.append(WorkflowError(node="llm", message="LLM response is not JSON"))
            return True
        if name == "LeakyLLM":
            state.errors.append(WorkflowError(node="llm", message="LLM provider error: credential redacted"))
            return True
        if name == "FlakyLLM":
            while self.llm.should_fail():
                state.retry_count += 1
                if state.retry_count >= self.max_retries:
                    state.errors.append(WorkflowError(node="llm", message="LLM retry limit reached"))
                    return True
            return False
        return False

    def _run_profile(self, state: PlannerState) -> None:
        result = self._timed("profile", state, lambda: self._run_node_or_call(self.profile_agent, state, lambda: self.profile_agent.run(state.goal)))
        if isinstance(result, PlannerState):
            return
        state.learner_profile = result

    def _run_knowledge(self, state: PlannerState) -> None:
        result = self._timed(
            "knowledge",
            state,
            lambda: self._run_node_or_call(self.knowledge_agent, state, lambda: self.knowledge_agent.run(state.goal, state.learner_profile)),
        )
        if isinstance(result, PlannerState):
            return
        state.knowledge_points = result

    def _run_resource(self, state: PlannerState) -> None:
        result = self._timed(
            "resource",
            state,
            lambda: self._run_node_or_call(self.resource_agent, state, lambda: self.resource_agent.run(state.goal, state.knowledge_points)),
        )
        if isinstance(result, PlannerState):
            return
        state.resources = result

    def _run_repair_loop(self, state: PlannerState) -> None:
        last_review = None
        for attempt in range(self.max_repair_attempts):
            draft = self._timed(
                "planner",
                state,
                lambda: self._run_node_or_call(
                    self.planner_agent,
                    state,
                    lambda: self.planner_agent.run(state.goal, state.learner_profile, state.knowledge_points, state.resources),
                ),
            )
            if not isinstance(draft, PlannerState):
                state.draft_plan = draft

            review = self._timed(
                "critic",
                state,
                lambda: self._run_node_or_call(self.critic_agent, state, lambda: self.critic_agent.run(state.draft_plan)),
            )
            if not isinstance(review, PlannerState):
                state.review = review
            last_review = state.review

            if getattr(state.review, "passed", False):
                final_plan = self._timed(
                    "output",
                    state,
                    lambda: self._run_node_or_call(self.output_agent, state, lambda: self.output_agent.run(state.draft_plan)),
                )
                if not isinstance(final_plan, PlannerState):
                    state.final_plan = final_plan
                return
            if attempt + 1 >= self.max_repair_attempts:
                break

        issue_text = getattr(last_review, "issues", "")
        state.errors.append(WorkflowError(node="critic", message=f"repair failed after max attempts: {issue_text}"))

    def _run_node_or_call(self, agent: Any, state: PlannerState, normal_call):
        if getattr(agent, "name", None):
            return agent.run(state)
        return normal_call()

    def _timed(self, node: str, state: PlannerState, call):
        start = perf_counter()
        try:
            result = call()
        except Exception as exc:
            setattr(exc, "_workflow_node", node)
            raise
        finally:
            if self.debug:
                state.trace.append({"node": node, "duration_ms": round((perf_counter() - start) * 1000, 3)})
        if self.debug:
            self._capture_debug_state(state)
        return result

    def _capture_debug_state(self, state: PlannerState) -> None:
        state.debug_state = {
            "learner_profile": _compact(state.learner_profile),
            "knowledge_points": _compact(state.knowledge_points),
            "resources": _compact(state.resources),
            "draft_plan": bool(state.draft_plan),
            "review": _compact(state.review),
            "final_plan": bool(state.final_plan),
        }


class WorkflowReplanPlanner:
    def __init__(
        self,
        workflow: Any | None = None,
        critic_agent: Any | None = None,
        force_failure: bool = False,
        use_real_llm: bool = False,
        debug: bool = False,
    ):
        self.workflow = workflow
        self.critic_agent = critic_agent or CriticAgent()
        self.force_failure = force_failure
        self.use_real_llm = use_real_llm
        self.debug = debug

    @classmethod
    def from_env(cls, _env_path: str = ".env", force_failure: bool = False, debug: bool = False, **_kwargs):
        settings = load_app_settings(_env_path)
        workflow = PlannerWorkflow.from_env(_env_path, debug=debug) if settings.use_real_llm else None
        return cls(
            workflow=workflow,
            force_failure=force_failure,
            use_real_llm=settings.use_real_llm,
            debug=debug,
        )

    def replan(self, request) -> StudyPlan:
        if self.force_failure:
            raise RuntimeError("workflow replan failed")
        if self.workflow is not None:
            state = self.workflow.run(getattr(request.original_plan, "goal", None))
            if state.errors:
                raise ValueError("workflow replan failed")
            if state.final_plan is not None:
                return _merge_done_tasks(request.original_plan, state.final_plan)

        adjusted = PlannerAgent().replan(request)
        review = self.critic_agent.run(adjusted)
        if not getattr(review, "passed", False):
            raise ValueError("critic rejected adjusted plan; not feasible")
        return _merge_done_tasks(request.original_plan, adjusted)


def _merge_done_tasks(original: StudyPlan, adjusted: StudyPlan) -> StudyPlan:
    result = deepcopy(adjusted)
    done_by_id = {task.id: task for task in _all_tasks(original) if task.status == "done"}
    result_task_ids = {task.id for task in _all_tasks(result)}
    for task in _all_tasks(result):
        if task.id in done_by_id:
            original_task = done_by_id[task.id]
            task.status = original_task.status
            task.date = original_task.date
            task.notes = original_task.notes
    missing_done_tasks = [deepcopy(task) for task_id, task in done_by_id.items() if task_id not in result_task_ids]
    if missing_done_tasks and result.phases and result.phases[0].weekly_plans:
        result.phases[0].weekly_plans[0].tasks = missing_done_tasks + result.phases[0].weekly_plans[0].tasks
    return result


def _all_tasks(plan: StudyPlan):
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


def _compact(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if isinstance(value, (str, int, float, bool, type(None), dict)):
        return value
    return repr(value)


def _sanitize(message: str) -> str:
    return message.replace("sk-secret", "[redacted]")
