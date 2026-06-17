"""shipready: rubric based ship-readiness evals for AI agents."""

from .grader import DEFAULT_MODEL, GradingError, grade, summarize
from .models import (
    Boundary,
    Criterion,
    CriterionGrade,
    Decision,
    EscalationEvent,
    Goal,
    GradingReport,
    Summary,
    TestCase,
    ToolCall,
    Workbook,
)
from .report import format_report, format_summary
from .workbook import WorkbookError, load_workbook

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "DEFAULT_MODEL",
    "GradingError",
    "grade",
    "summarize",
    "Boundary",
    "Criterion",
    "CriterionGrade",
    "Decision",
    "EscalationEvent",
    "Goal",
    "GradingReport",
    "Summary",
    "TestCase",
    "ToolCall",
    "Workbook",
    "format_report",
    "format_summary",
    "WorkbookError",
    "load_workbook",
]
