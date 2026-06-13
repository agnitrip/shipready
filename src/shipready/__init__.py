"""shipready: rubric based ship-readiness evals for AI agents."""

from .grader import DEFAULT_MODEL, GradingError, grade
from .models import (
    Boundary,
    Criterion,
    CriterionGrade,
    Goal,
    GradingReport,
    TestCase,
    Workbook,
)
from .report import format_report
from .workbook import WorkbookError, load_workbook

__version__ = "0.0.1"

__all__ = [
    "__version__",
    "DEFAULT_MODEL",
    "GradingError",
    "grade",
    "Boundary",
    "Criterion",
    "CriterionGrade",
    "Goal",
    "GradingReport",
    "TestCase",
    "Workbook",
    "format_report",
    "WorkbookError",
    "load_workbook",
]
