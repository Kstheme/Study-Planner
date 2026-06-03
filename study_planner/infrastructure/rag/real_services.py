from __future__ import annotations

from collections import defaultdict
import psycopg
from pymilvus import DataType, MilvusClient

from study_planner.domain.models import DocumentChunk, RetrievalResult
from study_planner.infrastructure.rag.local_services import LocalEmbeddingClient
from study_planner.infrastructure.settings import AppSettings


class PostgresMaterialRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required when USE_REAL_RAG_STORE=true.")
        self.database_url = _normalize_database_url(database_url)
        self.ensure_tables()

    def ensure_tables(self) -> None:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_materials (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        id TEXT PRIMARY KEY,
                        material_id TEXT NOT NULL REFERENCES rag_materials(id) ON DELETE CASCADE,
                        text TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page_number INTEGER,
                        chunk_index INTEGER NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            conn.commit()

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        groups: dict[str, list[DocumentChunk]] = defaultdict(list)
        for chunk in chunks:
            groups[chunk.material_id].append(chunk)

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                for material_id, material_chunks in groups.items():
                    first = material_chunks[0]
                    cursor.execute(
                        """
                        INSERT INTO rag_materials (id, filename, file_type, status, chunk_count, updated_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            filename = EXCLUDED.filename,
                            file_type = EXCLUDED.file_type,
                            status = EXCLUDED.status,
                            chunk_count = EXCLUDED.chunk_count,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            material_id,
                            first.metadata.get("filename", first.source),
                            first.metadata.get("file_type", ""),
                            "indexed",
                            len(material_chunks),
                        ),
                    )
                for chunk in chunks:
                    cursor.execute(
                        """
                        INSERT INTO rag_chunks
                            (id, material_id, text, source, page_number, chunk_index, metadata, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            text = EXCLUDED.text,
                            source = EXCLUDED.source,
                            page_number = EXCLUDED.page_number,
                            chunk_index = EXCLUDED.chunk_index,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            chunk.id,
                            chunk.material_id,
                            chunk.text,
                            chunk.source,
                            chunk.page_number,
                            chunk.chunk_index,
                            psycopg.types.json.Jsonb(chunk.metadata),
                        ),
                    )
            conn.commit()

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, DocumentChunk]:
        if not chunk_ids:
            return {}
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, material_id, text, source, page_number, chunk_index, metadata
                    FROM rag_chunks
                    WHERE id = ANY(%s)
                    """,
                    (chunk_ids,),
                )
                return {_row_to_chunk(row).id: _row_to_chunk(row) for row in cursor.fetchall()}

    def all_chunks(self) -> list[DocumentChunk]:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, material_id, text, source, page_number, chunk_index, metadata
                    FROM rag_chunks
                    ORDER BY updated_at DESC, chunk_index ASC
                    """
                )
                return [_row_to_chunk(row) for row in cursor.fetchall()]


class MilvusChunkVectorStore:
    def __init__(self, uri: str, collection_name: str, dimension: int = 3):
        self.collection_name = collection_name
        self.dimension = dimension
        self.client = MilvusClient(uri=uri)
        self.ensure_collection()

    def ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.ensure_index()
            self.client.load_collection(self.collection_name)
            return
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.dimension)
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            metric_type="COSINE",
        )
        self.ensure_index()
        self.client.load_collection(self.collection_name)

    def ensure_index(self) -> None:
        if self.client.list_indexes(self.collection_name):
            return
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self.client.create_index(self.collection_name, index_params)

    def upsert(self, chunks: list[DocumentChunk], dense_vectors: list[list[float]]) -> None:
        if not chunks:
            return
        rows = [
            {
                "id": chunk.id,
                "vector": dense_vectors[index],
                "material_id": chunk.material_id,
                "filename": chunk.metadata.get("filename", chunk.source),
                "file_type": chunk.metadata.get("file_type", ""),
                "source": chunk.source,
                "page_number": chunk.page_number or -1,
                "chunk_index": chunk.chunk_index,
            }
            for index, chunk in enumerate(chunks)
        ]
        self.client.upsert(collection_name=self.collection_name, data=rows)
        self.client.flush(self.collection_name)
        self.client.load_collection(self.collection_name)

    def search(self, query_vector: list[float], top_k: int, filters: dict | None = None) -> list[dict]:
        expression = _build_milvus_filter(filters)
        return self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            filter=expression,
            limit=top_k,
            output_fields=["id", "material_id", "filename", "file_type", "source", "page_number", "chunk_index"],
            anns_field="vector",
        )[0]


class RealRAGVectorStore:
    def __init__(
        self,
        settings: AppSettings,
        embedding_client: LocalEmbeddingClient | None = None,
        repository: PostgresMaterialRepository | None = None,
        vector_store: MilvusChunkVectorStore | None = None,
    ):
        self.settings = settings
        self.embedding_client = embedding_client or LocalEmbeddingClient()
        self.repository = repository or PostgresMaterialRepository(settings.database_url)
        self.vector_store = vector_store or MilvusChunkVectorStore(
            uri=settings.milvus_uri,
            collection_name=settings.milvus_collection,
        )

    def upsert(self, chunks, dense_vectors, sparse_vectors):
        self.repository.upsert_chunks(chunks)
        self.vector_store.upsert(chunks, dense_vectors)
        return len(chunks)

    def hybrid_search(self, query, top_k=5, filters=None):
        query_vector = self.embedding_client.embed_dense([query])[0]
        hits = self.vector_store.search(query_vector, top_k=top_k, filters=filters)
        chunk_ids = [_hit_id(hit) for hit in hits]
        chunks_by_id = self.repository.get_chunks_by_ids(chunk_ids)
        results: list[RetrievalResult] = []
        for hit in hits:
            chunk_id = _hit_id(hit)
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            results.append(RetrievalResult(chunk=chunk, score=float(hit.get("distance", hit.get("score", 0.0)))))
        return results

    def all_chunks(self) -> list[DocumentChunk]:
        return self.repository.all_chunks()


def _normalize_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _row_to_chunk(row) -> DocumentChunk:
    chunk_id, material_id, text, source, page_number, chunk_index, metadata = row
    return DocumentChunk(
        id=chunk_id,
        material_id=material_id,
        text=text,
        source=source,
        page_number=page_number,
        chunk_index=chunk_index,
        metadata=metadata or {},
    )


def _hit_id(hit: dict) -> str:
    entity = hit.get("entity") or {}
    return str(entity.get("id") or hit.get("id"))


def _build_milvus_filter(filters: dict | None) -> str:
    if not filters:
        return ""
    expressions = []
    for key, value in filters.items():
        if value is None:
            continue
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        expressions.append(f'{key} == "{escaped}"')
    return " and ".join(expressions)
