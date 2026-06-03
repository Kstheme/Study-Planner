# Study-Planner Features 实施清单

本文基于 `docs/PRD.md` 拆解 Study-Planner 的完整功能边界。目标是：按本文从上到下完成所有 features 后，可以交付一个可运行、可演示、可继续扩展的智能学习助手 MVP。

## 0. 功能总览

### 0.1 MVP 必做功能

| 编号 | Feature | 目标 |
|---|---|---|
| F0 | 项目基础架构 | 建立可扩展目录、配置、依赖、运行入口和测试基础 |
| F1 | 学习目标输入 | 收集完整 `StudyGoal`，提交给后续流程 |
| F2 | 智能学习计划生成 | 基于 `StudyGoal` 生成阶段、周、日三级学习计划 |
| F3 | 学习计划展示与编辑 | 展示计划、修改任务、标记状态、查看进度 |
| F4 | 资料上传与问答 | 上传资料、建立索引、基于资料问答并展示来源 |
| F5 | 复盘与动态调整 | 根据完成情况生成复盘，并重排后续计划 |
| F6 | 学习计划导出 | 导出 Markdown、HTML，预留 PDF |
| F7 | 持久化与数据管理 | 用 PostgreSQL 保存计划、任务、进度、资料元数据 |
| F8 | Agent 工作流编排 | 用 LangGraph 组织 Profile、Knowledge、Resource、Planner、Critic、Progress 流程 |
| F9 | Streamlit 产品集成 | 把全部能力整合成可用的多页面应用 |

### 0.2 暂不做的增强功能

以下功能不进入 MVP，完成 MVP 后再考虑：

- 多用户账号系统
- 复杂权限管理
- 移动端独立 App
- 日历视图
- 番茄钟
- 自动提醒
- 错题本
- FastAPI 后端服务化
- 复杂多模型管理界面

## F0. 项目基础架构

### 目标

建立一个可以支撑后续扩展的最小项目骨架，避免业务逻辑散落在 Streamlit 页面里。

### 功能范围

- 建立核心包 `study_planner`
- 建立分层目录：
  - `domain`
  - `application`
  - `agents`
  - `ports`
  - `infrastructure`
  - `interfaces/streamlit`
  - `prompts`
- 建立 `tests`
- 建立 `.env.example`
- 明确本地运行命令

### 实现要求

- `domain` 放核心业务模型和规则。
- `application` 放用户用例，例如生成计划、上传资料、复盘重排。
- `ports` 放抽象接口，例如 LLM、Repository、VectorStore、Exporter。
- `infrastructure` 放具体实现，例如 OpenAI、PostgreSQL、Milvus。
- `interfaces/streamlit` 只负责页面输入、按钮、展示和状态。
- 测试默认不依赖真实 LLM、PostgreSQL、Milvus。

### 验收标准

- 可以运行单元测试。
- 可以启动 Streamlit 首页。
- 项目目录职责清晰。
- 新功能可以按分层位置添加，不需要写到一个大文件里。

### 完成定义

- `python -m pytest` 能发现测试。
- `streamlit run study_planner/interfaces/streamlit/app.py` 能启动应用入口。
- README 或文档中有启动说明。

## F1. 学习目标输入

### 目标

用户在 Streamlit 页面填写学习目标和约束，系统将表单数据转换成结构化 `StudyGoal`，并提交给后续流程。

### 用户输入

- 学习主题
- 学习目标
- 截止日期
- 当前水平
- 每日可学习时间
- 每周可学习天数
- 学习偏好
- 薄弱点
- 额外要求

### 领域模型

`StudyGoal` 至少包含：

- `subject`
- `target`
- `deadline`
- `current_level`
- `daily_available_minutes`
- `weekly_available_days`
- `preferred_methods`
- `weak_points`
- `extra_requirements`

### 实现要求

- 必填字段为空时不能提交。
- 截止日期不能早于今天。
- 每日可学习时间必须在合理范围内。
- 每周学习天数必须在 1 到 7 之间。
- 学习偏好、薄弱点、额外要求允许为空。
- 文本字段需要去除前后空格。
- 薄弱点支持列表输入，也支持逗号分隔文本转换成列表。
- 提交后保存到 Streamlit Session State，供 F2 使用。

### 页面要求

- 页面名称：学习目标配置
- 必须有提交按钮。
- 提交成功后展示配置摘要。
- 校验失败时给出清晰错误提示。

### 测试要求

- 完整表单可生成 `StudyGoal`。
- 必填字段校验。
- 日期校验。
- 时间范围校验。
- 每周学习天数校验。
- 可选字段为空时可提交。
- 中文输入不乱码。
- 提交后能交给后续流程。

### 完成定义

- `tests/test_f1_study_goal_input.py` 全部通过。
- 页面可以收集完整 `StudyGoal`。
- F2 可以从状态中读取该 `StudyGoal`。

## F2. 智能学习计划生成

### 目标

根据 `StudyGoal` 生成完整结构化学习计划，计划必须包含阶段、周、日三级结构。

### 输出内容

学习计划必须包含：

- 总体学习路线
- 阶段目标
- 周计划
- 每日任务
- 学习方法
- 时间预算
- 风险提示
- 复习安排
- 执行建议

### 领域模型

至少需要：

- `StudyPlan`
- `StudyPhase`
- `WeeklyPlan`
- `StudyTask`
- `TimeBudget`
- `ReviewSchedule`

### 结构要求

```text
StudyPlan
  -> phases
      -> weekly_plans
          -> tasks
```

每个 `StudyTask` 至少包含：

- 标题
- 日期
- 时长
- 任务类型
- 关联知识点
- 学习方法
- 预期产出
- 是否需要复习
- 状态

### F2-A：Fake LLM 结构生成

目标：先用 Fake LLM 跑通数据结构、解析和校验，不依赖真实 API。

实现要求：

- `GenerateStudyPlanUseCase` 接收 `StudyGoal`。
- Fake LLM 返回字典或 JSON。
- 用例将结果转换为 `StudyPlan`。
- 系统计算 `TimeBudget`，不完全相信 LLM。
- 校验阶段、周、日三级结构。
- 校验每日任务总时长。
- 校验任务日期不超过截止日期。

验收标准：

- `tests/test_f2_generate_study_plan.py` 全部通过。

### F2-B：真实 LLM 接入

目标：真实模型可以根据 prompt 返回结构化 JSON，并进入 F2-A 的同一套解析与校验流程。

实现要求：

- 提供 `build_study_plan_prompt(goal)`。
- Prompt 必须包含完整 `StudyGoal`。
- Prompt 必须要求只输出 JSON。
- Prompt 必须明确输出字段和三级结构。
- `RealStudyPlanLLM` 能处理：
  - 普通字符串响应
  - LangChain message `content`
  - ```json 代码块
  - 非 JSON 响应
  - JSON 顶层不是对象
  - 有限重试
- ISO 日期字符串要转换为 `date`。
- 计划绑定调用方传入的原始 `StudyGoal`，不能让 LLM 覆盖用户目标。

验收标准：

- `tests/test_f2b_real_llm_integration.py` 全部通过。
- 手动测试真实 LLM 可生成合法 `StudyPlan`。

### 页面要求

- F1 提交后可点击“生成学习计划”。
- 生成中展示加载状态。
- 成功后把 `StudyPlan` 保存到 Session State。
- 失败时展示错误原因。

### 完成定义

- Fake LLM 测试通过。
- Real LLM 接入测试通过。
- 手动输入目标后可以生成阶段、周、日三级计划。
- 生成结果可被 F3 展示。

## F3. 学习计划展示与编辑

### 目标

用户可以在 Streamlit 中查看学习计划、编辑任务，并标记完成状态。

### 展示内容

- 总体目标摘要
- 总体学习路线
- 阶段计划 Tabs
- 周计划列表
- 今日任务
- 本周任务表格
- 风险提示
- 复习安排
- 学习方法
- 学习进度图表

### 编辑能力

用户可以修改：

- 任务状态
- 任务日期
- 任务时长
- 任务备注

任务状态至少包括：

- `todo`
- `doing`
- `done`
- `skipped`

### 实现要求

- 从 Session State 或 PostgreSQL 读取 `StudyPlan`。
- 页面显示阶段、周、日三级结构。
- 修改任务后更新当前计划状态。
- 完成率自动计算。
- 每日任务时长修改后不能超过每日可学习时间。
- 任务日期不能超过目标截止日期。

### 图表要求

至少提供：

- 总完成率
- 已完成任务数 / 总任务数
- 每日计划分钟数
- 每周计划分钟数

### 测试要求

- 能展示空计划提示。
- 能展示完整计划。
- 能按阶段和周查看任务。
- 能标记任务完成。
- 能修改任务日期、时长、备注。
- 修改非法日期或超时时长时被拒绝。
- 完成率计算正确。

### 完成定义

- 用户能在页面上看懂计划。
- 用户能更新任务状态。
- 更新后的计划能被 F5 读取。

## F4. 资料上传与问答

### 目标

用户上传学习资料，系统解析、切分、向量化并保存到 Milvus，用户可以基于资料提问，系统回答并展示引用来源。

### 支持文件类型

- PDF
- Markdown
- TXT
- 课程笔记

### 核心流程

```text
上传文件
  -> 保存原始文件
  -> 解析文本
  -> 文档切分
  -> 生成 dense embedding 和 sparse embedding
  -> 写入 Milvus hybrid collection
  -> 保存资料元数据到 PostgreSQL
  -> 用户提问
  -> 查询路由
  -> 查询改写或多查询分解
  -> Milvus 混合检索 dense + sparse
  -> RRF 融合排序
  -> 元数据过滤
  -> 可选重排与上下文压缩
  -> LLM 基于 chunks 回答
  -> 展示答案和引用来源
```

### 检索策略

参考 `all-in-rag` 第四章的混合检索、查询构建、查询重写和进阶检索内容，Study-Planner 的 F4 推荐采用以下检索方式：

#### MVP 默认策略：Milvus 混合检索

- 使用 Milvus 同时保存 `dense_vector` 和 `sparse_vector`。
- dense vector 用于语义召回，解决用户问法和资料措辞不同的问题。
- sparse vector 用于关键词精确匹配，适合课程术语、函数名、考试名、章节名。
- 查询时并行执行 dense search 和 sparse search。
- 使用 RRF 进行结果融合排序。
- 返回的 chunk 必须保留 `material_id`、`filename`、`page_number`、`chunk_index`、`snippet`。

#### 元数据过滤

每个 chunk 必须带元数据，用于查询构建和过滤：

- `material_id`
- `filename`
- `file_type`
- `source`
- `page_number`
- `section_title`
- `chunk_index`
- `created_at`
- `tags`

系统需要支持按资料、文件类型、章节、标签进行过滤。例如：

- “只看这份 PDF 里的递归内容”
- “从 Markdown 笔记里找动态规划”
- “总结第 3 页附近的内容”

#### 查询改写与多查询

用户问题较短、模糊或包含多个意图时，先进行查询改写：

- 简单问题：直接检索。
- 模糊问题：生成更明确的检索查询。
- 复杂问题：拆成多个子查询，分别检索后去重合并。
- 概念型问题：可选使用 HyDE 生成假设性答案，再用假设性答案向量检索。

#### 查询路由

根据用户意图选择处理路径：

- `qa`：资料问答
- `summary`：资料摘要
- `concept_explain`：概念解释
- `flashcard`：复习卡片
- `knowledge_points`：知识点提取

路由可以先用规则实现，后续升级为 LLM 意图识别。

#### 可选重排与压缩

MVP 默认使用 RRF。后续可以打开：

- `LLM rerank`：让 LLM 对 Top-K chunks 相关性排序。
- `Cross-Encoder rerank`：用于高精度重排。
- `Contextual compression`：只保留与问题相关的句子，减少上下文噪音。

MVP 不强制实现 Cross-Encoder 和 ColBERT，但接口应预留。

### 领域模型

至少需要：

- `LearningMaterial`
- `DocumentChunk`
- `MaterialQuestion`
- `MaterialAnswer`
- `Citation`
- `Flashcard`

### 抽象接口

需要定义：

- `DocumentParser`
- `EmbeddingClient`
- `VectorStore`
- `QueryRouter`
- `QueryRewriter`
- `HybridRetriever`
- `Reranker`
- `ContextCompressor`
- `MaterialRepository`
- `RAGAnswerService`

### 实现要求

- 上传资料后能保存文件名、类型、上传时间。
- 文档切片必须包含来源信息和可过滤元数据。
- Milvus 必须支持 dense + sparse 混合检索。
- 混合检索必须支持 RRF 融合排序。
- 检索必须支持按资料、文件类型、章节或标签进行元数据过滤。
- 查询较复杂时支持 query rewrite 或 multi-query。
- Milvus 检索结果必须能追溯到原文片段。
- 回答必须基于检索片段。
- 回答必须展示引用来源。
- 支持资料摘要。
- 支持概念解释。
- 支持生成复习卡片。
- 支持从资料提取知识点。

### 测试要求

- TXT/Markdown/PDF 解析测试。
- 文档切分测试。
- Milvus hybrid upsert/search 接口测试，可先用 Fake HybridVectorStore。
- dense 检索、sparse 检索、hybrid 检索和 RRF 排序测试。
- 元数据过滤测试。
- query rewrite 和 multi-query 测试。
- 查询路由测试。
- 可选 rerank/compression 测试。
- RAG 问答测试，可先用 Fake LLM。
- 回答引用来源测试。
- 空资料提问时给出提示。
- 检索不到资料时给出提示。

### 完成定义

- 用户能上传资料。
- 用户能对资料提问。
- 回答能显示引用来源。
- 资料可以辅助 F2 或 F5 生成更贴合资料的计划。

## F5. 复盘与动态调整

### 目标

用户更新学习进度后，系统生成复盘报告，并根据完成情况调整后续计划。

### 输入

- 当前 `StudyPlan`
- 任务完成状态
- 用户复盘文本
- 延期任务
- 薄弱点

### 输出

- 本周复盘
- 完成率分析
- 延期任务处理建议
- 薄弱知识点强化任务
- 后续计划重排
- 下一阶段学习建议

### 领域模型

至少需要：

- `TaskProgress`
- `ReviewReport`
- `ReplanRequest`
- `AdjustedStudyPlan`

### 实现要求

- 能统计任务完成率。
- 能识别延期任务。
- 能识别连续未完成任务。
- 能根据剩余时间重新安排任务。
- 重排后仍满足每日时间限制。
- 重排后仍满足截止日期限制。
- 用户确认后才保存调整后的计划。

### Agent 要求

Progress Agent 负责：

- 分析完成情况。
- 总结薄弱点。
- 生成复盘报告。
- 构造重排请求。

Planner/Critic 负责：

- 重新安排后续任务。
- 检查新计划是否过载。

### 页面要求

- 展示完成情况表格。
- 提供本周复盘输入框。
- 提供自动重排按钮。
- 展示调整前后对比。
- 提供保存调整按钮。

### 测试要求

- 完成率计算正确。
- 延期任务识别正确。
- 全部完成时不需要大幅重排。
- 部分延期时能重排剩余任务。
- 重排后不超过每日学习时间。
- 用户未确认时不覆盖原计划。
- 用户确认后保存新计划。

### 完成定义

- 用户可以从 F3 标记任务完成。
- F5 能根据进度生成复盘。
- F5 能生成调整后的计划。
- 调整后的计划能回到 F3 展示。

## F6. 学习计划导出

### 目标

用户可以导出学习计划和复盘报告，方便保存和分享。

### 支持格式

MVP 必须支持：

- Markdown
- HTML

后续增强：

- PDF

### 导出内容

- 学习目标
- 总体路线
- 阶段计划
- 周计划
- 每日任务
- 学习方法
- 风险提示
- 复习安排
- 时间预算
- 当前完成状态
- 复盘报告，若存在

### 抽象接口

需要定义：

- `Exporter`
- `MarkdownExporter`
- `HTMLExporter`
- `PDFExporter`，可预留

### 实现要求

- 导出内容与当前页面计划一致。
- Markdown 格式结构清晰。
- HTML 可直接打开查看。
- 文件名包含学习主题和日期。
- 没有计划时不能导出，并给出提示。

### 测试要求

- Markdown 导出包含关键字段。
- HTML 导出包含关键字段。
- 无计划导出时报错或提示。
- 中文内容不乱码。
- 已完成任务状态能导出。

### 完成定义

- 用户能下载 Markdown。
- 用户能下载 HTML。
- 导出文件能完整表达当前计划。

## F7. 持久化与数据管理

### 目标

使用 PostgreSQL 保存结构化数据，避免应用刷新后丢失计划和进度。

### 数据范围

需要保存：

- 学习目标
- 学习计划
- 阶段
- 周计划
- 每日任务
- 任务进度
- 复盘报告
- 资料元数据
- 导出记录，可选

### 抽象接口

需要定义：

- `StudyGoalRepository`
- `StudyPlanRepository`
- `TaskProgressRepository`
- `ReviewReportRepository`
- `MaterialRepository`

### 实现要求

- 业务代码只依赖 Repository 接口。
- PostgreSQL 实现放在 `infrastructure/db`。
- MVP 可以先把复杂嵌套计划以 JSONB 保存。
- 后续需要统计时，再拆成规范化表。
- 保存失败时页面给出错误提示。
- 读取失败时不影响应用启动。

### 建议数据表

MVP 可用：

- `study_goals`
- `study_plans`
- `task_progress`
- `review_reports`
- `materials`

### 测试要求

- Repository 保存和读取学习目标。
- Repository 保存和读取学习计划。
- 更新任务进度。
- 保存复盘报告。
- 数据库不可用时错误清晰。

### 完成定义

- 刷新 Streamlit 后能恢复最近的学习计划。
- 任务完成状态能持久保存。
- F3、F5、F6 可以读取持久化数据。

## F8. Agent 工作流编排

### 目标

用 LangGraph 将学习规划流程从单一 LLM 调用升级为可扩展多节点 Agent 工作流。

### 工作流节点

至少包含：

- Profile Agent：学习画像分析
- Knowledge Agent：知识点拆解
- Resource Agent：资料与资源检索
- Planner Agent：学习计划生成
- Critic Agent：可行性检查
- Progress Agent：复盘与重排
- Output Agent：结构化输出

### 状态模型

需要定义 `PlannerState`：

- `goal`
- `learner_profile`
- `knowledge_points`
- `resources`
- `draft_plan`
- `review`
- `final_plan`
- `errors`

### 实现要求

- 每个节点只做一件事。
- 工作流入口统一封装为 `PlannerWorkflow.run(goal)`。
- Application 层只调用 `PlannerWorkflow`，不直接依赖 LangGraph 细节。
- Critic 发现计划过载时，可以返回 Planner 修复。
- Output Agent 负责最终结构化输出和校验。

### 测试要求

- Profile 节点能生成画像。
- Knowledge 节点能生成知识点。
- Resource 节点能返回资料或资源。
- Planner 节点能生成草案。
- Critic 能发现明显过载。
- Workflow 能返回最终 `StudyPlan`。
- 节点失败时错误进入 `errors`。

### 完成定义

- F2 可以使用 LangGraph 工作流生成计划。
- F5 可以复用工作流进行动态调整。
- 替换单个 Agent 不影响页面层。

## F9. Streamlit 产品集成

### 目标

把 F1 到 F8 集成为完整可用的 Streamlit 应用。

### 页面结构

至少包含：

- 首页
- 学习目标配置页
- 学习计划看板页
- 资料问答页
- 复盘调整页

### 全局状态

Session State 至少管理：

- `study_goal`
- `study_plan`
- `selected_plan_id`
- `materials`
- `last_review_report`
- `errors`

### 页面流转

```text
学习目标配置
  -> 生成学习计划
  -> 学习计划看板
  -> 资料问答，可选
  -> 复盘调整
  -> 导出
```

### 实现要求

- 页面不直接调用 LLM SDK。
- 页面不直接写 SQL。
- 页面不直接调用 Milvus SDK。
- 页面只调用 Application UseCase。
- 长任务显示加载状态。
- 错误展示为用户可理解的信息。
- 关键操作完成后更新 Session State。

### 测试要求

- 手动测试主流程可以完整走通。
- 没有学习目标时不能生成计划。
- 没有学习计划时看板给出提示。
- 上传资料后资料问答可用。
- 更新进度后复盘可用。
- 导出按钮可下载文件。

### 完成定义

- 用户能从零开始完成完整流程：

```text
填写目标
  -> 生成计划
  -> 查看并编辑任务
  -> 上传资料并问答
  -> 标记进度
  -> 复盘调整
  -> 导出计划
```

## 10. 推荐实施顺序

### 第一阶段：可运行骨架

1. F0 项目基础架构
2. F1 学习目标输入
3. F2-A Fake LLM 计划生成
4. F3 基础计划展示

完成后，项目可以不依赖真实模型完成端到端演示。

### 第二阶段：真实智能能力

1. F2-B 真实 LLM 接入
2. F8 基础 LangGraph 工作流
3. F3 编辑与进度图表增强

完成后，项目可以用真实 LLM 生成计划。

### 第三阶段：资料能力

1. F4 资料上传
2. F4 文档解析和切片
3. F4 Milvus 检索
4. F4 RAG 问答和引用来源

完成后，项目具备资料问答能力。

### 第四阶段：闭环能力

1. F7 PostgreSQL 持久化
2. F5 复盘与动态调整
3. F6 导出
4. F9 全产品集成

完成后，项目形成完整学习闭环。

## 11. 全项目完成标准

项目完成时必须满足：

- 用户可以输入学习目标。
- 系统可以生成阶段、周、日三级学习计划。
- 用户可以查看和编辑计划。
- 用户可以上传资料并基于资料问答。
- 用户可以标记学习进度。
- 系统可以生成复盘并调整计划。
- 用户可以导出学习计划。
- PostgreSQL 能保存核心数据。
- Milvus 能保存和检索资料向量。
- Streamlit 页面能完整走通主流程。
- 单元测试覆盖核心领域逻辑和用例。
- 真实 LLM 接入有明确错误处理和手动验收方案。
