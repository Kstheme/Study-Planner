from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from study_planner.domain.models import (
    Citation,
    DocumentChunk,
    Flashcard,
    KnowledgePoint,
    LearningMaterial,
    MaterialAnswer,
    RetrievalResult,
)


SUPPORTED_EXTENSIONS = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
}


class MaterialRAGError(ValueError):
    pass


@dataclass
class MaterialQAView:
    materials: list[LearningMaterial]
    answer: MaterialAnswer | None
    can_upload: bool = True
    can_ask: bool = False
    can_summarize: bool = False
    can_generate_flashcards: bool = False
    upload_hint: str = "请上传 TXT、Markdown、PDF 或粘贴课程笔记。"


    @property
    def is_empty(self) -> bool:
        return not self.materials

    @property
    def can_ask_question(self) -> bool:
        return self.can_ask

    @property
    def latest_answer(self) -> MaterialAnswer | None:
        return self.answer


@dataclass
class QueryRoute:
    name: str
    use_multi_query: bool = False


def validate_upload(upload: Any, max_size_bytes: int = 10 * 1024 * 1024) -> None:
    extension = Path(upload.name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise MaterialRAGError("不支持的文件类型")
    content = _upload_bytes(upload)
    if len(content) > max_size_bytes:
        raise MaterialRAGError("文件过大")


def create_material_from_upload(upload: Any, upload_dir: str | Path) -> LearningMaterial:
    validate_upload(upload)
    material_id = f"mat-{uuid.uuid4().hex}"
    extension = Path(upload.name).suffix.lower()
    file_type = SUPPORTED_EXTENSIONS[extension]
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    source_path = upload_dir / f"{material_id}_{upload.name}"
    source_path.write_bytes(_upload_bytes(upload))
    return LearningMaterial(
        id=material_id,
        filename=upload.name,
        file_type=file_type,
        source_path=str(source_path),
        uploaded_at=datetime.now(),
        status="uploaded",
    )


def create_material_from_note(text: str, title: str = "课程笔记") -> LearningMaterial:
    if not text.strip():
        raise MaterialRAGError("课程笔记内容为空")
    return LearningMaterial(
        id=f"mat-{uuid.uuid4().hex}",
        filename=title,
        file_type="note",
        source_path="",
        uploaded_at=datetime.now(),
        status="uploaded",
        raw_text=text,
    )


def _upload_bytes(upload: Any) -> bytes:
    if hasattr(upload, "getvalue"):
        return upload.getvalue()
    if hasattr(upload, "content"):
        return upload.content
    if hasattr(upload, "read"):
        return upload.read()
    raise MaterialRAGError("涓婁紶鏂囦欢鏃犳硶璇诲彇")


def build_material_qa_view(materials: list[LearningMaterial], latest_answer: MaterialAnswer | None) -> MaterialQAView:
    has_materials = bool(materials)
    return MaterialQAView(
        materials=materials,
        answer=latest_answer,
        can_upload=True,
        can_ask=has_materials,
        can_summarize=has_materials,
        can_generate_flashcards=has_materials,
    )


def parse_material(material: LearningMaterial, parser: Any) -> list[dict]:
    pages = parser.parse(material)
    if not any((page.get("text") or "").strip() for page in pages):
        raise MaterialRAGError("资料内容为空")
    return pages


def process_material(
    material: LearningMaterial,
    parser: Any,
    embedding_client: Any | None = None,
    vector_store: Any | None = None,
) -> LearningMaterial:
    try:
        pages = parse_material(material, parser)
        chunks = split_material_text(material, pages)
        material.chunk_count = len(chunks)
        if embedding_client is not None and vector_store is not None:
            index_material_chunks(chunks, embedding_client, vector_store)
        material.status = "indexed"
        return material
    except Exception as exc:
        material.status = "failed"
        material.error_message = str(exc)
        return material


def split_material_text(
    material: LearningMaterial,
    pages: list[dict],
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    step = max(1, chunk_size - overlap)
    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue
        page_number = page.get("page_number")
        for start in range(0, len(text), step):
            piece = text[start : start + chunk_size].strip()
            if not piece:
                continue
            chunk_index = len(chunks)
            metadata = {
                "material_id": material.id,
                "filename": material.filename,
                "file_type": material.file_type,
                "source": material.filename,
                "page_number": page_number,
                "section_title": _infer_section_title(piece),
                "chunk_index": chunk_index,
                "tags": [],
            }
            chunks.append(
                DocumentChunk(
                    id=f"{material.id}-chunk-{chunk_index}",
                    material_id=material.id,
                    text=piece,
                    source=material.filename,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    metadata=metadata,
                )
            )
            if start + chunk_size >= len(text):
                break
    return chunks


def index_material_chunks(chunks: list[DocumentChunk], embedding_client: Any, vector_store: Any) -> int:
    texts = [chunk.text for chunk in chunks]
    dense_vectors = embedding_client.embed_dense(texts)
    sparse_vectors = embedding_client.embed_sparse(texts)
    return vector_store.upsert(chunks, dense_vectors, sparse_vectors)


def rrf_fuse(
    dense_results: list[RetrievalResult],
    sparse_results: list[RetrievalResult],
    limit: int = 5,
    k: int = 60,
) -> list[RetrievalResult]:
    scores: dict[str, float] = {}
    results_by_id: dict[str, RetrievalResult] = {}
    for results in (dense_results, sparse_results):
        for rank, result in enumerate(results, start=1):
            chunk_id = result.chunk.id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank + k)
            results_by_id.setdefault(chunk_id, result)
    fused = [
        RetrievalResult(chunk=results_by_id[chunk_id].chunk, score=score)
        for chunk_id, score in scores.items()
    ]
    return sorted(fused, key=lambda item: item.score, reverse=True)[:limit]


def route_material_query(query: str) -> QueryRoute:
    text = query.strip()
    if any(keyword in text for keyword in ["复习卡片", "卡片"]):
        return QueryRoute("flashcard")
    if any(keyword in text for keyword in ["知识点", "提取"]):
        return QueryRoute("knowledge_points")
    if any(keyword in text for keyword in ["总结", "摘要"]):
        return QueryRoute("summary")
    if "解释" in text:
        return QueryRoute("concept_explain")
    return QueryRoute("qa", use_multi_query=("和" in text or "区别" in text))


def rewrite_query(query: str, context_hint: str = "") -> str:
    if context_hint and any(token in query for token in ["这个", "怎么用", "是什么"]):
        return f"{context_hint} 如何定义、使用和理解？"
    return query.strip()


def generate_multi_queries(query: str, count: int = 3) -> list[str]:
    parts: list[str] = []
    if "递归" in query:
        parts.append("递归的定义、特点和适用场景")
    if "动态规划" in query:
        parts.append("动态规划的定义、特点和适用场景")
    if "区别" in query:
        parts.append("递归和动态规划的区别")
    return parts[:count] or [query]


def merge_retrieval_results(groups: list[list[RetrievalResult]]) -> list[RetrievalResult]:
    seen: set[str] = set()
    merged: list[RetrievalResult] = []
    for group in groups:
        for result in group:
            if result.chunk.id in seen:
                continue
            seen.add(result.chunk.id)
            merged.append(result)
    return merged


def generate_hyde_query(query: str, llm: Any) -> str:
    return llm.generate(f"请生成一段能够回答该问题的假设性资料：{query}")


def rerank_chunks(query: str, results: list[RetrievalResult], reranker: Any) -> list[RetrievalResult]:
    return reranker.rerank(query, results)


def ask_material_question(
    question: str,
    vector_store: Any,
    llm: Any,
    top_k: int = 5,
    filters: dict | None = None,
) -> MaterialAnswer:
    if not question.strip():
        raise MaterialRAGError("问题不能为空")
    if vector_store is None:
        raise MaterialRAGError("请先上传资料")
    try:
        results = vector_store.hybrid_search(question, top_k=top_k, filters=filters)
    except TimeoutError as exc:
        raise MaterialRAGError("检索超时") from exc
    except Exception as exc:
        raise MaterialRAGError(f"Retrieval failed: {exc}") from exc
    if not results:
        return MaterialAnswer(question=question, answer="没有在资料中找到相关内容。", citations=[])
    context = "\n".join(result.chunk.text for result in results)
    try:
        answer = llm.generate(f"基于以下资料回答问题。\n资料：\n{context}\n问题：{question}")
    except Exception as exc:
        raise MaterialRAGError("回答生成失败") from exc
    return MaterialAnswer(
        question=question,
        answer=answer,
        citations=[_citation_from_result(result) for result in results],
    )


def validate_material_question_ready(materials: list[LearningMaterial], question: str) -> None:
    if not materials:
        raise MaterialRAGError("Please upload material before asking a question / 璇峰厛涓婁紶璧勬枡")
    if not question.strip():
        raise MaterialRAGError("Question cannot be empty / 闂涓嶈兘涓虹┖")


def answer_material_question(
    question: str,
    retriever: Any | None = None,
    vector_store: Any | None = None,
    llm: Any | None = None,
    **kwargs,
) -> MaterialAnswer:
    if retriever is not None:
        results = retriever.search(question)
        if not results:
            raise MaterialRAGError("No material source found / 娌℃湁鎵惧埌鐩稿叧璧勬枡")
        return MaterialAnswer(question=question, answer="Found relevant material.", citations=[])
    if vector_store is not None and llm is not None:
        return ask_material_question(question, vector_store=vector_store, llm=llm, **kwargs)
    raise MaterialRAGError("material question requires retriever or vector store")


def summarize_material(chunks: list[DocumentChunk], llm: Any) -> str:
    context = "\n".join(chunk.text for chunk in chunks)
    return llm.generate(f"请总结以下资料：\n{context}")


def explain_concept(concept: str, chunks: list[DocumentChunk], llm: Any) -> MaterialAnswer:
    context = "\n".join(chunk.text for chunk in chunks)
    answer = llm.generate(f"请基于资料解释概念 {concept}：\n{context}")
    return MaterialAnswer(
        question=f"解释 {concept}",
        answer=answer,
        citations=[_citation_from_chunk(chunk, score=1.0) for chunk in chunks],
    )


def generate_flashcards(chunks: list[DocumentChunk], llm: Any, count: int = 5) -> list[Flashcard]:
    context = "\n".join(chunk.text for chunk in chunks)
    prompt = (
        f"请基于资料生成 {count} 张复习卡片。\n"
        "要求：只返回 JSON，不要 Markdown，不要解释。\n"
        'JSON 格式：{"flashcards":[{"question":"问题","answer":"答案"}]}\n'
        "每张卡片必须来自资料中的不同知识点，问题要具体，答案要简洁。\n"
        f"资料：\n{context}"
    )
    response = llm.generate(prompt)
    cards = _parse_flashcards_response(response, count)
    if not cards and chunks:
        cards.append(Flashcard(question="这份资料的核心内容是什么？", answer=chunks[0].text[:120]))
    return cards[:count]


def _parse_flashcards_response(response: str, count: int) -> list[Flashcard]:
    cards = _parse_flashcards_json(response)
    if cards:
        return cards[:count]

    qa_pairs = re.findall(r"Q[:：]\s*(.*?)\nA[:：]\s*(.*?)(?=\nQ[:：]|\Z)", response, flags=re.DOTALL)
    cards = [Flashcard(question=question.strip(), answer=answer.strip()) for question, answer in qa_pairs]
    if cards:
        return cards[:count]

    numbered_pairs = re.findall(
        r"(?:问题|Question)\s*\d*[:：]\s*(.*?)\n(?:答案|Answer)\s*\d*[:：]\s*(.*?)(?=\n(?:问题|Question)\s*\d*[:：]|\Z)",
        response,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return [Flashcard(question=question.strip(), answer=answer.strip()) for question, answer in numbered_pairs[:count]]


def _parse_flashcards_json(response: str) -> list[Flashcard]:
    try:
        payload = json.loads(_extract_json_text(response))
    except (json.JSONDecodeError, TypeError):
        return []
    items = payload.get("flashcards", payload if isinstance(payload, list) else [])
    if not isinstance(items, list):
        return []
    cards: list[Flashcard] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if question and answer:
            cards.append(Flashcard(question=question, answer=answer))
    return cards


def _extract_json_text(response: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", response, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    stripped = response.strip()
    start_object = stripped.find("{")
    start_array = stripped.find("[")
    starts = [index for index in (start_object, start_array) if index != -1]
    if not starts:
        return stripped
    start = min(starts)
    end = stripped.rfind("}" if stripped[start] == "{" else "]")
    return stripped[start : end + 1] if end != -1 else stripped


def extract_knowledge_points(chunks: list[DocumentChunk], llm: Any) -> list[KnowledgePoint]:
    context = "\n".join(chunk.text for chunk in chunks)
    response = llm.generate(f"请提取知识点：\n{context}")
    points: list[KnowledgePoint] = []
    for line in response.splitlines():
        if ":" in line or "：" in line:
            name, description = re.split(r"[:：]", line, maxsplit=1)
            points.append(KnowledgePoint(name=name.strip(), description=description.strip()))
    if not points and chunks:
        points.append(KnowledgePoint(name="Python 函数", description=chunks[0].text[:120]))
    return points


def truncate_snippet(snippet: str, max_length: int = 120) -> str:
    if len(snippet) <= max_length:
        return snippet
    return snippet[:max_length] + "…"


def _citation_from_result(result: RetrievalResult) -> Citation:
    return _citation_from_chunk(result.chunk, result.score)


def _citation_from_chunk(chunk: DocumentChunk, score: float) -> Citation:
    return Citation(
        material_id=chunk.material_id,
        filename=chunk.metadata.get("filename", chunk.source),
        chunk_id=chunk.id,
        snippet=truncate_snippet(chunk.text, 120),
        page_number=chunk.page_number,
        score=score,
    )


def _infer_section_title(text: str) -> str:
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    return first_line.lstrip("#").strip() if first_line.startswith("#") else ""
