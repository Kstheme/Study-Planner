from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from study_planner.domain.models import DocumentChunk
from study_planner.infrastructure.llm.material_llm import DeepSeekMaterialLLM
from study_planner.infrastructure.rag.local_services import (
    LocalDocumentParser,
    LocalEmbeddingClient,
    LocalHybridVectorStore,
    LocalMaterialLLM,
)
from study_planner.infrastructure.rag.real_services import RealRAGVectorStore
from study_planner.infrastructure.settings import AppSettings, load_app_settings


@dataclass
class MaterialRAGServices:
    parser: object
    embedding_client: object
    vector_store: object
    llm: object
    settings: AppSettings


def build_material_rag_services(
    env_path: str | Path,
    local_chunks: list[DocumentChunk] | None = None,
) -> MaterialRAGServices:
    settings = load_app_settings(env_path)
    return MaterialRAGServices(
        parser=LocalDocumentParser(),
        embedding_client=LocalEmbeddingClient(),
        vector_store=_build_vector_store(settings, local_chunks or []),
        llm=_build_llm(settings),
        settings=settings,
    )


def _build_llm(settings: AppSettings):
    if settings.use_real_llm:
        return DeepSeekMaterialLLM.from_settings(settings)
    return LocalMaterialLLM()


def _build_vector_store(settings: AppSettings, local_chunks: list[DocumentChunk]):
    if settings.use_real_rag_store:
        return RealRAGVectorStore(settings)
    return LocalHybridVectorStore(local_chunks)
