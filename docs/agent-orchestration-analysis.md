# Agent 编排分析：现状与优化建议

## Agent 编排总览

Study Planner 使用 DDD 分层架构，Agent 编排的核心在 `PlannerWorkflow`（`study_planner/agents/planner_workflow.py`），是一个**串行管道（Sequential Pipeline）**，包含 6 个 Node Agent，外加一个 Repair Loop。

### 整体流程

```
StudyGoal 输入
    │
    ▼
┌──────────────────────────────────────────────────┐
│ 1. ProfileAgent   →  分析学习者画像                │
│ 2. KnowledgeAgent →  提取知识点列表                 │
│ 3. ResourceAgent  →  RAG 检索学习资源               │
│                                                    │
│  ┌── Repair Loop (最多 N 次) ────────────────┐     │
│  │ 4. PlannerAgent → 生成学习计划草案            │     │
│  │ 5. CriticAgent  → 规则校验（通过则跳出循环）     │     │
│  └───────────────────────────────────────────┘     │
│                                                    │
│ 6. OutputAgent   →  规范化最终输出                   │
└──────────────────────────────────────────────────┘
    │
    ▼
StudyPlan 输出
```

---

## 每个 Agent 是否使用 LLM

| Agent | 文件 | 使用 LLM？ | 说明 |
|---|---|---|---|
| **ProfileAgent** | `nodes/profile.py` | ❌ **不用** | 纯规则引擎。检查 `current_level` 是否有"零"/"基础"来判断风险等级，根据 `daily_available_minutes` 判断时间紧张度 |
| **KnowledgeAgent** | `nodes/knowledge.py` | ⚠️ **可选，默认不用** | 有 `llm` 参数但默认为 `None`。无 LLM 时走 `_payload()` 方法——根据科目名返回硬编码知识点（"机器学习"→数学基础+监督学习，其他→变量+函数） |
| **ResourceAgent** | `nodes/resource.py` | ❌ **不用** | 调用 RAG 向量检索引擎搜索资料，但 RAG 本身只做检索不做生成，不调 LLM |
| **PlannerAgent** | `nodes/planner.py` | ⚠️ **可选，默认不用** | 如果注入的 `llm` 有 `generate_study_plan` 方法则调 LLM，否则走规则逻辑——取知识点名称列表，按日期和每日可用时间排列任务 |
| **CriticAgent** | `nodes/critic.py` | ❌ **不用** | 纯规则校验。检查：任务是否超过截止日期、每日是否超负荷、单任务是否超过 180 分钟、前置依赖顺序是否正确 |
| **OutputAgent** | `nodes/output.py` | ❌ **不用** | 纯数据规范化。字符串→date 对象转换、task ID 唯一性保证、status 字段校验 |
| **ProgressAgent** | `nodes/progress.py` | ❌ **不用** | 纯计算。统计完成率、逾期任务、连续未完成主题 |

### 真正的 LLM 层

| LLM 类 | 文件 | 说明 |
|---|---|---|
| **RealStudyPlanLLM** | `infrastructure/llm/real_study_plan_llm.py` | 调用 DeepSeek API（HTTP POST `/chat/completions`），支持 OpenAI/DeepSeek/Qwen 三种 provider。也内嵌了 `_FakeConfiguredChatModel` 作为假实现 |
| **DeepSeekMaterialLLM** | `infrastructure/llm/material_llm.py` | 用于 Material QA（学习资料问答），同样调 DeepSeek API |

---

## 关键设计要点

### 1. 开关控制

通过 `.env` 的 `USE_REAL_LLM` 控制：

```python
# planner_workflow.py 中的 from_env()
if settings.use_real_llm:
    # 注入 RealStudyPlanLLM → PlannerAgent
    kwargs.setdefault("planner_agent", PlannerAgent(llm=llm))
```

- `USE_REAL_LLM=false`（默认）：**整个 Agent 管道零 API 调用**，全部用规则+硬编码数据跑通
- `USE_REAL_LLM=true`：只给 `PlannerAgent` 注入真实的 DeepSeek LLM，其他 5 个 Agent 依然不用 LLM

### 2. 依赖注入 + Spy 模式

所有 Agent 通过构造函数注入，测试时可以用 `with_spy()` 创建打桩 Agent：

```python
PlannerWorkflow.with_spy(call_order=[])  # 每个节点只记录调用顺序，不执行真实逻辑
```

### 3. Repair Loop（修复循环）

Planner → Critic 这对接了一个重试机制（默认最多 2 次），只有 Critic 返回 `passed=True` 才会进入 Output 阶段。这是一种**不带 LLM 的自我修正**——CriticAgent 用规则发现计划中的问题，但问题在于 Critic 发现的 `issues` 从未回传给 PlannerAgent（见下方优化建议）。

### 4. 两个 LLM 的区别

- `RealStudyPlanLLM`：输入 StudyGoal，输出完整 JSON 学习计划（学习路径+阶段+周计划+每日任务），prompt 由 `study_plan_prompt.py` 构建
- `DeepSeekMaterialLLM`：通用的 prompt→text 生成，用于 Material QA 场景

---

## 现有 Agent 编排的优化建议

### 🔴 高优先级

#### 1. Repair Loop 形同虚设 —— Critic 反馈没有传给 Planner

**问题：** `CriticAgent.run()` 产生了具体的 `issues` 列表（"任务超期"、"每日超载"、"任务需拆分"），但这些**从未回传给 PlannerAgent**。PlannerAgent 每次重试都用完全相同的参数再跑一次——在 `temperature=0.2` 的情况下，很可能产生完全相同的结果。

**当前代码：**
```python
for attempt in range(self.max_repair_attempts):
    draft = self.planner_agent.run(goal, learner_profile, knowledge_points, resources)
    review = self.critic_agent.run(draft)
    if review.passed:
        ...
    # ❌ 重试时 Planner 收到的输入一模一样！
```

**建议方案：**
```python
# PlannerAgent.run() 增加 feedback 参数
def run(self, goal, learner_profile, knowledge_points, resources, feedback=None):
    if feedback:
        # 将 Critic 的 issues 注入 prompt，让 LLM 针对性修正
        ...

# Repair loop 中：
for attempt in range(self.max_repair_attempts):
    draft = self.planner_agent.run(..., feedback=state.review)
    review = self.critic_agent.run(draft)
    if review.passed:
        break
```

#### 2. KnowledgeAgent 无 LLM 时的回退太弱

**问题：** 只有两个科目的硬编码映射，其余全部返回"变量 + 函数"——这对一个学习计划系统来说过于简陋。

**建议方案：** 引入一个**知识图谱模板引擎**（不依赖 LLM），按学科→方向→知识点层级维护一份静态 taxonomy：

```python
KNOWLEDGE_TAXONOMY = {
    "Python": {
        "基础": [{"name": "变量与类型", ...}, {"name": "控制流", ...}, ...],
        "中级": [{"name": "装饰器", ...}, {"name": "生成器", ...}, ...],
    },
    "机器学习": {
        "初级": [{"name": "线性代数基础", ...}, {"name": "概率论", ...}, ...],
        ...
    },
}
```

### 🟡 中优先级

#### 3. ProfileAgent 和 KnowledgeAgent 可以并行

两者之间没有数据依赖：
- `ProfileAgent` 只读 `goal.current_level`/`goal.daily_available_minutes`/`goal.deadline`
- `KnowledgeAgent` 只读 `goal.subject`/`goal.weak_points`（`_payload()` 方法根本没有用到 `learner_profile`）

即使现在这两步都是纯规则计算（微秒级），如果未来 KnowledgeAgent 接入 LLM，这个并行化就会产生实际的延迟收益。

#### 4. ResourceAgent 应该按知识点分别检索

**问题：** 当前实现把所有知识点拼成**一个查询**，被前几个关键词主导，后面的知识点可能完全丢失。

**建议：** 对每个知识点独立检索，再合并去重：

```python
def run(self, goal, knowledge_points):
    all_results = []
    for point in (knowledge_points or []):
        results = self.rag.search(f"{goal.subject} {point.name}")
        all_results.extend(results)
    return self._deduplicate(all_results)
```

### 🟢 低优先级

#### 5. WorkflowReplanPlanner 与 PlannerWorkflow 有代码重复

`WorkflowReplanPlanner.replan()` 在 `workflow=None` 时的回退逻辑与 `PlannerAgent.replan()` 高度相似，`_merge_done_tasks` 在两个路径中都有调用。可以合并。

#### 6. State 在 Agent 间传递缺乏类型契约

每个 Agent 的输入/输出通过 `_run_node_or_call` 手动赋值给 state。建议让每个 Agent 返回 `dict[str, Any]` 并通过 `dataclasses.replace(state, **agent_output)` 更新。

#### 7. 缺少 Agent 级别的可观测性

当前 debug 模式只记录每个节点的耗时，建议额外记录每个 Agent 的输入摘要和输出摘要。

#### 8. `_llm_blocked` 的类名检测是反向依赖

Workflow 层不应该知道测试桩的类名。更好的做法是让异常类实现统一的 `is_blocked()` 协议方法，或者抛出一个统一的 `LLMBlockedError`。
