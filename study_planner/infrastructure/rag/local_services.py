from __future__ import annotations

import math
import re

from study_planner.application.material_rag import rrf_fuse
from study_planner.domain.models import DocumentChunk, RetrievalResult
from study_planner.infrastructure.rag.parsers import (
    MaterialParserRegistry,
    build_default_parser_registry,
)


class LocalDocumentParser(MaterialParserRegistry):
    def __init__(self):
        super().__init__(build_default_parser_registry().parsers)


class LocalEmbeddingClient:
    def embed_dense(self, texts):
        return [self._dense_vector(text) for text in texts]

    def embed_sparse(self, texts):
        return [self._sparse_vector(text) for text in texts]

    def _dense_vector(self, text: str):
        tokens = _tokenize(text)
        length = max(1, len(tokens))
        return [
            len(set(tokens)) / length,
            min(1.0, length / 200),
            sum(ord(char) for char in text[:50]) % 997 / 997,
        ]

    def _sparse_vector(self, text: str):
        tokens = _tokenize(text)
        counts = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        return counts


class LocalHybridVectorStore:
    def __init__(self, chunks: list[DocumentChunk] | None = None):
        self.chunks = list(chunks or [])

    def upsert(self, chunks, dense_vectors, sparse_vectors):
        existing = {chunk.id: chunk for chunk in self.chunks}
        for chunk in chunks:
            existing[chunk.id] = chunk
        self.chunks = list(existing.values())
        return len(chunks)

    def dense_search(self, query, top_k=5, filters=None):
        return self._search(query, top_k=top_k, filters=filters, mode="dense")

    def sparse_search(self, query, top_k=5, filters=None):
        return self._search(query, top_k=top_k, filters=filters, mode="sparse")

    def hybrid_search(self, query, top_k=5, filters=None):
        dense_results = self.dense_search(query, top_k=max(top_k, 10), filters=filters)
        sparse_results = self.sparse_search(query, top_k=max(top_k, 10), filters=filters)
        return rrf_fuse(dense_results, sparse_results, limit=top_k)

    def _search(self, query, top_k=5, filters=None, mode="dense"):
        query_tokens = _tokenize(query)
        results = []
        for chunk in self.chunks:
            if filters and not all(chunk.metadata.get(key) == value for key, value in filters.items()):
                continue
            chunk_tokens = _tokenize(chunk.text)
            score = _semantic_score(query_tokens, chunk_tokens) if mode == "dense" else _keyword_score(query_tokens, chunk_tokens)
            if score > 0:
                results.append(RetrievalResult(chunk=chunk, score=score))
        return sorted(results, key=lambda result: result.score, reverse=True)[:top_k]


class LocalMaterialLLM:
    def generate(self, prompt):
        if "复习卡片" in prompt:
            return "Q: 资料的核心概念是什么？\nA: 请根据资料中的定义和例子进行复习。"
        if "提取知识点" in prompt:
            return "核心概念: 资料中反复出现的重要概念\n应用方法: 将概念用于练习或项目"
        if "总结" in prompt:
            return "这份资料主要围绕核心概念、使用方法和复习重点展开。"
        if "解释概念" in prompt or "解释" in prompt:
            return "该概念可以理解为资料中描述的一种核心知识点，需要结合例子掌握。"

        context = ""
        marker = "资料："
        if marker in prompt:
            context = prompt.split(marker, 1)[1].split("问题：", 1)[0].strip()
        first_sentence = re.split(r"[。！？\n]", context)[0].strip() if context else ""
        if first_sentence:
            return f"根据资料，{first_sentence}。"
        return "没有在资料中找到足够的信息。"


def _tokenize(text: str):
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{1,4}", text.lower())
    return words


def _keyword_score(query_tokens, chunk_tokens):
    if not query_tokens or not chunk_tokens:
        return 0.0
    chunk_set = set(chunk_tokens)
    matches = sum(1 for token in query_tokens if token in chunk_set)
    return matches / len(query_tokens)


def _semantic_score(query_tokens, chunk_tokens):
    if not query_tokens or not chunk_tokens:
        return 0.0
    query_set = set(query_tokens)
    chunk_set = set(chunk_tokens)
    intersection = len(query_set & chunk_set)
    union = len(query_set | chunk_set)
    return intersection / math.sqrt(max(1, len(query_set) * len(chunk_set))) if union else 0.0
