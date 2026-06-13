"""Pydantic models for shipready workbooks and grading reports.

A workbook is the rubric for one agent. It has four parts:

    goals       what the agent is for
    boundaries  what the agent must not do
    framework   the grading criteria (each scored pass or fail)
    data_set    the test cases to grade against

A grading report is the result of grading one candidate output for one test
case against the workbook framework.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


def _require_unique_ids(items, label):
    """Raise if any two items in a list share an id."""
    seen = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"duplicate {label} id: {item.id!r}")
        seen.add(item.id)


class Goal(BaseModel):
    """One thing the agent is supposed to accomplish."""

    id: str
    description: str
    sub_goals: List[str] = Field(default_factory=list)


class Boundary(BaseModel):
    """A line the agent must not cross. Informs grading, not scored directly."""

    id: str
    name: str
    what_it_means: str
    example: Optional[str] = None


class Criterion(BaseModel):
    """One graded dimension. Every criterion resolves to pass or fail."""

    id: str
    criterion: str
    grades_what: str
    pass_label: str
    fail_label: str


class TestCase(BaseModel):
    """One input the agent is expected to handle, plus the target behavior."""

    id: str
    input: str
    expected_behavior: str
    notes: Optional[str] = None


class Workbook(BaseModel):
    """The full per-agent rubric loaded from a YAML file."""

    agent_name: str
    description: str
    goals: List[Goal] = Field(default_factory=list)
    boundaries: List[Boundary] = Field(default_factory=list)
    framework: List[Criterion]
    data_set: List[TestCase]

    @model_validator(mode="after")
    def _validate(self) -> "Workbook":
        if not self.framework:
            raise ValueError("framework must define at least one criterion")
        if not self.data_set:
            raise ValueError("data_set must define at least one test case")
        _require_unique_ids(self.goals, "goal")
        _require_unique_ids(self.boundaries, "boundary")
        _require_unique_ids(self.framework, "criterion")
        _require_unique_ids(self.data_set, "test case")
        return self

    def case(self, case_id: str) -> TestCase:
        """Return the test case with this id or raise KeyError."""
        for tc in self.data_set:
            if tc.id == case_id:
                return tc
        known = ", ".join(tc.id for tc in self.data_set)
        raise KeyError(f"no test case {case_id!r} in workbook (have: {known})")

    def criterion(self, criterion_id: str) -> Criterion:
        """Return the criterion with this id or raise KeyError."""
        for c in self.framework:
            if c.id == criterion_id:
                return c
        raise KeyError(f"no criterion {criterion_id!r} in workbook")


class CriterionGrade(BaseModel):
    """The verdict for one criterion on one candidate output."""

    criterion_id: str
    criterion: str
    passed: bool
    label: str
    justification: str


class GradingReport(BaseModel):
    """The full set of criterion verdicts for one graded output."""

    agent_name: str
    case_id: str
    model: str
    grades: List[CriterionGrade]

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.grades if g.passed)

    @property
    def total_count(self) -> int:
        return len(self.grades)

    @property
    def ship_ready(self) -> bool:
        """A case is ship-ready only when every criterion passes."""
        return all(g.passed for g in self.grades)
