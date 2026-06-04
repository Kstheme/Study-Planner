from pathlib import Path

from study_planner.infrastructure.settings import load_app_settings
from study_planner.interfaces.streamlit.persistence_state import build_storage_service
from study_planner.infrastructure.db.repositories import InMemoryStudyPlanRepository


def test_f7_settings_loads_postgres_persistence_switch(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "USE_POSTGRES_PERSISTENCE=true",
                "TEST_DATABASE_URL=postgresql://user:password@localhost:5432/study_planner_test",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_app_settings(env_file)

    assert settings.use_postgres_persistence is True
    assert settings.database_url == "postgresql://user:password@localhost:5432/study_planner_test"


def test_f7_storage_service_uses_in_memory_store_when_postgres_switch_is_off():
    settings = load_app_settings(Path("missing-env-file"))

    service = build_storage_service(settings)

    assert isinstance(service.plan_repository, InMemoryStudyPlanRepository)
