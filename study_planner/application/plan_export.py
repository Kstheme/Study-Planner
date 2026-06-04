from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape as html_escape
import re
from typing import Any, Protocol

from study_planner.domain.models import ReviewReport, StudyPlan, StudyTask


class ExportPlanError(ValueError):
    pass


@dataclass
class ExportRequest:
    study_plan: StudyPlan | None = None
    review_report: ReviewReport | None = None
    format: str = ""
    exported_at: datetime | None = None


@dataclass
class ExportResult:
    filename: str
    content: str | bytes
    mime_type: str
    extension: str


@dataclass
class ExportPageView:
    can_export: bool
    empty_message: str = ""
    available_formats: list[str] = field(default_factory=list)
    reserved_formats: list[str] = field(default_factory=list)
    disabled_formats: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.can_export

    @property
    def can_export_markdown(self) -> bool:
        return "markdown" in self.available_formats

    @property
    def can_export_html(self) -> bool:
        return "html" in self.available_formats


@dataclass
class ExportExperienceView:
    preview_html: str
    format_guidance: dict[str, str]


class Exporter(Protocol):
    def export(self, request: ExportRequest) -> ExportResult:
        ...


def _exported_at(request: ExportRequest) -> datetime:
    return request.exported_at or datetime.now()


def _format_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _safe_text(value: Any, default: str = "暂无") -> str:
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _join_list(values: list[Any] | tuple[Any, ...] | set[Any] | None, default: str = "暂无") -> str:
    if not values:
        return default
    return "、".join(str(value) for value in values if str(value)) or default


def _status_label(status: str) -> str:
    labels = {
        "todo": "todo 未开始",
        "doing": "doing 进行中",
        "done": "done 已完成",
        "skipped": "skipped 已跳过",
    }
    return labels.get(status, status)


def _all_tasks(plan: StudyPlan) -> list[StudyTask]:
    return [task for phase in plan.phases for week in phase.weekly_plans for task in week.tasks]


def _sorted_phases(plan: StudyPlan):
    return sorted(plan.phases, key=lambda phase: phase.phase_index)


def _sorted_weeks(phase):
    return sorted(phase.weekly_plans, key=lambda week: week.week_index)


def _sorted_tasks(week):
    return sorted(week.tasks, key=lambda task: (_format_date(task.date), task.id, task.title))


def _escape_md_cell(value: Any) -> str:
    text = _safe_text(value, "")
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("#", "\\#").replace("\n", " ")


def _extension_for_format(format_name: str) -> str:
    normalized = _normalize_format(format_name)
    if normalized == "markdown":
        return ".md"
    if normalized == "html":
        return ".html"
    if normalized == "pdf":
        return ".pdf"
    return f".{normalized}"


def _normalize_format(format_name: str) -> str:
    normalized = (format_name or "").strip().lower()
    aliases = {"md": "markdown", ".md": "markdown", "htm": "html", ".html": "html", ".pdf": "pdf"}
    return aliases.get(normalized, normalized)


def generate_export_filename(plan: StudyPlan, format: str, exported_at: datetime | None = None) -> str:
    when = exported_at or datetime.now()
    extension = _extension_for_format(format)
    subject = _safe_text(getattr(plan.goal, "subject", "study-plan"), "study-plan")
    subject = re.sub(r'[\\/:*?"<>|]+', "-", subject)
    subject = re.sub(r"\s+", "-", subject).strip(".-_ ") or "study-plan"
    date_part = when.date().isoformat()
    max_subject_len = max(10, 120 - len(date_part) - len(extension) - 2)
    subject = subject[:max_subject_len].rstrip(".-_ ") or "study-plan"
    return f"{subject}-{date_part}{extension}"


class MarkdownExporter:
    mime_type = "text/markdown; charset=utf-8"
    extension = ".md"

    def export(self, request: ExportRequest | StudyPlan) -> ExportResult | str:
        return_content_only = isinstance(request, StudyPlan)
        if return_content_only:
            request = ExportRequest(study_plan=request, format="markdown")
        plan = _require_plan(request.study_plan)
        lines: list[str] = []
        lines.append(f"# {_safe_text(plan.goal.subject)} 学习计划")
        lines.append("")
        lines.extend(_markdown_goal(plan))
        lines.extend(_markdown_time_budget(plan))
        lines.extend(_markdown_section("总体路线", [_safe_text(plan.overall_route)]))
        lines.extend(_markdown_section("学习方法", [_join_list(plan.methods)]))
        lines.extend(_markdown_phases(plan))
        lines.extend(_markdown_review_schedule(plan))
        lines.extend(_markdown_section("风险提示", plan.risks or ["暂无"]))
        lines.extend(_markdown_section("建议", [_safe_text(plan.suggestions)]))
        lines.extend(_markdown_review_report(request.review_report))
        content = "\n".join(lines).rstrip() + "\n"
        result = ExportResult(
            filename=generate_export_filename(plan, "markdown", _exported_at(request)),
            content=content,
            mime_type=self.mime_type,
            extension=self.extension,
        )
        return result.content if return_content_only else result


class HTMLExporter:
    mime_type = "text/html; charset=utf-8"
    extension = ".html"

    def export(self, request: ExportRequest | StudyPlan) -> ExportResult | str:
        return_content_only = isinstance(request, StudyPlan)
        if return_content_only:
            request = ExportRequest(study_plan=request, format="html")
        plan = _require_plan(request.study_plan)
        title = f"{_safe_text(plan.goal.subject)} 学习计划"
        body: list[str] = []
        body.append(_html_report_header(plan, request.review_report, _exported_at(request)))
        body.append(_html_goal(plan))
        body.append(_html_time_budget(plan))
        body.append(_html_section("总体路线", [plan.overall_route]))
        body.append(_html_section("学习方法", plan.methods or ["暂无"]))
        body.append(_html_phases(plan))
        body.append(_html_review_schedule(plan))
        body.append(_html_section("风险提示", plan.risks or ["暂无"]))
        body.append(_html_section("建议", [plan.suggestions or "暂无"]))
        body.append(_html_review_report(request.review_report))
        body.append('<p class="report-footer">由 Study Planner 导出。此文件为当前已确认学习计划的离线快照。</p>')
        style = _html_report_style()
        content = (
            "<!doctype html>\n"
            "<html lang=\"zh-CN\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            f"  <title>{html_escape(title)}</title>\n"
            f"  <style>{style}</style>\n"
            "</head>\n"
            "<body>\n"
            "<main class=\"report-shell\">\n"
            + "\n".join(body)
            + "\n</main>\n</body>\n</html>\n"
        )
        result = ExportResult(
            filename=generate_export_filename(plan, "html", _exported_at(request)),
            content=content,
            mime_type=self.mime_type,
            extension=self.extension,
        )
        return result.content if return_content_only else result


class PDFExporter:
    def export(self, request: ExportRequest) -> ExportResult:
        raise ExportPlanError("PDF 导出后续支持 / PDF export not implemented")


class ExportStudyPlanUseCase:
    def __init__(
        self,
        exporters: dict[str, Exporter] | None = None,
        session_state: dict | None = None,
        repository: Any | None = None,
        llm: Any | None = None,
    ):
        self._return_content_only = exporters is not None and not isinstance(exporters, dict)
        if exporters is not None and not isinstance(exporters, dict):
            exporters = {"markdown": exporters}
        self.exporters = exporters or {
            "markdown": MarkdownExporter(),
            "html": HTMLExporter(),
            "pdf": PDFExporter(),
        }
        self.session_state = session_state
        self.repository = repository
        self.llm = llm

    @classmethod
    def from_session(cls, session_state: dict):
        return cls(session_state=session_state)

    @classmethod
    def from_repository(cls, repository: Any):
        return cls(repository=repository)

    def execute(self, request: ExportRequest) -> ExportResult | str:
        format_name = _normalize_format(request.format or ("markdown" if self._return_content_only else ""))
        if not format_name:
            raise ExportPlanError("导出格式不能为空 / export format is required")
        exporter = self.exporters.get(format_name)
        if exporter is None:
            raise ExportPlanError(f"不支持的导出格式 / unsupported export format: {request.format}")

        resolved = ExportRequest(
            study_plan=request.study_plan or self._load_plan(),
            review_report=request.review_report if request.review_report is not None else self._load_report(),
            format=format_name,
            exported_at=request.exported_at,
        )
        _require_plan(resolved.study_plan)
        result = exporter.export(resolved)
        if self._return_content_only and isinstance(result, ExportResult):
            return result.content
        return result

    def _load_plan(self) -> StudyPlan | None:
        if self.session_state is not None:
            return self.session_state.get("study_plan")
        if self.repository is not None and hasattr(self.repository, "get_latest_study_plan"):
            return self.repository.get_latest_study_plan()
        return None

    def _load_report(self) -> ReviewReport | None:
        if self.session_state is not None:
            return self.session_state.get("last_review_report") or self.session_state.get("pending_review_report")
        if self.repository is not None and hasattr(self.repository, "get_latest_review_report"):
            return self.repository.get_latest_review_report()
        return None


def build_export_page_view(study_plan: StudyPlan | None) -> ExportPageView:
    if study_plan is None:
        return ExportPageView(can_export=False, empty_message="请先生成学习计划")
    return ExportPageView(
        can_export=True,
        available_formats=["markdown", "html"],
        reserved_formats=["pdf"],
        disabled_formats=["pdf"],
        summary={
            "subject": study_plan.goal.subject,
            "deadline": study_plan.goal.deadline,
            "phase_count": len(study_plan.phases),
            "task_count": len(_all_tasks(study_plan)),
        },
    )


def build_export_experience_view(study_plan: StudyPlan | None) -> ExportExperienceView:
    preview_html = HTMLExporter().export(study_plan) if study_plan is not None else ""
    return ExportExperienceView(
        preview_html=preview_html,
        format_guidance={
            "markdown": "适合继续编辑和复制到笔记工具。",
            "html": "适合直接打开、打印和分享。",
            "pdf": "预留格式，后续支持。",
        },
    )


def build_download_payload(result: ExportResult) -> dict[str, Any]:
    label_format = result.extension.lstrip(".").upper()
    return {
        "label": f"下载 {label_format}",
        "data": result.content,
        "file_name": result.filename,
        "mime": result.mime_type,
    }


def _require_plan(plan: StudyPlan | None) -> StudyPlan:
    if plan is None:
        raise ExportPlanError("需要先生成学习计划 / study plan is required")
    return plan


def _markdown_goal(plan: StudyPlan) -> list[str]:
    goal = plan.goal
    return [
        "## 学习目标",
        "",
        f"- 学习主题：{_safe_text(goal.subject)}",
        f"- 目标描述：{_safe_text(goal.target)}",
        f"- 截止日期：{_format_date(goal.deadline)}",
        f"- 当前水平：{_safe_text(goal.current_level)}",
        f"- 每日学习时间：{goal.daily_available_minutes} 分钟",
        f"- 每周学习天数：{goal.weekly_available_days} 天",
        f"- 学习偏好：{_join_list(goal.preferred_methods)}",
        f"- 薄弱点：{_join_list(goal.weak_points)}",
        f"- 额外要求：{_safe_text(goal.extra_requirements)}",
        "",
    ]


def _markdown_time_budget(plan: StudyPlan) -> list[str]:
    budget = plan.time_budget
    if budget is None:
        return ["## 时间预算", "", "暂无时间预算", ""]
    return [
        "## 时间预算",
        "",
        f"- 总天数：{budget.total_days}",
        f"- 总周数：{budget.total_weeks}",
        f"- 总可用分钟数：{budget.total_available_minutes}",
        f"- 计划任务分钟数：{budget.planned_minutes}",
        f"- 每日可学习分钟数：{budget.daily_available_minutes}",
        f"- 每周可学习天数：{budget.weekly_available_days}",
        "",
    ]


def _markdown_section(title: str, items: list[Any]) -> list[str]:
    lines = [f"## {title}", ""]
    for item in items or ["暂无"]:
        lines.append(f"- {_safe_text(item)}")
    lines.append("")
    return lines


def _markdown_phases(plan: StudyPlan) -> list[str]:
    lines = ["## 阶段计划", ""]
    for phase in _sorted_phases(plan):
        lines.extend(
            [
                f"### 阶段 {phase.phase_index}：{_safe_text(phase.title)}",
                "",
                f"- 阶段目标：{_safe_text(phase.objective)}",
                f"- 阶段时间：{_format_date(phase.start_date)} 至 {_format_date(phase.end_date)}",
                f"- 里程碑：{_safe_text(phase.milestone)}",
                "",
            ]
        )
        for week in _sorted_weeks(phase):
            lines.extend(
                [
                    f"#### 第 {week.week_index} 周",
                    "",
                    f"- 周时间：{_format_date(week.start_date)} 至 {_format_date(week.end_date)}",
                    f"- 周目标：{_safe_text(week.objective)}",
                    f"- 复习重点：{_safe_text(week.review_focus)}",
                    "",
                ]
            )
            tasks = _sorted_tasks(week)
            if not tasks:
                lines.extend(["暂无任务", ""])
                continue
            lines.extend(
                [
                    "| 任务ID | 任务 | 日期 | 时长 | 类型 | 状态 | 知识点 | 学习方法 | 预期产出 | 备注 |",
                    "| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for task in tasks:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _escape_md_cell(task.id),
                            _escape_md_cell(task.title),
                            _escape_md_cell(_format_date(task.date)),
                            _escape_md_cell(task.duration_minutes),
                            _escape_md_cell(task.task_type),
                            _escape_md_cell(_status_label(task.status)),
                            _escape_md_cell(_join_list(task.related_topics)),
                            _escape_md_cell(task.learning_method),
                            _escape_md_cell(task.expected_output),
                            _escape_md_cell(task.notes),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    return lines


def _markdown_review_schedule(plan: StudyPlan) -> list[str]:
    schedule = plan.review_schedule
    if schedule is None:
        return ["## 复习安排", "", "暂无复习安排", ""]
    return [
        "## 复习安排",
        "",
        f"- 每日复习：{schedule.daily_review_minutes} 分钟",
        f"- 每周复习日：{_safe_text(schedule.weekly_review_day)}",
        f"- 复习策略：{_safe_text(schedule.review_strategy)}",
        "",
    ]


def _markdown_review_report(report: ReviewReport | None) -> list[str]:
    if report is None:
        return ["## 复盘报告", "", "暂无复盘报告", ""]
    return [
        "## 复盘报告",
        "",
        f"- 复盘周期：{_format_date(report.period_start)} 至 {_format_date(report.period_end)}",
        f"- 完成率：{_format_percent(report.completion_rate)}",
        f"- 已完成任务：{report.completed_task_count}",
        f"- 总任务数：{report.total_task_count}",
        f"- 延期任务：{_join_list(report.overdue_tasks)}",
        f"- 连续未完成知识点：{_join_list(report.consecutive_unfinished_topics)}",
        f"- 薄弱点：{_join_list(report.weak_points)}",
        f"- 总结：{_safe_text(report.summary)}",
        f"- 建议：{_join_list(report.suggestions)}",
        "",
    ]


def _format_percent(value: float) -> str:
    percent = value * 100
    if abs(percent - round(percent)) < 0.05:
        return f"{percent:.0f}%"
    return f"{percent:.1f}%"


def _html_report_style() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #667085;
  --line: #d8dee9;
  --soft-line: #e8edf5;
  --paper: #ffffff;
  --canvas: #f4f7fb;
  --accent: #2563eb;
  --accent-ink: #173d8f;
  --accent-soft: #eaf1ff;
  --green: #0f766e;
  --green-soft: #e8f7f4;
  --amber: #b45309;
  --amber-soft: #fff4df;
  --red: #b42318;
  --red-soft: #fff0ed;
  --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
  line-height: 1.58;
  color: var(--ink);
  background: var(--canvas);
}
.report-shell {
  max-width: 1120px;
  margin: 0 auto;
  padding: 36px 28px 56px;
}
.hero {
  color: #fff;
  border-radius: 18px;
  padding: 34px 38px;
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.96), rgba(15, 118, 110, 0.92)),
    #2563eb;
  box-shadow: var(--shadow);
}
.eyebrow {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.86;
}
h1 {
  margin: 0;
  font-size: 34px;
  line-height: 1.18;
  letter-spacing: 0;
}
.hero-subtitle {
  max-width: 760px;
  margin: 12px 0 0;
  color: rgba(255, 255, 255, 0.88);
  font-size: 15px;
}
.hero-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 28px;
}
.metric {
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.13);
}
.metric-label {
  display: block;
  color: rgba(255, 255, 255, 0.76);
  font-size: 12px;
}
.metric-value {
  display: block;
  margin-top: 4px;
  font-size: 18px;
  font-weight: 750;
}
section {
  margin: 22px 0;
  padding: 24px 26px;
  border: 1px solid var(--soft-line);
  border-radius: 16px;
  background: var(--paper);
  box-shadow: 0 8px 26px rgba(15, 23, 42, 0.045);
}
h2 {
  margin: 0 0 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--soft-line);
  color: #111827;
  font-size: 20px;
  letter-spacing: 0;
}
h3 {
  margin: 24px 0 10px;
  color: var(--accent-ink);
  font-size: 18px;
}
h4 {
  margin: 18px 0 10px;
  color: #344054;
  font-size: 15px;
}
p { margin: 8px 0; }
ul {
  margin: 0;
  padding-left: 20px;
}
li + li { margin-top: 6px; }
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.kv-item {
  min-height: 70px;
  padding: 12px 14px;
  border: 1px solid var(--soft-line);
  border-radius: 12px;
  background: #fbfcff;
}
.kv-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.kv-value {
  margin-top: 5px;
  word-break: break-word;
}
.phase-card {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff, #fbfdff);
}
.phase-meta, .week-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 14px;
}
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font-size: 12px;
  font-weight: 700;
}
.week-block {
  margin-top: 16px;
  padding: 14px;
  border-radius: 12px;
  background: #f8fafc;
}
.table-wrap {
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 920px;
}
th, td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--soft-line);
  text-align: left;
  vertical-align: top;
  word-break: break-word;
}
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #eef3fb;
  color: #344054;
  font-size: 12px;
  font-weight: 800;
}
tbody tr:nth-child(even) { background: #fafcff; }
tbody tr:last-child td { border-bottom: 0; }
.status {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.status-todo { background: #eef2ff; color: #3730a3; }
.status-doing { background: var(--amber-soft); color: var(--amber); }
.status-done { background: var(--green-soft); color: var(--green); }
.status-skipped { background: var(--red-soft); color: var(--red); }
.empty {
  padding: 14px 16px;
  border: 1px dashed var(--line);
  border-radius: 12px;
  color: var(--muted);
  background: #fbfcff;
}
.report-footer {
  margin-top: 28px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}
@media (max-width: 760px) {
  .report-shell { padding: 18px 12px 32px; }
  .hero { padding: 24px 22px; border-radius: 14px; }
  h1 { font-size: 26px; }
  .hero-meta, .kv-grid { grid-template-columns: 1fr; }
  section { padding: 18px; border-radius: 14px; }
}
@media print {
  body { background: #fff; }
  .report-shell { max-width: none; padding: 0; }
  .hero, section { box-shadow: none; break-inside: avoid; }
  .table-wrap { overflow: visible; }
  th { position: static; }
}
""".strip()


def _html_report_header(plan: StudyPlan, report: ReviewReport | None, exported_at: datetime) -> str:
    phase_count = len(plan.phases)
    task_count = len(_all_tasks(plan))
    completed_count = sum(1 for task in _all_tasks(plan) if task.status == "done")
    report_text = "包含复盘报告" if report is not None else "暂无复盘报告"
    return (
        '<header class="hero">'
        '<p class="eyebrow">Study Planner Export</p>'
        f"<h1>{html_escape(_safe_text(plan.goal.subject))} 学习计划</h1>"
        f'<p class="hero-subtitle">{html_escape(_safe_text(plan.goal.target))}</p>'
        '<div class="hero-meta">'
        f'{_html_metric("导出日期", _format_date(exported_at))}'
        f'{_html_metric("截止日期", _format_date(plan.goal.deadline))}'
        f'{_html_metric("阶段 / 任务", f"{phase_count} / {task_count}")}'
        f'{_html_metric("已完成", f"{completed_count} 个")}'
        f'{_html_metric("每日学习", f"{plan.goal.daily_available_minutes} 分钟")}'
        f'{_html_metric("每周学习", f"{plan.goal.weekly_available_days} 天")}'
        f'{_html_metric("当前水平", _safe_text(plan.goal.current_level))}'
        f'{_html_metric("复盘状态", report_text)}'
        "</div>"
        "</header>"
    )


def _html_metric(label: str, value: Any) -> str:
    return (
        '<div class="metric">'
        f'<span class="metric-label">{html_escape(label)}</span>'
        f'<span class="metric-value">{html_escape(_safe_text(value))}</span>'
        "</div>"
    )


def _html_section(title: str, items: list[Any]) -> str:
    lis = "".join(f"<li>{html_escape(_safe_text(item))}</li>" for item in (items or ["暂无"]))
    return f"<section><h2>{html_escape(title)}</h2><ul>{lis}</ul></section>"


def _html_goal(plan: StudyPlan) -> str:
    goal = plan.goal
    rows = [
        ("学习主题", goal.subject),
        ("目标描述", goal.target),
        ("截止日期", _format_date(goal.deadline)),
        ("当前水平", goal.current_level),
        ("每日学习时间", f"{goal.daily_available_minutes} 分钟"),
        ("每周学习天数", f"{goal.weekly_available_days} 天"),
        ("学习偏好", _join_list(goal.preferred_methods)),
        ("薄弱点", _join_list(goal.weak_points)),
        ("额外要求", goal.extra_requirements),
    ]
    return _html_key_value_table("学习目标", rows)


def _html_time_budget(plan: StudyPlan) -> str:
    budget = plan.time_budget
    if budget is None:
        return "<section><h2>时间预算</h2><p>暂无时间预算</p></section>"
    return _html_key_value_table(
        "时间预算",
        [
            ("总天数", budget.total_days),
            ("总周数", budget.total_weeks),
            ("总可用分钟数", budget.total_available_minutes),
            ("计划任务分钟数", budget.planned_minutes),
            ("每日可学习分钟数", budget.daily_available_minutes),
            ("每周可学习天数", budget.weekly_available_days),
        ],
    )


def _html_key_value_table(title: str, rows: list[tuple[str, Any]]) -> str:
    body = "".join(
        '<div class="kv-item">'
        f'<div class="kv-label">{html_escape(str(key))}</div>'
        f'<div class="kv-value">{html_escape(_safe_text(value))}</div>'
        "</div>"
        for key, value in rows
    )
    return f'<section><h2>{html_escape(title)}</h2><div class="kv-grid">{body}</div></section>'


def _html_phases(plan: StudyPlan) -> str:
    parts = ["<section><h2>阶段计划</h2>"]
    for phase in _sorted_phases(plan):
        parts.append('<div class="phase-card">')
        parts.append(f"<h3>阶段 {phase.phase_index}：{html_escape(_safe_text(phase.title))}</h3>")
        parts.append(
            '<div class="phase-meta">'
            f'<span class="pill">阶段时间：{html_escape(_format_date(phase.start_date))} 至 {html_escape(_format_date(phase.end_date))}</span>'
            f'<span class="pill">里程碑：{html_escape(_safe_text(phase.milestone))}</span>'
            "</div>"
            f"<p><strong>阶段目标：</strong>{html_escape(_safe_text(phase.objective))}</p>"
        )
        for week in _sorted_weeks(phase):
            parts.append('<div class="week-block">')
            parts.append(f"<h4>第 {week.week_index} 周</h4>")
            parts.append(
                '<div class="week-meta">'
                f'<span class="pill">周时间：{html_escape(_format_date(week.start_date))} 至 {html_escape(_format_date(week.end_date))}</span>'
                f'<span class="pill">复习重点：{html_escape(_safe_text(week.review_focus))}</span>'
                "</div>"
                f"<p><strong>周目标：</strong>{html_escape(_safe_text(week.objective))}</p>"
            )
            tasks = _sorted_tasks(week)
            if not tasks:
                parts.append('<p class="empty">暂无任务</p>')
                parts.append("</div>")
                continue
            parts.append(
                '<div class="table-wrap"><table><thead><tr>'
                "<th>任务ID</th><th>任务</th><th>日期</th><th>时长</th><th>类型</th><th>状态</th>"
                "<th>知识点</th><th>学习方法</th><th>预期产出</th><th>备注</th>"
                "</tr></thead><tbody>"
            )
            for task in tasks:
                cells = [
                    task.id,
                    task.title,
                    _format_date(task.date),
                    task.duration_minutes,
                    task.task_type,
                    _html_status(task.status),
                    _join_list(task.related_topics),
                    task.learning_method,
                    task.expected_output,
                    task.notes,
                ]
                parts.append("<tr>" + "".join(_html_task_cell(cell) for cell in cells) + "</tr>")
            parts.append("</tbody></table></div>")
            parts.append("</div>")
        parts.append("</div>")
    parts.append("</section>")
    return "\n".join(parts)


def _html_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    class_name = {
        "todo": "status-todo",
        "doing": "status-doing",
        "done": "status-done",
        "skipped": "status-skipped",
    }.get(normalized, "status-todo")
    return f'<span class="status {class_name}">{html_escape(_status_label(status))}</span>'


def _html_task_cell(value: Any) -> str:
    text = _safe_text(value, "")
    if text.startswith('<span class="status '):
        return f"<td>{text}</td>"
    return f"<td>{html_escape(text)}</td>"


def _html_review_schedule(plan: StudyPlan) -> str:
    schedule = plan.review_schedule
    if schedule is None:
        return "<section><h2>复习安排</h2><p>暂无复习安排</p></section>"
    return _html_key_value_table(
        "复习安排",
        [
            ("每日复习", f"{schedule.daily_review_minutes} 分钟"),
            ("每周复习日", schedule.weekly_review_day),
            ("复习策略", schedule.review_strategy),
        ],
    )


def _html_review_report(report: ReviewReport | None) -> str:
    if report is None:
        return "<section><h2>复盘报告</h2><p>暂无复盘报告</p></section>"
    return _html_key_value_table(
        "复盘报告",
        [
            ("复盘周期", f"{_format_date(report.period_start)} 至 {_format_date(report.period_end)}"),
            ("完成率", _format_percent(report.completion_rate)),
            ("已完成任务", report.completed_task_count),
            ("总任务数", report.total_task_count),
            ("延期任务", _join_list(report.overdue_tasks)),
            ("连续未完成知识点", _join_list(report.consecutive_unfinished_topics)),
            ("薄弱点", _join_list(report.weak_points)),
            ("总结", report.summary),
            ("建议", _join_list(report.suggestions)),
        ],
    )

