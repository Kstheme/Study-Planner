# Study-Planner 智能学习助手

Study-Planner 是一个基于 Streamlit 的智能学习助手。它可以帮助用户填写学习目标、生成结构化学习计划、编辑任务进度、上传学习资料，并基于资料进行问答、摘要、复习卡片和知识点提取。

这个项目按“边学习边做项目”的方式构建，重点不是堆功能，而是练习可扩展架构：

- `domain`：核心业务模型
- `application`：用例和业务规则
- `infrastructure`：LLM、解析器、RAG、PostgreSQL、Milvus 等具体实现
- `interfaces/streamlit`：Streamlit 页面
- `docs`：PRD、features、测试方案
- `tests`：自动化测试

## 当前进度

已完成：

- F1：学习目标输入
- F2-A：Fake LLM 学习计划生成
- F2-B：DeepSeek 真实 LLM 学习计划生成
- F3：学习计划展示与编辑
- F4：资料上传、解析、RAG 问答、摘要、复习卡片、知识点提取
- F4 真实模式切换：DeepSeek + PostgreSQL/Milvus
- F5：详细测试用例文档

尚未完整实现：

- F5 复盘与动态调整的应用层和页面逻辑
- F6 导出
- F7 全量学习计划、任务、复盘数据持久化
- F8 LangGraph 多 Agent 工作流

## 功能说明

### F1 学习目标输入

用户可以填写：

- 学习主题
- 学习目标
- 截止日期
- 当前水平
- 每日可学习时间
- 每周可学习天数
- 学习偏好
- 薄弱点
- 额外要求

系统会将表单数据转换为结构化 `StudyGoal`，供后续流程使用。

### F2 智能学习计划生成

系统可以生成结构化 `StudyPlan`，包含：

- 总体学习路线
- 阶段目标
- 周计划
- 每日任务
- 学习方法
- 时间预算
- 风险提示
- 复习安排

生成结果会经过应用层校验，再保存到 Streamlit Session State。

### F3 学习计划展示与编辑

看板支持：

- 学习计划总览
- 今日任务
- 本周任务
- 阶段和周视图
- 进度统计
- 修改任务状态
- 修改任务日期、时长、备注
- 校验每日学习时长是否超限

### F4 资料上传与问答

支持资料类型：

- TXT
- Markdown
- PDF
- 粘贴课程笔记

PDF 解析使用 PyMuPDF。文档解析模块已经抽象为 parser registry，后续要添加图片 OCR、音频转写，只需要新增 parser 并注册即可。

F4 页面支持：

- 上传并索引资料
- 基于资料提问
- 展示引用来源
- 生成资料摘要
- 生成复习卡片
- 提取知识点

## 架构

```text
Streamlit UI
  -> Application 用例
  -> Domain 模型
  -> Infrastructure 适配器
      -> LLM：FakeLLM / DeepSeek
      -> RAG Store：本地内存 / PostgreSQL + Milvus
      -> Parsers：note / text / markdown / PyMuPDF PDF
```

核心目录：

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

## 环境配置

复制 `.env.example` 为 `.env`，然后按需填写。

关键开关：

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
```

### 本地 Fake 模式

适合开发和跑自动化测试：

```env
USE_REAL_LLM=false
USE_REAL_RAG_STORE=false
```

此模式使用：

- 本地 Fake LLM
- 本地内存检索
- 不调用 DeepSeek
- F4 运行时不依赖 PostgreSQL/Milvus

### 真实 LLM + 本地检索

适合测试 DeepSeek 回答效果，但暂时不使用真实数据库：

```env
USE_REAL_LLM=true
USE_REAL_RAG_STORE=false
DEEPSEEK_API_KEY=你的 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 真实 LLM + 真实 RAG 存储

适合测试 DeepSeek + PostgreSQL + Milvus：

```env
USE_REAL_LLM=true
USE_REAL_RAG_STORE=true

DATABASE_URL=postgresql+psycopg://user:password@localhost:5433/study_planner
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=study_materials

DEEPSEEK_API_KEY=你的 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

当前真实 RAG 适配器会自动创建：

- PostgreSQL 表：`rag_materials`、`rag_chunks`
- Milvus collection 和 vector index

注意：当前 embedding 仍然是项目里的本地演示版 embedding。PostgreSQL/Milvus 链路是真实的，但语义检索效果还不是生产级。

## 安装依赖

项目使用 `uv`：

```powershell
uv sync
```

如果当前环境缺少 Streamlit 或 pytest，可以安装：

```powershell
uv add streamlit pytest python-dotenv
```

## 启动项目

```powershell
uv run streamlit run study_planner/interfaces/streamlit/app.py
```

当前页面包括：

- Goal Setup
- Plan Dashboard
- Material QA

## 运行测试

运行全部测试：

```powershell
uv run pytest
```

运行单个 feature 测试：

```powershell
uv run pytest tests/test_f1_study_goal_input.py
uv run pytest tests/test_f2_generate_study_plan.py
uv run pytest tests/test_f2b_real_llm_integration.py
uv run pytest tests/test_f3_plan_dashboard_editing.py
uv run pytest tests/test_f4_material_upload_rag.py
```

部分真实 LLM 测试受 `USE_REAL_LLM` 控制。如果不想调用 DeepSeek，请保持：

```env
USE_REAL_LLM=false
```

## 文档

推荐阅读：

- `docs/PRD.md`：产品需求文档
- `docs/features.md`：功能拆解
- `docs/test_docs/F3_test.md`：F3 测试方案
- `docs/test_docs/F4_test.md`：F4 测试方案
- `docs/test_docs/F5_test.md`：F5 测试方案

## 开发约定

- Application 层不要直接调用 Streamlit、DeepSeek、PostgreSQL、Milvus。
- Streamlit 页面只负责页面输入、展示和状态，不承载复杂业务逻辑。
- 涉及 LLM 的地方必须服从统一 `USE_REAL_LLM` 开关。
- 涉及 RAG 存储的地方必须服从 `USE_REAL_RAG_STORE` 开关。
- 新增文档解析器放在 `study_planner/infrastructure/rag/parsers`。

## 下一步建议

1. 根据 `docs/test_docs/F5_test.md` 实现 F5 测试代码。
2. 实现 F5 的进度分析、复盘报告、调整预览和保存逻辑。
3. 添加 F5 Streamlit 页面。
4. 完善学习计划和任务进度的 PostgreSQL 持久化。
5. 将当前演示 embedding 替换为生产级 embedding 模型。
