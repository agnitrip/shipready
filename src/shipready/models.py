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

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator


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
    """One graded dimension. Each criterion resolves to pass, warn, or fail.

    target selects which artifact the criterion is graded against. "output"
    grades the agent's final answer (the v0 paradigm). "process" grades the
    agent's behavior through the supplied trace artifacts (tool calls,
    reasoning, decisions, escalations). Defaults to "output" so existing
    workbooks load unchanged.

    severity controls whether a fail blocks ship-readiness. "hard" (the
    default) means a fail blocks. "soft" means a fail surfaces in the report
    but does not block the verdict.

    applies_to scopes a criterion to specific expected branches. When set, the
    criterion is graded only when the test case's expected_verdict is in the
    list (for example a stub-completeness criterion that applies only when
    expected_verdict is "stub"). When None (the default) the criterion always
    applies.
    """

    id: str
    criterion: str
    grades_what: str
    pass_label: str
    fail_label: str
    target: Literal["output", "process"] = "output"
    severity: Literal["hard", "soft"] = "hard"
    applies_to: Optional[List[str]] = None


class ToolCall(BaseModel):
    """One tool invocation in the agent's trace."""

    tool: str
    args: dict = Field(default_factory=dict)
    returned: Optional[str] = None
    step: Optional[int] = None


class Decision(BaseModel):
    """One decision the agent made during the run."""

    at: str
    decision: str
    rationale: Optional[str] = None


class EscalationEvent(BaseModel):
    """One point where the agent escalated or handed off."""

    at: str
    reason: str
    handed_off_to: Optional[str] = None


class TestCase(BaseModel):
    """One input the agent is expected to handle, plus the target behavior.

    The optional process artifact fields hold the agent's trace for this case.
    They are graded by criteria whose target is "process". All are optional so
    output-only workbooks stay valid.

    expected_verdict is an agent-defined free string naming the branch the
    agent was expected to take (for example "produce", "refuse", or "stub").
    It scopes criteria via their applies_to and gives decision criteria the
    expected branch to grade against.
    """

    id: str
    input: str
    expected_behavior: str
    notes: Optional[str] = None
    expected_verdict: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    reasoning_trace: Optional[str] = None
    decisions_log: Optional[List[Decision]] = None
    escalation_events: Optional[List[EscalationEvent]] = None


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
    """The verdict for one criterion on one candidate output.

    status is pass, warn, or fail. severity is copied from the criterion so the
    report can decide on its own whether a fail blocks. passed is kept as a
    computed field (status is not fail) so older --json consumers and counts
    that read passed keep working.
    """

    criterion_id: str
    criterion: str
    severity: Literal["hard", "soft"] = "hard"
    status: Literal["pass", "warn", "fail"]
    label: str
    justification: str

    @computed_field
    @property
    def passed(self) -> bool:
        return self.status != "fail"


class Summary(BaseModel):
    """PM-facing synthesis of a grading report from a second grading pass.

    Short bullets only. This is the legible artifact a reader skims, not a
    re-narration of the per-criterion justifications.
    """

    went_well: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    watch: List[str] = Field(default_factory=list)
    verdict: str


class GradingReport(BaseModel):
    """The full set of criterion verdicts for one graded output."""

    agent_name: str
    case_id: str
    model: str
    grades: List[CriterionGrade]
    summary: Optional[Summary] = None

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.grades if g.passed)

    @property
    def total_count(self) -> int:
        return len(self.grades)

    @property
    def has_warnings(self) -> bool:
        """True when something non-blocking should still catch the eye.

        A warn on any criterion, or a fail on a soft criterion.
        """
        return any(
            g.status == "warn" or (g.severity == "soft" and g.status == "fail")
            for g in self.grades
        )

    @property
    def ship_ready(self) -> bool:
        """Ship-ready unless a hard criterion failed.

        A warn never blocks. A soft fail never blocks; it surfaces only.
        """
        return not any(
            g.severity == "hard" and g.status == "fail" for g in self.grades
        )
