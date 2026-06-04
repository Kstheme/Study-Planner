from __future__ import annotations

from typing import Any


DEFAULT_KEYS = {
    "study_goal": None,
    "study_plan": None,
    "selected_plan_id": None,
    "materials": list,
    "last_review_report": None,
    "errors": list,
}


def initialize_session_state(state: dict) -> dict:
    for key, default in DEFAULT_KEYS.items():
        if key not in state:
            state[key] = default() if callable(default) else default
    return state


def set_study_goal(state: dict, goal: Any) -> None:
    state["study_goal"] = goal


def set_study_plan(state: dict, plan: Any) -> None:
    state["study_plan"] = plan


def save_plan_to_session(state: dict, plan: Any, plan_id: str | None = None) -> str | None:
    state["study_plan"] = plan
    state["selected_plan_id"] = plan_id
    return plan_id


def add_material_to_session(state: dict, material: Any) -> None:
    state.setdefault("materials", [])
    state["materials"].append(material)


def set_last_review_report(state: dict, report: Any) -> None:
    state["last_review_report"] = report


def set_pending_adjusted_plan(state: dict, plan: Any, report: Any | None = None) -> None:
    state["pending_adjusted_plan"] = plan
    if report is not None:
        state["pending_review_report"] = report


def commit_pending_adjustment(state: dict) -> Any:
    adjusted = state.get("pending_adjusted_plan")
    if adjusted is None:
        raise ValueError("No pending adjusted plan")
    state["study_plan"] = adjusted
    if state.get("pending_review_report") is not None:
        state["last_review_report"] = state["pending_review_report"]
    state.pop("pending_adjusted_plan", None)
    state.pop("pending_review_report", None)
    return adjusted


def restore_latest_plan(state: dict, service: Any) -> Any:
    plan = getattr(service, "saved_plan", None)
    if plan is None and hasattr(service, "get_latest_study_plan"):
        plan = service.get_latest_study_plan()
    if plan is None and hasattr(service, "load_latest_study_plan"):
        plan = service.load_latest_study_plan()
    if plan is not None:
        state["study_plan"] = plan
    return plan


def save_dashboard_plan(state: dict, plan: Any, service: Any) -> str | None:
    original = state.get("study_plan")
    try:
        plan_id = service.save_study_plan(plan, goal_id=state.get("selected_goal_id"))
    except Exception:
        state["study_plan"] = original
        raise
    state["study_plan"] = plan
    state["selected_plan_id"] = plan_id
    return plan_id


def set_review_text(state: dict, text: str) -> None:
    state["review_text"] = text


def preserve_plan_on_error(state: dict, error: Exception) -> None:
    add_ui_error(state, error)


def dedupe_pending_actions(state: dict) -> None:
    seen = []
    for action in state.get("pending_actions", []):
        if action not in seen:
            seen.append(action)
    state["pending_actions"] = seen


def add_ui_error(state: dict, error: Exception | str) -> None:
    from study_planner.application.ui_errors import sanitize_error_message

    state.setdefault("errors", [])
    state["errors"].append(sanitize_error_message(error))


def assert_same_current_plan(state: dict, pages: list[str]) -> bool:
    if state.get("study_plan") is None:
        raise AssertionError(f"study_plan missing for pages: {', '.join(pages)}")
    return True


def reset_for_new_plan(state: dict) -> None:
    state.pop("pending_adjusted_plan", None)
    state.pop("pending_review_report", None)
    state["last_review_report"] = None
