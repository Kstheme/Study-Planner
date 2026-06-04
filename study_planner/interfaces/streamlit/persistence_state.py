from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from study_planner.application.persistence import StorageError, StorageService, build_persistent_app_state
from study_planner.infrastructure.db.repositories import (
    InMemoryExportRecordRepository,
    InMemoryMaterialRepository,
    InMemoryReviewReportRepository,
    InMemoryStudyGoalRepository,
    InMemoryStudyPlanRepository,
    InMemoryTaskProgressRepository,
    PostgresDatabaseInitializer,
    PostgresExportRecordRepository,
    PostgresMaterialRepository,
    PostgresReviewReportRepository,
    PostgresStudyGoalRepository,
    PostgresStudyPlanRepository,
    PostgresTaskProgressRepository,
)
from study_planner.infrastructure.settings import AppSettings, load_app_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@st.cache_resource
def get_storage_service() -> StorageService:
    settings = load_app_settings(PROJECT_ROOT / ".env")
    return build_storage_service(settings)


def build_storage_service(settings: AppSettings) -> StorageService:
    if settings.use_postgres_persistence:
        return _build_postgres_storage_service(settings)
    return _build_in_memory_storage_service()


def restore_persistent_state() -> StorageService:
    try:
        service = get_storage_service()
    except StorageError as exc:
        st.session_state["storage_available"] = False
        st.session_state["storage_startup_error"] = str(exc)
        return _build_in_memory_storage_service()

    app_state = build_persistent_app_state(st.session_state, service)
    st.session_state["storage_available"] = app_state.storage_available
    st.session_state["storage_startup_error"] = app_state.startup_error

    if app_state.study_plan is not None and not st.session_state.get("selected_plan_id"):
        metadata = service.plan_repository.metadata_latest()
        st.session_state["selected_plan_id"] = metadata.get("id")

    if "study_goal" not in st.session_state:
        try:
            latest_goal = service.get_latest_study_goal()
            if latest_goal is not None:
                st.session_state["study_goal"] = latest_goal
        except StorageError:
            pass

    return service


def render_storage_status() -> None:
    if st.session_state.get("storage_available", True):
        if st.session_state.get("selected_plan_id"):
            st.caption(f"已启用持久化，当前计划 ID：{st.session_state['selected_plan_id']}")
        else:
            st.caption("已启用持久化，暂无已保存计划。")
        return

    st.warning(f"持久化存储暂不可用：{st.session_state.get('storage_startup_error') or '读取失败'}")


def save_goal_and_plan_to_storage(service: StorageService, goal, plan) -> str:
    plan = ensure_stable_task_ids(plan)
    goal_id, plan_id = service.save_goal_and_plan(goal, plan)
    st.session_state["study_goal"] = goal
    st.session_state["study_plan"] = plan
    st.session_state["selected_goal_id"] = goal_id
    st.session_state["selected_plan_id"] = plan_id
    return plan_id


def save_plan_to_storage(service: StorageService, plan, goal_id: str | None = None) -> str:
    plan = ensure_stable_task_ids(plan)
    plan_id = service.save_study_plan(plan, goal_id=goal_id)
    st.session_state["study_plan"] = plan
    st.session_state["selected_plan_id"] = plan_id
    return plan_id


def ensure_stable_task_ids(plan):
    counter = 1
    used_ids: set[str] = set()
    for phase in plan.phases:
        for weekly_plan in phase.weekly_plans:
            for task in weekly_plan.tasks:
                if not task.id or task.id in used_ids:
                    while f"task-{counter}" in used_ids:
                        counter += 1
                    task.id = f"task-{counter}"
                used_ids.add(task.id)
                counter += 1
    return plan


def _build_in_memory_storage_service() -> StorageService:
    return StorageService(
        goal_repository=InMemoryStudyGoalRepository(clock=datetime.now),
        plan_repository=InMemoryStudyPlanRepository(clock=datetime.now),
        task_progress_repository=InMemoryTaskProgressRepository(clock=datetime.now),
        review_report_repository=InMemoryReviewReportRepository(clock=datetime.now),
        material_repository=InMemoryMaterialRepository(clock=datetime.now),
        export_record_repository=InMemoryExportRecordRepository(clock=datetime.now),
    )


def _build_postgres_storage_service(settings: AppSettings) -> StorageService:
    if not settings.database_url:
        raise StorageError("DATABASE_URL is required when USE_POSTGRES_PERSISTENCE=true")
    initializer = PostgresDatabaseInitializer(database_url=settings.database_url)
    initializer.initialize()
    return StorageService(
        goal_repository=PostgresStudyGoalRepository(database_url=settings.database_url),
        plan_repository=PostgresStudyPlanRepository(database_url=settings.database_url),
        task_progress_repository=PostgresTaskProgressRepository(database_url=settings.database_url),
        review_report_repository=PostgresReviewReportRepository(database_url=settings.database_url),
        material_repository=PostgresMaterialRepository(database_url=settings.database_url),
        export_record_repository=PostgresExportRecordRepository(database_url=settings.database_url),
    )
