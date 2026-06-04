# Study Planner

> An AI-powered learning operating system for turning goals into plans, tracking execution, reviewing progress, replanning intelligently, and exporting polished study reports.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/pytest-feature%20tested-0A7BBB?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-16A34A)](./LICENSE)

[**English**](./README.md) | [**简体中文**](./README_zh.md)

Study Planner is a Streamlit application for learners who want more than a static checklist. It captures a learning goal, generates a structured plan with AI, keeps task progress editable and persistent, answers questions over learning materials with RAG, creates review reports, replans unfinished work, and exports a professional HTML or Markdown report.

The project is designed as a serious, test-driven AI application rather than a demo script. The code is split into domain, application, infrastructure, agents, and Streamlit interface layers so Fake and Real modes can be switched without rewriting UI logic.

![Study Planner Home Workspace](docs/assets/home-workspace.png)

## Why Study Planner

Most study tools stop at "make a plan." Real learning needs a loop:

1. Define the goal.
2. Generate a plan.
3. Execute daily tasks.
4. Ask questions over your own materials.
5. Review what actually happened.
6. Replan without overwriting completed work.
7. Export a report you can keep, share, or print.

Study Planner implements that full loop with Fake mode for fast local development and Real mode for DeepSeek, PostgreSQL, and Milvus-backed workflows.

## Highlights

- **Goal-to-plan generation**: converts learning goals into phases, weekly plans, daily tasks, time budgets, risks, and review schedules.
- **Fake and Real LLM modes**: local FakeLLM for development and tests; DeepSeek integration for Real workflows.
- **Plan dashboard**: edit task status, date, duration, and notes; preserve task IDs; recover state after refresh.
- **Business-grade charts**: daily load trend, task status distribution, task type analysis, topic distribution, review load, and material quality.
- **Material RAG**: upload TXT, Markdown, PDF, or pasted notes; ask questions; show citations; generate summaries, flashcards, and knowledge points.
- **Review and replanning**: generate review reports from real task state, identify weak points, preview adjustments, and save adjusted plans.
- **Persistence**: in-memory mode for development; PostgreSQL repositories for goals, plans, task progress, review reports, materials, and exports.
- **Export**: Markdown and polished HTML reports with plan details and recent review data.
- **Agent workflow**: modular profile, knowledge, resource, planner, critic, output, and progress agents with testable contracts.
- **Streamlit UI polish**: custom navigation labels, visual hierarchy, clean cards, charts, and consistent page flow.

## Product Tour

### 1. Learning Home

The home page acts as a learner workspace: it shows current plan status, review status, persistence availability, recommended next step, and plan analytics when a plan exists.

![Learning Home](docs/assets/home-workspace.png)

### 2. Goal Setup

Collects the topic, target outcome, deadline, current level, daily available minutes, weekly available days, preferred methods, weak points, and extra requirements.

![Goal Setup](docs/assets/goal-setup.png)

### 3. Plan Dashboard

Shows the generated study plan, progress metrics, charts, today tasks, current week tasks, phase tabs, and editable task controls.

![Plan Dashboard](docs/assets/plan-dashboard.png)

### 4. Material QA

Processes learning materials and supports direct QA, concept explanation, summaries, flashcards, and knowledge point extraction with citations.

![Material QA](docs/assets/material-qa.png)

### 5. Review and Replan

Generates review reports from actual task state, displays completion metrics and weak points, previews adjusted plans, and prevents completed tasks from being overwritten.

![Review & Replan](docs/assets/review-replan.png)

### 6. Export Report

Exports the confirmed current plan and recent review report as Markdown or professional HTML.

![HTML Export Report](docs/assets/html-export-report.png)

## Feature Matrix

| Area | Fake Mode | Real Mode |
| --- | --- | --- |
| Goal input | Yes | Yes |
| Study plan generation | FakeLLM | DeepSeek |
| Agent workflow | Fake/test contracts | Real workflow contracts |
| Plan dashboard | In-memory/session | PostgreSQL persistence supported |
| Task editing | Yes | Yes |
| Refresh recovery | Yes | PostgreSQL-backed |
| Material upload | Local parser/store | PostgreSQL + Milvus store |
| Material QA | Local fake/local services | DeepSeek + Real RAG services |
| Review report | Fake/local logic | DeepSeek-supported flow |
| Replanning | Deterministic/testable | Real workflow contract |
| Export Markdown | Yes | Yes |
| Export HTML | Yes | Yes |

## Architecture

Study Planner follows a layered architecture:

```text
Streamlit Interface
  -> Application use cases
  -> Domain models
  -> Infrastructure adapters
  -> External services
```

Core directories:

```text
study_planner/
  agents/                  # Planner and review workflow agents
  application/             # Use cases, page view models, business rules
  domain/                  # Core dataclasses and domain entities
  infrastructure/
    db/                    # PostgreSQL repositories
    llm/                   # DeepSeek / real LLM adapters
    rag/                   # Parser, embedding, vector store factories
  interfaces/
    streamlit/             # Streamlit app, pages, UI components
  prompts/                 # Prompt templates

docs/
  PRD.md
  features.md
  test_docs/
  assets/                  # README images and visual assets

tests/
  test_f1_*.py ... test_f9_*.py
```

### Layered Architecture

![Architecture Diagram](docs/assets/architecture.svg)

### Agent Workflow Pipeline

The 6-agent sequential pipeline inside `PlannerWorkflow`, showing rule-based vs LLM-powered agents, the Planner ↔ Critic repair loop, and the review/replan path.

![Agent Workflow](docs/assets/agent-workflow.svg)

### Product Workflow

The full learning loop from goal setup through execution, review, replanning, and export.

![Learning Loop](docs/assets/learning-loop.svg)

## Quick Start

### Requirements

- Python 3.12+
- `uv`
- Streamlit runtime
- Optional for Real mode:
  - DeepSeek API key
  - PostgreSQL
  - Milvus

### Install

```powershell
uv sync
```

If your local environment does not already include the UI/test packages, add them:

```powershell
uv add streamlit pytest pandas altair python-dotenv
```

### Run

```powershell
uv run streamlit run study_planner/interfaces/streamlit/app.py
```

Open:

```text
http://localhost:8501
```

The sidebar uses product-friendly names:

- Learning Home
- Configure Learning Goal
- Plan Dashboard
- Material QA
- Review & Replan
- Export Study Report

## Configuration

Copy `.env.example` to `.env` and choose a mode.

### Fake Local Mode

Best for development, UI testing, and automated tests.

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
USE_POSTGRES_PERSISTENCE=false
```

### Real LLM Mode

Uses DeepSeek for plan generation and review/replanning flows.

```env
USE_REAL_LLM=true
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

USE_REAL_RAG_STORE=false
USE_POSTGRES_PERSISTENCE=false
```

### Real Persistence Mode

Uses PostgreSQL for app persistence.

```env
USE_POSTGRES_PERSISTENCE=true
DATABASE_URL=postgresql://user:password@localhost:5432/study_planner
```

For tests, you can also provide:

```env
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/study_planner_test
```

### Real RAG Mode

Uses PostgreSQL/Milvus-backed material storage and retrieval.

```env
USE_REAL_RAG_STORE=true
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=study_materials
```

Full Real mode:

```env
USE_REAL_LLM=true
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

USE_POSTGRES_PERSISTENCE=true
DATABASE_URL=postgresql://user:password@localhost:5432/study_planner

USE_REAL_RAG_STORE=true
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=study_materials
```

## Testing

Run the main suite:

```powershell
uv run pytest
```

Run feature suites:

```powershell
uv run pytest tests/test_f1_study_goal_input.py
uv run pytest tests/test_f2_generate_study_plan.py
uv run pytest tests/test_f3_plan_dashboard_editing.py
uv run pytest tests/test_f4_material_upload_rag.py
uv run pytest tests/test_f5_review_replan.py
uv run pytest tests/test_f6_plan_export.py
uv run pytest tests/test_f7_persistence.py
uv run pytest tests/test_f8_agent_workflow.py
uv run pytest -m "not manual" tests/test_f9_streamlit_integration.py
```

Run Real/manual acceptance tests after configuring external services:

```powershell
uv run pytest -q -m manual tests/test_f9_streamlit_integration.py
```

## Manual Acceptance Checklist

Fake mode:

- Generate a plan from a learning goal.
- Edit a task and refresh the page.
- Add material notes and ask a question.
- Generate a review report.
- Preview and save a replan result.
- Export HTML and open it in a browser.

Real mode:

- Confirm DeepSeek generates a non-Fake plan.
- Confirm PostgreSQL restores the plan and task edits after refresh.
- Confirm Real RAG returns citations.
- Confirm review metrics match actual task state.
- Confirm replanning does not overwrite completed tasks.
- Confirm HTML export uses the latest confirmed plan.

## Design Notes

The Streamlit UI is intentionally organized around user flow rather than implementation names. Analysis is not split into a separate page because users need analytics in context:

- Plan analytics live in the Plan Dashboard.
- Material analytics live in Material QA.
- Review analytics live in Review & Replan.

This keeps the workflow comfortable: users see the data at the moment they need to act on it.

## Development Principles

- Domain models should not depend on Streamlit, DeepSeek, PostgreSQL, or Milvus.
- Application use cases own business behavior and validation.
- Infrastructure adapters own external service details.
- Streamlit pages should stay thin and call application/infrastructure services.
- Fake and Real modes must obey `.env` switches.
- Tests should prefer small, decoupled helpers over end-to-end-only assertions.

## Roadmap

- Production-grade embedding model and reranking.
- Better cost/latency observability for Real LLM workflows.
- PDF export from the polished HTML report.
- More visual QA around Streamlit layouts.
- Optional authentication and multi-user plan ownership.
- Deployment guide for Streamlit + PostgreSQL + Milvus.

## License

This project is licensed under the MIT License — see [LICENSE](./LICENSE) for details.
