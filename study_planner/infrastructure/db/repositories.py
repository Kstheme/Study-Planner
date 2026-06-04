from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from typing import Any, Callable
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from study_planner.application.persistence import ExportRecord, StorageError
from study_planner.application.plan_dashboard import VALID_TASK_STATUSES
from study_planner.domain.models import (
    LearningMaterial,
    ReviewReport,
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TaskProgress,
    TimeBudget,
    WeeklyPlan,
)


Clock = Callable[[], datetime]


class _InMemoryEntityRepository:
    table_name = ""
    id_prefix = "row"

    def __init__(self, clock: Clock | None = None):
        self.clock = clock or datetime.now
        self._rows: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._sequence = 0

    def get_by_id(self, entity_id: str):
        value = self._rows.get(entity_id)
        return deepcopy(value) if value is not None else None

    def metadata(self, entity_id: str) -> dict[str, Any]:
        metadata = self._metadata.get(entity_id)
        return deepcopy(metadata) if metadata is not None else {}

    def get_latest(self):
        if not self._rows:
            return None
        latest_id = max(self._rows, key=lambda entity_id: self._latest_key(entity_id))
        return self.get_by_id(latest_id)

    def delete(self, entity_id: str) -> None:
        self._rows.pop(entity_id, None)
        self._metadata.pop(entity_id, None)

    def table_exists(self, name: str) -> bool:
        return name == self.table_name

    def _next_id(self) -> str:
        self._sequence += 1
        return f"{self.id_prefix}-{self._sequence}"

    def _insert(self, value: Any, extra_metadata: dict[str, Any] | None = None, entity_id: str | None = None) -> str:
        now = self.clock()
        entity_id = entity_id or self._next_id()
        self._rows[entity_id] = deepcopy(value)
        self._metadata[entity_id] = {
            "id": entity_id,
            "created_at": now,
            "updated_at": now,
            "_order": self._sequence,
            **(extra_metadata or {}),
        }
        return entity_id

    def _touch(self, entity_id: str) -> None:
        self._sequence += 1
        self._metadata[entity_id]["updated_at"] = self.clock()
        self._metadata[entity_id]["_order"] = self._sequence

    def _latest_key(self, entity_id: str):
        metadata = self._metadata[entity_id]
        return metadata["updated_at"], metadata.get("_order", 0)


class InMemoryStudyGoalRepository(_InMemoryEntityRepository):
    table_name = "study_goals"
    id_prefix = "goal"

    def save(self, goal: StudyGoal) -> str:
        return self._insert(goal)


class InMemoryStudyPlanRepository(_InMemoryEntityRepository):
    table_name = "study_plans"
    id_prefix = "plan"

    def __init__(self, clock: Clock | None = None):
        super().__init__(clock=clock)
        self.fail_next_save = False

    def save(self, plan: StudyPlan, goal_id: str | None = None) -> str:
        if self.fail_next_save:
            self.fail_next_save = False
            raise RuntimeError("database unavailable")
        return self._insert(plan, {"goal_id": goal_id})

    def metadata_latest(self) -> dict[str, Any]:
        if not self._rows:
            return {}
        latest_id = max(self._rows, key=lambda entity_id: self._latest_key(entity_id))
        return self.metadata(latest_id)

    def update_task(
        self,
        plan_id: str,
        task_id: str,
        status: str | None = None,
        new_date: date | None = None,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> StudyPlan:
        plan = self.get_by_id(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        task = _find_task(plan, task_id)
        if status is not None:
            if status not in VALID_TASK_STATUSES:
                raise ValueError("invalid task status 状态")
            task.status = status
        if new_date is not None:
            task.date = new_date
        if duration_minutes is not None:
            if duration_minutes <= 0:
                raise ValueError("invalid task duration minutes")
            task.duration_minutes = duration_minutes
        if notes is not None:
            task.notes = notes
        self._rows[plan_id] = deepcopy(plan)
        self._touch(plan_id)
        return deepcopy(plan)


class InMemoryTaskProgressRepository(_InMemoryEntityRepository):
    table_name = "task_progress"
    id_prefix = "progress"

    def save(self, progress: TaskProgress) -> str:
        return self._insert(progress)

    def save_progress(self, progress: TaskProgress) -> str:
        return self.save(progress)


class InMemoryReviewReportRepository(_InMemoryEntityRepository):
    table_name = "review_reports"
    id_prefix = "review"

    def save(self, report: ReviewReport, plan_id: str | None = None) -> str:
        return self._insert(report, {"plan_id": plan_id})

    def get_latest(self, plan_id: str | None = None):
        ids = [
            entity_id
            for entity_id in self._rows
            if plan_id is None or self._metadata[entity_id].get("plan_id") == plan_id
        ]
        if not ids:
            return None
        latest_id = max(ids, key=lambda entity_id: self._latest_key(entity_id))
        return self.get_by_id(latest_id)

    def list_by_plan_id(self, plan_id: str) -> list[ReviewReport]:
        ids = [entity_id for entity_id in self._rows if self._metadata[entity_id].get("plan_id") == plan_id]
        ids.sort(key=lambda entity_id: self._metadata[entity_id]["created_at"])
        return [self.get_by_id(entity_id) for entity_id in ids]


class InMemoryMaterialRepository:
    table_name = "materials"

    def __init__(self, clock: Clock | None = None):
        self.clock = clock or datetime.now
        self._rows: dict[str, LearningMaterial] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def save(self, material: LearningMaterial) -> str:
        now = self.clock()
        self._rows[material.id] = deepcopy(material)
        self._metadata[material.id] = {"id": material.id, "created_at": now, "updated_at": now}
        return material.id

    def get_by_id(self, material_id: str) -> LearningMaterial | None:
        value = self._rows.get(material_id)
        return deepcopy(value) if value is not None else None

    def list_all(self) -> list[LearningMaterial]:
        return [deepcopy(value) for value in self._rows.values()]

    def update_status(
        self,
        material_id: str,
        status: str,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> LearningMaterial:
        material = self.get_by_id(material_id)
        if material is None:
            raise KeyError(material_id)
        material.status = status
        if chunk_count is not None:
            material.chunk_count = chunk_count
        if error_message is not None:
            material.error_message = error_message
        self._rows[material_id] = deepcopy(material)
        self._metadata[material_id]["updated_at"] = self.clock()
        return deepcopy(material)

    def table_exists(self, name: str) -> bool:
        return name == self.table_name


class InMemoryExportRecordRepository(_InMemoryEntityRepository):
    table_name = "export_records"
    id_prefix = "export"

    def save(self, record: ExportRecord) -> str:
        return self._insert(record)


class JsonPayloadCodec:
    def __init__(self, schema_version: int = 1):
        self.schema_version = schema_version

    def to_jsonable(self, value: Any) -> dict[str, Any]:
        payload = _to_jsonable(value)
        if not isinstance(payload, dict):
            raise TypeError("payload root must be a JSON object")
        payload["schema_version"] = self.schema_version
        return payload

    def study_plan_from_jsonable(self, payload: dict[str, Any]) -> StudyPlan:
        payload = dict(payload)
        payload.pop("schema_version", None)
        return _study_plan_from_payload(payload)


class DatabaseInitializer:
    def __init__(self):
        self._tables: set[str] = set()

    def initialize(self) -> None:
        self._tables.update({"study_goals", "study_plans", "task_progress", "review_reports", "materials"})

    def has_table(self, name: str) -> bool:
        return name in self._tables


class PostgresDatabaseInitializer:
    table_names = ("study_goals", "study_plans", "task_progress", "review_reports", "materials", "export_records")

    def __init__(self, database_url: str, schema: str = "public", connection_factory: Callable | None = None):
        self.database_url = _normalize_database_url(database_url)
        self.schema = schema
        self.connection_factory = connection_factory or psycopg.connect

    def initialize(self) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
                    cursor.execute(
                        self._create_table_sql(
                            "study_goals",
                            """
                            id TEXT PRIMARY KEY,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                    cursor.execute(
                        self._create_table_sql(
                            "study_plans",
                            """
                            id TEXT PRIMARY KEY,
                            goal_id TEXT,
                            payload JSONB NOT NULL,
                            schema_version INTEGER NOT NULL DEFAULT 1,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                    cursor.execute(
                        self._create_table_sql(
                            "task_progress",
                            """
                            id TEXT PRIMARY KEY,
                            task_id TEXT NOT NULL,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                    cursor.execute(
                        self._create_table_sql(
                            "review_reports",
                            """
                            id TEXT PRIMARY KEY,
                            plan_id TEXT,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                    cursor.execute(
                        self._create_table_sql(
                            "materials",
                            """
                            id TEXT PRIMARY KEY,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                    cursor.execute(
                        self._create_table_sql(
                            "export_records",
                            """
                            id TEXT PRIMARY KEY,
                            plan_id TEXT NOT NULL,
                            format TEXT NOT NULL,
                            filename TEXT NOT NULL,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                            """,
                        )
                    )
                conn.commit()
        except Exception as exc:
            raise _postgres_error("database initialization failed") from exc

    def drop_all(self) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
                conn.commit()
        except Exception as exc:
            raise _postgres_error("database cleanup failed") from exc

    def has_table(self, name: str) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = %s AND table_name = %s
                        )
                        """,
                        (self.schema, name),
                    )
                    return bool(cursor.fetchone()[0])
        except Exception as exc:
            raise _postgres_error("database table check failed") from exc

    def _connect(self):
        return _connect_with_timeout(self.connection_factory, self.database_url)

    def _create_table_sql(self, table_name: str, columns_sql: str):
        return sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
            sql.Identifier(self.schema),
            sql.Identifier(table_name),
            sql.SQL(columns_sql),
        )


class _PostgresJsonRepository:
    table_name = ""
    id_prefix = "row"

    def __init__(self, database_url: str, schema: str = "public", connection_factory: Callable | None = None):
        self.database_url = _normalize_database_url(database_url)
        self.schema = schema
        self.connection_factory = connection_factory or psycopg.connect

    def get_by_id(self, entity_id: str):
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        self._select_sql("WHERE id = %s"),
                        (entity_id,),
                    )
                    row = cursor.fetchone()
            return self._value_from_row(row) if row else None
        except Exception as exc:
            raise _postgres_error("database read failed") from exc

    def metadata(self, entity_id: str) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        self._metadata_sql("WHERE id = %s"),
                        (entity_id,),
                    )
                    row = cursor.fetchone()
            return self._metadata_from_row(row) if row else {}
        except Exception as exc:
            raise _postgres_error("database metadata read failed") from exc

    def get_latest(self):
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(self._select_sql("ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT 1"))
                    row = cursor.fetchone()
            return self._value_from_row(row) if row else None
        except Exception as exc:
            raise _postgres_error("database read failed") from exc

    def delete(self, entity_id: str) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DELETE FROM {}.{} WHERE id = %s").format(
                            sql.Identifier(self.schema),
                            sql.Identifier(self.table_name),
                        ),
                        (entity_id,),
                    )
                conn.commit()
        except Exception as exc:
            raise _postgres_error("database delete failed") from exc

    def table_exists(self, name: str) -> bool:
        return PostgresDatabaseInitializer(
            self.database_url,
            schema=self.schema,
            connection_factory=self.connection_factory,
        ).has_table(name)

    def _insert_payload(
        self,
        value: Any,
        extra_columns: dict[str, Any] | None = None,
        entity_id: str | None = None,
    ) -> str:
        entity_id = entity_id or _new_id(self.id_prefix)
        payload = self._payload_for_save(value)
        extra_columns = extra_columns or {}
        column_names = ["id", *extra_columns.keys(), "payload"]
        values = [entity_id, *extra_columns.values(), Jsonb(payload)]
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
        assignments = [
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
            for column in [*extra_columns.keys(), "payload"]
        ]
        assignments.append(sql.SQL("updated_at = clock_timestamp()"))
        query = sql.SQL(
            "INSERT INTO {}.{} ({}) VALUES ({}) "
            "ON CONFLICT (id) DO UPDATE SET {}"
        ).format(
            sql.Identifier(self.schema),
            sql.Identifier(self.table_name),
            sql.SQL(", ").join(sql.Identifier(column) for column in column_names),
            placeholders,
            sql.SQL(", ").join(assignments),
        )
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, values)
                conn.commit()
            return entity_id
        except Exception as exc:
            raise _postgres_error("database save failed") from exc

    def _connect(self):
        return _connect_with_timeout(self.connection_factory, self.database_url)

    def _table_sql(self):
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(self.table_name))

    def _select_sql(self, suffix: str):
        return sql.SQL("SELECT id, payload, created_at, updated_at FROM {}.{} {}").format(
            sql.Identifier(self.schema),
            sql.Identifier(self.table_name),
            sql.SQL(suffix),
        )

    def _metadata_sql(self, suffix: str):
        return sql.SQL("SELECT id, created_at, updated_at FROM {}.{} {}").format(
            sql.Identifier(self.schema),
            sql.Identifier(self.table_name),
            sql.SQL(suffix),
        )

    def _payload_for_save(self, value: Any) -> dict[str, Any]:
        payload = _to_jsonable(value)
        if not isinstance(payload, dict):
            raise TypeError("repository payload root must be object")
        return payload

    def _value_from_row(self, row):
        return self._from_payload(row[1])

    def _metadata_from_row(self, row) -> dict[str, Any]:
        entity_id, created_at, updated_at = row
        return {"id": entity_id, "created_at": created_at, "updated_at": updated_at}

    def _from_payload(self, payload: dict[str, Any]):
        return payload


class PostgresStudyGoalRepository(_PostgresJsonRepository):
    table_name = "study_goals"
    id_prefix = "goal"

    def save(self, goal: StudyGoal) -> str:
        return self._insert_payload(goal)

    def _from_payload(self, payload: dict[str, Any]) -> StudyGoal:
        return _dataclass_from_payload(StudyGoal, payload)


class PostgresStudyPlanRepository(_PostgresJsonRepository):
    table_name = "study_plans"
    id_prefix = "plan"

    def __init__(
        self,
        database_url: str | DatabaseInitializer | None = None,
        schema: str = "public",
        connection_factory: Callable | None = None,
        initializer: DatabaseInitializer | None = None,
    ):
        legacy_initializer = initializer or (database_url if isinstance(database_url, DatabaseInitializer) else None)
        self._legacy_initializer = legacy_initializer
        if legacy_initializer is not None:
            self.initializer = legacy_initializer
            self.database_url = ""
            self.schema = schema
            self.connection_factory = connection_factory or psycopg.connect
            return
        super().__init__(database_url or "", schema=schema, connection_factory=connection_factory)
        self.codec = JsonPayloadCodec(schema_version=1)

    def save(self, plan: StudyPlan, goal_id: str | None = None) -> str:
        payload = self.codec.to_jsonable(plan)
        return self._insert_payload(payload, {"goal_id": goal_id, "schema_version": self.codec.schema_version})

    def get_latest(self) -> StudyPlan | None:
        if self._legacy_initializer is not None:
            if not self.initializer.has_table("study_plans"):
                raise StorageError("database not initialized: missing table study_plans")
            return None
        return super().get_latest()

    def metadata(self, entity_id: str) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, goal_id, schema_version, created_at, updated_at "
                            "FROM {}.{} WHERE id = %s"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name)),
                        (entity_id,),
                    )
                    row = cursor.fetchone()
            if not row:
                return {}
            entity_id, goal_id, schema_version, created_at, updated_at = row
            return {
                "id": entity_id,
                "goal_id": goal_id,
                "schema_version": schema_version,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        except Exception as exc:
            raise _postgres_error("database metadata read failed") from exc

    def metadata_latest(self) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, goal_id, schema_version, created_at, updated_at "
                            "FROM {}.{} ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT 1"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name))
                    )
                    row = cursor.fetchone()
            if not row:
                return {}
            entity_id, goal_id, schema_version, created_at, updated_at = row
            return {
                "id": entity_id,
                "goal_id": goal_id,
                "schema_version": schema_version,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        except Exception as exc:
            raise _postgres_error("database metadata read failed") from exc

    def update_task(
        self,
        plan_id: str,
        task_id: str,
        status: str | None = None,
        new_date: date | None = None,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> StudyPlan:
        plan = self.get_by_id(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        task = _find_task(plan, task_id)
        if status is not None:
            if status not in VALID_TASK_STATUSES:
                raise ValueError("invalid task status 状态")
            task.status = status
        if new_date is not None:
            task.date = new_date
        if duration_minutes is not None:
            if duration_minutes <= 0:
                raise ValueError("invalid task duration minutes")
            task.duration_minutes = duration_minutes
        if notes is not None:
            task.notes = notes
        payload = self.codec.to_jsonable(plan)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "UPDATE {}.{} SET payload = %s, schema_version = %s, updated_at = clock_timestamp() "
                            "WHERE id = %s"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name)),
                        (Jsonb(payload), self.codec.schema_version, plan_id),
                    )
                conn.commit()
            return deepcopy(plan)
        except Exception as exc:
            raise _postgres_error("database task update failed") from exc

    def _payload_for_save(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else self.codec.to_jsonable(value)

    def _from_payload(self, payload: dict[str, Any]) -> StudyPlan:
        return self.codec.study_plan_from_jsonable(payload)


class PostgresTaskProgressRepository(_PostgresJsonRepository):
    table_name = "task_progress"
    id_prefix = "progress"

    def save(self, progress: TaskProgress) -> str:
        return self.save_progress(progress)

    def save_progress(self, progress: TaskProgress) -> str:
        return self._insert_payload(progress, {"task_id": progress.task_id})

    def list_by_task_id(self, task_id: str) -> list[TaskProgress]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, payload, created_at, updated_at FROM {}.{} "
                            "WHERE task_id = %s ORDER BY created_at ASC, id ASC"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name)),
                        (task_id,),
                    )
                    rows = cursor.fetchall()
            return [self._value_from_row(row) for row in rows]
        except Exception as exc:
            raise _postgres_error("database progress read failed") from exc

    def _from_payload(self, payload: dict[str, Any]) -> TaskProgress:
        return _dataclass_from_payload(TaskProgress, payload)


class PostgresReviewReportRepository(_PostgresJsonRepository):
    table_name = "review_reports"
    id_prefix = "review"

    def save(self, report: ReviewReport, plan_id: str | None = None) -> str:
        return self._insert_payload(report, {"plan_id": plan_id})

    def get_latest(self, plan_id: str | None = None):
        where = "WHERE plan_id = %s " if plan_id is not None else ""
        params = (plan_id,) if plan_id is not None else ()
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, payload, created_at, updated_at FROM {}.{} "
                            "{}ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT 1"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name), sql.SQL(where)),
                        params,
                    )
                    row = cursor.fetchone()
            return self._value_from_row(row) if row else None
        except Exception as exc:
            raise _postgres_error("database review read failed") from exc

    def list_by_plan_id(self, plan_id: str) -> list[ReviewReport]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, payload, created_at, updated_at FROM {}.{} "
                            "WHERE plan_id = %s ORDER BY created_at ASC, id ASC"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name)),
                        (plan_id,),
                    )
                    rows = cursor.fetchall()
            return [self._value_from_row(row) for row in rows]
        except Exception as exc:
            raise _postgres_error("database review read failed") from exc

    def _from_payload(self, payload: dict[str, Any]) -> ReviewReport:
        return _dataclass_from_payload(ReviewReport, payload)


class PostgresMaterialRepository(_PostgresJsonRepository):
    table_name = "materials"
    id_prefix = "material"

    def save(self, material: LearningMaterial) -> str:
        return self._insert_payload(material, entity_id=material.id)

    def list_all(self) -> list[LearningMaterial]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, payload, created_at, updated_at FROM {}.{} "
                            "ORDER BY created_at ASC, id ASC"
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table_name))
                    )
                    rows = cursor.fetchall()
            return [self._value_from_row(row) for row in rows]
        except Exception as exc:
            raise _postgres_error("database material read failed") from exc

    def update_status(
        self,
        material_id: str,
        status: str,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> LearningMaterial:
        material = self.get_by_id(material_id)
        if material is None:
            raise KeyError(material_id)
        material.status = status
        if chunk_count is not None:
            material.chunk_count = chunk_count
        if error_message is not None:
            material.error_message = error_message
        self._insert_payload(material, entity_id=material_id)
        return material

    def _from_payload(self, payload: dict[str, Any]) -> LearningMaterial:
        return _dataclass_from_payload(LearningMaterial, payload)


class PostgresExportRecordRepository(_PostgresJsonRepository):
    table_name = "export_records"
    id_prefix = "export"

    def save(self, record: ExportRecord) -> str:
        return self._insert_payload(
            record,
            {
                "plan_id": record.plan_id,
                "format": record.format,
                "filename": record.filename,
            },
        )

    def _from_payload(self, payload: dict[str, Any]) -> ExportRecord:
        return _dataclass_from_payload(ExportRecord, payload)


def _normalize_database_url(database_url: str) -> str:
    return (database_url or "").replace("postgresql+psycopg://", "postgresql://", 1)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _postgres_error(message: str) -> StorageError:
    return StorageError(f"{message}: storage unavailable")


def _connect_with_timeout(connection_factory: Callable, database_url: str):
    try:
        return connection_factory(database_url, connect_timeout=3)
    except TypeError:
        return connection_factory(database_url)


def _find_task(plan: StudyPlan, task_id: str) -> StudyTask:
    for phase in plan.phases:
        for week in phase.weekly_plans:
            for task in week.tasks:
                if task.id == task_id:
                    return task
    raise KeyError(task_id)


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return deepcopy(value)


def _study_plan_from_payload(payload: dict[str, Any]) -> StudyPlan:
    return StudyPlan(
        goal=_dataclass_from_payload(StudyGoal, payload["goal"]),
        overall_route=payload["overall_route"],
        phases=[
            StudyPhase(
                phase_index=phase["phase_index"],
                title=phase["title"],
                objective=phase["objective"],
                start_date=_parse_date(phase["start_date"]),
                end_date=_parse_date(phase["end_date"]),
                milestone=phase["milestone"],
                weekly_plans=[
                    WeeklyPlan(
                        week_index=week["week_index"],
                        start_date=_parse_date(week["start_date"]),
                        end_date=_parse_date(week["end_date"]),
                        objective=week["objective"],
                        tasks=[_dataclass_from_payload(StudyTask, task) for task in week.get("tasks", [])],
                        review_focus=week.get("review_focus", ""),
                    )
                    for week in phase.get("weekly_plans", [])
                ],
            )
            for phase in payload.get("phases", [])
        ],
        methods=list(payload.get("methods", [])),
        time_budget=_dataclass_from_payload(TimeBudget, payload["time_budget"]),
        risks=list(payload.get("risks", [])),
        review_schedule=_dataclass_from_payload(ReviewSchedule, payload["review_schedule"]),
        suggestions=payload.get("suggestions", ""),
    )


def _dataclass_from_payload(cls: type, payload: dict[str, Any]):
    data = dict(payload)
    for field in fields(cls):
        if field.name not in data:
            continue
        if field.type is date or field.name.endswith("_date") or field.name == "deadline":
            data[field.name] = _parse_date(data[field.name])
        elif field.type is datetime or field.name.endswith("_at"):
            data[field.name] = _parse_datetime(data[field.name])
    return cls(**data)


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
