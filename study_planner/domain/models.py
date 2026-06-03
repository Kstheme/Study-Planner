from dataclasses import dataclass, field
from datetime import date
from datetime import datetime


@dataclass
class StudyGoal:
    """
    学习目标数据模型
    
    用于存储和管理用户的学习目标信息，包括学科、目标、截止日期等关键属性。
    
    Attributes:
        subject (str): 学习科目名称，例如"数学"、"英语"等
        target (str): 具体学习目标描述，例如"掌握微积分基础"、"通过英语四级考试"等
        deadline (date): 目标完成的截止日期
        current_level (str): 当前学习水平，例如"初级"、"中级"、"高级"等
        daily_available_minutes (int): 每日可用于学习的时间（分钟）
        weekly_available_days (int): 每周可用于学习的天数
        preferred_methods (list[str]): 偏好的学习方法列表，例如["视频课程", "做题练习", "阅读教材"]
        weak_points (list[str]): 薄弱知识点列表，需要重点加强的内容
        extra_requirements (str): 额外要求或备注信息，默认为空字符串
    """
    subject: str
    target: str
    deadline: date
    current_level: str
    daily_available_minutes: int
    weekly_available_days: int
    preferred_methods: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)
    extra_requirements: str = ""


@dataclass
class StudyTask:
    title: str
    date: date
    duration_minutes: int
    task_type: str
    related_topics: list[str] = field(default_factory=list)
    learning_method: str = ""
    expected_output: str = ""
    review_required: bool = False
    status: str = "todo"
    id: str = ""
    notes: str = ""


@dataclass
class WeeklyPlan:
    week_index: int
    start_date: date
    end_date: date
    objective: str
    tasks: list[StudyTask] = field(default_factory=list)
    review_focus: str = ""


@dataclass
class StudyPhase:
    phase_index: int
    title: str
    objective: str
    start_date: date
    end_date: date
    milestone: str
    weekly_plans: list[WeeklyPlan] = field(default_factory=list)


@dataclass
class TimeBudget:
    total_days: int
    total_weeks: int
    total_available_minutes: int
    planned_minutes: int
    daily_available_minutes: int
    weekly_available_days: int


@dataclass
class ReviewSchedule:
    daily_review_minutes: int
    weekly_review_day: str
    review_strategy: str


@dataclass
class StudyPlan:
    goal: StudyGoal
    overall_route: str
    phases: list[StudyPhase]
    methods: list[str]
    time_budget: TimeBudget
    risks: list[str]
    review_schedule: ReviewSchedule
    suggestions: str = ""


@dataclass
class LearningMaterial:
    id: str
    filename: str
    file_type: str
    source_path: str
    uploaded_at: datetime
    status: str
    chunk_count: int = 0
    error_message: str = ""
    raw_text: str = ""


@dataclass
class DocumentChunk:
    id: str
    material_id: str
    text: str
    source: str
    page_number: int | None = None
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunk: DocumentChunk
    score: float


@dataclass
class Citation:
    filename: str
    chunk_id: str
    snippet: str
    score: float
    material_id: str = ""
    page_number: int | None = None


@dataclass
class MaterialAnswer:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Flashcard:
    question: str
    answer: str


@dataclass
class KnowledgePoint:
    name: str
    description: str = ""
    prerequisites: list[str] = field(default_factory=list)
    difficulty: int = 1
    importance: int = 1
    mastery_level: int = 0
