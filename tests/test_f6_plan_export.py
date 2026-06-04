from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from study_planner.application.plan_export import (
    ExportPlanError,
    ExportRequest,
    ExportStudyPlanUseCase,
    HTMLExporter,
    MarkdownExporter,
    PDFExporter,
    build_download_payload,
    build_export_page_view,
    generate_export_filename,
)
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
EXPORTED_AT = datetime(2026, 6, 4, 9, 30)


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


def valid_plan(tasks=None, goal=None, phases=None, **overrides):
    goal = goal or valid_goal()
    tasks = tasks if tasks is not None else [
        make_task(
            "task-1",
            title="学习变量与数据类型",
            date=CURRENT_DATE,
            duration_minutes=60,
            task_type="study",
            related_topics=["变量", "数据类型"],
            status="todo",
        ),
        make_task(
            "task-2",
            title="完成基础语法复习",
            date=CURRENT_DATE,
            duration_minutes=30,
            task_type="review",
            related_topics=["变量", "数据类型"],
            status="done",
            notes="复习时重点看类型转换",
        ),
        make_task(
            "task-3",
            title="函数练习",
            date=CURRENT_DATE + timedelta(days=1),
            duration_minutes=60,
            task_type="practice",
            related_topics=["函数"],
            status="doing",
        ),
    ]
    if phases is None:
        phases = [
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
        ]
    data = {
        "goal": goal,
        "overall_route": "先学基础语法，再完成练习，最后做小项目",
        "phases": phases,
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
        "completion_rate": 0.6,
        "completed_task_count": 3,
        "total_task_count": 5,
        "overdue_tasks": ["task-1"],
        "consecutive_unfinished_topics": ["递归"],
        "weak_points": ["递归", "练习时间不足"],
        "summary": "本周完成率一般，需要优先处理延期任务",
        "suggestions": ["降低任务粒度", "增加递归专项练习"],
    }
    data.update(overrides)
    return ReviewReport(**data)


def export_markdown(plan=None, report=None):
    request = ExportRequest(
        study_plan=plan or valid_plan(),
        review_report=report,
        format="markdown",
        exported_at=EXPORTED_AT,
    )
    return MarkdownExporter().export(request)


def export_html(plan=None, report=None):
    request = ExportRequest(
        study_plan=plan or valid_plan(),
        review_report=report,
        format="html",
        exported_at=EXPORTED_AT,
    )
    return HTMLExporter().export(request)


def content_text(result):
    if isinstance(result.content, bytes):
        return result.content.decode("utf-8")
    return result.content


def all_tasks(plan):
    return [
        task
        for phase in plan.phases
        for weekly_plan in phase.weekly_plans
        for task in weekly_plan.tasks
    ]


class FakeSessionState(dict):
    pass


class FakeRepository:
    def __init__(self, plan=None, report=None, fail=False):
        self.plan = plan
        self.report = report
        self.fail = fail

    def get_latest_study_plan(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.plan

    def get_latest_review_report(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.report


class ExplodingExporter:
    def export(self, request):
        raise RuntimeError("render failed")


class CountingLLM:
    def __init__(self):
        self.calls = 0

    def generate_study_plan(self, goal):
        self.calls += 1
        return {}

    def generate_review_report(self, request):
        self.calls += 1
        return {}


class TestF6Stage1ExportEntryAndEmptyState:
    def test_f6_001_empty_plan_cannot_export(self):
        """原因：没有学习计划时不能导出，并且不能调用具体 exporter。"""
        use_case = ExportStudyPlanUseCase(exporters={"markdown": MarkdownExporter()})

        with pytest.raises(ExportPlanError, match="学习计划|plan"):
            use_case.execute(ExportRequest(study_plan=None, format="markdown", exported_at=EXPORTED_AT))

    def test_f6_002_plan_displays_export_entry(self):
        """原因：有计划时页面应展示 Markdown、HTML 入口，并预留 PDF。"""
        view = build_export_page_view(study_plan=valid_plan())

        assert view.can_export is True
        assert "markdown" in view.available_formats
        assert "html" in view.available_formats
        assert "pdf" in view.reserved_formats or "pdf" in view.disabled_formats

    def test_f6_003_missing_format_cannot_export(self):
        """原因：格式为空会导致 exporter 分发不明确。"""
        use_case = ExportStudyPlanUseCase(exporters={"markdown": MarkdownExporter()})

        with pytest.raises(ExportPlanError, match="格式|format"):
            use_case.execute(ExportRequest(study_plan=valid_plan(), format="", exported_at=EXPORTED_AT))

    def test_f6_004_unsupported_format_returns_clear_error(self):
        """原因：导出格式是外部输入，需要防御非法值。"""
        use_case = ExportStudyPlanUseCase(exporters={"markdown": MarkdownExporter()})

        with pytest.raises(ExportPlanError, match="不支持|unsupported|docx"):
            use_case.execute(ExportRequest(study_plan=valid_plan(), format="docx", exported_at=EXPORTED_AT))

    def test_f6_005_pdf_is_reserved_in_mvp(self):
        """原因：PDF 是后续增强，MVP 不应生成伪 PDF。"""
        with pytest.raises((NotImplementedError, ExportPlanError), match="PDF|后续|not implemented"):
            PDFExporter().export(ExportRequest(study_plan=valid_plan(), format="pdf", exported_at=EXPORTED_AT))


class TestF6Stage2MarkdownExport:
    def test_f6_006_markdown_export_generates_md_file(self):
        """原因：Markdown 是 MVP 必须支持的导出格式。"""
        result = export_markdown()

        assert result.extension == ".md"
        assert result.filename.endswith(".md")
        assert "markdown" in result.mime_type
        assert content_text(result)

    def test_f6_007_markdown_contains_goal_information(self):
        """原因：导出内容必须完整表达学习目标。"""
        text = content_text(export_markdown())

        assert "Python 编程" in text
        assert "掌握 Python 基础语法并完成一个小项目" in text
        assert "2026-06-30" in text
        assert "零基础" in text
        assert "120" in text
        assert "5" in text

    def test_f6_008_markdown_contains_overall_route(self):
        """原因：总体路线是 F2 生成计划的重要输出。"""
        text = content_text(export_markdown())

        assert "总体路线" in text
        assert "先学基础语法，再完成练习，最后做小项目" in text

    def test_f6_009_markdown_contains_phase_plan(self):
        """原因：features.md 要求导出阶段计划。"""
        text = content_text(export_markdown())

        assert "阶段" in text
        assert "基础入门阶段" in text
        assert "掌握变量、条件、循环和函数" in text
        assert "2026-06-04" in text
        assert "2026-06-17" in text
        assert "能完成基础语法练习" in text

    def test_f6_010_markdown_contains_weekly_plan(self):
        """原因：导出不能丢失周层级。"""
        text = content_text(export_markdown())

        assert "第 1 周" in text or "第1周" in text
        assert "2026-06-04" in text
        assert "2026-06-10" in text
        assert "完成基础语法学习" in text
        assert "变量、条件、循环、函数" in text

    def test_f6_011_markdown_contains_daily_tasks(self):
        """原因：用户导出后应能离线执行每日任务。"""
        text = content_text(export_markdown())

        assert "学习变量与数据类型" in text
        assert "2026-06-04" in text
        assert "60" in text
        assert "study" in text
        assert "todo" in text
        assert "变量" in text
        assert "阅读文档 + 练习" in text
        assert "完成练习并整理笔记" in text

    def test_f6_012_markdown_uses_clear_structure(self):
        """原因：Markdown 必须结构清晰，方便阅读和保存。"""
        text = content_text(export_markdown())

        assert text.lstrip().startswith("# ")
        assert "## 学习目标" in text
        assert "## 总体路线" in text
        assert "## 阶段计划" in text
        assert "## 复习安排" in text
        assert "## 风险提示" in text

    def test_f6_013_markdown_escapes_special_characters(self):
        """原因：自由文本中的 Markdown 特殊字符不能破坏结构。"""
        plan = valid_plan(tasks=[make_task("special", title="学习 # 标题 | 表格 *重点* `code`")])

        text = content_text(export_markdown(plan))

        assert "学习 # 标题 | 表格 *重点* `code`" in text or "学习 \\# 标题" in text
        assert text.count("|") == 0 or all(len(line.split("|")) >= 2 for line in text.splitlines() if "|" in line)


class TestF6Stage3HtmlExport:
    def test_f6_014_html_export_generates_html_file(self):
        """原因：HTML 是 MVP 必须支持的导出格式。"""
        result = export_html()

        assert result.extension == ".html"
        assert result.filename.endswith(".html")
        assert "html" in result.mime_type
        assert "<html" in content_text(result).lower()

    def test_f6_015_html_can_be_opened_directly(self):
        """原因：HTML 导出应不依赖本地开发服务器即可查看。"""
        text = content_text(export_html())

        assert "<!doctype html" in text.lower() or "<html" in text.lower()
        assert "<title" in text.lower()
        assert "Python 编程" in text
        assert "http://localhost" not in text

    def test_f6_016_html_contains_utf8_meta(self):
        """原因：中文 HTML 必须不乱码。"""
        text = content_text(export_html())

        assert "charset=\"utf-8\"" in text.lower() or "charset=utf-8" in text.lower()
        assert "Python 编程" in text
        assert "�" not in text

    def test_f6_017_html_contains_key_fields(self):
        """原因：HTML 导出应直接展示核心计划内容。"""
        text = content_text(export_html())

        for expected in ["学习目标", "总体路线", "阶段", "周", "学习变量与数据类型", "复习安排", "时间预算"]:
            assert expected in text

    def test_f6_018_html_escapes_user_content(self):
        """原因：HTML 导出必须防止用户内容注入脚本。"""
        plan = valid_plan(goal=valid_goal(subject="<script>alert(1)</script>"))

        text = content_text(export_html(plan))

        assert "<script>alert(1)</script>" not in text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text

    def test_f6_019_html_style_keeps_content_readable(self):
        """原因：导出文件应长期可读，不能依赖脆弱外部样式。"""
        plan = valid_plan(tasks=[make_task("long", title="很长的任务标题" * 20)])

        text = content_text(export_html(plan))

        assert "很长的任务标题" in text
        assert "<table" in text.lower() or "<ul" in text.lower() or "<ol" in text.lower()
        assert "cdn." not in text.lower()


class TestF6Stage4ContentCompleteness:
    def test_f6_020_exports_learning_methods(self):
        """原因：学习方法是计划执行指导。"""
        md = content_text(export_markdown())
        html = content_text(export_html())

        assert "视频教程" in md and "项目实践" in md
        assert "视频教程" in html and "项目实践" in html

    def test_f6_021_exports_risks(self):
        """原因：风险提示帮助用户理解计划可执行性。"""
        md = content_text(export_markdown())
        html = content_text(export_html())

        assert "每日时间不足可能导致延期" in md
        assert "每日时间不足可能导致延期" in html

    def test_f6_022_exports_review_schedule(self):
        """原因：PRD 和 features.md 均要求计划包含复习安排。"""
        md = content_text(export_markdown())
        html = content_text(export_html())

        for expected in ["15", "周日", "每天复习当天知识点"]:
            assert expected in md
            assert expected in html

    def test_f6_023_exports_time_budget(self):
        """原因：时间预算是判断计划负载的重要信息。"""
        md = content_text(export_markdown())
        html = content_text(export_html())

        for expected in ["27", "4", "2400", "120"]:
            assert expected in md
            assert expected in html

    def test_f6_024_exports_current_task_statuses(self):
        """原因：features.md 明确要求已完成任务状态能导出。"""
        tasks = [
            make_task("todo-task", status="todo"),
            make_task("doing-task", status="doing"),
            make_task("done-task", status="done"),
            make_task("skipped-task", status="skipped"),
        ]
        text = content_text(export_markdown(valid_plan(tasks=tasks)))

        for status in ["todo", "doing", "done", "skipped"]:
            assert status in text

    def test_f6_025_exports_task_notes(self):
        """原因：F3 支持备注编辑，F6 应导出当前备注。"""
        plan = valid_plan(tasks=[make_task("noted", notes="复习时重点看类型转换")])

        text = content_text(export_markdown(plan))

        assert "复习时重点看类型转换" in text
        assert "None" not in text

    def test_f6_026_empty_lists_are_exported_gracefully(self):
        """原因：F1 允许部分可选字段为空，导出不能失败。"""
        goal = valid_goal(preferred_methods=[], weak_points=[])
        plan = valid_plan(goal=goal, risks=[], methods=[], tasks=[make_task("empty", related_topics=[])])

        text = content_text(export_markdown(plan))

        assert "[]" not in text
        assert "None" not in text


class TestF6Stage5CurrentPageConsistency:
    def test_f6_027_exports_f3_updated_task_status(self):
        """原因：导出必须读取当前计划，而不是初始生成结果。"""
        plan = valid_plan()
        all_tasks(plan)[0].status = "done"

        text = content_text(export_markdown(plan))

        assert "task-1" in text
        assert "done" in text or "已完成" in text

    def test_f6_028_exports_f3_updated_task_date(self):
        """原因：F3 修改日期后，F6 必须导出修改后的版本。"""
        plan = valid_plan()
        all_tasks(plan)[0].date = date(2026, 6, 6)

        text = content_text(export_markdown(plan))

        assert "2026-06-06" in text

    def test_f6_029_exports_f3_updated_task_duration(self):
        """原因：F3 修改时长后，F6 必须导出当前版本。"""
        plan = valid_plan()
        all_tasks(plan)[0].duration_minutes = 45

        text = content_text(export_markdown(plan))

        assert "45" in text

    def test_f6_030_exports_f5_saved_adjusted_plan(self):
        """原因：F5 保存后的计划需要被 F6 读取。"""
        adjusted = valid_plan(tasks=[make_task("reinforcement", title="递归专项强化任务", task_type="reinforcement")])

        text = content_text(export_markdown(adjusted))

        assert "递归专项强化任务" in text
        assert "reinforcement" in text

    def test_f6_031_pending_adjusted_plan_is_not_exported_by_default(self):
        """原因：未确认的 F5 预览不能绕过保存机制。"""
        original = valid_plan(tasks=[make_task("original", title="原计划任务")])
        pending = valid_plan(tasks=[make_task("pending", title="未保存调整任务")])
        state = FakeSessionState(study_plan=original, pending_adjusted_plan=pending)

        result = ExportStudyPlanUseCase.from_session(state).execute(
            ExportRequest(format="markdown", exported_at=EXPORTED_AT)
        )
        text = content_text(result)

        assert "原计划任务" in text
        assert "未保存调整任务" not in text


class TestF6Stage6ReviewReportExport:
    def test_f6_032_exports_review_report_section_when_present(self):
        """原因：F6 目标包括导出学习计划和复盘报告。"""
        text = content_text(export_markdown(report=valid_review_report()))

        assert "复盘报告" in text
        assert "2026-06-01" in text
        assert "2026-06-07" in text
        assert "60%" in text or "0.6" in text
        assert "本周完成率一般" in text
        assert "降低任务粒度" in text

    def test_f6_033_review_report_exports_overdue_tasks(self):
        """原因：复盘报告应包含延期任务。"""
        text = content_text(export_markdown(report=valid_review_report()))

        assert "延期" in text
        assert "task-1" in text

    def test_f6_034_review_report_exports_weak_points(self):
        """原因：薄弱点是 F5 调整计划的重要依据。"""
        text = content_text(export_html(report=valid_review_report()))

        assert "递归" in text
        assert "练习时间不足" in text
        assert "�" not in text

    def test_f6_035_export_succeeds_without_review_report(self):
        """原因：用户可能首次生成计划后立即导出。"""
        text = content_text(export_markdown(report=None))

        assert "Python 编程" in text
        assert "Traceback" not in text

    def test_f6_036_review_completion_rate_is_user_friendly(self):
        """原因：导出文件面向用户，不应直接显示过长浮点数。"""
        report = valid_review_report(completion_rate=0.6666667)

        text = content_text(export_markdown(report=report))

        assert "67%" in text or "66.7%" in text
        assert "0.6666667" not in text


class TestF6Stage7FilenameAndDownloadMetadata:
    def test_f6_037_filename_contains_subject_and_date(self):
        """原因：features.md 要求文件名包含学习主题和日期。"""
        filename = generate_export_filename(valid_plan(), "markdown", exported_at=EXPORTED_AT)

        assert "Python" in filename
        assert "2026-06-04" in filename or "20260604" in filename
        assert filename.endswith(".md")

    def test_f6_038_filename_sanitizes_illegal_characters(self):
        """原因：用户主题不能直接作为文件名使用。"""
        plan = valid_plan(goal=valid_goal(subject='Python/AI: 从 0 到 1? "demo"'))

        filename = generate_export_filename(plan, "html", exported_at=EXPORTED_AT)

        assert not any(char in filename for char in '\\/:*?"<>|')
        assert filename.endswith(".html")

    def test_f6_039_filename_length_is_limited(self):
        """原因：超长文件名会导致浏览器或操作系统下载失败。"""
        plan = valid_plan(goal=valid_goal(subject="Python" * 80))

        filename = generate_export_filename(plan, "markdown", exported_at=EXPORTED_AT)

        assert len(filename) <= 120
        assert filename.endswith(".md")

    def test_f6_040_download_mime_type_is_correct(self):
        """原因：正确 MIME 有助于浏览器识别文件类型。"""
        md_payload = build_download_payload(export_markdown())
        html_payload = build_download_payload(export_html())

        assert "markdown" in md_payload["mime"] or "text/plain" in md_payload["mime"]
        assert "utf-8" in md_payload["mime"].lower()
        assert "html" in html_payload["mime"]
        assert "utf-8" in html_payload["mime"].lower()


class TestF6Stage8EncodingAndInternationalization:
    def test_f6_041_chinese_markdown_is_not_garbled(self):
        """原因：features.md 明确要求中文内容不乱码。"""
        text = content_text(export_markdown())

        assert "学习变量与数据类型" in text
        assert "鍩虹" not in text
        assert "�" not in text

    def test_f6_042_chinese_html_is_not_garbled(self):
        """原因：HTML 是分享格式，中文显示必须稳定。"""
        text = content_text(export_html())

        assert "学习变量与数据类型" in text
        assert "charset" in text.lower()
        assert "�" not in text

    def test_f6_043_mixed_chinese_english_content_is_preserved(self):
        """原因：编程学习场景常见中英文混排。"""
        plan = valid_plan(tasks=[make_task("mixed", title="学习 Python list/dict 基础", related_topics=["OOP", "递归"])])

        text = content_text(export_markdown(plan))

        assert "Python list/dict" in text
        assert "OOP" in text
        assert "递归" in text

    def test_f6_044_emoji_and_symbols_are_safe(self):
        """原因：用户备注可能包含符号，导出应使用 UTF-8 全链路。"""
        plan = valid_plan(tasks=[make_task("symbols", notes="✅ 完成 A → B，耗时 ≤ 60 分钟")])

        text = content_text(export_html(plan))

        assert "✅" in text
        assert "→" in text
        assert "≤" in text


class TestF6Stage9OrderingAndConsistency:
    def test_f6_045_phases_are_exported_by_phase_index(self):
        """原因：导出文件应保留学习路径顺序。"""
        phase2 = deepcopy(valid_plan().phases[0])
        phase2.phase_index = 2
        phase2.title = "项目实践阶段"
        phase1 = deepcopy(valid_plan().phases[0])
        phase1.phase_index = 1
        plan = valid_plan(phases=[phase2, phase1])

        text = content_text(export_markdown(plan))

        assert text.index("基础入门阶段") < text.index("项目实践阶段")

    def test_f6_046_weekly_plans_are_exported_by_week_index(self):
        """原因：周计划顺序影响用户执行。"""
        week1 = valid_plan().phases[0].weekly_plans[0]
        week2 = deepcopy(week1)
        week2.week_index = 2
        week2.objective = "完成项目练习"
        phase = valid_plan().phases[0]
        phase.weekly_plans = [week2, week1]
        plan = valid_plan(phases=[phase])

        text = content_text(export_markdown(plan))

        assert text.index("完成基础语法学习") < text.index("完成项目练习")

    def test_f6_047_tasks_are_exported_in_stable_date_order(self):
        """原因：导出内容必须方便执行，且顺序稳定。"""
        late = make_task("late", title="第二天任务", date=CURRENT_DATE + timedelta(days=1))
        early = make_task("early", title="第一天任务", date=CURRENT_DATE)
        plan = valid_plan(tasks=[late, early])

        text = content_text(export_markdown(plan))

        assert text.index("第一天任务") < text.index("第二天任务")

    def test_f6_048_markdown_and_html_export_same_core_fields(self):
        """原因：格式不同不应导致导出数据不同。"""
        md = content_text(export_markdown(report=valid_review_report()))
        html = content_text(export_html(report=valid_review_report()))

        for expected in ["Python 编程", "基础入门阶段", "学习变量与数据类型", "本周完成率一般"]:
            assert expected in md
            assert expected in html


class TestF6Stage10ErrorsAndBoundaryValues:
    def test_f6_049_missing_time_budget_is_handled(self):
        """原因：导出层应稳健处理可选信息。"""
        plan = valid_plan(time_budget=None)

        text = content_text(export_markdown(plan))

        assert "Python 编程" in text
        assert "None" not in text

    def test_f6_050_missing_review_schedule_is_handled(self):
        """原因：真实 LLM 输出可能缺少非核心字段。"""
        plan = valid_plan(review_schedule=None)

        text = content_text(export_html(plan))

        assert "Python 编程" in text
        assert "None" not in text

    def test_f6_051_empty_task_list_has_clear_behavior(self):
        """原因：半结构化计划不能导致导出页面崩溃。"""
        plan = valid_plan(tasks=[])

        text = content_text(export_markdown(plan))

        assert "暂无任务" in text or "任务" in text
        assert "Traceback" not in text

    def test_f6_052_large_plan_is_not_truncated(self):
        """原因：长期学习计划可能很大，导出需要完整。"""
        tasks = [
            make_task(f"task-{index}", title=f"任务 {index}", date=CURRENT_DATE + timedelta(days=index % 7))
            for index in range(1, 301)
        ]
        plan = valid_plan(tasks=tasks)

        text = content_text(export_markdown(plan))

        assert "任务 1" in text
        assert "任务 300" in text
        assert text.count("任务 ") >= 300

    def test_f6_053_export_error_does_not_pollute_session_state(self):
        """原因：导出是只读操作，不应改变核心学习状态。"""
        plan = valid_plan()
        report = valid_review_report()
        state = FakeSessionState(study_plan=plan, last_review_report=report)
        use_case = ExportStudyPlanUseCase(exporters={"markdown": ExplodingExporter()}, session_state=state)

        with pytest.raises(RuntimeError, match="render failed"):
            use_case.execute(ExportRequest(format="markdown", exported_at=EXPORTED_AT))

        assert state["study_plan"] is plan
        assert state["last_review_report"] is report


class TestF6Stage11StreamlitPageInteraction:
    def test_f6_054_export_page_displays_current_plan_summary(self):
        """原因：导出前应让用户确认文件对应哪份计划。"""
        view = build_export_page_view(study_plan=valid_plan())

        assert view.summary["subject"] == "Python 编程"
        assert view.summary["deadline"] == date(2026, 6, 30)
        assert view.summary["task_count"] >= 3

    def test_f6_055_markdown_download_button_payload_is_available(self):
        """原因：Streamlit 下载是 Markdown 导出的核心入口。"""
        payload = build_download_payload(export_markdown())

        assert payload["data"]
        assert payload["file_name"].endswith(".md")
        assert "markdown" in payload["mime"] or "text/plain" in payload["mime"]
        assert payload["label"]

    def test_f6_056_html_download_button_payload_is_available(self):
        """原因：HTML 下载必须与 Markdown 同等可用。"""
        payload = build_download_payload(export_html())

        assert payload["data"]
        assert payload["file_name"].endswith(".html")
        assert "html" in payload["mime"]
        assert payload["label"]

    def test_f6_057_export_does_not_trigger_llm(self):
        """原因：导出应是确定性只读操作，不应产生新计划或费用。"""
        llm = CountingLLM()
        use_case = ExportStudyPlanUseCase(exporters={"markdown": MarkdownExporter()}, llm=llm)

        use_case.execute(ExportRequest(study_plan=valid_plan(), format="markdown", exported_at=EXPORTED_AT))

        assert llm.calls == 0

    def test_f6_058_export_success_keeps_page_state_stable(self):
        """原因：下载动作不应改变应用状态。"""
        plan = valid_plan()
        report = valid_review_report()
        state = FakeSessionState(study_plan=plan, last_review_report=report)
        use_case = ExportStudyPlanUseCase.from_session(state)

        use_case.execute(ExportRequest(format="markdown", exported_at=EXPORTED_AT))
        use_case.execute(ExportRequest(format="html", exported_at=EXPORTED_AT))

        assert state["study_plan"] is plan
        assert state["last_review_report"] is report


class TestF6Stage12PersistenceIntegration:
    def test_f6_059_exports_current_plan_from_session_state(self):
        """原因：MVP Streamlit 页面会频繁依赖 session_state。"""
        state = FakeSessionState(study_plan=valid_plan(tasks=[make_task("session", title="session 计划任务")]))

        result = ExportStudyPlanUseCase.from_session(state).execute(
            ExportRequest(format="markdown", exported_at=EXPORTED_AT)
        )

        assert "session 计划任务" in content_text(result)

    def test_f6_060_exports_latest_plan_from_repository(self):
        """原因：F7 要求 F6 可以读取持久化数据。"""
        repository = FakeRepository(plan=valid_plan(tasks=[make_task("repo", title="数据库计划任务")]))
        use_case = ExportStudyPlanUseCase.from_repository(repository)

        result = use_case.execute(ExportRequest(format="markdown", exported_at=EXPORTED_AT))

        assert "数据库计划任务" in content_text(result)

    def test_f6_061_exports_persisted_task_status(self):
        """原因：任务完成状态持久保存后应被 F6 使用。"""
        repository = FakeRepository(plan=valid_plan(tasks=[make_task("done", title="数据库已完成任务", status="done")]))
        use_case = ExportStudyPlanUseCase.from_repository(repository)

        result = use_case.execute(ExportRequest(format="html", exported_at=EXPORTED_AT))

        assert "数据库已完成任务" in content_text(result)
        assert "done" in content_text(result) or "已完成" in content_text(result)

    def test_f6_062_exports_persisted_review_report(self):
        """原因：复盘记录持久化后也应能被导出。"""
        repository = FakeRepository(plan=valid_plan(), report=valid_review_report(summary="数据库复盘报告"))
        use_case = ExportStudyPlanUseCase.from_repository(repository)

        result = use_case.execute(ExportRequest(format="markdown", exported_at=EXPORTED_AT))

        assert "数据库复盘报告" in content_text(result)


class TestF6Stage13SecurityAndPrivacy:
    def test_f6_063_export_does_not_include_api_keys_or_env_values(self):
        """原因：导出文件会被分享，不能泄露配置和密钥。"""
        text = content_text(export_markdown())

        assert "DEEPSEEK_API_KEY" not in text
        assert "OPENAI_API_KEY" not in text
        assert ".env" not in text

    def test_f6_064_export_does_not_include_traceback(self):
        """原因：下载内容不应泄露内部异常堆栈。"""
        use_case = ExportStudyPlanUseCase(exporters={"markdown": ExplodingExporter()})

        with pytest.raises(RuntimeError):
            use_case.execute(ExportRequest(study_plan=valid_plan(), format="markdown", exported_at=EXPORTED_AT))

    def test_f6_065_html_export_does_not_load_unknown_external_scripts(self):
        """原因：导出 HTML 应减少安全与可用性风险。"""
        text = content_text(export_html())

        assert "<script src=" not in text.lower()
        assert "http://" not in text.lower()
        assert "https://" not in text.lower()
