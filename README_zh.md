# Study Planner 智能学习规划助手

> 一个把学习目标拆成可执行计划、追踪真实进度、基于资料问答、自动复盘调整，并导出专业学习报告的 AI 学习工作台。

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/pytest-feature%20tested-0A7BBB?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-16A34A)](./LICENSE)

[**English**](./README.md) | [**简体中文**](./README_zh.md)

Study Planner 是一个基于 Streamlit 的智能学习助手。它不是只生成一份静态计划，而是围绕完整学习闭环设计：配置目标、生成计划、执行任务、资料问答、复盘分析、自动重排、导出报告。

项目采用分层架构，区分 `domain`、`application`、`infrastructure`、`agents` 和 `interfaces/streamlit`。Fake 模式适合本地开发和测试，Real 模式可以接入 DeepSeek、PostgreSQL 和 Milvus。

![Study Planner 首页工作台](docs/assets/home-workspace.png)

## 为什么做 Study Planner

真正的学习不是"生成计划"就结束了。学习过程更像一个循环：

1. 明确目标。
2. 生成计划。
3. 执行每日任务。
4. 基于自己的资料提问。
5. 复盘真实完成情况。
6. 在不覆盖已完成任务的前提下重新安排。
7. 导出可以保存、分享或打印的学习报告。

Study Planner 把这个闭环做成了一个可测试、可扩展的 AI 应用。

## 核心亮点

- **目标到计划生成**：根据学习主题、目标、截止日期、时间预算和偏好生成阶段、周计划、每日任务。
- **Fake / Real 双模式**：FakeLLM 支持本地开发和自动化测试；Real 模式支持 DeepSeek。
- **学习计划看板**：查看目标、阶段、今日任务、本周任务；编辑任务状态、日期、时长和备注。
- **业务图表**：每日学习负载、任务状态分布、任务类型分析、高频知识点、复盘负载、资料质量。
- **资料 RAG 问答**：支持 TXT、Markdown、PDF 和粘贴笔记；可问答、摘要、生成复习卡片和提取知识点。
- **复盘与动态调整**：根据真实任务状态生成复盘报告，识别薄弱点，预览调整计划并保存。
- **持久化**：开发模式可用内存存储；Real 模式支持 PostgreSQL repository。
- **导出报告**：支持 Markdown 和美观的 HTML 学习报告。
- **Agent 工作流**：包含 profile、knowledge、resource、planner、critic、output、progress 等模块化节点。
- **更友好的 Streamlit UI**：中文侧边栏、首页引导、统一视觉、清爽配色和专业图表。

## 产品预览

### 1. 学习首页

首页是学习工作台：展示当前计划状态、复盘状态、持久化状态、下一步建议，以及已有计划的分析图表。

![学习首页](docs/assets/home-workspace.png)

### 2. 配置学习目标

收集学习主题、学习目标、截止日期、当前水平、每日学习时间、每周学习天数、学习偏好、薄弱点和额外要求。

![配置学习目标](docs/assets/goal-setup.png)

### 3. 计划看板

展示学习计划、进度指标、业务图表、今日任务、本周任务、阶段计划和任务编辑控件。

![计划看板](docs/assets/plan-dashboard.png)

### 4. 资料问答

上传或粘贴资料后，可以进行资料问答、概念解释、摘要、复习卡片和知识点提取，并展示引用来源。

![资料问答](docs/assets/material-qa.png)

### 5. 复盘与调整

根据真实任务完成情况生成复盘报告，展示完成率、延期任务、薄弱点和建议，并预览调整前后差异。

![复盘与调整](docs/assets/review-replan.png)

### 6. 导出学习报告

导出当前已确认学习计划和最近复盘报告，支持 Markdown 和 HTML。

![HTML 导出报告](docs/assets/html-export-report.png)

## 功能矩阵

| 功能 | Fake 模式 | Real 模式 |
| --- | --- | --- |
| 学习目标输入 | 支持 | 支持 |
| 学习计划生成 | FakeLLM | DeepSeek |
| Agent 工作流 | Fake / 测试契约 | Real 工作流契约 |
| 计划看板 | Session / 内存 | PostgreSQL 持久化 |
| 任务编辑 | 支持 | 支持 |
| 刷新恢复 | 支持 | PostgreSQL 恢复 |
| 资料上传 | 本地解析 / 本地检索 | PostgreSQL + Milvus |
| 资料问答 | 本地服务 / Fake | DeepSeek + Real RAG |
| 复盘报告 | 本地逻辑 / Fake | DeepSeek 支持 |
| 自动重排 | 可测试逻辑 | Real 工作流契约 |
| Markdown 导出 | 支持 | 支持 |
| HTML 导出 | 支持 | 支持 |

## 架构设计

Study Planner 采用分层架构：

```text
Streamlit Interface
  -> Application use cases
  -> Domain models
  -> Infrastructure adapters
  -> External services
```

核心目录：

```text
study_planner/
  agents/                  # 计划生成和复盘调整相关 Agent
  application/             # 用例、页面视图模型、业务规则
  domain/                  # 核心数据模型
  infrastructure/
    db/                    # PostgreSQL repository
    llm/                   # DeepSeek / Real LLM 适配器
    rag/                   # Parser、Embedding、Vector Store 工厂
  interfaces/
    streamlit/             # Streamlit 入口、页面和 UI 组件
  prompts/                 # Prompt 模板

docs/
  PRD.md
  features.md
  test_docs/
  assets/                  # README 图片和视觉资源

tests/
  test_f1_*.py ... test_f9_*.py
```

### 分层架构图

![分层架构图](docs/assets/architecture.svg)

### Agent 编排管道

`PlannerWorkflow` 内的 6 Agent 串行管道，展示规则引擎与 LLM 增强节点的分工、Planner ↔ Critic 修复循环、以及复盘/重排路径。

![Agent 编排图](docs/assets/agent-workflow.svg)

### 产品流程图

从目标配置到执行、复盘、重排、导出的完整学习闭环。

![产品流程图](docs/assets/learning-loop.svg)

## 快速开始

### 环境要求

- Python 3.12+
- `uv`
- Streamlit 运行环境
- Real 模式可选依赖：
  - DeepSeek API Key
  - PostgreSQL
  - Milvus

### 安装

```powershell
uv sync
```

如果本地环境缺少 UI 或测试依赖，可以补充安装：

```powershell
uv add streamlit pytest pandas altair python-dotenv
```

### 启动

```powershell
uv run streamlit run study_planner/interfaces/streamlit/app.py
```

打开：

```text
http://localhost:8501
```

侧边栏页面名称：

- 学习首页
- 配置学习目标
- 计划看板
- 资料问答
- 复盘与调整
- 导出学习报告

## 配置说明

复制 `.env.example` 为 `.env`，然后选择运行模式。

### Fake 本地模式

适合开发、UI 调试和自动化测试。

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
USE_POSTGRES_PERSISTENCE=false
```

### Real LLM 模式

使用 DeepSeek 生成学习计划、复盘和调整建议。

```env
USE_REAL_LLM=true
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

USE_REAL_RAG_STORE=false
USE_POSTGRES_PERSISTENCE=false
```

### PostgreSQL 持久化模式

使用 PostgreSQL 保存目标、计划、任务进度、复盘报告等数据。

```env
USE_POSTGRES_PERSISTENCE=true
DATABASE_URL=postgresql://user:password@localhost:5432/study_planner
```

测试库可以配置：

```env
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/study_planner_test
```

### Real RAG 模式

使用 PostgreSQL / Milvus 存储和检索学习资料。

```env
USE_REAL_RAG_STORE=true
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=study_materials
```

完整 Real 模式：

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

## 测试

运行主测试套件：

```powershell
uv run pytest
```

按功能运行：

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

配置好外部服务后，可以运行 Real 手动验收用例：

```powershell
uv run pytest -q -m manual tests/test_f9_streamlit_integration.py
```

## 手动验收清单

Fake 模式：

- 配置目标并生成学习计划。
- 修改任务状态和备注，刷新后仍存在。
- 添加资料笔记并提问。
- 生成复盘报告。
- 预览并保存自动重排结果。
- 导出 HTML 并用浏览器打开。

Real 模式：

- DeepSeek 生成非 Fake 学习计划。
- PostgreSQL 刷新后恢复计划和任务修改。
- Real RAG 能返回引用来源。
- 复盘指标和当前任务状态一致。
- 自动重排不覆盖已完成任务。
- HTML 导出使用最新已确认计划。

## UI 与信息架构说明

当前没有新增独立"分析页"。分析被放在用户需要做决策的地方：

- 计划相关分析在"计划看板"。
- 资料相关分析在"资料问答"。
- 复盘相关分析在"复盘与调整"。

这样用户不用为了看数据额外跳页，使用路径更顺。

## 开发原则

- `domain` 不依赖 Streamlit、DeepSeek、PostgreSQL、Milvus。
- `application` 承担用例和业务规则。
- `infrastructure` 负责外部服务和存储适配。
- Streamlit 页面只负责输入、展示和状态组织。
- Fake / Real 模式必须服从 `.env` 开关。
- 测试优先使用可复用、解耦的 helper，而不是只写端到端断言。

## 路线图

- 替换为生产级 embedding 模型和 reranker。
- 增加 Real LLM 成本、耗时、错误恢复观测。
- 从 HTML 报告进一步支持 PDF 导出。
- 增强 Streamlit 页面视觉回归检查。
- 支持认证和多用户计划归属。
- 补充 Streamlit + PostgreSQL + Milvus 部署指南。

## 开源许可

本项目基于 MIT License 开源 — 详见 [LICENSE](./LICENSE)。
