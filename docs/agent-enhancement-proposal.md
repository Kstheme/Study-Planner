# Agent 增强方案：LLM 接入点与新 Agent 设计

## 核心洞察：当前 Workflow 缺失的关键环节

当前流程本质上是：

```
目标 → 画像(规则) → 知识点(硬编码) → 资源(一次检索) → 生成计划(可选LLM) → 规则校验 → 输出
```

但**一个真正有效的学习规划系统**需要回答 7 个问题，当前的 Agent 链只回答了其中 3 个：

| 问题 | 当前谁来回答 | 充分吗？ |
|---|---|---|
| 1. 学习者是谁？ | ProfileAgent (规则) | ❌ 只读了字符串是否含"零/基础" |
| 2. 学什么？ | KnowledgeAgent (硬编码2科) | ❌ 这是最大的短板 |
| 3. 怎么学？ | 无 | ❌ **完全缺失** |
| 4. 用什么学？ | ResourceAgent (一次 RAG) | ⚠️ 有但粗糙 |
| 5. 具体计划？ | PlannerAgent (可选 LLM) | ⚠️ 但缺少上游上下文 |
| 6. 计划好吗？ | CriticAgent (规则) | ⚠️ 只做结构校验，不做语义判断 |
| 7. 学得怎么样？ | ProgressAgent + SimpleReplan | ⚠️ 只算完成率，不做归因 |

---

## Tier 1：立刻做 —— 投入产出比最高

### 1. KnowledgeAgent 必须接入 LLM

这是整个系统最薄弱的环节。`_payload()` 里硬编码 2 个学科，其余全返回"变量 + 函数"。**知识点分解是学习计划的地基，地基歪了后面全歪。**

**具体做法：**

```python
# study_planner/agents/nodes/knowledge.py 改造

class KnowledgeAgent:
    def __init__(self, llm=None):
        self.llm = llm

    def run(self, goal, learner_profile=None):
        if self.llm is not None:
            return self._llm_decompose(goal, learner_profile)
        return self._template_decompose(goal)  # 保留模板回退

    def _llm_decompose(self, goal, learner_profile):
        prompt = f"""你是课程设计专家。请将学习目标分解为知识点树。

        学科：{goal.subject}
        目标：{goal.target}
        当前水平：{goal.current_level}
        薄弱点：{', '.join(goal.weak_points)}
        可用时间：每天{goal.daily_available_minutes}分钟，
        共{(goal.deadline - date.today()).days}天

        要求：
        1. 知识点必须有层级结构（大知识点→子知识点）
        2. 标注前置依赖关系（哪个必须先学）
        3. 根据用户水平和时间约束调整深度和粒度
        4. 标注每个知识点的难度(1-5)和重要性(1-5)

        输出JSON数组，每个元素：
        {{"name", "description", "prerequisites", "difficulty",
          "importance", "subtopics": [...]}}"""
        return self.llm.generate(prompt)  # 结构化解析
```

**为什么 LLM 在这里不可替代：** 知识点分解需要"领域知识 + 教学经验"——知道《机器学习》应该先讲线性代数而非直接上神经网络，知道对"零基础"用户要拆到多细——规则系统永远做不好这件事。

### 2. 把上游 Agent 的输出喂给 PlannerAgent 的 prompt

当前 `build_study_plan_prompt()` 只用了原始 `StudyGoal`，但 Workflow 中 ProfileAgent、KnowledgeAgent、ResourceAgent 已经产出了丰富的中间结果。**这些结果全被丢弃了。**

```python
# prompts/study_plan_prompt.py 改造

def build_study_plan_prompt(goal, learner_profile=None,
                            knowledge_points=None, resources=None):
    prompt = f"""你是学习规划专家。请根据以下完整信息生成学习计划。

    ## 学习者画像
    - 水平：{learner_profile.level}
    - 风险等级：{learner_profile.risk_level}
    - 风险提示：{', '.join(learner_profile.risks)}

    ## 知识点体系（必须覆盖）
    {_format_knowledge_tree(knowledge_points)}

    ## 可用学习资源
    {_format_resources(resources)}

    ## 约束条件
    - 每日{goal.daily_available_minutes}分钟
    - 每周{goal.weekly_available_days}天
    - 截止日期：{goal.deadline}
    ...
    """
```

**效果：** 假设 KnowledgeAgent 产出了"线性代数→梯度下降→损失函数→反向传播"的依赖链，PlannerAgent 就能安排合理的学习顺序和节奏，而不是随机排列。

---

## Tier 2：建议近期做 —— 中等投入，显著提升

### 3. 新增 LearningStrategyAgent（LLM）

**为什么需要：** 学"Python 编程"和学"世界历史"的最优策略完全不同——编程需要大量练习+项目，历史需要阅读+思维导图+时间线记忆。当前 planner 用同一套模板生成所有计划。

**位置：** 插入在 KnowledgeAgent 之后、PlannerAgent 之前。

```python
# study_planner/agents/nodes/strategy.py (新文件)

class LearningStrategyAgent:
    """根据学科性质和学习者特征，选择最优学习策略。"""

    def __init__(self, llm=None):
        self.llm = llm

    def run(self, goal, learner_profile, knowledge_points) -> dict:
        if self.llm:
            return self._llm_strategy(goal, learner_profile, knowledge_points)
        return self._rule_strategy(goal)

    def _llm_strategy(self, goal, learner_profile, knowledge_points):
        prompt = f"""你是学习策略专家。为以下学习场景推荐最佳策略。

        学科：{goal.subject}（类型：{self._classify_subject(goal.subject)}）
        学习者水平：{goal.current_level}
        知识点数量：{len(knowledge_points)}
        总时间：{(goal.deadline - date.today()).days}天

        请推荐：
        1. 学习阶段划分（如：基础→进阶→实战）
        2. 每阶段的学习方法配比（阅读% / 练习% / 项目%）
        3. 复习策略（间隔复习 / 每日巩固 / 周总结）
        4. 里程碑设置建议
        5. 可能的风险和应对
        """
        ...

    def _rule_strategy(self, goal) -> dict:
        """基于学科分类的规则回退"""
        subject_type = self._classify_subject(goal.subject)
        strategies = {
            "programming": {
                "phase_structure": ["语法基础", "核心库", "项目实战"],
                "method_ratio": {"reading": 20, "coding": 60, "project": 20},
            },
            "math": {
                "phase_structure": ["理论", "计算练习", "综合应用"],
                "method_ratio": {"reading": 30, "practice": 60, "testing": 10},
            },
            "language": {
                "phase_structure": ["语音词汇", "句型语法", "场景应用"],
                "method_ratio": {"memorization": 30, "listening": 30, "speaking": 40},
            },
        }
        return strategies.get(subject_type, strategies.get("default", {...}))
```

### 4. 新增 SemanticCriticAgent（LLM）—— 与结构 Critic 形成双层校验

**为什么需要：** 当前 CriticAgent 只检查**硬约束**（日期、时长、依赖），不检查**软质量**（学习路径是否合理、难度递进是否平滑、方法是否多样）。

**双层校验架构：**

```
PlannerAgent ──→ StructuralCritic (规则，现有) ──→ 日期/时长/依赖 OK?
             ──→ SemanticCritic (LLM，新增) ──→ 教学/认知质量 OK?
             ──→ 两者都通过 → OutputAgent
```

```python
# study_planner/agents/nodes/semantic_critic.py (新文件)

class SemanticCriticAgent:
    """用LLM评判学习计划的教学质量。"""

    def run(self, plan, learner_profile, knowledge_points) -> CriticReview:
        prompt = f"""你是教学督导。请评审这份学习计划的质量。

        ## 学习者情况
        {learner_profile.summary}
        风险：{learner_profile.risks}

        ## 需覆盖的知识点
        {[kp.name for kp in knowledge_points]}

        ## 计划内容
        阶段数：{len(plan.phases)}
        总任务数：{sum(len(wp.tasks)
                       for p in plan.phases
                       for wp in p.weekly_plans)}
        学习方法：{plan.methods}

        请从以下维度评分(1-5)并给出改进建议：
        1. 知识点覆盖度——计划是否覆盖了所有必需知识点？
        2. 学习路径合理性——顺序是否符合认知规律（先基础后进阶）？
        3. 难度递进——任务难度是否逐步提升？
        4. 方法多样性——是否混合了阅读、练习、项目等多种方式？
        5. 时间可行性——对于该水平的学习者，节奏是否合理？
        6. 复习机制——复习安排是否符合间隔记忆原理？

        返回JSON: {{"scores": {{...}}, "issues": [...],
                    "suggestions": [...], "passed": bool}}
        """
```

---

## Tier 3：长远来看值得加

### 5. 新增 DiagnosticAgent（LLM）—— 前置诊断

目前 `weak_points` 是用户自己填的，但用户往往不知道自己的真正薄弱点。一个对话式诊断能更准确地定位。

**位置：** 与 ProfileAgent 并行，或紧跟其后。

```python
# study_planner/agents/nodes/diagnostic.py (新文件)

class DiagnosticAgent:
    """通过对话式提问，诊断学习者的真实水平分布。"""

    def __init__(self, llm=None):
        self.llm = llm

    def generate_questions(self, goal, knowledge_points) -> list[str]:
        """针对知识树生成诊断性问题，评估每个知识点的掌握度"""
        ...

    def calibrate_mastery(self, answers, knowledge_points) -> dict:
        """根据回答调整每个知识点的 mastery_level"""
        ...
```

### 6. 新增 ReflectionAgent（LLM）—— 复盘归因

当前 `ProgressAgent` 只算数字（完成率、逾期数），但不说**为什么**。`LocalReviewLLM` 的复盘是模板化的。

**位置：** 在 ProgressAgent 之后，ReplanPlanner 之前。

```python
# study_planner/agents/nodes/reflection.py (新文件)

class ReflectionAgent:
    """分析学习数据，做归因推理。"""

    def __init__(self, llm=None):
        self.llm = llm

    def analyze(self, progress_context, review_report, original_plan) -> dict:
        prompt = f"""你是学习教练。分析以下学习数据：

        完成率：{progress_context.completion_rate}
        逾期任务：{progress_context.overdue_task_ids}
        连续未完成主题：{progress_context.consecutive_unfinished_topics}
        用户反思：{review_report.summary}

        请分析：
        1. 未完成的根本原因
           （时间不足？难度过高？动机下降？方法不当？）
        2. 是否需要调整学习策略
           （而非仅仅重新排期）
        3. 具体的行为建议
        """
```

---

## 优化后的完整 Agent 编排图

```
                          StudyGoal
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ProfileAgent    DiagnosticAgent   KnowledgeAgent
        (规则+可选LLM)   (NEW, LLM)       (LLM增强)
              │               │               │
              │          mastery_levels        │
              │               │               │
              └───────────────┼───────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ResourceAgent        LearningStrategyAgent
            (增强:逐点检索)       (NEW, LLM)
                    │                   │
                    └─────────┬─────────┘
                              ▼
                        PlannerAgent
                        (LLM, 接收完整上游上下文)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            StructuralCritic      SemanticCritic
            (规则, 现有)           (NEW, LLM)
                    │                   │
                    └─────────┬─────────┘
                         都通过？
                          │ YES
                          ▼
                      OutputAgent
                      (规则, 现有)
                          │
                          ▼
                      StudyPlan
                          │
                          ▼ (学习进行中...)
                    ProgressAgent (规则)
                          │
                          ▼
                    ReflectionAgent (NEW, LLM)
                          │
                          ▼
                    ReplanPlanner (增强)
```

---

## 实施优先级排序

| 优先级 | 改动 | 对应文件 | 效果 |
|--------|------|----------|------|
| 🔴 P0 | KnowledgeAgent 接入 LLM | `agents/nodes/knowledge.py` 改造 | 让"学什么"从硬编码变成智能分解 |
| 🔴 P0 | Planner 接收上游上下文 | `prompts/study_plan_prompt.py` 改造 | 让 LLM 有完整信息做决策 |
| 🟡 P1 | LearningStrategyAgent | `agents/nodes/strategy.py` 新建 | 让"怎么学"有方法论支撑 |
| 🟡 P1 | SemanticCriticAgent | `agents/nodes/semantic_critic.py` 新建 | 让质量校验从"格式"升级到"内容" |
| 🟢 P2 | ResourceAgent 逐点检索 | `agents/nodes/resource.py` 改造 | 提高资料匹配精度 |
| 🟢 P2 | DiagnosticAgent | `agents/nodes/diagnostic.py` 新建 | 更准确的学习起点定位 |
| 🟢 P3 | ReflectionAgent | `agents/nodes/reflection.py` 新建 | 从"算数字"升级到"做归因" |

---

## 最快见效路径

先做 P0（KnowledgeAgent + Planner prompt 增强），两个改动加起来改动点少（2-3 个文件），但能让生成的计划质量从"能用"变成"好用"，因为 LLM 终于知道应该教什么、教给谁了。
