from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSettings:
    use_real_llm: bool = False
    use_real_rag_store: bool = False
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = ""
    database_url: str = ""
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "study_materials"


def load_app_settings(env_path: str | Path = ".env") -> AppSettings:
    values = _read_env_file(env_path)
    return AppSettings(
        use_real_llm=_as_bool(_get(values, "USE_REAL_LLM", "false")),
        use_real_rag_store=_as_bool(_get(values, "USE_REAL_RAG_STORE", "false")),
        deepseek_api_key=_get(values, "DEEPSEEK_API_KEY", ""),
        deepseek_base_url=_get(values, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=_get(values, "DEEPSEEK_MODEL", ""),
        database_url=_get(values, "DATABASE_URL", ""),
        milvus_uri=_get(values, "MILVUS_URI", "http://localhost:19530"),
        milvus_collection=_get(values, "MILVUS_COLLECTION", "study_materials"),
    )


def _get(values: dict[str, str], key: str, default: str = "") -> str:
    return values.get(key) or os.environ.get(key, default)


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_env_file(env_path: str | Path) -> dict[str, str]:
    path = Path(env_path)
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
