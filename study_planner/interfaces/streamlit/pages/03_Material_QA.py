from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from study_planner.application.material_rag import (
    MaterialRAGError,
    ask_material_question,
    build_material_qa_view,
    create_material_from_note,
    create_material_from_upload,
    explain_concept,
    extract_knowledge_points,
    generate_flashcards,
    process_material,
    route_material_query,
    summarize_material,
)
from study_planner.infrastructure.rag.factory import build_material_rag_services


st.set_page_config(page_title="资料问答", page_icon="📚", layout="wide")
st.title("📚 资料问答")


class UploadedFileAdapter:
    def __init__(self, uploaded_file):
        self.name = uploaded_file.name
        self.content = uploaded_file.getvalue()

    def read(self):
        return self.content


def _init_state() -> None:
    st.session_state.setdefault("materials", [])
    st.session_state.setdefault("material_chunks", [])
    st.session_state.setdefault("latest_answer", None)
    st.session_state.setdefault("material_summary", "")
    st.session_state.setdefault("flashcards", [])
    st.session_state.setdefault("knowledge_points", [])


def _services():
    return build_material_rag_services(PROJECT_ROOT / ".env", st.session_state["material_chunks"])


def _save_vector_store(store) -> None:
    if hasattr(store, "chunks"):
        st.session_state["material_chunks"] = store.chunks


def _process_and_save_material(material):
    services = _services()
    processed = process_material(
        material,
        parser=services.parser,
        embedding_client=services.embedding_client,
        vector_store=services.vector_store,
    )
    _save_vector_store(services.vector_store)
    st.session_state["materials"].append(processed)
    return processed


def _format_material(material):
    return {
        "文件名": material.filename,
        "类型": material.file_type,
        "状态": material.status,
        "切片数": material.chunk_count,
        "上传时间": material.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        "错误": material.error_message,
    }


def _all_chunks():
    services = _services()
    if hasattr(services.vector_store, "all_chunks"):
        return services.vector_store.all_chunks()
    return st.session_state["material_chunks"]


_init_state()

view = build_material_qa_view(st.session_state["materials"], st.session_state["latest_answer"])

upload_col, note_col = st.columns(2)

with upload_col:
    st.subheader("上传资料")
    uploaded_files = st.file_uploader(
        "支持 TXT、Markdown、PDF",
        type=["txt", "md", "markdown", "pdf"],
        accept_multiple_files=True,
    )
    if st.button("处理上传资料", disabled=not uploaded_files):
        for uploaded_file in uploaded_files or []:
            try:
                material = create_material_from_upload(
                    UploadedFileAdapter(uploaded_file),
                    upload_dir=PROJECT_ROOT / "data" / "uploads",
                )
                processed = _process_and_save_material(material)
                if processed.status == "failed":
                    st.error(f"{processed.filename} 处理失败：{processed.error_message}")
                else:
                    st.success(f"{processed.filename} 已处理")
            except MaterialRAGError as exc:
                st.error(str(exc))

with note_col:
    st.subheader("课程笔记")
    note_title = st.text_input("笔记标题", value="课程笔记")
    note_text = st.text_area("粘贴笔记内容", height=180)
    if st.button("保存并处理笔记", disabled=not note_text.strip()):
        try:
            material = create_material_from_note(note_text, title=note_title.strip() or "课程笔记")
            processed = _process_and_save_material(material)
            if processed.status == "failed":
                st.error(f"{processed.filename} 处理失败：{processed.error_message}")
            else:
                st.success(f"{processed.filename} 已处理")
        except MaterialRAGError as exc:
            st.error(str(exc))

st.subheader("资料列表")
if view.materials:
    st.dataframe([_format_material(material) for material in view.materials], use_container_width=True)
else:
    st.info(view.upload_hint)

st.subheader("基于资料提问")
question = st.text_input("输入你的问题")
top_k = st.slider("检索片段数量", min_value=1, max_value=10, value=5)

action_col1, action_col2, action_col3, action_col4 = st.columns(4)

with action_col1:
    ask_clicked = st.button("提问", disabled=not view.can_ask)
with action_col2:
    summary_clicked = st.button("生成摘要", disabled=not view.can_summarize)
with action_col3:
    flashcard_clicked = st.button("生成复习卡片", disabled=not view.can_generate_flashcards)
with action_col4:
    knowledge_clicked = st.button("提取知识点", disabled=not view.can_summarize)

services = _services()
llm = services.llm

if ask_clicked:
    try:
        route = route_material_query(question)
        if route.name == "summary":
            st.session_state["material_summary"] = summarize_material(_all_chunks(), llm=llm)
        elif route.name == "flashcard":
            st.session_state["flashcards"] = generate_flashcards(_all_chunks(), llm=llm, count=5)
        elif route.name == "knowledge_points":
            st.session_state["knowledge_points"] = extract_knowledge_points(_all_chunks(), llm=llm)
        elif route.name == "concept_explain":
            concept = question.replace("解释", "").replace("一下", "").strip() or question
            st.session_state["latest_answer"] = explain_concept(concept, chunks=_all_chunks(), llm=llm)
        else:
            st.session_state["latest_answer"] = ask_material_question(
                question,
                vector_store=services.vector_store,
                llm=llm,
                top_k=top_k,
            )
        st.rerun()
    except MaterialRAGError as exc:
        st.error(str(exc))

if summary_clicked:
    st.session_state["material_summary"] = summarize_material(_all_chunks(), llm=llm)
    st.rerun()

if flashcard_clicked:
    st.session_state["flashcards"] = generate_flashcards(_all_chunks(), llm=llm, count=5)
    st.rerun()

if knowledge_clicked:
    st.session_state["knowledge_points"] = extract_knowledge_points(_all_chunks(), llm=llm)
    st.rerun()

if st.session_state["latest_answer"]:
    answer = st.session_state["latest_answer"]
    st.subheader("回答")
    st.write(answer.answer)
    st.markdown("#### 引用来源")
    if answer.citations:
        for citation in answer.citations:
            with st.expander(f"{citation.filename} · {citation.chunk_id} · score {citation.score:.4f}"):
                if citation.page_number:
                    st.caption(f"页码：{citation.page_number}")
                st.write(citation.snippet)
    else:
        st.info("暂无引用来源")

if st.session_state["material_summary"]:
    st.subheader("资料摘要")
    st.write(st.session_state["material_summary"])

if st.session_state["flashcards"]:
    st.subheader("复习卡片")
    for index, card in enumerate(st.session_state["flashcards"], start=1):
        with st.expander(f"卡片 {index}: {card.question}"):
            st.write(card.answer)

if st.session_state["knowledge_points"]:
    st.subheader("知识点")
    for point in st.session_state["knowledge_points"]:
        st.markdown(f"- **{point.name}**：{point.description}")
