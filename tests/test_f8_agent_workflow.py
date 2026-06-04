from datetime import date, datetime, timedelta
from importlib import import_module

import pytest

from study_planner.domain.models import (
    ReviewReport,
    ReviewSchedule,
    StudyGoal,
    StudyPhase,
    StudyPlan,
    StudyTask,
    TimeBudget,
    WeeklyPlan,
)


CURRENT_DATE = date(2026, 6, 4)


def f8_attr(module_name: str, attr_name: str):
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"F8 module is required: {module_name}") from exc
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise AssertionError(f"F8 attribute is required: {module_name}.{attr_name}") from exc


def valid_goal(**overrides):
    data = {
        "subject": "Python 编程",
        "target": "掌握 Python 基础语法并完成一个小项目",
        "deadline": date(2026, 6, 30),
        "current_level": "零基础",
        "daily_available_minutes": 120,
        "weekly_available_days": 5,
        "preferred_methods": ["视频教程", "项目实践"],
        "weak_points": ["递归", "面向对象"],
        "extra_requirements": "多安排练习任务",
    }
    data.update(overrides)
    return StudyGoal(**data)


def make_task(task_id="task-1", **overrides):
    data = {
        "id": task_id,
        "title": f"学习任务 {task_id}",
        "date": CURRENT_DATE,
        "duration_minutes": 60,
        "task_type": "study",
        "related_topics": ["Python 基础"],
        "learning_method": "阅读文档 + 练习",
        "expected_output": "完成练习并整理笔记",
        "review_required": True,
        "status": "todo",
        "notes": "",
    }
    data.update(overrides)
    return StudyTask(**data)


def valid_plan(tasks=None, goal=None, **overrides):
    goal = goal or valid_goal()
    tasks = tasks if tasks is not None else [
        make_task("task-1", status="done"),
        make_task("task-2", date=CURRENT_DATE + timedelta(days=1)),
    ]
    data = {
        "goal": goal,
        "overall_route": "先学基础语法，再完成练习，最后做小项目。",
        "phases": [
            StudyPhase(
                phase_index=1,
                title="基础入门阶段",
                objective="掌握变量、条件、循环和函数",
                start_date=CURRENT_DATE,
                end_date=CURRENT_DATE + timedelta(days=13),
                milestone="能完成基础语法练习",
                weekly_plans=[
                    WeeklyPlan(
                        week_index=1,
                        start_date=CURRENT_DATE,
                        end_date=CURRENT_DATE + timedelta(days=6),
                        objective="完成基础语法学习",
                        review_focus="变量、条件、循环、函数",
                        tasks=tasks,
                    )
                ],
            )
        ],
        "methods": ["视频教程", "阅读文档", "项目实践"],
        "time_budget": TimeBudget(
            total_days=27,
            total_weeks=4,
            total_available_minutes=2400,
            planned_minutes=sum(task.duration_minutes for task in tasks),
            daily_available_minutes=goal.daily_available_minutes,
            weekly_available_days=goal.weekly_available_days,
        ),
        "risks": ["每日时间不足可能导致延期"],
        "review_schedule": ReviewSchedule(
            daily_review_minutes=15,
            weekly_review_day="周日",
            review_strategy="每天复习当天知识点，每周整理薄弱点",
        ),
        "suggestions": "每天完成一个可检查产出",
    }
    data.update(overrides)
    return StudyPlan(**data)


def valid_review_report(**overrides):
    data = {
        "period_start": date(2026, 6, 1),
        "period_end": date(2026, 6, 7),
        "completion_rate": 0.5,
        "completed_task_count": 1,
        "total_task_count": 2,
        "overdue_tasks": ["task-2"],
        "consecutive_unfinished_topics": ["递归"],
        "weak_points": ["递归"],
        "summary": "需要补足递归练习",
        "suggestions": ["增加递归专项练习"],
    }
    data.update(overrides)
    return ReviewReport(**data)


def all_tasks(plan):
    return [
        task
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    ]


class SpyNode:
    def __init__(self, name, output_key=None, output_value=None, fail=False):
        self.name = name
        self.output_key = output_key
        self.output_value = output_value
        self.fail = fail
        self.calls = []

    def run(self, state):
        self.calls.append(state)
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        if self.output_key:
            setattr(state, self.output_key, self.output_value)
        return state


class TestF8Stage1PlannerState:
    def test_f8_001_planner_state_contains_required_fields(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")

        state = PlannerState(goal=valid_goal())

        for field_name in [
            "goal",
            "learner_profile",
            "knowledge_points",
            "resources",
            "draft_plan",
            "review",
            "final_plan",
            "errors",
        ]:
            assert hasattr(state, field_name)

    def test_f8_002_planner_state_initializes_empty_flow_state(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        goal = valid_goal()

        state = PlannerState(goal=goal)

        assert state.goal == goal
        assert state.errors == []
        assert state.final_plan is None

    def test_f8_003_planner_state_saves_profile_output_without_overwriting_goal(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        LearnerProfile = f8_attr("study_planner.agents.nodes.profile", "LearnerProfile")
        goal = valid_goal()
        profile = LearnerProfile(level="零基础", risk_level="medium", preferences=["项目实践"])

        state = PlannerState(goal=goal)
        state.learner_profile = profile

        assert state.goal == goal
        assert state.learner_profile == profile

    def test_f8_004_planner_state_saves_knowledge_points(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        KnowledgePoint = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgePoint")
        points = [KnowledgePoint(name="变量", description="基础语法", difficulty=1, importance=5)]

        state = PlannerState(goal=valid_goal(), knowledge_points=points)

        assert state.knowledge_points == points
        assert state.knowledge_points[0].name == "变量"

    def test_f8_005_planner_state_saves_empty_resources(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")

        state = PlannerState(goal=valid_goal(), resources=[])

        assert state.resources == []

    def test_f8_006_planner_state_saves_draft_and_final_plan_separately(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        draft = valid_plan()
        final = valid_plan(tasks=[make_task("final-task", status="todo")])

        state = PlannerState(goal=draft.goal, draft_plan=draft, final_plan=final)

        assert state.draft_plan == draft
        assert state.final_plan == final
        assert state.draft_plan is not state.final_plan

    def test_f8_007_planner_state_accumulates_multiple_node_errors(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        WorkflowError = f8_attr("study_planner.agents.planner_state", "WorkflowError")

        state = PlannerState(goal=valid_goal())
        state.errors.append(WorkflowError(node="resource", message="RAG unavailable"))
        state.errors.append(WorkflowError(node="critic", message="plan overloaded"))

        assert [error.node for error in state.errors] == ["resource", "critic"]

    def test_f8_008_planner_state_rejects_or_records_unserializable_values(self):
        PlannerState = f8_attr("study_planner.agents.planner_state", "PlannerState")
        validate_state_serializable = f8_attr("study_planner.agents.planner_state", "validate_state_serializable")

        state = PlannerState(goal=valid_goal())
        state.resources = [object()]

        with pytest.raises(ValueError, match="serializable|JSON|序列化"):
            validate_state_serializable(state)


class TestF8Stage2ProfileAgent:
    def test_f8_009_profile_agent_generates_learner_profile(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")

        profile = ProfileAgent().run(valid_goal())

        assert profile.level == "零基础"
        assert profile.preferences
        assert hasattr(profile, "risk_level")

    def test_f8_010_profile_agent_does_not_mutate_original_goal(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")
        goal = valid_goal()
        before = valid_goal()

        ProfileAgent().run(goal)

        assert goal == before

    def test_f8_011_profile_agent_identifies_zero_based_risk(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")

        profile = ProfileAgent().run(valid_goal(current_level="零基础"))

        assert "基础" in " ".join(profile.risks) or profile.risk_level in {"medium", "high"}

    def test_f8_012_profile_agent_identifies_tight_deadline(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")

        profile = ProfileAgent().run(valid_goal(deadline=CURRENT_DATE + timedelta(days=3), daily_available_minutes=30))

        assert any("时间" in risk or "deadline" in risk.lower() for risk in profile.risks)

    def test_f8_013_profile_agent_preserves_chinese_input(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")

        profile = ProfileAgent().run(valid_goal(subject="机器学习", weak_points=["数学基础"]))

        assert "机器学习" in profile.summary
        assert "数学基础" in profile.summary or "数学基础" in getattr(profile, "weak_points", [])

    def test_f8_014_profile_agent_supports_empty_optional_fields(self):
        ProfileAgent = f8_attr("study_planner.agents.nodes.profile", "ProfileAgent")

        profile = ProfileAgent().run(valid_goal(preferred_methods=[], weak_points=[], extra_requirements=""))

        assert profile is not None
        assert getattr(profile, "preferences", []) == []

    def test_f8_015_profile_agent_failure_enters_workflow_errors(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        workflow = PlannerWorkflow(profile_agent=SpyNode("profile", fail=True))
        result = workflow.run(valid_goal())

        assert result.errors
        assert result.errors[0].node == "profile"


class TestF8Stage3KnowledgeAgent:
    def test_f8_016_knowledge_agent_generates_knowledge_points(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        points = KnowledgeAgent().run(goal=valid_goal(), learner_profile=None)

        assert points
        assert all(point.name for point in points)

    def test_f8_017_knowledge_agent_marks_prerequisites(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        points = KnowledgeAgent().run(goal=valid_goal(subject="机器学习"), learner_profile=None)

        assert any(getattr(point, "prerequisites", []) for point in points)

    def test_f8_018_knowledge_agent_difficulty_is_in_range(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        points = KnowledgeAgent().run(goal=valid_goal(), learner_profile=None)

        assert all(1 <= point.difficulty <= 5 for point in points)

    def test_f8_019_knowledge_agent_importance_is_in_range(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        points = KnowledgeAgent().run(goal=valid_goal(), learner_profile=None)

        assert all(1 <= point.importance <= 5 for point in points)

    def test_f8_020_knowledge_agent_deduplicates_points(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")
        fake_llm = {"knowledge_points": [{"name": "变量"}, {"name": "变量"}]}

        points = KnowledgeAgent(llm=fake_llm).run(goal=valid_goal(), learner_profile=None)

        assert [point.name for point in points].count("变量") == 1

    def test_f8_021_knowledge_agent_keeps_user_weak_points(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        points = KnowledgeAgent().run(goal=valid_goal(weak_points=["递归"]), learner_profile=None)

        assert "递归" in {point.name for point in points} or any("递归" in point.description for point in points)

    def test_f8_022_knowledge_agent_handles_non_json_llm_response(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        with pytest.raises(ValueError, match="JSON|结构化|parse"):
            KnowledgeAgent(llm="这是一段普通文本").run(goal=valid_goal(), learner_profile=None)

    def test_f8_023_knowledge_agent_rejects_empty_points_or_records_error(self):
        KnowledgeAgent = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgeAgent")

        with pytest.raises(ValueError, match="知识点|knowledge|empty"):
            KnowledgeAgent(llm={"knowledge_points": []}).run(goal=valid_goal(), learner_profile=None)


class TestF8Stage4ResourceAgent:
    def test_f8_024_resource_agent_returns_learning_resources(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")
        KnowledgePoint = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgePoint")
        points = [KnowledgePoint(name="变量", description="", difficulty=1, importance=5)]

        resources = ResourceAgent().run(goal=valid_goal(), knowledge_points=points)

        assert isinstance(resources, list)
        if resources:
            assert hasattr(resources[0], "title")
            assert hasattr(resources[0], "source")

    def test_f8_025_resource_agent_no_material_returns_empty_list(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")

        resources = ResourceAgent(rag=None).run(goal=valid_goal(), knowledge_points=[])

        assert resources == []

    def test_f8_026_resource_agent_calls_rag_service(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")
        FakeRAG = f8_attr("study_planner.agents.testing", "FakeRAG")
        rag = FakeRAG(results=[{"title": "Python 官方文档", "source": "docs"}])

        resources = ResourceAgent(rag=rag).run(goal=valid_goal(), knowledge_points=[])

        assert rag.queries
        assert resources[0].title == "Python 官方文档"

    def test_f8_027_resource_agent_failure_can_degrade_to_empty_resources(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")
        FakeRAG = f8_attr("study_planner.agents.testing", "FakeRAG")

        resources = ResourceAgent(rag=FakeRAG(fail=True), allow_degraded=True).run(goal=valid_goal(), knowledge_points=[])

        assert resources == []

    def test_f8_028_resource_agent_preserves_citations(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")
        FakeRAG = f8_attr("study_planner.agents.testing", "FakeRAG")
        rag = FakeRAG(results=[{"title": "递归笔记", "source": "note.md", "chunk_id": "chunk-1"}])

        resources = ResourceAgent(rag=rag).run(goal=valid_goal(), knowledge_points=[])

        assert resources[0].source == "note.md"
        assert resources[0].chunk_id == "chunk-1"

    def test_f8_029_resource_agent_links_resources_to_knowledge_points(self):
        ResourceAgent = f8_attr("study_planner.agents.nodes.resource", "ResourceAgent")
        KnowledgePoint = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgePoint")
        points = [KnowledgePoint(name="递归", description="", difficulty=3, importance=5)]

        resources = ResourceAgent().run(goal=valid_goal(), knowledge_points=points)

        assert all(getattr(resource, "related_topics", []) is not None for resource in resources)

    def test_f8_030_resource_agent_does_not_directly_depend_on_milvus_sdk(self):
        module = import_module("study_planner.agents.nodes.resource")

        assert "pymilvus" not in getattr(module, "__dict__", {})


class TestF8Stage5PlannerAgent:
    def test_f8_031_planner_agent_generates_draft_plan(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")

        draft = PlannerAgent().run(goal=valid_goal(), learner_profile=None, knowledge_points=[], resources=[])

        assert isinstance(draft, StudyPlan)
        assert draft.phases

    def test_f8_032_planner_agent_binds_original_goal(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")
        goal = valid_goal(subject="数据分析")

        draft = PlannerAgent().run(goal=goal, learner_profile=None, knowledge_points=[], resources=[])

        assert draft.goal == goal

    def test_f8_033_planner_agent_generates_three_level_structure(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")

        draft = PlannerAgent().run(goal=valid_goal(), learner_profile=None, knowledge_points=[], resources=[])

        assert draft.phases
        assert draft.phases[0].weekly_plans
        assert draft.phases[0].weekly_plans[0].tasks

    def test_f8_034_planner_agent_tasks_contain_required_fields(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")

        task = all_tasks(PlannerAgent().run(goal=valid_goal(), learner_profile=None, knowledge_points=[], resources=[]))[0]

        for field_name in ["title", "date", "duration_minutes", "task_type", "related_topics", "learning_method", "expected_output", "status", "id"]:
            assert getattr(task, field_name) is not None

    def test_f8_035_planner_agent_uses_knowledge_points_for_task_topics(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")
        KnowledgePoint = f8_attr("study_planner.agents.nodes.knowledge", "KnowledgePoint")
        points = [KnowledgePoint(name="递归", description="", difficulty=3, importance=5)]

        draft = PlannerAgent().run(goal=valid_goal(), learner_profile=None, knowledge_points=points, resources=[])

        assert any("递归" in task.related_topics or "递归" in task.title for task in all_tasks(draft))

    def test_f8_036_planner_agent_uses_resource_outputs(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")
        LearningResource = f8_attr("study_planner.agents.nodes.resource", "LearningResource")
        resources = [LearningResource(title="Python 官方文档", source="docs.python.org", related_topics=["变量"])]

        draft = PlannerAgent().run(goal=valid_goal(), learner_profile=None, knowledge_points=[], resources=resources)

        assert any("Python 官方文档" in task.learning_method or "docs.python.org" in task.learning_method for task in all_tasks(draft))

    def test_f8_037_planner_agent_handles_missing_fields(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")

        with pytest.raises(ValueError, match="phases|字段|结构"):
            PlannerAgent(llm={"overall_route": "missing phases"}).run(
                goal=valid_goal(), learner_profile=None, knowledge_points=[], resources=[]
            )

    def test_f8_038_planner_agent_supports_replan_request(self):
        PlannerAgent = f8_attr("study_planner.agents.nodes.planner", "PlannerAgent")
        ReplanRequest = f8_attr("study_planner.agents.nodes.progress", "WorkflowReplanRequest")
        plan = valid_plan()
        request = ReplanRequest(original_plan=plan, review_report=valid_review_report(), remaining_tasks=[all_tasks(plan)[1]])

        adjusted = PlannerAgent().replan(request)

        assert isinstance(adjusted, StudyPlan)
        assert all_tasks(adjusted)[0].status == "done"


class TestF8Stage6CriticAgent:
    def test_f8_039_critic_agent_detects_daily_overload(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")
        plan = valid_plan(tasks=[make_task("a", duration_minutes=90), make_task("b", duration_minutes=90)])

        review = CriticAgent().run(plan)

        assert review.passed is False
        assert any("overload" in issue.code or "过载" in issue.message for issue in review.issues)

    def test_f8_040_critic_agent_detects_tasks_after_deadline(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")
        goal = valid_goal(deadline=date(2026, 6, 10))
        plan = valid_plan(goal=goal, tasks=[make_task("late", date=date(2026, 6, 11))])

        review = CriticAgent().run(plan)

        assert review.passed is False
        assert any("deadline" in issue.code or "截止" in issue.message for issue in review.issues)

    def test_f8_041_critic_agent_detects_prerequisite_order_errors(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")
        plan = valid_plan(tasks=[
            make_task("advanced", title="学习递归优化", date=CURRENT_DATE),
            make_task("basic", title="学习函数基础", date=CURRENT_DATE + timedelta(days=1)),
        ])

        review = CriticAgent(prerequisites={"advanced": ["basic"]}).run(plan)

        assert review.passed is False
        assert any("prerequisite" in issue.code or "先修" in issue.message for issue in review.issues)

    def test_f8_042_critic_agent_detects_oversized_task(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")
        plan = valid_plan(tasks=[make_task("huge", duration_minutes=240)])

        review = CriticAgent(max_single_task_minutes=120).run(plan)

        assert review.passed is False
        assert any("split" in issue.code or "拆分" in issue.message for issue in review.issues)

    def test_f8_043_critic_agent_passes_reasonable_plan(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")

        review = CriticAgent().run(valid_plan())

        assert review.passed is True
        assert review.issues == []

    def test_f8_044_critic_failure_returns_to_planner_for_repair(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakePlannerAgent = f8_attr("study_planner.agents.testing", "FakePlannerAgent")
        planner = FakePlannerAgent(outputs=[
            valid_plan(tasks=[make_task("a", duration_minutes=90), make_task("b", duration_minutes=90)]),
            valid_plan(tasks=[make_task("a", duration_minutes=60), make_task("b", date=CURRENT_DATE + timedelta(days=1))]),
        ])

        result = PlannerWorkflow(planner_agent=planner).run(valid_goal())

        assert planner.call_count == 2
        assert result.final_plan is not None
        assert result.review.passed is True

    def test_f8_045_critic_repair_loop_has_max_attempts(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakePlannerAgent = f8_attr("study_planner.agents.testing", "FakePlannerAgent")
        overloaded = valid_plan(tasks=[make_task("a", duration_minutes=90), make_task("b", duration_minutes=90)])

        result = PlannerWorkflow(planner_agent=FakePlannerAgent(always=overloaded), max_repair_attempts=2).run(valid_goal())

        assert result.errors
        assert "repair" in result.errors[-1].message.lower() or "修复" in result.errors[-1].message

    def test_f8_046_critic_repair_keeps_original_goal(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        goal = valid_goal(subject="机器学习")

        result = PlannerWorkflow().run(goal)

        assert result.final_plan.goal == goal

    def test_f8_047_critic_review_is_serializable(self):
        CriticAgent = f8_attr("study_planner.agents.nodes.critic", "CriticAgent")
        serialize_critic_review = f8_attr("study_planner.agents.nodes.critic", "serialize_critic_review")

        payload = serialize_critic_review(CriticAgent().run(valid_plan()))

        assert isinstance(payload, dict)
        assert "passed" in payload


class TestF8Stage7OutputAgent:
    def test_f8_048_output_agent_returns_study_plan(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")

        final_plan = OutputAgent().run(valid_plan())

        assert isinstance(final_plan, StudyPlan)

    def test_f8_049_output_agent_validates_required_fields(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")
        payload = {"goal": valid_goal(), "phases": []}

        with pytest.raises(ValueError, match="time_budget|字段|required"):
            OutputAgent().run(payload)

    def test_f8_050_output_agent_normalizes_date_fields(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")
        payload = valid_plan()
        payload.goal.deadline = "2026-06-30"
        all_tasks(payload)[0].date = "2026-06-04"

        final_plan = OutputAgent().run(payload)

        assert isinstance(final_plan.goal.deadline, date)
        assert isinstance(all_tasks(final_plan)[0].date, date)

    def test_f8_051_output_agent_generates_stable_task_ids(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")
        plan = valid_plan(tasks=[make_task("", id=""), make_task("", id="")])

        final_plan = OutputAgent().run(plan)
        ids = [task.id for task in all_tasks(final_plan)]

        assert all(ids)
        assert len(ids) == len(set(ids))

    def test_f8_052_output_agent_normalizes_task_status(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")
        plan = valid_plan(tasks=[make_task("task-1", status="未开始")])

        final_plan = OutputAgent().run(plan)

        assert all_tasks(final_plan)[0].status == "todo"

    def test_f8_053_output_agent_rejects_invalid_task_status(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")

        with pytest.raises(ValueError, match="status|状态"):
            OutputAgent().run(valid_plan(tasks=[make_task("bad", status="unknown")]))

    def test_f8_054_output_agent_preserves_chinese_content(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")

        final_plan = OutputAgent().run(valid_plan(goal=valid_goal(subject="机器学习")))

        assert final_plan.goal.subject == "机器学习"

    def test_f8_055_output_agent_does_not_call_llm(self):
        OutputAgent = f8_attr("study_planner.agents.nodes.output", "OutputAgent")
        ExplodingLLM = f8_attr("study_planner.agents.testing", "ExplodingLLM")

        final_plan = OutputAgent(llm=ExplodingLLM()).run(valid_plan())

        assert isinstance(final_plan, StudyPlan)


class TestF8Stage8ProgressAgent:
    def test_f8_056_progress_agent_generates_review_context(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")

        context = ProgressAgent().run(valid_plan(), current_date=CURRENT_DATE)

        assert context.total_task_count == 2
        assert context.completed_task_count == 1

    def test_f8_057_progress_agent_completion_rate_uses_real_state(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        tasks = [make_task(f"task-{index}", status="done" if index == 1 else "todo") for index in range(1, 28)]

        context = ProgressAgent().run(valid_plan(tasks=tasks), current_date=CURRENT_DATE)

        assert context.total_task_count == 27
        assert context.completed_task_count == 1
        assert context.completion_rate == pytest.approx(1 / 27)

    def test_f8_058_progress_agent_identifies_overdue_tasks(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        plan = valid_plan(tasks=[make_task("late", date=CURRENT_DATE - timedelta(days=1), status="todo")])

        context = ProgressAgent().run(plan, current_date=CURRENT_DATE)

        assert "late" in context.overdue_task_ids

    def test_f8_059_progress_agent_identifies_consecutive_unfinished_topics(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        tasks = [make_task(f"r-{index}", related_topics=["递归"], status="todo") for index in range(3)]

        context = ProgressAgent().run(valid_plan(tasks=tasks), current_date=CURRENT_DATE)

        assert "递归" in context.consecutive_unfinished_topics

    def test_f8_060_progress_agent_builds_replan_request(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")

        request = ProgressAgent().build_replan_request(valid_plan(), valid_review_report(), current_date=CURRENT_DATE)

        assert request.remaining_tasks
        assert request.remaining_days >= 0

    def test_f8_061_progress_agent_does_not_replan_done_tasks(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        plan = valid_plan()

        request = ProgressAgent().build_replan_request(plan, valid_review_report(), current_date=CURRENT_DATE)

        assert all(task.status != "done" for task in request.remaining_tasks)

    def test_f8_062_progress_agent_errors_when_goal_is_expired(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")

        with pytest.raises(ValueError, match="deadline|过期"):
            ProgressAgent().build_replan_request(
                valid_plan(goal=valid_goal(deadline=date(2026, 6, 1))),
                valid_review_report(),
                current_date=CURRENT_DATE,
            )


class TestF8Stage9WorkflowGraph:
    def test_f8_063_workflow_entrypoint_is_run_goal(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow().run(valid_goal())

        assert result.final_plan is not None or result.errors

    def test_f8_064_workflow_executes_f2_nodes_in_order(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        call_order = []

        result = PlannerWorkflow.with_spy(call_order=call_order).run(valid_goal())

        assert call_order[:6] == ["profile", "knowledge", "resource", "planner", "critic", "output"]
        assert result

    def test_f8_065_workflow_passes_state_between_nodes(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow().run(valid_goal())

        assert result.learner_profile is not None
        assert result.knowledge_points is not None
        assert result.draft_plan is not None

    def test_f8_066_workflow_enters_output_when_critic_passes(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(critic_agent=SpyNode("critic", output_key="review", output_value=type("Review", (), {"passed": True})())).run(valid_goal())

        assert result.final_plan is not None

    def test_f8_067_workflow_returns_to_planner_when_critic_fails(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakeCriticAgent = f8_attr("study_planner.agents.testing", "FakeCriticAgent")
        FakePlannerAgent = f8_attr("study_planner.agents.testing", "FakePlannerAgent")
        planner = FakePlannerAgent()

        PlannerWorkflow(planner_agent=planner, critic_agent=FakeCriticAgent(fail_first=True)).run(valid_goal())

        assert planner.call_count >= 2

    def test_f8_068_workflow_stops_after_max_repair_attempts(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakeCriticAgent = f8_attr("study_planner.agents.testing", "FakeCriticAgent")

        result = PlannerWorkflow(critic_agent=FakeCriticAgent(always_fail=True), max_repair_attempts=2).run(valid_goal())

        assert result.errors

    def test_f8_069_workflow_node_failure_enters_errors(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(knowledge_agent=SpyNode("knowledge", fail=True)).run(valid_goal())

        assert result.errors
        assert result.errors[0].node == "knowledge"

    def test_f8_070_workflow_can_skip_resource_node(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(use_resources=False).run(valid_goal())

        assert result.resources == []
        assert result.final_plan is not None

    def test_f8_071_workflow_result_is_traceable(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(debug=True).run(valid_goal())

        assert result.trace
        assert all("node" in item for item in result.trace)

    def test_f8_072_workflow_does_not_depend_on_helloagents(self):
        workflow_module = import_module("study_planner.agents.planner_workflow")

        assert "helloagents" not in repr(workflow_module.__dict__).lower()


class TestF8Stage10F2Integration:
    def test_f8_073_f2_can_generate_plan_via_planner_workflow(self):
        GenerateStudyPlanUseCase = f8_attr("study_planner.application.generate_study_plan", "GenerateStudyPlanUseCase")
        FakePlannerWorkflow = f8_attr("study_planner.agents.testing", "FakePlannerWorkflow")

        plan = GenerateStudyPlanUseCase(workflow=FakePlannerWorkflow(plan=valid_plan())).execute(valid_goal())

        assert isinstance(plan, StudyPlan)

    def test_f8_074_f2_keeps_fake_llm_tests_available(self):
        FakePlannerWorkflow = f8_attr("study_planner.agents.testing", "FakePlannerWorkflow")

        result = FakePlannerWorkflow(plan=valid_plan()).run(valid_goal())

        assert result.final_plan is not None

    def test_f8_075_f2_workflow_output_matches_existing_plan_contract(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        plan = PlannerWorkflow().run(valid_goal()).final_plan

        assert plan.phases
        assert plan.phases[0].weekly_plans
        assert all_tasks(plan)
        assert plan.time_budget
        assert plan.review_schedule

    def test_f8_076_f2_workflow_output_can_be_displayed_by_f3(self):
        build_dashboard_view = f8_attr("study_planner.application.plan_dashboard", "build_dashboard_view")
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        view = build_dashboard_view(PlannerWorkflow().run(valid_goal()).final_plan, today=CURRENT_DATE)

        assert view.is_empty is False
        assert view.task_rows

    def test_f8_077_f2_workflow_output_can_be_saved_by_f7(self):
        StorageService = f8_attr("study_planner.application.persistence", "StorageService")
        InMemoryStudyGoalRepository = f8_attr("study_planner.infrastructure.db.repositories", "InMemoryStudyGoalRepository")
        InMemoryStudyPlanRepository = f8_attr("study_planner.infrastructure.db.repositories", "InMemoryStudyPlanRepository")
        InMemoryTaskProgressRepository = f8_attr("study_planner.infrastructure.db.repositories", "InMemoryTaskProgressRepository")
        InMemoryReviewReportRepository = f8_attr("study_planner.infrastructure.db.repositories", "InMemoryReviewReportRepository")
        InMemoryMaterialRepository = f8_attr("study_planner.infrastructure.db.repositories", "InMemoryMaterialRepository")
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        service = StorageService(
            goal_repository=InMemoryStudyGoalRepository(),
            plan_repository=InMemoryStudyPlanRepository(),
            task_progress_repository=InMemoryTaskProgressRepository(),
            review_report_repository=InMemoryReviewReportRepository(),
            material_repository=InMemoryMaterialRepository(),
        )

        plan_id = service.save_study_plan(PlannerWorkflow().run(valid_goal()).final_plan)

        assert plan_id

    def test_f8_078_f2_workflow_failure_returns_readable_error(self):
        GenerateStudyPlanUseCase = f8_attr("study_planner.application.generate_study_plan", "GenerateStudyPlanUseCase")
        FakePlannerWorkflow = f8_attr("study_planner.agents.testing", "FakePlannerWorkflow")

        with pytest.raises(Exception, match="workflow|计划|生成"):
            GenerateStudyPlanUseCase(workflow=FakePlannerWorkflow(errors=["planner failed"])).execute(valid_goal())

    def test_f8_079_f2_application_layer_does_not_import_langgraph(self):
        module = import_module("study_planner.application.generate_study_plan")

        assert "langgraph" not in repr(module.__dict__).lower()


class TestF8Stage11F5Integration:
    def test_f8_080_f5_can_reuse_planner_workflow_for_replan(self):
        WorkflowReplanPlanner = f8_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")

        adjusted = WorkflowReplanPlanner(workflow=f8_attr("study_planner.agents.testing", "FakePlannerWorkflow")(plan=valid_plan())).replan(
            type("Request", (), {"original_plan": valid_plan(), "review_report": valid_review_report(), "remaining_tasks": []})()
        )

        assert isinstance(adjusted, StudyPlan)

    def test_f8_081_f5_replan_only_changes_unfinished_tasks(self):
        WorkflowReplanPlanner = f8_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        original = valid_plan()

        adjusted = WorkflowReplanPlanner().replan(
            type("Request", (), {"original_plan": original, "review_report": valid_review_report(), "remaining_tasks": [all_tasks(original)[1]]})()
        )

        assert all_tasks(adjusted)[0].status == "done"
        assert all_tasks(adjusted)[0].date == all_tasks(original)[0].date

    def test_f8_082_f5_replan_result_still_goes_through_critic(self):
        WorkflowReplanPlanner = f8_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        FakeCriticAgent = f8_attr("study_planner.agents.testing", "FakeCriticAgent")

        with pytest.raises(ValueError, match="critic|过载|可行"):
            WorkflowReplanPlanner(critic_agent=FakeCriticAgent(always_fail=True)).replan(
                type("Request", (), {"original_plan": valid_plan(), "review_report": valid_review_report(), "remaining_tasks": []})()
            )

    def test_f8_083_f5_replan_can_preview_diff(self):
        calculate_plan_diff = f8_attr("study_planner.application.review_replan", "calculate_plan_diff")
        original = valid_plan()
        adjusted = valid_plan(tasks=[make_task("task-1", status="done"), make_task("task-2", date=CURRENT_DATE + timedelta(days=3))])

        diff = calculate_plan_diff(original, adjusted)

        assert diff.rows

    def test_f8_084_f5_replan_failure_does_not_override_original_plan(self):
        generate_adjustment_preview = f8_attr("study_planner.application.review_replan", "generate_adjustment_preview")
        original = valid_plan()
        state = {"study_plan": original}

        with pytest.raises(Exception):
            generate_adjustment_preview(
                type("Request", (), {"original_plan": original, "review_report": valid_review_report()})(),
                planner=SpyNode("planner", fail=True),
                session_state=state,
            )

        assert state["study_plan"] == original
        assert "pending_adjusted_plan" not in state

    def test_f8_085_f5_review_metrics_use_real_plan_state(self):
        ProgressAgent = f8_attr("study_planner.agents.nodes.progress", "ProgressAgent")
        tasks = [make_task(f"task-{index}", status="done" if index == 1 else "todo") for index in range(1, 28)]

        context = ProgressAgent().run(valid_plan(tasks=tasks), current_date=CURRENT_DATE)

        assert context.completed_task_count == 1
        assert context.total_task_count == 27
        assert context.completion_rate == pytest.approx(1 / 27)

    def test_f8_086_f5_application_layer_does_not_import_langgraph(self):
        module = import_module("study_planner.application.review_replan")

        assert "langgraph" not in repr(module.__dict__).lower()


class TestF8Stage12ErrorsAndObservability:
    def test_f8_087_llm_timeout_enters_errors(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        TimeoutLLM = f8_attr("study_planner.agents.testing", "TimeoutLLM")

        result = PlannerWorkflow(llm=TimeoutLLM()).run(valid_goal())

        assert result.errors
        assert "timeout" in result.errors[0].message.lower()

    def test_f8_088_non_json_llm_response_enters_errors(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakeLLM = f8_attr("study_planner.agents.testing", "FakeLLM")

        result = PlannerWorkflow(llm=FakeLLM(response="plain text")).run(valid_goal())

        assert result.errors
        assert "json" in result.errors[0].message.lower() or "结构" in result.errors[0].message

    def test_f8_089_node_errors_do_not_leak_api_key(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        LeakyLLM = f8_attr("study_planner.agents.testing", "LeakyLLM")

        result = PlannerWorkflow(llm=LeakyLLM(secret="sk-secret")).run(valid_goal())

        assert result.errors
        assert "sk-secret" not in result.errors[0].message

    def test_f8_090_workflow_records_node_execution_order(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(debug=True).run(valid_goal())

        assert [item["node"] for item in result.trace][:2] == ["profile", "knowledge"]

    def test_f8_091_workflow_records_node_duration(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(debug=True).run(valid_goal())

        assert all("duration_ms" in item for item in result.trace)

    def test_f8_092_workflow_debug_mode_returns_intermediate_state(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(debug=True).run(valid_goal())

        assert result.debug_state
        assert "learner_profile" in result.debug_state

    def test_f8_093_workflow_does_not_expose_full_prompt_by_default(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(debug=False).run(valid_goal())

        assert "prompt" not in repr(result).lower()

    def test_f8_094_workflow_supports_retry_strategy(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FlakyLLM = f8_attr("study_planner.agents.testing", "FlakyLLM")

        result = PlannerWorkflow(llm=FlakyLLM(failures_before_success=1), max_retries=2).run(valid_goal())

        assert result.final_plan is not None
        assert result.retry_count == 1

    def test_f8_095_workflow_retry_count_has_limit(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FlakyLLM = f8_attr("study_planner.agents.testing", "FlakyLLM")

        result = PlannerWorkflow(llm=FlakyLLM(always_fail=True), max_retries=2).run(valid_goal())

        assert result.errors
        assert result.retry_count == 2


class TestF8Stage13ReplaceabilityAndDecoupling:
    def test_f8_096_can_replace_profile_agent(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow(profile_agent=SpyNode("profile", output_key="learner_profile", output_value={"level": "fake"})).run(valid_goal())

        assert result.learner_profile

    def test_f8_097_can_replace_planner_agent(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakePlannerAgent = f8_attr("study_planner.agents.testing", "FakePlannerAgent")

        result = PlannerWorkflow(planner_agent=FakePlannerAgent(always=valid_plan(goal=valid_goal(subject="替换计划")))).run(valid_goal())

        assert result.final_plan.goal.subject == "替换计划"

    def test_f8_098_can_replace_critic_agent(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")
        FakeCriticAgent = f8_attr("study_planner.agents.testing", "FakeCriticAgent")

        result = PlannerWorkflow(critic_agent=FakeCriticAgent(always_pass=True)).run(valid_goal())

        assert result.review.passed is True

    def test_f8_099_streamlit_pages_do_not_import_agent_nodes(self):
        pages = [
            "study_planner.interfaces.streamlit.pages.01_Goal_Setup",
            "study_planner.interfaces.streamlit.pages.02_Plan_Dashboard",
            "study_planner.interfaces.streamlit.pages.04_Review_Replan",
        ]

        for module_name in pages:
            module = import_module(module_name)
            assert "study_planner.agents.nodes" not in repr(module.__dict__)

    def test_f8_100_workflow_does_not_write_database_directly(self):
        module = import_module("study_planner.agents.planner_workflow")

        assert "Postgres" not in repr(module.__dict__)
        assert "psycopg" not in repr(module.__dict__)

    def test_f8_101_workflow_does_not_touch_streamlit_session_state(self):
        module = import_module("study_planner.agents.planner_workflow")

        assert "streamlit" not in repr(module.__dict__).lower()
        assert "session_state" not in repr(module.__dict__)


class TestF8Stage14RealLLMManualAcceptanceContracts:
    @pytest.mark.manual
    def test_f8_102_real_llm_can_complete_f2_workflow(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow.from_env(".env").run(valid_goal())

        assert isinstance(result.final_plan, StudyPlan)

    @pytest.mark.manual
    def test_f8_103_real_llm_result_goes_through_critic(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow.from_env(".env").run(valid_goal())

        assert result.review is not None

    @pytest.mark.manual
    def test_f8_104_real_llm_non_json_output_is_retried_or_reported(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow.from_env(".env", force_non_json_once=True).run(valid_goal())

        assert result.final_plan is not None or result.errors

    @pytest.mark.manual
    def test_f8_105_real_llm_can_complete_f5_replan_workflow(self):
        WorkflowReplanPlanner = f8_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        plan = valid_plan(tasks=[make_task("done", status="done"), make_task("todo", status="todo")])

        adjusted = WorkflowReplanPlanner.from_env(".env").replan(
            type("Request", (), {"original_plan": plan, "review_report": valid_review_report(), "remaining_tasks": [all_tasks(plan)[1]]})()
        )

        assert isinstance(adjusted, StudyPlan)
        assert all_tasks(adjusted)[0].status == "done"

    @pytest.mark.manual
    def test_f8_106_real_llm_cost_and_duration_are_observable(self):
        PlannerWorkflow = f8_attr("study_planner.agents.planner_workflow", "PlannerWorkflow")

        result = PlannerWorkflow.from_env(".env", debug=True).run(valid_goal())

        assert result.trace
        assert any("duration_ms" in item for item in result.trace)

    @pytest.mark.manual
    def test_f8_107_real_llm_failure_does_not_override_existing_plan(self):
        WorkflowReplanPlanner = f8_attr("study_planner.agents.planner_workflow", "WorkflowReplanPlanner")
        original = valid_plan()

        with pytest.raises(Exception):
            WorkflowReplanPlanner.from_env(".env", force_failure=True).replan(
                type("Request", (), {"original_plan": original, "review_report": valid_review_report(), "remaining_tasks": all_tasks(original)})()
            )

        assert original == valid_plan()
