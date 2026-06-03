from datetime import datetime

import pytest

from study_planner.application.material_rag import (
    MaterialRAGError,
    ask_material_question,
    build_material_qa_view,
    create_material_from_note,
    create_material_from_upload,
    explain_concept,
    extract_knowledge_points,
    generate_flashcards,
    generate_hyde_query,
    generate_multi_queries,
    index_material_chunks,
    merge_retrieval_results,
    parse_material,
    process_material,
    rerank_chunks,
    rewrite_query,
    route_material_query,
    rrf_fuse,
    split_material_text,
    summarize_material,
    truncate_snippet,
    validate_upload,
)
from study_planner.domain.models import (
    Citation,
    DocumentChunk,
    Flashcard,
    KnowledgePoint,
    LearningMaterial,
    MaterialAnswer,
    RetrievalResult,
)


class FakeUpload:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self.content = content

    def read(self):
        return self.content


class FakeParser:
    def __init__(self, pages=None, error=None):
        self.pages = pages or [{"text": "Python 函数用于封装可复用代码。", "page_number": 1}]
        self.error = error

    def parse(self, material: LearningMaterial):
        if self.error:
            raise self.error
        return self.pages


class FakeEmbeddingClient:
    def __init__(self, error=None):
        self.error = error

    def embed_dense(self, texts):
        if self.error:
            raise self.error
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_sparse(self, texts):
        if self.error:
            raise self.error
        return [{1: 0.8, 7: 0.2} for _ in texts]


class FakeHybridVectorStore:
    def __init__(self, dense_results=None, sparse_results=None, error=None, timeout=False):
        self.rows = []
        self.dense_results = dense_results or []
        self.sparse_results = sparse_results or []
        self.error = error
        self.timeout = timeout
        self.upsert_calls = []
        self.search_calls = []

    def upsert(self, chunks, dense_vectors, sparse_vectors):
        if self.error:
            raise self.error
        self.upsert_calls.append((chunks, dense_vectors, sparse_vectors))
        self.rows.extend(chunks)
        return len(chunks)

    def dense_search(self, query, top_k=5, filters=None):
        self.search_calls.append(("dense", query, top_k, filters))
        if self.timeout:
            raise TimeoutError("milvus timeout")
        return self._filter_results(self.dense_results, filters)

    def sparse_search(self, query, top_k=5, filters=None):
        self.search_calls.append(("sparse", query, top_k, filters))
        if self.timeout:
            raise TimeoutError("milvus timeout")
        return self._filter_results(self.sparse_results, filters)

    def hybrid_search(self, query, top_k=5, filters=None):
        dense = self.dense_search(query, top_k, filters)
        sparse = self.sparse_search(query, top_k, filters)
        return rrf_fuse(dense, sparse, limit=top_k)

    def _filter_results(self, results, filters):
        if not filters:
            return results
        filtered = []
        for result in results:
            metadata = result.chunk.metadata
            if all(metadata.get(key) == value for key, value in filters.items()):
                filtered.append(result)
        return filtered


class FakeLLM:
    def __init__(self, response=None, error=None):
        self.response = response or "函数是用于封装可复用代码的结构。"
        self.error = error
        self.prompts = []

    def generate(self, prompt):
        if self.error:
            raise self.error
        self.prompts.append(prompt)
        return self.response


class FakeRepository:
    def __init__(self):
        self.materials = []

    def save_material(self, material):
        self.materials.append(material)
        return material

    def list_materials(self):
        return self.materials


class FakeReranker:
    def rerank(self, query, results):
        return sorted(results, key=lambda result: result.score, reverse=True)


class FakeCompressor:
    def compress(self, query, chunks):
        return [
            DocumentChunk(
                id=chunk.id,
                material_id=chunk.material_id,
                text=chunk.text.split("。")[0] + "。",
                source=chunk.source,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                metadata=chunk.metadata,
            )
            for chunk in chunks
        ]


def make_material(**overrides):
    data = {
        "id": "mat-1",
        "filename": "python.md",
        "file_type": "markdown",
        "source_path": "uploads/python.md",
        "uploaded_at": datetime(2026, 6, 3, 10, 0, 0),
        "status": "uploaded",
        "chunk_count": 0,
        "error_message": "",
    }
    data.update(overrides)
    return LearningMaterial(**data)


def make_chunk(chunk_id="chunk-1", **overrides):
    data = {
        "id": chunk_id,
        "material_id": "mat-1",
        "text": "Python 函数用于封装可复用代码。",
        "source": "python.md",
        "page_number": 1,
        "chunk_index": 0,
        "metadata": {
            "material_id": "mat-1",
            "filename": "python.md",
            "file_type": "markdown",
            "source": "python.md",
            "page_number": 1,
            "section_title": "函数",
            "chunk_index": 0,
            "tags": ["python", "函数"],
        },
    }
    data.update(overrides)
    return DocumentChunk(**data)


def make_result(chunk_id="chunk-1", score=0.9, **overrides):
    return RetrievalResult(chunk=make_chunk(chunk_id, **overrides), score=score)


class TestF4Stage1UploadAndValidation:
    def test_f4_1_01_material_qa_view_opens_without_materials(self):
        """原因：先保证资料问答页基础状态可用。"""
        view = build_material_qa_view(materials=[], latest_answer=None)

        assert view.can_upload is True
        assert view.materials == []
        assert view.answer is None
        assert view.upload_hint

    def test_f4_1_02_accepts_txt_upload(self, tmp_path):
        """原因：TXT 是最基础的学习资料格式。"""
        upload = FakeUpload("note.txt", b"Python function")

        material = create_material_from_upload(upload, upload_dir=tmp_path)

        assert material.filename == "note.txt"
        assert material.file_type == "txt"
        assert material.status == "uploaded"

    def test_f4_1_03_accepts_markdown_upload(self, tmp_path):
        """原因：学习笔记常用 Markdown。"""
        material = create_material_from_upload(FakeUpload("python.md", b"# Python"), upload_dir=tmp_path)

        assert material.file_type == "markdown"

    def test_f4_1_04_accepts_pdf_upload(self, tmp_path):
        """原因：课程资料和教材常用 PDF。"""
        material = create_material_from_upload(FakeUpload("course.pdf", b"%PDF-1.4"), upload_dir=tmp_path)

        assert material.file_type == "pdf"

    def test_f4_1_05_accepts_pasted_course_note(self):
        """原因：用户可能只想粘贴课程笔记。"""
        material = create_material_from_note("递归是一种函数调用自身的技术。", title="递归笔记")

        assert material.filename == "递归笔记"
        assert material.file_type == "note"
        assert material.status == "uploaded"

    def test_f4_1_06_rejects_unsupported_file_type(self):
        """原因：防止无效文件进入解析流程。"""
        with pytest.raises(MaterialRAGError, match="文件类型"):
            validate_upload(FakeUpload("malware.exe", b"bad"))

    def test_f4_1_07_upload_success_appears_in_material_list(self):
        """原因：用户需要知道哪些资料已经进入系统。"""
        repo = FakeRepository()
        material = repo.save_material(make_material())

        view = build_material_qa_view(materials=repo.list_materials(), latest_answer=None)

        assert material in view.materials
        assert view.materials[0].filename == "python.md"


class TestF4Stage2DocumentParsing:
    def test_f4_2_01_parses_txt_as_plain_text(self):
        """原因：保证基础文本资料可用。"""
        pages = parse_material(make_material(file_type="txt"), parser=FakeParser())

        assert pages[0]["text"] == "Python 函数用于封装可复用代码。"

    def test_f4_2_02_parses_markdown_preserving_headings_and_code(self):
        """原因：标题和代码块对学习问答很重要。"""
        parser = FakeParser(pages=[{"text": "# 函数\n```python\ndef f(): pass\n```", "page_number": None}])

        pages = parse_material(make_material(file_type="markdown"), parser=parser)

        assert "# 函数" in pages[0]["text"]
        assert "def f()" in pages[0]["text"]

    def test_f4_2_03_parses_pdf_with_page_numbers(self):
        """原因：PDF 引用来源需要页码。"""
        parser = FakeParser(pages=[{"text": "第一页内容", "page_number": 1}, {"text": "第二页内容", "page_number": 2}])

        pages = parse_material(make_material(file_type="pdf"), parser=parser)

        assert pages[0]["page_number"] == 1
        assert pages[1]["page_number"] == 2

    def test_f4_2_04_empty_file_parse_fails(self):
        """原因：空资料不能产生有效问答。"""
        with pytest.raises(MaterialRAGError, match="为空"):
            parse_material(make_material(), parser=FakeParser(pages=[{"text": "", "page_number": 1}]))

    def test_f4_2_05_parse_failure_updates_material_status(self):
        """原因：用户需要知道资料为什么不可用。"""
        material = process_material(make_material(), parser=FakeParser(error=RuntimeError("broken pdf")))

        assert material.status == "failed"
        assert "broken pdf" in material.error_message


class TestF4Stage3Chunking:
    def test_f4_3_01_long_text_splits_into_multiple_chunks(self):
        """原因：RAG 检索依赖合理切片。"""
        text = "Python 函数用于封装可复用代码。" * 80

        chunks = split_material_text(make_material(), [{"text": text, "page_number": 1}], chunk_size=120, overlap=20)

        assert len(chunks) > 1
        assert all(chunk.material_id == "mat-1" for chunk in chunks)

    def test_f4_3_02_short_text_creates_one_chunk(self):
        """原因：短资料不应被无意义切碎。"""
        chunks = split_material_text(make_material(), [{"text": "短文本", "page_number": 1}], chunk_size=500, overlap=50)

        assert len(chunks) == 1

    def test_f4_3_03_chunks_keep_source_metadata(self):
        """原因：引用来源依赖 chunk 元数据。"""
        chunks = split_material_text(make_material(), [{"text": "Python 函数", "page_number": 3}], chunk_size=500, overlap=50)

        assert chunks[0].metadata["filename"] == "python.md"
        assert chunks[0].metadata["page_number"] == 3

    def test_f4_3_04_does_not_create_empty_chunks(self):
        """原因：空 chunk 会降低检索质量。"""
        chunks = split_material_text(make_material(), [{"text": "\n\nPython\n\n", "page_number": 1}], chunk_size=500, overlap=50)

        assert all(chunk.text.strip() for chunk in chunks)

    def test_f4_3_05_chunk_order_is_stable(self):
        """原因：稳定切分有利于测试和引用。"""
        pages = [{"text": "A" * 300 + "B" * 300, "page_number": 1}]

        first = split_material_text(make_material(), pages, chunk_size=100, overlap=10)
        second = split_material_text(make_material(), pages, chunk_size=100, overlap=10)

        assert [chunk.chunk_index for chunk in first] == [chunk.chunk_index for chunk in second]
        assert [chunk.text for chunk in first] == [chunk.text for chunk in second]


class TestF4Stage4HybridRetrieval:
    def test_f4_4_01_embedding_client_generates_dense_and_sparse_vectors(self):
        """原因：混合检索需要同时具备语义向量和稀疏关键词向量。"""
        client = FakeEmbeddingClient()

        dense = client.embed_dense(["Python 函数"])
        sparse = client.embed_sparse(["Python 函数"])

        assert len(dense) == 1
        assert len(sparse) == 1
        assert isinstance(sparse[0], dict)

    def test_f4_4_02_hybrid_vector_store_upserts_chunks(self):
        """原因：F4 要求写入 Milvus hybrid collection。"""
        chunks = [make_chunk()]
        store = FakeHybridVectorStore()

        count = index_material_chunks(chunks, embedding_client=FakeEmbeddingClient(), vector_store=store)

        assert count == 1
        assert len(store.upsert_calls) == 1

    def test_f4_4_03_dense_search_returns_semantic_chunks(self):
        """原因：dense 检索负责语义召回。"""
        store = FakeHybridVectorStore(dense_results=[make_result(score=0.8)])

        results = store.dense_search("如何定义可复用代码块")

        assert results[0].chunk.text == "Python 函数用于封装可复用代码。"

    def test_f4_4_04_sparse_search_returns_keyword_matches(self):
        """原因：专业术语、函数名、库名需要精确匹配。"""
        result = make_result(metadata={**make_chunk().metadata, "tags": ["pytest"]})
        store = FakeHybridVectorStore(sparse_results=[result])

        results = store.sparse_search("pytest 怎么写测试")

        assert "pytest" in results[0].chunk.metadata["tags"]

    def test_f4_4_05_hybrid_search_fuses_dense_and_sparse_results(self):
        """原因：混合检索需要同时利用语义和关键词召回。"""
        dense = [make_result("A", 0.9), make_result("B", 0.7), make_result("C", 0.5)]
        sparse = [make_result("C", 0.9), make_result("D", 0.7), make_result("A", 0.5)]
        fused = rrf_fuse(dense, sparse, limit=4)

        ids = [result.chunk.id for result in fused]

        assert "A" in ids
        assert "C" in ids
        assert len(ids) == len(set(ids))

    def test_f4_4_06_rrf_ranking_is_stable(self):
        """原因：RRF 是 MVP 默认融合策略，需要可复现。"""
        dense = [make_result("A"), make_result("B")]
        sparse = [make_result("B"), make_result("A")]

        assert rrf_fuse(dense, sparse, limit=2) == rrf_fuse(dense, sparse, limit=2)

    def test_f4_4_07_metadata_filter_returns_only_matching_material(self):
        """原因：用户可能只想问某一份资料。"""
        result_a = make_result("A", material_id="mat-a", metadata={**make_chunk().metadata, "material_id": "mat-a"})
        result_b = make_result("B", material_id="mat-b", metadata={**make_chunk().metadata, "material_id": "mat-b"})
        store = FakeHybridVectorStore(dense_results=[result_a, result_b])

        results = store.dense_search("函数", filters={"material_id": "mat-a"})

        assert [result.chunk.metadata["material_id"] for result in results] == ["mat-a"]

    def test_f4_4_08_metadata_filter_supports_file_type(self):
        """原因：查询构建需要支持按资料类型过滤。"""
        pdf = make_result("pdf", metadata={**make_chunk().metadata, "file_type": "pdf"})
        md = make_result("md", metadata={**make_chunk().metadata, "file_type": "markdown"})
        store = FakeHybridVectorStore(dense_results=[pdf, md])

        results = store.dense_search("函数", filters={"file_type": "pdf"})

        assert results[0].chunk.metadata["file_type"] == "pdf"

    def test_f4_4_09_retrieval_results_trace_back_to_source(self):
        """原因：PRD 要求回答展示引用来源。"""
        result = make_result()

        assert result.chunk.material_id
        assert result.chunk.metadata["filename"] == "python.md"
        assert result.chunk.id
        assert result.chunk.text

    def test_f4_4_10_milvus_unavailable_raises_clear_error(self):
        """原因：外部服务不可用时要可诊断。"""
        store = FakeHybridVectorStore(timeout=True)

        with pytest.raises(TimeoutError):
            store.dense_search("函数")


class TestF4Stage5QueryConstructionRewriteRouting:
    def test_f4_5_01_simple_question_routes_to_direct_qa(self):
        """原因：简单问题应走低成本路径。"""
        route = route_material_query("Python 函数是什么？")

        assert route.name == "qa"
        assert route.use_multi_query is False

    def test_f4_5_02_ambiguous_question_is_rewritten(self):
        """原因：查询改写可以弥合短问题和资料表达的差距。"""
        rewritten = rewrite_query("这个怎么用？", context_hint="Python 函数")

        assert "Python" in rewritten
        assert "函数" in rewritten

    def test_f4_5_03_complex_question_generates_multi_queries(self):
        """原因：多意图问题直接检索容易漏召回。"""
        queries = generate_multi_queries("递归和动态规划有什么区别，分别适合解决什么问题？", count=3)

        assert len(queries) >= 2
        assert any("递归" in query for query in queries)
        assert any("动态规划" in query for query in queries)

    def test_f4_5_04_multi_query_results_are_merged_and_deduplicated(self):
        """原因：多查询检索必须避免重复上下文。"""
        merged = merge_retrieval_results([[make_result("chunk-1"), make_result("chunk-2")], [make_result("chunk-2"), make_result("chunk-3")]])

        assert [result.chunk.id for result in merged] == ["chunk-1", "chunk-2", "chunk-3"]

    def test_f4_5_05_summary_query_routes_to_summary(self):
        """原因：摘要不应走普通问答 prompt。"""
        assert route_material_query("总结这份资料").name == "summary"

    def test_f4_5_06_concept_query_routes_to_concept_explain(self):
        """原因：概念解释需要更教学化的回答方式。"""
        assert route_material_query("解释一下递归").name == "concept_explain"

    def test_f4_5_07_flashcard_query_routes_to_flashcard(self):
        """原因：复习卡片有独立输出结构。"""
        assert route_material_query("根据这份资料生成复习卡片").name == "flashcard"

    def test_f4_5_08_knowledge_point_query_routes_to_knowledge_points(self):
        """原因：知识点提取需要结构化输出。"""
        assert route_material_query("提取这份资料的知识点").name == "knowledge_points"

    def test_f4_5_09_hyde_generates_hypothetical_answer(self):
        """原因：HyDE 适合抽象概念问题，能提升语义召回。"""
        hyde = generate_hyde_query("为什么装饰器有用？", llm=FakeLLM("装饰器可以在不修改原函数的情况下扩展行为。"))

        assert "装饰器" in hyde
        assert "函数" in hyde

    def test_f4_5_10_reranker_can_change_candidate_order(self):
        """原因：预留 rerank 能力，支持未来高精度检索。"""
        results = [make_result("low", score=0.1), make_result("high", score=0.9)]

        reranked = rerank_chunks("函数", results, reranker=FakeReranker())

        assert reranked[0].chunk.id == "high"

    def test_f4_5_11_context_compressor_reduces_noise(self):
        """原因：压缩可以减少 LLM 上下文噪音和 token 成本。"""
        noisy = make_chunk(text="Python 函数用于封装可复用代码。这里还有很多无关内容。")

        compressed = FakeCompressor().compress("函数", [noisy])

        assert compressed[0].text == "Python 函数用于封装可复用代码。"


class TestF4Stage6MaterialQA:
    def test_f4_6_01_can_answer_with_materials(self):
        """原因：这是 F4 主流程。"""
        answer = ask_material_question(
            "Python 中函数是什么？",
            vector_store=FakeHybridVectorStore(dense_results=[make_result()]),
            llm=FakeLLM(),
        )

        assert isinstance(answer, MaterialAnswer)
        assert answer.answer
        assert answer.citations

    def test_f4_6_02_qa_uses_retrieved_chunks_as_context(self):
        """原因：防止 LLM 脱离资料自由回答。"""
        llm = FakeLLM()

        ask_material_question("Python 函数是什么？", vector_store=FakeHybridVectorStore(dense_results=[make_result()]), llm=llm)

        assert "Python 函数用于封装可复用代码" in llm.prompts[0]

    def test_f4_6_03_answer_contains_citations(self):
        """原因：PRD 要求展示引用来源。"""
        answer = ask_material_question("函数是什么？", vector_store=FakeHybridVectorStore(dense_results=[make_result()]), llm=FakeLLM())

        citation = answer.citations[0]
        assert isinstance(citation, Citation)
        assert citation.filename == "python.md"
        assert citation.snippet

    def test_f4_6_04_no_retrieval_results_returns_no_answer_hint(self):
        """原因：防止模型编造答案。"""
        answer = ask_material_question("量子计算是什么？", vector_store=FakeHybridVectorStore(dense_results=[]), llm=FakeLLM())

        assert "没有" in answer.answer
        assert answer.citations == []

    def test_f4_6_05_question_without_materials_is_rejected(self):
        """原因：问答必须基于资料。"""
        with pytest.raises(MaterialRAGError, match="上传资料"):
            ask_material_question("函数是什么？", vector_store=None, llm=FakeLLM())

    def test_f4_6_06_empty_question_is_rejected(self):
        """原因：空问题没有意义。"""
        with pytest.raises(MaterialRAGError, match="问题"):
            ask_material_question("", vector_store=FakeHybridVectorStore(), llm=FakeLLM())

    def test_f4_6_07_chinese_question_gets_chinese_answer(self):
        """原因：产品主要面向中文用户。"""
        answer = ask_material_question("函数是什么？", vector_store=FakeHybridVectorStore(dense_results=[make_result()]), llm=FakeLLM("函数是一种封装代码的方式。"))

        assert "函数" in answer.answer

    def test_f4_6_08_out_of_material_question_does_not_assert_external_facts(self):
        """原因：RAG 问答应降低幻觉。"""
        answer = ask_material_question("量子计算是什么？", vector_store=FakeHybridVectorStore(dense_results=[]), llm=FakeLLM())

        assert "资料" in answer.answer


class TestF4Stage7SummaryCardsKnowledgePoints:
    def test_f4_7_01_generates_material_summary(self):
        """原因：PRD 要求支持资料摘要。"""
        summary = summarize_material([make_chunk()], llm=FakeLLM("本文介绍了 Python 函数。"))

        assert "Python" in summary

    def test_f4_7_02_summary_uses_material_context(self):
        """原因：摘要不能脱离资料。"""
        llm = FakeLLM("摘要")

        summarize_material([make_chunk()], llm=llm)

        assert "Python 函数用于封装可复用代码" in llm.prompts[0]

    def test_f4_7_03_explains_concept_with_citation(self):
        """原因：PRD 要求支持概念解释。"""
        answer = explain_concept("递归", chunks=[make_chunk(text="递归是函数调用自身。")], llm=FakeLLM("递归是函数调用自身。"))

        assert "递归" in answer.answer
        assert answer.citations

    def test_f4_7_04_generates_flashcards(self):
        """原因：PRD 要求生成复习卡片。"""
        cards = generate_flashcards([make_chunk()], llm=FakeLLM("Q: 函数是什么？\nA: 封装可复用代码。"), count=3)

        assert cards
        assert isinstance(cards[0], Flashcard)
        assert cards[0].question
        assert cards[0].answer

    def test_f4_7_05_flashcard_count_is_limited(self):
        """原因：防止一次生成过多内容。"""
        cards = generate_flashcards([make_chunk()], llm=FakeLLM(), count=5)

        assert len(cards) <= 5

    def test_f4_7_06_extracts_knowledge_points(self):
        """原因：PRD 要求从资料中提取知识点。"""
        points = extract_knowledge_points([make_chunk()], llm=FakeLLM("函数: 封装可复用代码"))

        assert points
        assert isinstance(points[0], KnowledgePoint)
        assert points[0].name

    def test_f4_7_07_knowledge_points_can_be_used_by_study_plan(self):
        """原因：资料能力应服务学习规划。"""
        points = extract_knowledge_points([make_chunk()], llm=FakeLLM("函数: 封装可复用代码"))

        assert points[0].name in {"函数", "Python 函数"}


class TestF4Stage8PageState:
    def test_f4_8_01_page_view_shows_upload_controls(self):
        """原因：页面入口必须完整。"""
        view = build_material_qa_view(materials=[], latest_answer=None)

        assert view.can_upload

    def test_f4_8_02_page_view_shows_material_list(self):
        """原因：用户需要管理资料。"""
        view = build_material_qa_view(materials=[make_material()], latest_answer=None)

        assert len(view.materials) == 1

    def test_f4_8_03_page_view_shows_question_input(self):
        """原因：问答是 F4 主入口。"""
        view = build_material_qa_view(materials=[make_material()], latest_answer=None)

        assert view.can_ask

    def test_f4_8_04_page_view_shows_answer_and_citations(self):
        """原因：PRD 明确要求展示引用来源。"""
        answer = MaterialAnswer(question="函数是什么？", answer="函数封装代码。", citations=[Citation(filename="python.md", chunk_id="chunk-1", snippet="函数", score=0.9)])

        view = build_material_qa_view(materials=[make_material()], latest_answer=answer)

        assert view.answer == answer
        assert view.answer.citations

    def test_f4_8_05_page_view_shows_summary_action(self):
        """原因：PRD 页面设计包含资料摘要按钮。"""
        view = build_material_qa_view(materials=[make_material()], latest_answer=None)

        assert view.can_summarize

    def test_f4_8_06_page_view_shows_flashcard_action(self):
        """原因：PRD 页面设计包含复习卡片生成按钮。"""
        view = build_material_qa_view(materials=[make_material()], latest_answer=None)

        assert view.can_generate_flashcards

    def test_f4_8_07_session_state_keeps_materials_and_latest_answer(self):
        """原因：用户切换页面不应立即丢失上下文。"""
        session = {"materials": [make_material()], "latest_answer": MaterialAnswer(question="Q", answer="A", citations=[])}

        view = build_material_qa_view(materials=session["materials"], latest_answer=session["latest_answer"])

        assert view.materials
        assert view.answer.answer == "A"


class TestF4Stage9FailuresAndEdges:
    def test_f4_9_01_rejects_oversized_file(self):
        """原因：防止大文件拖垮应用。"""
        upload = FakeUpload("large.txt", b"x" * 1024)

        with pytest.raises(MaterialRAGError, match="文件过大"):
            validate_upload(upload, max_size_bytes=100)

    def test_f4_9_02_duplicate_filename_gets_distinct_material_id(self, tmp_path):
        """原因：避免资料被意外覆盖。"""
        first = create_material_from_upload(FakeUpload("same.txt", b"one"), upload_dir=tmp_path)
        second = create_material_from_upload(FakeUpload("same.txt", b"two"), upload_dir=tmp_path)

        assert first.id != second.id

    def test_f4_9_03_embedding_failure_updates_material_status(self):
        """原因：embedding 是外部能力，必须防守。"""
        material = make_material()

        failed = process_material(material, parser=FakeParser(), embedding_client=FakeEmbeddingClient(error=RuntimeError("embedding failed")), vector_store=FakeHybridVectorStore())

        assert failed.status == "failed"
        assert "embedding failed" in failed.error_message

    def test_f4_9_04_llm_answer_failure_is_clear(self):
        """原因：模型服务不可用时不能破坏用户状态。"""
        with pytest.raises(MaterialRAGError, match="回答生成失败"):
            ask_material_question("函数是什么？", vector_store=FakeHybridVectorStore(dense_results=[make_result()]), llm=FakeLLM(error=RuntimeError("llm down")))

    def test_f4_9_05_milvus_search_timeout_is_clear(self):
        """原因：向量服务不稳定时需要用户可理解的反馈。"""
        with pytest.raises(MaterialRAGError, match="检索超时"):
            ask_material_question("函数是什么？", vector_store=FakeHybridVectorStore(timeout=True), llm=FakeLLM())

    def test_f4_9_06_long_citation_snippet_is_truncated(self):
        """原因：保持页面可读性。"""
        snippet = truncate_snippet("很长的引用" * 100, max_length=30)

        assert len(snippet) <= 31
        assert snippet.endswith("…")
