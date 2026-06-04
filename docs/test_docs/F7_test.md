# F7 持久化与数据管理测试用例方案

## 1. 测试目标

F7 的目标是：使用 PostgreSQL 或等价持久化实现保存学习目标、学习计划、任务进度、复盘报告和资料元数据，避免 Streamlit 应用刷新、重启或页面跳转后丢失关键学习状态。

本测试方案覆盖：

- Repository 抽象接口
- 学习目标保存与读取
- 学习计划保存与读取
- 阶段、周计划、每日任务结构持久化
- 任务状态、日期、时长、备注持久化
- 复盘报告保存与读取
- 资料元数据保存与读取
- 导出记录可选保存
- PostgreSQL JSONB MVP 存储策略
- Streamlit 刷新后恢复最近计划
- F3、F5、F6 与持久化数据集成
- 数据库不可用时的错误提示
- 保存失败、读取失败、事务回滚
- 中文编码、时间字段、空字段、安全边界

## 2. 需求依据

### 2.1 PRD 依据

PRD 中 F7 相关要求包括：

- 技术选型使用 PostgreSQL 保存计划、任务、进度、用户配置和复盘记录。
- Streamlit 页面层通过 StorageService 与 PostgreSQL 交互。
- 数据层包含 PostgreSQL：计划、任务、进度、配置。
- 学习计划、任务完成状态、复盘记录需要保存。
- 页面刷新后不应丢失学习计划和进度。
- 保存失败或状态复杂时需要明确边界和错误提示。

### 2.2 features.md 依据

features.md 对 F7 的要求包括：

- 使用 PostgreSQL 保存结构化数据，避免应用刷新后丢失计划和进度。
- 数据范围包括学习目标、学习计划、阶段、周计划、每日任务、任务进度、复盘报告、资料元数据、导出记录可选。
- 需要定义 `StudyGoalRepository`、`StudyPlanRepository`、`TaskProgressRepository`、`ReviewReportRepository`、`MaterialRepository`。
- 业务代码只依赖 Repository 接口。
- PostgreSQL 实现放在 `infrastructure/db`。
- MVP 可以先把复杂嵌套计划以 JSONB 保存。
- 保存失败时页面给出错误提示。
- 读取失败时不影响应用启动。
- 测试要求包括 Repository 保存和读取学习目标、学习计划、更新任务进度、保存复盘报告、数据库不可用时错误清晰。
- 完成定义包括刷新 Streamlit 后能恢复最近的学习计划、任务完成状态能持久保存、F3/F5/F6 可以读取持久化数据。

## 3. 功能边界

### 3.1 输入

F7 至少接收：

- `StudyGoal`
- `StudyPlan`
- `TaskProgress` 或任务状态更新请求
- `ReviewReport`
- `LearningMaterial`
- 可选导出记录
- 数据库连接配置
- 当前用户或当前 session 标识，MVP 可使用默认单用户

### 3.2 输出

F7 至少输出：

- 已保存实体 ID
- 最近学习目标
- 最近学习计划
- 指定计划的任务进度
- 最近复盘报告
- 资料元数据列表
- 保存失败错误
- 读取失败错误或空状态

### 3.3 不做范围

MVP 阶段不要求：

- 多用户账号体系
- 权限隔离和团队协作
- 复杂 SQL 统计报表
- 完整规范化阶段/周/任务表拆分
- 数据版本冲突多人合并
- 自动备份和恢复策略
- 跨设备同步
- 数据迁移工具链全量覆盖

## 4. 建议领域模型与接口

测试可以驱动实现以下抽象：

```python
StudyGoalRepository
StudyPlanRepository
TaskProgressRepository
ReviewReportRepository
MaterialRepository
ExportRecordRepository  # 可选
StorageService
```

字段建议：

```text
StudyGoalRepository
  - save(goal) -> str
  - get_latest() -> StudyGoal | None
  - get_by_id(goal_id) -> StudyGoal | None

StudyPlanRepository
  - save(plan) -> str
  - get_latest() -> StudyPlan | None
  - get_by_id(plan_id) -> StudyPlan | None
  - update_task(plan_id, task_id, status, date, duration_minutes, notes) -> StudyPlan

TaskProgressRepository
  - save_progress(progress) -> str
  - get_by_task_id(task_id) -> TaskProgress | None
  - list_by_plan_id(plan_id) -> list[TaskProgress]

ReviewReportRepository
  - save(report, plan_id=None) -> str
  - get_latest(plan_id=None) -> ReviewReport | None
  - list_by_plan_id(plan_id) -> list[ReviewReport]

MaterialRepository
  - save(material) -> str
  - get_by_id(material_id) -> LearningMaterial | None
  - list_all() -> list[LearningMaterial]
```

MVP 数据表建议：

```text
study_goals
  - id
  - payload JSONB
  - created_at
  - updated_at

study_plans
  - id
  - goal_id
  - payload JSONB
  - created_at
  - updated_at

task_progress
  - id
  - plan_id
  - task_id
  - status
  - planned_date
  - actual_completed_at
  - duration_minutes
  - related_topics JSONB
  - notes
  - updated_at

review_reports
  - id
  - plan_id
  - payload JSONB
  - created_at

materials
  - id
  - filename
  - file_type
  - source_path
  - uploaded_at
  - status
  - chunk_count
  - error_message
  - raw_text 可选
```

## 5. 测试数据基线

默认学习目标：

```text
subject: Python 编程
target: 掌握 Python 基础语法并完成一个小项目
deadline: 2026-06-30
current_level: 零基础
daily_available_minutes: 120
weekly_available_days: 5
preferred_methods: 视频教程、项目实践
weak_points: 递归、面向对象
extra_requirements: 多安排练习任务
```

默认学习计划：

```text
overall_route: 先学基础语法，再完成练习，最后做小项目
methods: 视频教程、阅读文档、项目实践
risks: 每日时间不足可能导致延期
suggestions: 每天完成一个可检查产出

阶段 1: 基础入门阶段
  start_date: 2026-06-04
  end_date: 2026-06-17
  milestone: 能完成基础语法练习

第 1 周:
  start_date: 2026-06-04
  end_date: 2026-06-10
  objective: 完成基础语法学习

任务:
  task-1: 学习变量与数据类型, todo, 2026-06-04, 60 分钟
  task-2: 完成基础语法复习, done, 2026-06-04, 30 分钟
  task-3: 函数练习, doing, 2026-06-05, 60 分钟
```

默认复盘报告：

```text
period_start: 2026-06-01
period_end: 2026-06-07
completion_rate: 0.6
completed_task_count: 3
total_task_count: 5
overdue_tasks: task-1
weak_points: 递归、练习时间不足
summary: 本周完成率一般，需要优先处理延期任务
suggestions: 降低任务粒度、增加递归专项练习
```

默认资料元数据：

```text
id: material-1
filename: python-basics.pdf
file_type: pdf
source_path: uploads/python-basics.pdf
uploaded_at: 2026-06-04T09:30:00
status: ready
chunk_count: 12
```

## 6. 阶段一：Repository 抽象与依赖边界

### TC-F7-001 业务层只依赖 Repository 抽象

前置条件：
- 应用层用例需要保存或读取学习计划。

操作：
- 检查应用层模块导入依赖。

期望结果：
- 应用层不直接导入 PostgreSQL 驱动。
- 应用层不直接写 SQL。
- 应用层通过 repository 接口完成保存和读取。

编写原因：
- features.md 明确要求业务代码只依赖 Repository 接口。

### TC-F7-002 PostgreSQL 实现位于 infrastructure/db

前置条件：
- 项目包含 PostgreSQL repository 实现。

操作：
- 检查模块路径。

期望结果：
- PostgreSQL 相关实现位于 `study_planner/infrastructure/db` 或等价基础设施目录。
- Streamlit 页面不直接调用数据库实现。

编写原因：
- 保持页面、业务和基础设施解耦，便于替换数据库。

### TC-F7-003 Repository 接口可被 FakeRepository 替代

前置条件：
- 构造 FakeRepository。

操作：
- 将 FakeRepository 注入应用层用例。

期望结果：
- 用例可以正常保存和读取数据。
- 不需要真实 PostgreSQL。

编写原因：
- 自动化测试和离线开发需要可替换依赖。

### TC-F7-004 Repository 错误统一转换为业务可理解错误

前置条件：
- Repository 底层抛出数据库异常。

操作：
- 调用应用层保存或读取方法。

期望结果：
- 应用层返回清晰错误，例如 `StorageError`。
- 页面可展示用户可理解提示。
- 不暴露原始连接字符串或敏感配置。

编写原因：
- 数据库错误不能直接泄露到底层页面。

## 7. 阶段二：学习目标持久化

### TC-F7-005 保存学习目标成功

前置条件：
- 构造有效 `StudyGoal`。

操作：
- 调用 `StudyGoalRepository.save(goal)`。

期望结果：
- 返回非空 goal_id。
- 数据库存在对应记录。
- `created_at` 和 `updated_at` 被写入。

编写原因：
- F1 输入的学习目标是后续计划生成和恢复的基础。

### TC-F7-006 读取最近学习目标成功

前置条件：
- 已保存至少一个 `StudyGoal`。

操作：
- 调用 `StudyGoalRepository.get_latest()`。

期望结果：
- 返回最近保存的学习目标。
- 字段与保存前一致。

编写原因：
- 页面刷新或重启后需要恢复最近配置。

### TC-F7-007 按 ID 读取学习目标成功

前置条件：
- 已保存一个 `StudyGoal` 并获得 goal_id。

操作：
- 调用 `StudyGoalRepository.get_by_id(goal_id)`。

期望结果：
- 返回对应目标。
- 不返回其他目标。

编写原因：
- 学习计划需要关联原始目标。

### TC-F7-008 保存中文学习目标不乱码

前置条件：
- `StudyGoal` 包含中文主题、中文目标、中文薄弱点。

操作：
- 保存后读取。

期望结果：
- 中文内容完整保留。
- 不出现乱码或替换字符。

编写原因：
- 产品面向中文学习场景，持久化必须使用正确编码。

### TC-F7-009 可选字段为空时仍能保存学习目标

前置条件：
- `preferred_methods=[]`
- `weak_points=[]`
- `extra_requirements=""`

操作：
- 保存并读取学习目标。

期望结果：
- 保存成功。
- 空列表仍为空列表。
- 空字符串仍为空字符串或按约定默认值返回。

编写原因：
- F1 允许部分输入为空，F7 不能阻断。

## 8. 阶段三：学习计划持久化

### TC-F7-010 保存完整学习计划成功

前置条件：
- 构造包含阶段、周计划、每日任务的 `StudyPlan`。

操作：
- 调用 `StudyPlanRepository.save(plan)`。

期望结果：
- 返回非空 plan_id。
- 数据库存在计划记录。
- 计划 payload 包含完整结构。

编写原因：
- F2 生成的完整计划必须可保存。

### TC-F7-011 读取最近学习计划成功

前置条件：
- 已保存一个 `StudyPlan`。

操作：
- 调用 `StudyPlanRepository.get_latest()`。

期望结果：
- 返回最近计划。
- 学习目标、总体路线、阶段、周计划、任务完整。

编写原因：
- 完成定义要求刷新后恢复最近学习计划。

### TC-F7-012 按 ID 读取学习计划成功

前置条件：
- 保存多个 `StudyPlan`。

操作：
- 调用 `StudyPlanRepository.get_by_id(plan_id)`。

期望结果：
- 返回指定计划。
- 不串读其他计划。

编写原因：
- 后续多计划管理和复盘关联需要稳定 ID。

### TC-F7-013 学习计划关联原始学习目标

前置条件：
- 保存 `StudyGoal`。
- 基于该目标保存 `StudyPlan`。

操作：
- 读取计划。

期望结果：
- 计划能追溯到 goal_id 或包含原始 goal。
- 不被 LLM 输出覆盖用户目标。

编写原因：
- F2 要求计划绑定调用方传入的原始目标。

### TC-F7-014 JSONB 保存复杂嵌套计划

前置条件：
- 学习计划包含多阶段、多周、多任务。

操作：
- 保存计划并检查数据库 payload。

期望结果：
- JSONB payload 能保存完整嵌套结构。
- 读取后能还原为 `StudyPlan`。

编写原因：
- features.md 允许 MVP 先使用 JSONB 保存复杂计划。

### TC-F7-015 保存计划时保留任务 ID

前置条件：
- 计划中任务包含 `id=task-1`。

操作：
- 保存并读取计划。

期望结果：
- 任务 ID 不丢失。
- 后续更新任务状态可定位该任务。

编写原因：
- F3、F5、F6 都依赖稳定任务 ID。

### TC-F7-016 保存计划时保留任务备注

前置条件：
- 计划中任务包含 notes。

操作：
- 保存并读取计划。

期望结果：
- notes 字段完整保留。
- 空 notes 不显示为 `None`。

编写原因：
- F3 支持任务备注编辑，必须持久化。

### TC-F7-017 保存计划时保留复习安排

前置条件：
- `StudyPlan.review_schedule` 非空。

操作：
- 保存并读取计划。

期望结果：
- 每日复习分钟数、每周复习日、复习策略完整保留。

编写原因：
- 复习安排是 F2/F6 的关键导出内容。

### TC-F7-018 保存计划时保留时间预算

前置条件：
- `StudyPlan.time_budget` 非空。

操作：
- 保存并读取计划。

期望结果：
- 总天数、总周数、总可用分钟数、计划分钟数等完整保留。

编写原因：
- 时间预算用于看板展示和导出。

## 9. 阶段四：任务进度持久化

### TC-F7-019 更新任务状态为 done 成功

前置条件：
- 已保存计划。
- 任务 `task-1` 状态为 `todo`。

操作：
- 调用更新任务状态接口，将 `task-1` 改为 `done`。

期望结果：
- 保存成功。
- 再次读取计划时 `task-1.status == "done"`。

编写原因：
- 完成定义要求任务完成状态能持久保存。

### TC-F7-020 更新任务状态为 doing 成功

前置条件：
- 已保存计划。

操作：
- 将某任务状态改为 `doing`。

期望结果：
- 状态保存为 `doing`。
- F3 读取后显示进行中。

编写原因：
- 任务状态至少包含 todo、doing、done、skipped。

### TC-F7-021 更新任务状态为 skipped 成功

前置条件：
- 已保存计划。

操作：
- 将某任务状态改为 `skipped`。

期望结果：
- 状态保存为 `skipped`。
- F5 统计时不误算为已完成。

编写原因：
- skipped 代表未完成风险，必须正确持久化。

### TC-F7-022 更新任务日期成功

前置条件：
- 已保存计划。

操作：
- 将任务日期从 `2026-06-04` 改为 `2026-06-06`。

期望结果：
- 读取计划时任务日期为新日期。
- F6 导出时显示新日期。

编写原因：
- F3 支持编辑任务日期。

### TC-F7-023 更新任务时长成功

前置条件：
- 已保存计划。

操作：
- 将任务时长从 60 分钟改为 45 分钟。

期望结果：
- 读取计划时任务时长为 45。
- 时间预算或日统计可按当前计划重新计算。

编写原因：
- F3 支持编辑任务时长。

### TC-F7-024 更新任务备注成功

前置条件：
- 已保存计划。

操作：
- 更新任务 notes 为 `复习时重点看类型转换`。

期望结果：
- 读取计划时备注完整保留。
- F6 导出时包含备注。

编写原因：
- 备注是用户执行计划的重要补充信息。

### TC-F7-025 更新不存在任务返回明确错误

前置条件：
- 已保存计划。

操作：
- 更新 `task-not-exists`。

期望结果：
- 返回明确错误：任务不存在。
- 原计划不被修改。

编写原因：
- 防止错误 task_id 污染计划数据。

### TC-F7-026 非法任务状态不能保存

前置条件：
- 已保存计划。

操作：
- 将任务状态更新为 `unknown`。

期望结果：
- 更新失败。
- 返回明确错误。
- 原状态保持不变。

编写原因：
- F3/F5 对状态枚举有约束。

## 10. 阶段五：复盘报告持久化

### TC-F7-027 保存复盘报告成功

前置条件：
- 已保存学习计划。
- 构造有效 `ReviewReport`。

操作：
- 调用 `ReviewReportRepository.save(report, plan_id)`。

期望结果：
- 返回 report_id。
- 数据库存在对应记录。

编写原因：
- F5 生成的复盘报告需要保存。

### TC-F7-028 读取最近复盘报告成功

前置条件：
- 已保存一个复盘报告。

操作：
- 调用 `ReviewReportRepository.get_latest(plan_id)`。

期望结果：
- 返回最近报告。
- 完成率、延期任务、薄弱点、建议完整。

编写原因：
- F6 导出需要读取最近复盘报告。

### TC-F7-029 复盘报告关联学习计划

前置条件：
- 保存两个不同计划。
- 分别保存复盘报告。

操作：
- 按 plan_id 读取复盘报告。

期望结果：
- 每个计划只读取自己的报告。
- 不串读其他计划报告。

编写原因：
- 后续多计划或历史记录需要正确关联。

### TC-F7-030 保存复盘报告中文内容不乱码

前置条件：
- 复盘报告 summary、weak_points、suggestions 均包含中文。

操作：
- 保存并读取报告。

期望结果：
- 中文完整保留。
- 不出现乱码或替换字符。

编写原因：
- F5 复盘内容面向中文用户。

### TC-F7-031 保存复盘报告空列表字段成功

前置条件：
- `overdue_tasks=[]`
- `weak_points=[]`
- `suggestions=[]`

操作：
- 保存并读取复盘报告。

期望结果：
- 保存成功。
- 空列表仍为空列表。
- 不显示为 `None`。

编写原因：
- 完成率较好时可能没有延期任务或薄弱点。

## 11. 阶段六：资料元数据持久化

### TC-F7-032 保存资料元数据成功

前置条件：
- 构造有效 `LearningMaterial`。

操作：
- 调用 `MaterialRepository.save(material)`。

期望结果：
- 返回 material_id。
- 数据库存在资料元数据记录。

编写原因：
- F4 资料上传需要保存资料状态和索引信息。

### TC-F7-033 按 ID 读取资料元数据成功

前置条件：
- 已保存资料元数据。

操作：
- 调用 `MaterialRepository.get_by_id(material_id)`。

期望结果：
- 返回对应资料。
- filename、file_type、status、chunk_count 正确。

编写原因：
- 资料问答需要定位资料来源。

### TC-F7-034 列出全部资料元数据成功

前置条件：
- 保存多个资料元数据。

操作：
- 调用 `MaterialRepository.list_all()`。

期望结果：
- 返回全部资料。
- 按上传时间或 ID 稳定排序。

编写原因：
- F4 页面需要展示资料列表。

### TC-F7-035 更新资料处理状态成功

前置条件：
- 资料初始状态为 `processing`。

操作：
- 更新为 `ready`，chunk_count 为 12。

期望结果：
- 状态和 chunk_count 被持久化。
- 页面刷新后仍显示 ready。

编写原因：
- 资料解析是异步或多步骤过程，状态必须保存。

### TC-F7-036 保存资料处理错误信息成功

前置条件：
- 资料解析失败。

操作：
- 更新 status 为 `failed`，error_message 为错误说明。

期望结果：
- 错误信息被保存。
- 页面可显示失败原因。

编写原因：
- F4 要处理上传或解析失败场景。

## 12. 阶段七：导出记录持久化，可选

### TC-F7-037 保存导出记录成功

前置条件：
- 用户成功导出 Markdown 或 HTML。

操作：
- 保存导出记录。

期望结果：
- 记录包含 plan_id、format、filename、exported_at。
- 不保存完整文件内容，除非产品明确要求。

编写原因：
- features.md 将导出记录列为可选数据范围。

### TC-F7-038 导出记录缺失不影响 F6 导出

前置条件：
- 未实现或未启用导出记录 repository。

操作：
- 执行 F6 导出。

期望结果：
- 导出仍成功。
- 不因导出记录保存失败阻塞下载。

编写原因：
- 导出记录是可选能力，不应影响 MVP 主流程。

## 13. 阶段八：Streamlit 刷新与恢复

### TC-F7-039 刷新后恢复最近学习计划

前置条件：
- 已保存学习计划到数据库。
- 清空 `st.session_state` 或模拟页面刷新。

操作：
- 打开学习计划看板。

期望结果：
- 页面从 repository 读取最近计划。
- 看板显示计划内容。
- 不要求用户重新生成计划。

编写原因：
- F7 完成定义要求刷新后恢复最近学习计划。

### TC-F7-040 刷新后恢复任务完成状态

前置条件：
- 任务 `task-1` 已更新为 `done` 并保存。
- 清空 session_state。

操作：
- 打开 F3 看板。

期望结果：
- `task-1` 显示为已完成。
- 完成率按已完成状态计算。

编写原因：
- 完成定义要求任务完成状态能持久保存。

### TC-F7-041 刷新后恢复最近复盘报告

前置条件：
- 已保存复盘报告。
- 清空 session_state。

操作：
- 打开 F5 或 F6 页面。

期望结果：
- 页面能读取最近复盘报告。
- F6 导出时包含该报告。

编写原因：
- F5/F6 需要共享复盘状态。

### TC-F7-042 数据库无计划时页面显示空状态

前置条件：
- session_state 无计划。
- repository 中也无计划。

操作：
- 打开 F3/F5/F6 页面。

期望结果：
- 页面显示需要先生成学习计划。
- 不报错。

编写原因：
- 新用户或清空数据库后必须有友好空状态。

## 14. 阶段九：F3 集成

### TC-F7-043 F3 打开时读取持久化计划

前置条件：
- repository 中存在最近学习计划。
- session_state 为空。

操作：
- 打开 F3 看板页面。

期望结果：
- 页面显示 repository 中的计划。
- session_state 可被同步为该计划。

编写原因：
- F3 是计划执行主页面，必须接入持久化。

### TC-F7-044 F3 保存任务修改后写入数据库

前置条件：
- F3 已加载计划。

操作：
- 修改任务状态、日期、时长、备注并保存。

期望结果：
- session_state 更新。
- repository 中对应计划也更新。
- 刷新后仍保留修改。

编写原因：
- 用户在 F3 的编辑不能只存在于内存。

### TC-F7-045 F3 保存失败时页面提示错误

前置条件：
- repository 保存任务修改时抛出异常。

操作：
- 在 F3 保存任务修改。

期望结果：
- 页面显示保存失败提示。
- 当前计划不被半更新污染。

编写原因：
- features.md 要求保存失败时页面给出错误提示。

## 15. 阶段十：F5 集成

### TC-F7-046 F5 读取持久化计划生成复盘

前置条件：
- repository 中存在最近计划。
- session_state 为空。

操作：
- 打开 F5 页面并生成复盘。

期望结果：
- F5 能读取计划。
- 复盘统计基于持久化任务状态。

编写原因：
- F5 依赖 F3 更新后的进度。

### TC-F7-047 F5 保存复盘报告到数据库

前置条件：
- F5 成功生成复盘报告。

操作：
- 保存复盘报告。

期望结果：
- repository 中存在报告。
- 刷新后仍能读取。

编写原因：
- 复盘报告是 F7 数据范围。

### TC-F7-048 F5 保存调整后计划到数据库

前置条件：
- F5 生成调整预览。
- 用户确认保存。

操作：
- 保存调整后计划。

期望结果：
- repository 中最新计划为调整后计划。
- 原计划不被部分损坏。
- F3 刷新后显示调整后计划。

编写原因：
- F5 调整结果需要回流到计划看板和持久化层。

### TC-F7-049 F5 保存调整失败时回滚

前置条件：
- F5 保存调整时 repository 抛出异常。

操作：
- 点击保存调整。

期望结果：
- 页面提示保存失败。
- session_state 中原计划保持不变。
- 数据库中原计划保持不变。

编写原因：
- 调整计划不能在失败时造成计划丢失。

## 16. 阶段十一：F6 集成

### TC-F7-050 F6 从持久化计划导出

前置条件：
- repository 中存在最近计划。
- session_state 为空。

操作：
- 打开 F6 导出页面并下载 Markdown/HTML。

期望结果：
- F6 使用 repository 中的计划导出。
- 导出内容完整。

编写原因：
- F7 完成定义要求 F6 可以读取持久化数据。

### TC-F7-051 F6 导出持久化任务状态

前置条件：
- 数据库中 `task-1.status == done`。

操作：
- F6 导出 Markdown/HTML。

期望结果：
- 导出文件中 `task-1` 为已完成。

编写原因：
- 导出必须反映当前持久化状态。

### TC-F7-052 F6 导出持久化复盘报告

前置条件：
- repository 中存在最近复盘报告。

操作：
- F6 导出 Markdown/HTML。

期望结果：
- 导出文件包含复盘报告。
- 报告内容与数据库一致。

编写原因：
- F6 导出学习计划和复盘报告。

## 17. 阶段十二：数据库不可用与错误处理

### TC-F7-053 应用启动时数据库不可用不崩溃

前置条件：
- PostgreSQL 服务不可用或连接配置错误。

操作：
- 启动 Streamlit 应用。

期望结果：
- 应用仍能启动。
- 页面给出数据库不可用提示。
- 用户仍可在 session_state 中临时使用 MVP 功能，或进入空状态。

编写原因：
- features.md 要求读取失败时不影响应用启动。

### TC-F7-054 读取计划失败时错误清晰

前置条件：
- repository 读取计划时抛出异常。

操作：
- 打开 F3/F5/F6 页面。

期望结果：
- 页面显示读取失败提示。
- 不出现 Python traceback。
- 不阻塞整个应用启动。

编写原因：
- 数据库不可用时错误必须清晰。

### TC-F7-055 保存计划失败时错误清晰

前置条件：
- repository 保存计划时抛出异常。

操作：
- F1 生成计划后尝试保存。

期望结果：
- 页面显示保存失败提示。
- session_state 中可保留当前计划作为临时状态，或按产品约定处理。
- 不静默失败。

编写原因：
- 保存失败时页面需要明确反馈。

### TC-F7-056 保存任务进度失败时错误清晰

前置条件：
- repository 更新任务进度时抛出异常。

操作：
- F3 保存任务修改。

期望结果：
- 页面显示保存失败。
- 用户知道修改没有持久化。

编写原因：
- 避免用户误以为进度已保存。

### TC-F7-057 保存复盘报告失败时错误清晰

前置条件：
- repository 保存复盘报告时抛出异常。

操作：
- F5 点击生成复盘或保存复盘。

期望结果：
- 页面提示保存失败。
- 复盘报告可临时保留在 session_state，或按产品约定处理。

编写原因：
- F5 输出不能因保存失败无提示丢失。

## 18. 阶段十三：事务与一致性

### TC-F7-058 保存学习目标和计划使用一致事务

前置条件：
- F1/F2 生成目标和计划。

操作：
- 保存目标和计划，中途模拟计划保存失败。

期望结果：
- 不留下孤立或不可用数据，或孤立数据有明确状态。
- 页面提示保存失败。

编写原因：
- 目标和计划是强关联数据。

### TC-F7-059 保存调整计划和复盘报告保持一致

前置条件：
- F5 同时保存调整后计划和复盘报告。

操作：
- 模拟复盘保存成功但计划保存失败。

期望结果：
- 事务回滚，或有明确补偿策略。
- 不出现报告指向不存在的新计划。

编写原因：
- F5 保存涉及多实体一致性。

### TC-F7-060 更新任务状态不影响其他任务

前置条件：
- 计划中有多个任务。

操作：
- 只更新 `task-1` 状态。

期望结果：
- `task-2`、`task-3` 保持原状态。
- 阶段、周计划结构不变。

编写原因：
- 局部更新必须避免误改其他任务。

### TC-F7-061 并发保存时使用最后写入或明确冲突策略

前置条件：
- 两个页面实例加载同一计划。

操作：
- 页面 A 更新任务备注。
- 页面 B 更新任务状态。

期望结果：
- 系统按明确策略处理：最后写入、字段级合并或冲突提示。
- 不产生损坏 JSON。

编写原因：
- Streamlit 多窗口或刷新可能导致并发写入。

## 19. 阶段十四：数据校验与安全

### TC-F7-062 保存前校验任务状态枚举

前置条件：
- 任务状态为非法值。

操作：
- 保存计划或任务进度。

期望结果：
- 保存失败或被规范化。
- 错误提示清晰。

编写原因：
- 避免非法状态污染 F3/F5/F6。

### TC-F7-063 保存前校验任务日期不超过 deadline

前置条件：
- 任务日期晚于目标 deadline。

操作：
- 保存计划。

期望结果：
- 保存失败或应用层先阻止。
- 不保存不可执行计划。

编写原因：
- F2/F3 均要求任务日期约束。

### TC-F7-064 保存前校验每日任务时长不超限

前置条件：
- 同一天任务总时长超过每日可学习时间。

操作：
- 保存计划或更新任务时长。

期望结果：
- 保存失败或应用层提示过载。
- 不持久化过载计划。

编写原因：
- 防止持久化绕过业务约束。

### TC-F7-065 SQL 注入字符串作为用户输入不会破坏数据库

前置条件：
- 学习主题包含 `'); DROP TABLE study_plans; --`。

操作：
- 保存学习目标和计划。

期望结果：
- 保存成功或按普通文本处理。
- 数据表不被破坏。
- 读取后原文被安全保留。

编写原因：
- 用户输入必须通过参数化查询或 JSON 序列化安全保存。

### TC-F7-066 导出或页面读取不泄露数据库连接信息

前置条件：
- 数据库连接失败。

操作：
- 打开页面或导出。

期望结果：
- 页面不显示数据库密码、连接 URI、用户名。
- 错误提示只包含必要信息。

编写原因：
- 配置和凭据不能暴露给用户。

## 20. 阶段十五：时间与排序

### TC-F7-067 created_at 和 updated_at 自动维护

前置条件：
- 保存目标或计划。

操作：
- 首次保存后读取时间字段。
- 更新后再次读取。

期望结果：
- `created_at` 不变。
- `updated_at` 更新。

编写原因：
- 最近计划和历史记录依赖时间字段。

### TC-F7-068 get_latest 返回更新时间最新记录

前置条件：
- 保存多个计划。

操作：
- 更新较旧计划。
- 调用 get_latest。

期望结果：
- 返回 updated_at 最新的计划，或按产品约定返回 created_at 最新计划。
- 排序规则明确且测试固定。

编写原因：
- “最近计划”必须定义清楚。

### TC-F7-069 日期字段保存为日期而非不稳定字符串

前置条件：
- 计划包含 date 字段。

操作：
- 保存并读取计划。

期望结果：
- Python 对象中仍为 `date`。
- ISO 字符串能正确解析。

编写原因：
- F3/F5 依赖日期比较。

### TC-F7-070 datetime 字段保存和读取稳定

前置条件：
- 资料上传时间或复盘完成时间包含 datetime。

操作：
- 保存并读取。

期望结果：
- 时间不丢失。
- 时区策略明确，MVP 可统一使用 naive local 或 UTC。

编写原因：
- 上传记录和复盘记录需要稳定排序。

## 21. 阶段十六：迁移与初始化

### TC-F7-071 首次启动可初始化数据库表

前置条件：
- PostgreSQL 数据库为空。

操作：
- 启动应用或运行初始化脚本。

期望结果：
- 创建所需表。
- 重复执行不报错。

编写原因：
- MVP 需要可部署、可重复初始化。

### TC-F7-072 缺少表时错误清晰

前置条件：
- 数据库连接成功但缺少 `study_plans` 表。

操作：
- 保存或读取计划。

期望结果：
- 返回明确提示：需要初始化数据库。
- 不出现难懂 SQL 错误。

编写原因：
- 部署阶段常见数据库未初始化。

### TC-F7-073 JSONB schema 版本可被识别

前置条件：
- 计划 payload 包含 schema_version。

操作：
- 保存并读取。

期望结果：
- schema_version 保留。
- 读取时可根据版本兼容处理。

编写原因：
- 后续从 JSONB 迁移到规范化表时需要版本信息。

## 22. 阶段十七：自动化测试建议

### 22.1 单元测试

建议覆盖：

- Repository 接口契约
- dataclass 到 JSON 的序列化和反序列化
- date/datetime 编码解码
- 任务状态更新函数
- 错误转换函数
- 文件/资料元数据转换

### 22.2 集成测试

建议覆盖：

- 使用测试 PostgreSQL 或 SQLite 替身保存和读取目标、计划、任务状态、复盘报告
- 数据库断连场景
- 初始化表脚本
- 事务回滚

### 22.3 页面测试

建议覆盖：

- F3 刷新恢复计划
- F3 保存任务进度
- F5 保存复盘和调整计划
- F6 从持久化数据导出
- 数据库失败时页面提示

### 22.4 手动测试

建议覆盖：

- 生成计划后刷新浏览器
- 修改任务状态后刷新浏览器
- 生成复盘后刷新浏览器
- 重启 Streamlit 后恢复最近计划
- 停止 PostgreSQL 后打开应用

## 23. 用例优先级

### P0 必测

- TC-F7-005 保存学习目标成功
- TC-F7-006 读取最近学习目标成功
- TC-F7-010 保存完整学习计划成功
- TC-F7-011 读取最近学习计划成功
- TC-F7-019 更新任务状态为 done 成功
- TC-F7-024 更新任务备注成功
- TC-F7-027 保存复盘报告成功
- TC-F7-028 读取最近复盘报告成功
- TC-F7-039 刷新后恢复最近学习计划
- TC-F7-040 刷新后恢复任务完成状态
- TC-F7-043 F3 打开时读取持久化计划
- TC-F7-044 F3 保存任务修改后写入数据库
- TC-F7-048 F5 保存调整后计划到数据库
- TC-F7-050 F6 从持久化计划导出
- TC-F7-053 应用启动时数据库不可用不崩溃

### P1 应测

- TC-F7-001 业务层只依赖 Repository 抽象
- TC-F7-004 Repository 错误统一转换为业务可理解错误
- TC-F7-014 JSONB 保存复杂嵌套计划
- TC-F7-026 非法任务状态不能保存
- TC-F7-030 保存复盘报告中文内容不乱码
- TC-F7-032 保存资料元数据成功
- TC-F7-035 更新资料处理状态成功
- TC-F7-045 F3 保存失败时页面提示错误
- TC-F7-049 F5 保存调整失败时回滚
- TC-F7-052 F6 导出持久化复盘报告
- TC-F7-058 保存学习目标和计划使用一致事务
- TC-F7-065 SQL 注入字符串作为用户输入不会破坏数据库
- TC-F7-071 首次启动可初始化数据库表

### P2 可后续补充

- TC-F7-037 保存导出记录成功
- TC-F7-038 导出记录缺失不影响 F6 导出
- TC-F7-061 并发保存时使用最后写入或明确冲突策略
- TC-F7-068 get_latest 返回更新时间最新记录
- TC-F7-070 datetime 字段保存和读取稳定
- TC-F7-073 JSONB schema 版本可被识别

## 24. 完成定义

F7 测试完成需要满足：

- Repository 能保存和读取学习目标。
- Repository 能保存和读取完整学习计划。
- 任务状态、日期、时长、备注能持久保存。
- 复盘报告能持久保存并被读取。
- 资料元数据能保存和读取。
- 刷新 Streamlit 后能恢复最近学习计划。
- 重启 Streamlit 后能恢复最近学习计划。
- F3 可以读取和写入持久化任务进度。
- F5 可以读取持久化计划并保存复盘/调整结果。
- F6 可以读取持久化计划和复盘报告进行导出。
- 数据库不可用时应用不崩溃，错误提示清晰。
- 保存失败不会造成半更新或计划丢失。

## 25. 风险清单

| 风险 | 影响 | 测试防护 |
| --- | --- | --- |
| 只保存 session_state | 刷新后计划丢失 | TC-F7-039、TC-F7-040 |
| 任务 ID 丢失 | F3/F5 无法定位任务 | TC-F7-015 |
| 保存失败无提示 | 用户误以为数据已保存 | TC-F7-045、TC-F7-055、TC-F7-056 |
| 读取失败阻塞启动 | 应用不可用 | TC-F7-053、TC-F7-054 |
| JSONB 反序列化失败 | 计划无法恢复 | TC-F7-014、TC-F7-069 |
| 中文乱码 | 页面和导出不可读 | TC-F7-008、TC-F7-030 |
| 复盘和计划不一致 | F5/F6 展示错误 | TC-F7-029、TC-F7-059 |
| SQL 注入 | 数据库损坏或泄露 | TC-F7-065 |
| 多窗口并发覆盖 | 用户修改丢失 | TC-F7-061 |
| 未初始化数据库 | 部署后功能不可用 | TC-F7-071、TC-F7-072 |

## 26. 建议实现顺序

1. 定义 Repository 接口和 `StorageError`。
2. 实现 dataclass 与 JSON payload 的序列化/反序列化。
3. 实现内存 FakeRepository，先通过应用层测试。
4. 实现 PostgreSQL 表初始化。
5. 实现 `StudyGoalRepository` 和 `StudyPlanRepository`。
6. 实现任务进度更新能力。
7. 实现 `ReviewReportRepository`。
8. 实现 `MaterialRepository`。
9. 将 F3 读取/保存接入 StorageService。
10. 将 F5 复盘报告和调整计划保存接入 StorageService。
11. 将 F6 导出读取接入 StorageService。
12. 补齐数据库不可用、保存失败和事务回滚测试。
