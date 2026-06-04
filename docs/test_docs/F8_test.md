# F8 Agent 工作流编排测试用例方案

## 1. 测试目标

F8 的目标是：用 LangGraph 或等价可编排图工作流，把学习规划从单一 LLM 调用升级为可扩展、多节点、可替换、可恢复的 Agent 工作流。工作流需要覆盖学习画像分析、知识点拆解、资料与资源检索、计划生成、可行性检查、结构化输出，以及复盘后的动态重排。

测试重点不是验证某个模型回答是否“聪明”，而是验证工作流边界清晰、节点职责单一、状态传递稳定、错误可控、可替换性强，并且 F2/F5 可以复用同一套工作流能力。

## 2. 需求来源

### 2.1 PRD 相关要求

PRD 中 F8 相关要求包括：

- 项目采用 LangGraph 作为 Agent 编排框架。
- 不依赖 HelloAgents 框架。
- 多 Agent 协作完成信息分析、任务拆解、计划生成、结构化输出、复盘和动态调整。
- Agent 层至少包含：
  - Profile Agent：学习画像分析
  - Knowledge Agent：知识点拆解
  - Resource Agent：资料与资源检索
  - Planner Agent：学习计划生成
  - Critic Agent：可行性检查
  - Progress Agent：复盘与重排
  - Output Agent：结构化输出
- Critic Agent 负责检查计划是否过载、是否遗漏先修知识、任务顺序是否合理。
- Progress Agent 读取完成情况，分析延期任务，总结薄弱点，触发重排。
- Agent 编排必须服务于 F2 学习计划生成和 F5 复盘动态调整。

### 2.2 features.md 相关要求

features.md 对 F8 的要求包括：

- 使用 LangGraph 将学习规划流程从单一 LLM 调用升级为可扩展多节点 Agent 工作流。
- 需要定义 `PlannerState`，至少包含：
  - `goal`
  - `learner_profile`
  - `knowledge_points`
  - `resources`
  - `draft_plan`
  - `review`
  - `final_plan`
  - `errors`
- 每个节点只做一件事。
- 工作流入口统一封装为 `PlannerWorkflow.run(goal)`。
- Application 层只调用 `PlannerWorkflow`，不直接依赖 LangGraph 细节。
- Critic 发现计划过载时，可以返回 Planner 修复。
- Output Agent 负责最终结构化输出和校验。
- 测试需要覆盖：
  - Profile 节点能生成画像。
  - Knowledge 节点能生成知识点。
  - Resource 节点能返回资料或资源。
  - Planner 节点能生成草案。
  - Critic 能发现明显过载。
  - Workflow 能返回最终 `StudyPlan`。
  - 节点失败时错误进入 `errors`。
- 完成定义包括：
  - F2 可以使用 LangGraph 工作流生成计划。
  - F5 可以复用工作流进行动态调整。
  - 替换单个 Agent 不影响页面层。

## 3. 测试范围

### 3.1 范围内

- `PlannerState` 状态结构。
- Profile / Knowledge / Resource / Planner / Critic / Output / Progress 节点。
- 节点输入输出契约。
- 工作流图结构与节点顺序。
- Critic -> Planner 修复回路。
- Output 结构化校验。
- Workflow 统一入口。
- F2 调用工作流生成计划。
- F5 调用工作流进行复盘重排。
- Fake LLM / Fake RAG / Fake Repository 下的可重复测试。
- Real LLM 手动验收边界。
- 错误处理、超时、重试、部分失败降级。
- 日志、trace、状态可观测性。
- 与页面层解耦。

### 3.2 范围外

- 真实模型内容质量的主观评分。
- 真实 Milvus 检索效果的召回率评估。
- PostgreSQL 持久化完整性，已由 F7 覆盖。
- Streamlit 页面视觉细节，属于 F9。
- 导出格式细节，属于 F6。

## 4. 测试对象建议

建议后续实现时至少包含以下模块或等价结构：

```text
study_planner/
  agents/
    planner_state.py
    planner_workflow.py
    nodes/
      profile.py
      knowledge.py
      resource.py
      planner.py
      critic.py
      output.py
      progress.py
  application/
    generate_study_plan.py
    review_replan.py
  infrastructure/
    llm/
    rag/
```

测试文件建议：

```text
tests/test_f8_agent_workflow.py
tests/test_f8_workflow_integration.py
```

## 5. 输入数据

### 5.1 StudyGoal

至少包含：

- `subject`
- `target`
- `deadline`
- `current_level`
- `daily_available_minutes`
- `weekly_available_days`
- `preferred_methods`
- `weak_points`
- `extra_requirements`

### 5.2 已有资料上下文

可选输入：

- 已上传资料元数据。
- RAG 检索片段。
- 用户指定资料偏好。
- KnowledgePoint 列表。

### 5.3 复盘上下文

F5 复用工作流时至少输入：

- 当前 `StudyPlan`
- `ReviewReport`
- 未完成任务
- 延期任务
- 剩余天数
- 每日可用时间

## 6. 输出数据

### 6.1 Workflow 输出

至少输出：

- `final_plan: StudyPlan`
- `errors: list`
- `review` 或 critic 检查结果
- 可选：节点执行记录、修复次数、资源引用信息

### 6.2 节点输出

- Profile Agent 输出 `LearnerProfile` 或等价结构。
- Knowledge Agent 输出 `KnowledgePoint` 列表。
- Resource Agent 输出 `LearningResource` 或 RAG 资源列表。
- Planner Agent 输出 `draft_plan`。
- Critic Agent 输出可行性检查结果。
- Output Agent 输出合法 `StudyPlan`。
- Progress Agent 输出重排请求或调整建议。

## 7. 测试环境

### 7.1 Fake 环境

默认自动化测试使用 Fake 环境：

- Fake LLM：返回固定结构化 JSON。
- Fake RAG：返回固定资源列表。
- Fake Critic：可配置通过、失败、过载、缺先修。
- Fake Planner：可配置首次生成过载计划，二次修复成功。
- Fake LangGraph Runner：如暂未引入真实 LangGraph，可先用等价图执行器验证状态流。

### 7.2 Real 环境

真实手动或集成测试使用：

- `USE_REAL_LLM=true`
- DeepSeek 或其他真实模型配置。
- 可选真实 RAG。
- 可选 LangSmith trace。

Real 环境测试不应阻塞普通 CI。

## 8. 测试策略

### 8.1 单元测试

验证单个节点输入输出、异常处理、字段完整性。

### 8.2 工作流测试

验证多个节点按顺序执行、状态正确传递、回路可控、最终输出合法。

### 8.3 集成测试

验证 F2/F5 通过 workflow 入口完成原有功能。

### 8.4 契约测试

验证 Application 层不依赖 LangGraph 细节，只依赖 `PlannerWorkflow` 接口。

### 8.5 手动测试

验证真实 LLM 下工作流可生成合理计划和调整计划。

## 9. 测试用例总览

| 阶段 | 范围 | 用例数 |
|---|---|---:|
| 阶段一 | PlannerState 状态结构 | 8 |
| 阶段二 | Profile Agent | 7 |
| 阶段三 | Knowledge Agent | 8 |
| 阶段四 | Resource Agent | 7 |
| 阶段五 | Planner Agent | 8 |
| 阶段六 | Critic Agent | 9 |
| 阶段七 | Output Agent | 8 |
| 阶段八 | Progress Agent | 7 |
| 阶段九 | Workflow 图编排 | 10 |
| 阶段十 | F2 集成 | 7 |
| 阶段十一 | F5 集成 | 7 |
| 阶段十二 | 错误处理与可观测性 | 9 |
| 阶段十三 | 替换性与解耦 | 6 |
| 阶段十四 | Real LLM 手动验收 | 6 |
| 合计 |  | 107 |

## 10. 阶段一：PlannerState 状态结构

### TC-F8-001 PlannerState 包含必需字段

前置条件：

- 定义 `PlannerState` 或等价结构。

步骤：

1. 构造最小 `PlannerState`。
2. 检查字段。

预期结果：

- 包含 `goal`、`learner_profile`、`knowledge_points`、`resources`、`draft_plan`、`review`、`final_plan`、`errors`。

原因：

- features.md 明确要求这些状态字段。

### TC-F8-002 PlannerState 可以初始化为空流程状态

前置条件：

- 有合法 `StudyGoal`。

步骤：

1. 用 `StudyGoal` 初始化状态。
2. 其他节点产物为空。

预期结果：

- `goal` 有值。
- `errors` 默认为空列表。
- `final_plan` 为空。

原因：

- 工作流需要从用户目标开始逐步填充状态。

### TC-F8-003 PlannerState 保存 Profile 节点输出

步骤：

1. 运行 Profile 节点。
2. 将结果写入状态。

预期结果：

- `learner_profile` 被正确填充。
- `goal` 不被覆盖。

原因：

- 节点只能追加自身职责范围内的数据。

### TC-F8-004 PlannerState 保存 Knowledge 节点输出

步骤：

1. 输入含目标和画像的状态。
2. 运行 Knowledge 节点。

预期结果：

- `knowledge_points` 非空。
- 每个知识点包含名称、难度、重要性或等价字段。

原因：

- Planner 需要知识点作为任务拆解依据。

### TC-F8-005 PlannerState 保存 Resource 节点输出

步骤：

1. 输入含知识点的状态。
2. 运行 Resource 节点。

预期结果：

- `resources` 可以为空列表或资源列表。
- 空资源不应中断工作流。

原因：

- 用户可能没有上传资料。

### TC-F8-006 PlannerState 保存 draft_plan 和 final_plan

步骤：

1. Planner 节点写入 `draft_plan`。
2. Output 节点写入 `final_plan`。

预期结果：

- `draft_plan` 保留草案。
- `final_plan` 是结构化 `StudyPlan`。

原因：

- Critic 和 Output 需要区分草案和最终计划。

### TC-F8-007 PlannerState errors 可累积多个节点错误

步骤：

1. 模拟 Resource 节点失败。
2. 模拟 Critic 节点失败。
3. 检查 `errors`。

预期结果：

- `errors` 包含两个错误。
- 错误包含节点名和可读消息。

原因：

- 节点失败时错误进入 `errors` 是 F8 测试要求。

### TC-F8-008 PlannerState 不保存不可序列化对象

步骤：

1. 节点返回不可 JSON 序列化对象。
2. 写入状态前进行检查。

预期结果：

- 拒绝或转换不可序列化对象。
- `errors` 记录原因。

原因：

- LangGraph 状态通常需要可检查、可追踪、可恢复。

## 11. 阶段二：Profile Agent

### TC-F8-009 Profile Agent 能生成学习画像

步骤：

1. 输入 `StudyGoal`。
2. 运行 Profile Agent。

预期结果：

- 输出学习画像。
- 包含当前水平、时间约束、偏好、风险初判。

原因：

- PRD 要求 Profile Agent 分析用户当前水平、时间约束和学习偏好。

### TC-F8-010 Profile Agent 不修改原始目标

步骤：

1. 输入目标。
2. 运行 Profile Agent。
3. 比较输入目标。

预期结果：

- `StudyGoal` 原始字段不被覆盖。

原因：

- 用户原始目标是后续流程的事实源。

### TC-F8-011 Profile Agent 识别零基础风险

步骤：

1. 输入 `current_level=零基础`。
2. 运行 Profile Agent。

预期结果：

- 画像中包含入门难度或基础薄弱风险。

原因：

- 计划生成要基于学习画像调整任务粒度。

### TC-F8-012 Profile Agent 识别时间紧张

步骤：

1. 输入 deadline 很近、每日学习时间较少的目标。
2. 运行 Profile Agent。

预期结果：

- 输出时间紧张或过载风险。

原因：

- Critic 和 Planner 需要用该信息控制计划可行性。

### TC-F8-013 Profile Agent 保留中文输入

步骤：

1. 输入中文目标、偏好和薄弱点。
2. 运行 Profile Agent。

预期结果：

- 输出中文不乱码。

原因：

- 产品面向中文学习场景。

### TC-F8-014 Profile Agent 支持空可选字段

步骤：

1. 输入空 `preferred_methods`、空 `weak_points`。
2. 运行 Profile Agent。

预期结果：

- 不报错。
- 输出画像包含默认或空列表。

原因：

- F1 允许可选字段为空。

### TC-F8-015 Profile Agent 失败时错误进入状态

步骤：

1. 让 Profile Agent 抛出异常。
2. 运行工作流。

预期结果：

- `errors` 包含 Profile 节点错误。
- 工作流按策略停止或降级。

原因：

- 节点失败必须可追踪。

## 12. 阶段三：Knowledge Agent

### TC-F8-016 Knowledge Agent 能生成知识点列表

步骤：

1. 输入学习目标和画像。
2. 运行 Knowledge Agent。

预期结果：

- 输出 `KnowledgePoint` 列表。
- 至少包含名称、描述、难度、重要性。

原因：

- PRD 要求 Knowledge Agent 拆解知识点。

### TC-F8-017 Knowledge Agent 标注先修关系

步骤：

1. 输入有明显先修关系的主题，如机器学习。
2. 运行 Knowledge Agent。

预期结果：

- 部分知识点包含 prerequisites。

原因：

- Critic 需要检查任务顺序是否符合先修关系。

### TC-F8-018 Knowledge Agent 难度范围合法

步骤：

1. 运行 Knowledge Agent。
2. 检查 difficulty。

预期结果：

- 难度值在约定范围内，例如 1 到 5。

原因：

- Planner 需要根据难度分配任务时长。

### TC-F8-019 Knowledge Agent 重要性范围合法

步骤：

1. 运行 Knowledge Agent。
2. 检查 importance。

预期结果：

- 重要性值在约定范围内，例如 1 到 5。

原因：

- 后续复习和强化任务需要使用重要性。

### TC-F8-020 Knowledge Agent 去重重复知识点

步骤：

1. Fake LLM 返回重复知识点。
2. 运行 Knowledge Agent。

预期结果：

- 输出知识点名称去重。

原因：

- 重复知识点会导致重复任务。

### TC-F8-021 Knowledge Agent 保留用户薄弱点

步骤：

1. `StudyGoal.weak_points` 包含“递归”。
2. 运行 Knowledge Agent。

预期结果：

- 知识点或画像中保留“递归”。

原因：

- 用户薄弱点影响计划重点。

### TC-F8-022 Knowledge Agent 处理 LLM 非 JSON 返回

步骤：

1. Fake LLM 返回普通文本。
2. 运行 Knowledge Agent。

预期结果：

- 抛出可理解错误或进入 `errors`。

原因：

- LLM 输出不稳定是 PRD 风险。

### TC-F8-023 Knowledge Agent 处理空知识点

步骤：

1. Fake LLM 返回空列表。
2. 运行 Knowledge Agent。

预期结果：

- 工作流拒绝继续生成计划，或用兜底知识点。
- `errors` 或 warnings 记录原因。

原因：

- Planner 不能在完全无知识点时盲目生成。

## 13. 阶段四：Resource Agent

### TC-F8-024 Resource Agent 能返回资料资源

步骤：

1. 输入知识点和已有资料。
2. 运行 Resource Agent。

预期结果：

- 输出资源列表。
- 每条资源包含标题、来源、关联知识点。

原因：

- PRD 要求 Resource Agent 处理资料和资源。

### TC-F8-025 Resource Agent 无资料时返回空列表

步骤：

1. 不提供资料。
2. 运行 Resource Agent。

预期结果：

- 返回空资源列表。
- 工作流继续执行。

原因：

- F2 不应强依赖 F4 资料。

### TC-F8-026 Resource Agent 可以调用 RAG 服务

步骤：

1. 注入 Fake RAG。
2. 运行 Resource Agent。

预期结果：

- Fake RAG 收到查询。
- resources 包含检索结果。

原因：

- Resource Agent 与 RAGService 有明确交互。

### TC-F8-027 Resource Agent 失败时可降级

步骤：

1. Fake RAG 抛出异常。
2. 运行 Resource Agent。

预期结果：

- `errors` 记录 Resource 错误。
- resources 为空。
- Planner 仍可基于知识点生成计划。

原因：

- 资料服务失败不应阻断基础计划生成。

### TC-F8-028 Resource Agent 保留引用来源

步骤：

1. Fake RAG 返回带 citation 的资源。
2. 运行 Resource Agent。

预期结果：

- resources 保留 filename、chunk_id 或 URL。

原因：

- 后续计划任务可绑定资源来源。

### TC-F8-029 Resource Agent 支持按知识点过滤资源

步骤：

1. 输入多个知识点。
2. Fake RAG 返回混合资源。

预期结果：

- 每条资源能关联到至少一个知识点。

原因：

- Planner 需要给任务绑定相关资源。

### TC-F8-030 Resource Agent 不直接依赖 Milvus SDK

步骤：

1. 检查 Resource Agent 模块导入。

预期结果：

- 不直接导入 Milvus SDK。
- 通过 RAG 抽象接口调用。

原因：

- 页面和 Agent 层应与基础设施解耦。

## 14. 阶段五：Planner Agent

### TC-F8-031 Planner Agent 能生成草案计划

步骤：

1. 输入目标、画像、知识点、资源。
2. 运行 Planner Agent。

预期结果：

- 输出 `draft_plan`。
- 包含阶段、周计划和任务。

原因：

- Planner Agent 负责学习计划生成。

### TC-F8-032 草案计划绑定原始 StudyGoal

步骤：

1. 输入目标。
2. 运行 Planner Agent。

预期结果：

- `draft_plan.goal == input_goal`。

原因：

- LLM 不应覆盖用户原始目标。

### TC-F8-033 草案计划包含三层结构

步骤：

1. 运行 Planner Agent。
2. 检查 `phases -> weekly_plans -> tasks`。

预期结果：

- 三层结构完整。

原因：

- F2 已要求阶段、周、日三级计划。

### TC-F8-034 草案任务包含必需字段

步骤：

1. 检查任务字段。

预期结果：

- 至少包含 title、date、duration_minutes、task_type、related_topics、learning_method、expected_output、status、id。

原因：

- F3/F5/F6 都依赖任务字段。

### TC-F8-035 Planner Agent 使用 KnowledgePoint 生成任务主题

步骤：

1. 输入知识点“递归”。
2. 运行 Planner Agent。

预期结果：

- 任务相关 topics 或标题中包含该知识点。

原因：

- 知识点拆解必须影响计划。

### TC-F8-036 Planner Agent 使用 Resource 输出

步骤：

1. 输入资源“Python 官方文档”。
2. 运行 Planner Agent。

预期结果：

- 任务学习方法或资源引用包含相关资源。

原因：

- Resource Agent 结果应被消费。

### TC-F8-037 Planner Agent 处理 LLM 缺字段

步骤：

1. Fake Planner LLM 返回缺少 phases。
2. 运行 Planner Agent。

预期结果：

- 抛出结构化错误。
- `errors` 包含 Planner 节点错误。

原因：

- Output 不应接收明显无效草案。

### TC-F8-038 Planner Agent 支持重排请求

步骤：

1. 输入 `ReplanRequest`。
2. 运行 Planner Agent。

预期结果：

- 只重排未完成任务或延期任务。
- 已完成任务保持完成状态。

原因：

- F5 需要复用工作流进行动态调整。

## 15. 阶段六：Critic Agent

### TC-F8-039 Critic Agent 能发现每日过载

步骤：

1. 输入某日总任务时长超过每日可用时间的草案。
2. 运行 Critic Agent。

预期结果：

- review 标记不可通过。
- 包含过载日期和分钟数。

原因：

- PRD 风险要求 Critic 检查每日任务时长。

### TC-F8-040 Critic Agent 能发现任务超过 deadline

步骤：

1. 输入任务日期晚于目标 deadline 的草案。
2. 运行 Critic Agent。

预期结果：

- review 标记不可通过。
- 错误说明 deadline 超限。

原因：

- 计划必须可执行。

### TC-F8-041 Critic Agent 能发现缺少先修

步骤：

1. 输入知识点先修关系。
2. 计划中高级任务早于先修任务。
3. 运行 Critic Agent。

预期结果：

- review 标记先修顺序错误。

原因：

- PRD 要求 Critic 检查任务顺序是否合理。

### TC-F8-042 Critic Agent 能发现任务粒度过大

步骤：

1. 输入单个任务时长过长的草案。
2. 运行 Critic Agent。

预期结果：

- review 建议拆分任务。

原因：

- 过大任务影响执行体验。

### TC-F8-043 Critic Agent 通过合理计划

步骤：

1. 输入合法草案。
2. 运行 Critic Agent。

预期结果：

- review 通过。
- 不产生错误。

原因：

- 合理计划不应被误拒。

### TC-F8-044 Critic 失败后返回 Planner 修复

步骤：

1. Planner 首次生成过载草案。
2. Critic 标记失败。
3. 工作流返回 Planner 修复。

预期结果：

- Planner 被调用第二次。
- 第二次草案不再过载。

原因：

- features.md 明确 Critic 可以返回 Planner 修复。

### TC-F8-045 Critic 修复次数有上限

步骤：

1. Fake Planner 每次都生成过载计划。
2. 运行 workflow。

预期结果：

- 达到最大修复次数后停止。
- `errors` 包含无法修复。

原因：

- 防止工作流无限循环。

### TC-F8-046 Critic 修复保留用户目标

步骤：

1. Critic 要求修复。
2. Planner 二次生成。

预期结果：

- 修复后计划仍绑定原始目标。

原因：

- 修复不能漂移目标。

### TC-F8-047 Critic Review 可序列化

步骤：

1. 运行 Critic。
2. 尝试序列化 review。

预期结果：

- review 可转 JSON。

原因：

- 状态需要可观测和可持久化。

## 16. 阶段七：Output Agent

### TC-F8-048 Output Agent 输出 StudyPlan

步骤：

1. 输入通过 Critic 的草案。
2. 运行 Output Agent。

预期结果：

- 输出 `StudyPlan` 实例。

原因：

- Output Agent 负责最终结构化输出。

### TC-F8-049 Output Agent 校验必需字段

步骤：

1. 输入缺少 time_budget 的草案。
2. 运行 Output Agent。

预期结果：

- 抛出结构化校验错误。

原因：

- 最终输出必须可被 F3/F5/F6 使用。

### TC-F8-050 Output Agent 规范化日期字段

步骤：

1. 草案日期为 ISO 字符串。
2. 运行 Output Agent。

预期结果：

- 输出中日期为 `date` 类型。

原因：

- F3/F5 依赖日期比较。

### TC-F8-051 Output Agent 生成稳定任务 ID

步骤：

1. 草案任务缺少 id。
2. 运行 Output Agent。

预期结果：

- 每个任务都有稳定唯一 id。

原因：

- F3 编辑、F5 重排、F7 持久化、F6 导出都依赖任务 ID。

### TC-F8-052 Output Agent 规范化任务状态

步骤：

1. 草案任务状态为空或中文。
2. 运行 Output Agent。

预期结果：

- 状态规范化为 todo、doing、done、skipped 之一，或报错。

原因：

- F3/F5 状态枚举必须稳定。

### TC-F8-053 Output Agent 拒绝非法状态

步骤：

1. 草案任务状态为 unknown。
2. 运行 Output Agent。

预期结果：

- 输出失败。
- `errors` 包含非法状态。

原因：

- 防止无效计划进入看板。

### TC-F8-054 Output Agent 保留中文内容

步骤：

1. 输入中文草案。
2. 运行 Output Agent。

预期结果：

- 中文内容不乱码。

原因：

- 产品面向中文用户。

### TC-F8-055 Output Agent 不调用 LLM

步骤：

1. 注入会报错的 LLM。
2. 运行 Output Agent。

预期结果：

- Output Agent 不触发 LLM。

原因：

- Output 只负责结构化和校验，职责单一。

## 17. 阶段八：Progress Agent

### TC-F8-056 Progress Agent 能根据任务状态生成复盘上下文

步骤：

1. 输入含 done/todo/skipped 的计划。
2. 运行 Progress Agent。

预期结果：

- 输出完成率、未完成任务、延期任务、薄弱点。

原因：

- Progress Agent 是 F5 动态调整入口。

### TC-F8-057 Progress Agent 完成率使用真实状态

步骤：

1. 计划 27 个任务，只完成 1 个。
2. 运行 Progress Agent。

预期结果：

- 完成率为 1/27。
- 已完成任务为 1。
- 总任务为 27。

原因：

- 不能让 LLM 编造复盘数字。

### TC-F8-058 Progress Agent 识别延期任务

步骤：

1. 输入过去日期且未完成的任务。
2. 运行 Progress Agent。

预期结果：

- 延期任务列表包含该任务 ID。

原因：

- F5 重排依赖延期任务。

### TC-F8-059 Progress Agent 识别连续未完成主题

步骤：

1. 多个未完成任务都关联“递归”。
2. 运行 Progress Agent。

预期结果：

- 薄弱主题包含“递归”。

原因：

- PRD 要求总结薄弱点。

### TC-F8-060 Progress Agent 构造 ReplanRequest

步骤：

1. 输入复盘报告和当前计划。
2. 运行 Progress Agent。

预期结果：

- 输出 `ReplanRequest`。
- 包含剩余任务、剩余天数、每日可用时间。

原因：

- Planner 需要基于 ReplanRequest 重排。

### TC-F8-061 Progress Agent 不重排已完成任务

步骤：

1. 输入已完成任务和未完成任务。
2. 运行 Progress + Planner 重排。

预期结果：

- 已完成任务日期和状态不变。

原因：

- F5 保存调整不能污染已完成历史。

### TC-F8-062 Progress Agent 目标过期时报错

步骤：

1. 当前日期晚于 deadline。
2. 运行 Progress Agent。

预期结果：

- 返回明确错误，要求调整 deadline 或重新生成计划。

原因：

- 过期目标无法自动重排。

## 18. 阶段九：Workflow 图编排

### TC-F8-063 Workflow 入口为 PlannerWorkflow.run(goal)

步骤：

1. 实例化 workflow。
2. 调用 `run(goal)`。

预期结果：

- 返回最终计划或状态结果。

原因：

- features.md 要求统一入口。

### TC-F8-064 Workflow 按正确顺序执行 F2 节点

步骤：

1. 用 Spy 节点记录调用顺序。
2. 执行 F2 计划生成。

预期结果：

- 顺序为 Profile -> Knowledge -> Resource -> Planner -> Critic -> Output。

原因：

- PRD 架构图要求这些依赖关系。

### TC-F8-065 Workflow 状态在节点间传递

步骤：

1. Profile 输出画像。
2. Knowledge 读取画像。
3. Planner 读取知识点和资源。

预期结果：

- 每个节点能读取上游结果。

原因：

- 图工作流的核心价值是显式状态传递。

### TC-F8-066 Workflow Critic 通过后进入 Output

步骤：

1. Critic 返回通过。
2. 执行 workflow。

预期结果：

- Output 节点被调用。
- 返回 final_plan。

原因：

- 合法草案应进入最终结构化输出。

### TC-F8-067 Workflow Critic 失败后回到 Planner

步骤：

1. Critic 首次返回失败。
2. 执行 workflow。

预期结果：

- Planner 被再次调用。
- 修复后再次 Critic。

原因：

- F8 要求修复回路。

### TC-F8-068 Workflow 达到最大修复次数后停止

步骤：

1. Critic 总是失败。
2. 执行 workflow。

预期结果：

- 不无限循环。
- 返回错误状态。

原因：

- 防止 LangGraph 回路失控。

### TC-F8-069 Workflow 节点失败进入 errors

步骤：

1. Knowledge 节点抛出异常。
2. 执行 workflow。

预期结果：

- `errors` 包含节点名、错误信息。

原因：

- features.md 要求节点失败进入 errors。

### TC-F8-070 Workflow 可配置跳过 Resource 节点

步骤：

1. 设置无资料模式。
2. 执行 workflow。

预期结果：

- Resource 节点可返回空列表或被跳过。
- Planner 仍执行。

原因：

- F2 不能强依赖 F4。

### TC-F8-071 Workflow 结果可追踪

步骤：

1. 执行 workflow。
2. 读取执行记录。

预期结果：

- 能看到节点执行顺序、耗时或状态摘要。

原因：

- 多 Agent 流程需要可观测性。

### TC-F8-072 Workflow 不依赖 HelloAgents

步骤：

1. 检查 imports。

预期结果：

- 不导入 HelloAgents 框架。

原因：

- PRD 明确不依赖 HelloAgents。

## 19. 阶段十：F2 集成

### TC-F8-073 F2 可以通过 PlannerWorkflow 生成计划

步骤：

1. 构造 `GenerateStudyPlanUseCase`。
2. 注入 Fake PlannerWorkflow。
3. 执行生成。

预期结果：

- 返回 `StudyPlan`。
- UseCase 调用 workflow 而不是直接调用 LLM。

原因：

- F8 完成定义要求 F2 使用工作流生成计划。

### TC-F8-074 F2 保持 Fake LLM 测试可用

步骤：

1. 使用 Fake Agent 节点。
2. 执行 F2 测试。

预期结果：

- 不依赖真实 LLM。

原因：

- 自动化测试默认不依赖真实服务。

### TC-F8-075 F2 生成计划结构兼容原 F2

步骤：

1. 使用 workflow 生成计划。
2. 运行 F2 原有结构断言。

预期结果：

- phases、weekly_plans、tasks、time_budget、review_schedule 均存在。

原因：

- F8 不应破坏已有 F2 契约。

### TC-F8-076 F2 工作流输出可被 F3 展示

步骤：

1. 生成计划。
2. 调用 F3 看板 view builder。

预期结果：

- 看板非空。
- 任务列表可展示。

原因：

- 主流程必须连贯。

### TC-F8-077 F2 工作流输出可被 F7 保存

步骤：

1. 生成计划。
2. 调用 StorageService 保存。

预期结果：

- 保存成功。
- 任务 ID 保留。

原因：

- F7 持久化依赖稳定计划结构。

### TC-F8-078 F2 工作流失败时返回可读错误

步骤：

1. PlannerWorkflow 返回 errors。
2. 执行 F2 UseCase。

预期结果：

- 抛出 `StudyPlanGenerationError` 或等价错误。
- 错误不泄露底层 prompt 或密钥。

原因：

- 页面需要展示用户可理解错误。

### TC-F8-079 F2 Application 层不直接依赖 LangGraph

步骤：

1. 检查 `application/generate_study_plan.py` imports。

预期结果：

- 不直接导入 LangGraph。
- 只依赖 `PlannerWorkflow` 抽象或接口。

原因：

- features.md 要求 Application 层不依赖 LangGraph 细节。

## 20. 阶段十一：F5 集成

### TC-F8-080 F5 可以复用 PlannerWorkflow 重排计划

步骤：

1. 构造当前计划和 ReviewReport。
2. 调用 F5 重排入口。
3. 注入 Fake PlannerWorkflow。

预期结果：

- 输出调整后计划。

原因：

- F8 完成定义要求 F5 复用工作流。

### TC-F8-081 F5 重排只处理未完成任务

步骤：

1. 输入含 done 和 todo 的计划。
2. 运行 F5 workflow 重排。

预期结果：

- done 任务不被移动。
- todo/overdue 任务被重排。

原因：

- 用户完成历史不能被覆盖。

### TC-F8-082 F5 重排后仍经过 Critic

步骤：

1. Planner 重排后产生过载计划。
2. Critic 检查。

预期结果：

- Critic 阻止过载调整保存。

原因：

- 动态调整也必须可执行。

### TC-F8-083 F5 重排后可预览 diff

步骤：

1. 生成调整计划。
2. 计算原计划和调整计划差异。

预期结果：

- diff 包含移动任务、新任务或压缩任务。

原因：

- F5 要求保存前预览。

### TC-F8-084 F5 重排失败不覆盖原计划

步骤：

1. Workflow 重排失败。
2. 检查 session 或 repository。

预期结果：

- 原计划不变。
- pending_adjusted_plan 为空。

原因：

- 防止失败造成计划丢失。

### TC-F8-085 F5 重排报告使用真实统计数字

步骤：

1. 计划 27 个任务，只完成 1 个。
2. Progress + Workflow 生成复盘和重排。

预期结果：

- 完成率为 1/27。
- 不使用 LLM 编造的数字。

原因：

- F5 最近暴露了真实问题，需回归覆盖。

### TC-F8-086 F5 Application 层不直接依赖 LangGraph

步骤：

1. 检查 `application/review_replan.py` imports。

预期结果：

- 不直接导入 LangGraph。
- 通过 workflow 抽象调用。

原因：

- 保持应用层和编排实现解耦。

## 21. 阶段十二：错误处理与可观测性

### TC-F8-087 LLM 超时进入 errors

步骤：

1. Fake LLM 模拟超时。
2. 运行节点。

预期结果：

- `errors` 记录超时。
- 错误消息可读。

原因：

- 真实 LLM 调用可能超时。

### TC-F8-088 LLM 返回非 JSON 时进入 errors

步骤：

1. Fake LLM 返回普通文本。
2. 运行 Planner 或 Output。

预期结果：

- `errors` 包含解析失败。

原因：

- PRD 风险要求结构化输出校验。

### TC-F8-089 节点错误不泄露 API Key

步骤：

1. Fake LLM 抛出包含密钥的底层异常。
2. 工作流包装错误。

预期结果：

- 用户可见错误不包含 API Key。

原因：

- 安全边界。

### TC-F8-090 工作流记录节点执行顺序

步骤：

1. 执行 workflow。
2. 读取 trace 或 execution log。

预期结果：

- 包含节点顺序。

原因：

- 多 Agent 调试需要可观测。

### TC-F8-091 工作流记录节点耗时

步骤：

1. 执行 workflow。
2. 查看节点耗时。

预期结果：

- 能识别慢节点。

原因：

- 真实 LLM/RAG 成本和速度需要监控。

### TC-F8-092 Workflow 支持 debug 模式

步骤：

1. 开启 debug。
2. 执行 workflow。

预期结果：

- 返回中间状态或 trace。

原因：

- 开发和测试需要定位节点问题。

### TC-F8-093 Workflow 默认不暴露 prompt 全文

步骤：

1. 执行真实 LLM workflow。
2. 查看页面错误或普通输出。

预期结果：

- 不暴露完整 prompt。

原因：

- 避免泄露系统提示和用户隐私。

### TC-F8-094 Workflow 支持重试策略

步骤：

1. Fake LLM 第一次失败、第二次成功。
2. 执行节点。

预期结果：

- 节点最终成功。
- 记录一次重试。

原因：

- LLM 网络波动常见。

### TC-F8-095 Workflow 重试次数有上限

步骤：

1. Fake LLM 持续失败。
2. 执行节点。

预期结果：

- 达到上限后失败。
- 不无限重试。

原因：

- 防止成本失控。

## 22. 阶段十三：替换性与解耦

### TC-F8-096 可以替换 Profile Agent

步骤：

1. 注入 Fake Profile Agent。
2. 执行 workflow。

预期结果：

- workflow 正常运行。

原因：

- 替换单个 Agent 不影响页面层。

### TC-F8-097 可以替换 Planner Agent

步骤：

1. 注入 Fake Planner Agent。
2. 执行 workflow。

预期结果：

- 使用新 Planner 输出。

原因：

- Planner 可能从 Fake LLM 切换到 Real LLM 或 LangGraph 节点。

### TC-F8-098 可以替换 Critic Agent

步骤：

1. 注入严格 Critic。
2. 执行 workflow。

预期结果：

- workflow 使用新 Critic 结果。

原因：

- Critic 策略可能升级。

### TC-F8-099 页面层不导入 Agent 节点

步骤：

1. 检查 Streamlit pages imports。

预期结果：

- 页面不直接导入具体 Agent 节点。
- 页面只调用 Application UseCase。

原因：

- F9 要求页面只调用 Application UseCase。

### TC-F8-100 Workflow 不直接写数据库

步骤：

1. 检查 workflow imports。

预期结果：

- workflow 不直接导入 PostgreSQL repository。

原因：

- F7 持久化由 StorageService 负责。

### TC-F8-101 Workflow 不直接操作 Streamlit session_state

步骤：

1. 检查 workflow 代码。

预期结果：

- 不导入 streamlit。
- 不读写 session_state。

原因：

- Agent 工作流应与 UI 解耦。

## 23. 阶段十四：Real LLM 手动验收

### TC-F8-102 Real LLM 可以完成 F2 工作流

步骤：

1. 设置 `USE_REAL_LLM=true`。
2. 配置 DeepSeek API。
3. 输入学习目标。
4. 运行 workflow。

预期结果：

- 返回合法 `StudyPlan`。
- F3 可展示。

原因：

- F8 需要支持真实智能能力。

### TC-F8-103 Real LLM 结果经过 Critic

步骤：

1. 使用真实 LLM 生成计划。
2. 查看 critic review。

预期结果：

- 如果计划过载，进入修复。
- 如果合理，进入 Output。

原因：

- 真实 LLM 输出也不能绕过可行性检查。

### TC-F8-104 Real LLM 输出非 JSON 时可恢复或报错

步骤：

1. 人为让模型返回非 JSON。
2. 执行 workflow。

预期结果：

- 有重试或明确错误。

原因：

- 真实模型格式不稳定。

### TC-F8-105 Real LLM 可以完成 F5 重排

步骤：

1. 创建带延期任务的计划。
2. 标记部分完成。
3. 调用 F5 workflow。

预期结果：

- 输出调整计划。
- 已完成任务不变。
- 调整计划不过载。

原因：

- F5 需要复用工作流。

### TC-F8-106 Real LLM 成本和耗时可观测

步骤：

1. 执行真实 workflow。
2. 查看 trace 或日志。

预期结果：

- 能看到节点耗时。
- 可选记录 token 或调用次数。

原因：

- 多 Agent 真实调用成本更高。

### TC-F8-107 Real LLM 失败不影响已有计划

步骤：

1. 已有学习计划。
2. 真实 workflow 调整失败。

预期结果：

- 原计划不被覆盖。
- 页面显示错误。

原因：

- 用户数据安全优先。

## 24. 优先级建议

### P0 必须自动化

- TC-F8-001 PlannerState 包含必需字段
- TC-F8-009 Profile Agent 能生成学习画像
- TC-F8-016 Knowledge Agent 能生成知识点列表
- TC-F8-024 Resource Agent 无资料时不阻断
- TC-F8-031 Planner Agent 能生成草案计划
- TC-F8-039 Critic Agent 能发现每日过载
- TC-F8-044 Critic 失败后返回 Planner 修复
- TC-F8-048 Output Agent 输出 StudyPlan
- TC-F8-051 Output Agent 生成稳定任务 ID
- TC-F8-063 Workflow 入口为 PlannerWorkflow.run(goal)
- TC-F8-064 Workflow 按正确顺序执行 F2 节点
- TC-F8-067 Workflow Critic 失败后回到 Planner
- TC-F8-069 Workflow 节点失败进入 errors
- TC-F8-073 F2 可以通过 PlannerWorkflow 生成计划
- TC-F8-080 F5 可以复用 PlannerWorkflow 重排计划
- TC-F8-085 F5 重排报告使用真实统计数字
- TC-F8-099 页面层不导入 Agent 节点

### P1 建议自动化

- Knowledge 先修关系、难度、重要性。
- Resource 引用来源。
- Output 日期规范化和状态规范化。
- 修复次数上限。
- 错误脱敏。
- Debug trace。

### P2 可手动或后续增强

- Real LLM 主观质量验收。
- token 成本统计。
- LangSmith trace 深度分析。
- 复杂资源推荐质量。

## 25. 回归测试建议

F8 实现后至少回归：

```text
tests/test_f2_generate_study_plan.py
tests/test_f2b_real_llm_integration.py
tests/test_f3_plan_dashboard_editing.py
tests/test_f5_review_replan.py
tests/test_f6_plan_export.py
tests/test_f7_persistence.py
tests/test_f8_agent_workflow.py
```

## 26. 完成定义

F8 测试完成需要满足：

- 工作流有统一入口 `PlannerWorkflow.run(goal)` 或等价入口。
- PlannerState 字段完整且可追踪。
- Profile、Knowledge、Resource、Planner、Critic、Output、Progress 节点职责清晰。
- Fake 环境下可以稳定生成合法 `StudyPlan`。
- Critic 可以发现过载并触发 Planner 修复。
- 修复回路有次数上限。
- Output Agent 对最终计划做结构化校验。
- F2 可以通过工作流生成计划。
- F5 可以通过工作流重排计划。
- 节点失败进入 `errors`，错误可读且不泄露密钥。
- Application 层不直接依赖 LangGraph 细节。
- 页面层不直接依赖 Agent 节点。
- 替换单个 Agent 不影响页面层和 Application 用例。

## 27. 主要风险与覆盖

| 风险 | 影响 | 覆盖用例 |
|---|---|---|
| 单节点职责混乱 | 后续难替换和调试 | TC-F8-009 到 TC-F8-062 |
| LLM 编造结构或数字 | 计划不可执行、复盘错误 | TC-F8-037、TC-F8-052、TC-F8-085 |
| Critic 回路无限循环 | 成本失控、页面卡死 | TC-F8-045、TC-F8-068 |
| Resource 失败阻塞 F2 | 无资料时不能生成计划 | TC-F8-025、TC-F8-027 |
| Output 未校验 | F3/F5/F6 后续崩溃 | TC-F8-049 到 TC-F8-055 |
| Application 依赖 LangGraph | 难以替换编排实现 | TC-F8-079、TC-F8-086 |
| 页面直接调用 Agent | UI 与业务耦合 | TC-F8-099 |
| 节点错误不可见 | 难定位真实问题 | TC-F8-087 到 TC-F8-095 |
| 真实 LLM 不稳定 | 生产不可用 | TC-F8-102 到 TC-F8-107 |

## 28. 建议实现顺序

1. 定义 `PlannerState` 和节点输入输出 dataclass。
2. 实现 Fake 节点和节点协议。
3. 实现 Profile、Knowledge、Resource、Planner、Critic、Output 节点单测。
4. 实现 `PlannerWorkflow.run(goal)`。
5. 实现 Critic 修复回路和最大修复次数。
6. 将 F2 UseCase 改为可注入 workflow。
7. 将 F5 重排改为可复用 workflow。
8. 增加错误记录、trace 和 debug 输出。
9. 接入真实 LangGraph。
10. 接入 Real LLM 手动验收。
