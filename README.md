# Study-Planner

Study-Planner is a Streamlit-based intelligent learning assistant. It helps a learner collect a study goal, generate a structured study plan, edit task progress, upload learning materials, and ask questions over those materials with RAG.

The project is built as a learning-oriented MVP with clear layers:

- `domain`: core data models
- `application`: use cases and business rules
- `infrastructure`: LLM, parser, RAG, PostgreSQL, and Milvus adapters
- `interfaces/streamlit`: Streamlit pages
- `docs`: PRD, feature breakdown, and test design documents
- `tests`: automated tests for implemented features

## Current Status

Implemented:

- F1: Study goal input
- F2-A: Fake LLM study plan generation
- F2-B: DeepSeek real LLM integration for plan generation
- F3: Study plan dashboard and task editing
- F4: Material upload, parsing, RAG, QA, summary, flashcards, and knowledge point extraction
- F4 real mode switch: DeepSeek LLM plus PostgreSQL/Milvus RAG store
- F5: detailed test design document

Not fully implemented yet:

- F5 review and dynamic replanning application/page logic
- F6 export
- Full F7 persistence for all plan/task/review data
- Full LangGraph multi-agent workflow

## Features

### Study Goal Input

Users can enter:

- Study topic
- Goal
- Deadline
- Current level
- Daily available study time
- Weekly available study days
- Preferred learning methods
- Weak points
- Extra requirements

The page builds a structured `StudyGoal` and passes it to later flows.

### Study Plan Generation

The system can generate a structured `StudyPlan` with:

- Overall learning route
- Phases
- Weekly plans
- Daily tasks
- Learning methods
- Time budget
- Risks
- Review schedule

The generated plan is validated before being stored in Streamlit session state.

### Plan Dashboard

The dashboard supports:

- Plan overview
- Today tasks
- Current week tasks
- Phase and week views
- Progress calculation
- Task status editing
- Task date, duration, and notes editing
- Daily time limit validation

### Material Upload And RAG QA

Supported material types:

- TXT
- Markdown
- PDF
- Pasted course notes

PDF parsing uses PyMuPDF. Parsers are decoupled through a parser registry, so new parsers such as image OCR or audio transcription can be added later.

The F4 page supports:

- Upload and index materials
- Ask questions over materials
- Show citations
- Generate summaries
- Generate flashcards
- Extract knowledge points

## Architecture

```text
Streamlit UI
  -> Application use cases
  -> Domain models
  -> Infrastructure adapters
      -> LLM: FakeLLM / DeepSeek
      -> RAG store: in-memory / PostgreSQL + Milvus
      -> Parsers: note / text / markdown / PyMuPDF PDF
```

Core directories:

```text
study_planner/
  application/
    generate_study_plan.py
    material_rag.py
    plan_dashboard.py
    study_goal_input.py
  domain/
    models.py
  infrastructure/
    settings.py
    llm/
    rag/
  interfaces/
    streamlit/
      app.py
      pages/
  prompts/
```

## Environment

Copy `.env.example` to `.env` and fill in the values you need.

Important switches:

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
```

### Fake Local Mode

Use this mode for development and tests:

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
```

This uses:

- Local fake LLM responses
- Local in-memory vector store
- No DeepSeek call
- No PostgreSQL/Milvus dependency for F4 runtime

### Real LLM With Local RAG Store

Use this mode to call DeepSeek while keeping local in-memory retrieval:

```env
USE_REAL_LLM=true
USE_REAL_RAG_STORE=false
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### Real LLM With Real RAG Store

Use this mode for DeepSeek plus PostgreSQL/Milvus:

```env
USE_REAL_LLM=true
USE_REAL_RAG_STORE=true

DATABASE_URL=postgresql+psycopg://user:password@localhost:5433/study_planner
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=study_materials

DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

The current real RAG adapter automatically creates:

- PostgreSQL tables: `rag_materials`, `rag_chunks`
- Milvus collection and vector index

Note: the current embedding implementation is still a small local demo embedding. The PostgreSQL/Milvus path is real, but the embedding quality is not production-grade yet.

## Install

This project uses `uv`.

```powershell
uv sync
```

If Streamlit or pytest are missing in your environment, install them into the project environment:

```powershell
uv add streamlit pytest python-dotenv
```

## Run

Start the Streamlit app:

```powershell
uv run streamlit run study_planner/interfaces/streamlit/app.py
```

Pages:

- Goal Setup
- Plan Dashboard
- Material QA

## Test

Run all current tests:

```powershell
uv run pytest
```

Run feature-specific tests:

```powershell
uv run pytest tests/test_f1_study_goal_input.py
uv run pytest tests/test_f2_generate_study_plan.py
uv run pytest tests/test_f2b_real_llm_integration.py
uv run pytest tests/test_f3_plan_dashboard_editing.py
uv run pytest tests/test_f4_material_upload_rag.py
```

Some real LLM tests are guarded by `USE_REAL_LLM`. Keep `USE_REAL_LLM=false` if you do not want to call DeepSeek.

## Documentation

Useful docs:

- `docs/PRD.md`: product requirements
- `docs/features.md`: feature breakdown
- `docs/test_docs/F3_test.md`: F3 test plan
- `docs/test_docs/F4_test.md`: F4 test plan
- `docs/test_docs/F5_test.md`: F5 test plan

## Development Notes

- Application code should not directly call Streamlit, DeepSeek, PostgreSQL, or Milvus.
- Streamlit pages should call application use cases or infrastructure factories.
- LLM usage should respect `USE_REAL_LLM`.
- RAG storage should respect `USE_REAL_RAG_STORE`.
- New document parsers should be added under `study_planner/infrastructure/rag/parsers`.

## Suggested Next Steps

1. Implement F5 domain models and tests from `docs/test_docs/F5_test.md`.
2. Build F5 application use cases for progress analysis, review report generation, and replanning preview.
3. Add the F5 Streamlit page.
4. Add persistence for full study plans and task progress.
5. Replace the demo embedding with a production embedding model.
