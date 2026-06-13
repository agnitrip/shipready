"""Claude grading pipeline.

Given a workbook, one test case, and a candidate agent output, build a
structured prompt, send it to Claude, and parse the response into a
GradingReport. The candidate output is supplied by the caller. In v0 you run
your agent separately and hand its output to shipready.
"""

from __future__ import annotations

import json
from typing import List, Optional

from .models import (
    CriterionGrade,
    GradingReport,
    TestCase,
    Workbook,
)

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You are an expert evaluator grading whether an AI agent's output and "
    "behavior meet a predefined rubric. Some criteria target the agent's final "
    "OUTPUT. Other criteria target the agent's PROCESS, which you inspect "
    "through the supplied trace artifacts (tool calls, reasoning, decisions, "
    "escalations). Grade each criterion against the artifact it targets. For "
    "each criterion, decide pass or fail and write a one or two sentence "
    "justification grounded in the relevant artifact. Do not invent criteria "
    "that were not provided, and do not let a strong result on one criterion "
    "excuse a failure on another. When a criterion targets the output and the "
    "output is missing, fail it if content is required. When a criterion "
    "targets the process and the relevant trace artifact is missing, mark it "
    "failed with a justification noting the missing trace."
)


class GradingError(Exception):
    """Raised when Claude's response cannot be parsed into a complete report."""


def _format_goals(workbook: Workbook) -> str:
    if not workbook.goals:
        return "(none specified)"
    lines = []
    for g in workbook.goals:
        lines.append(f"- [{g.id}] {g.description.strip()}")
        for sub in g.sub_goals:
            lines.append(f"    - {sub.strip()}")
    return "\n".join(lines)


def _format_boundaries(workbook: Workbook) -> str:
    if not workbook.boundaries:
        return "(none specified)"
    lines = []
    for b in workbook.boundaries:
        lines.append(f"- [{b.id}] {b.name}: {b.what_it_means.strip()}")
        if b.example:
            lines.append(f"    example: {b.example.strip()}")
    return "\n".join(lines)


def _format_framework(workbook: Workbook) -> str:
    lines = []
    for c in workbook.framework:
        lines.append(f"- id: {c.id}")
        lines.append(f"  criterion: {c.criterion.strip()}")
        lines.append(f"  target: {c.target}")
        lines.append(f"  grades_what: {c.grades_what.strip()}")
        lines.append(f"  pass means: {c.pass_label}")
        lines.append(f"  fail means: {c.fail_label}")
    return "\n".join(lines)


def _format_trace(case: TestCase) -> str:
    """Render the present trace artifacts as labeled blocks.

    Only non-empty artifacts produce a block, so missing sections leave no
    empty headers behind. Returns "" when the case carries no trace at all.
    """
    blocks = []

    if case.tool_calls:
        lines = ["TOOL CALLS:"]
        for tc in case.tool_calls:
            step = f"step {tc.step}: " if tc.step is not None else ""
            args = json.dumps(tc.args, ensure_ascii=False) if tc.args else "{}"
            line = f"- {step}{tc.tool}(args={args})"
            if tc.returned:
                line += f" -> returned: {tc.returned.strip()}"
            lines.append(line)
        blocks.append("\n".join(lines))

    if case.reasoning_trace and case.reasoning_trace.strip():
        blocks.append("REASONING TRACE:\n" + case.reasoning_trace.strip())

    if case.decisions_log:
        lines = ["DECISIONS:"]
        for d in case.decisions_log:
            line = f"- [{d.at}] {d.decision}"
            if d.rationale:
                line += f" (rationale: {d.rationale.strip()})"
            lines.append(line)
        blocks.append("\n".join(lines))

    if case.escalation_events:
        lines = ["ESCALATIONS:"]
        for e in case.escalation_events:
            line = f"- [{e.at}] {e.reason}"
            if e.handed_off_to:
                line += f" -> handed off to: {e.handed_off_to}"
            lines.append(line)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def build_user_prompt(
    workbook: Workbook, case: TestCase, agent_output: str
) -> str:
    """Assemble the user message Claude grades. Printed verbatim under verbose.

    Trace artifact sections are rendered only when the workbook has at least one
    process criterion and the case actually carries the artifact. That keeps
    output-only workbooks identical to before and avoids empty trace headers.
    """
    criterion_ids = ", ".join(c.id for c in workbook.framework)
    description = workbook.description.strip()
    case_input = case.input.strip()
    expected = case.expected_behavior.strip()
    notes = case.notes.strip() if case.notes else ""
    output_block = agent_output.strip() or "(the agent produced no output)"
    has_process = any(c.target == "process" for c in workbook.framework)
    schema_example = (
        '{"grades": [{"criterion_id": "<id>", "passed": true, '
        '"justification": "<one or two sentences>"}]}'
    )

    case_block = (
        f"TEST CASE [{case.id}]\n"
        f"Input given to the agent:\n{case_input}\n\n"
        f"Expected behavior:\n{expected}"
    )
    if notes:
        case_block += f"\nNotes: {notes}"

    sections = [
        f'You are grading the output and behavior of an AI agent named '
        f'"{workbook.agent_name}".',
        f"Agent purpose: {description}",
        "GOALS (what the agent is for):\n" + _format_goals(workbook),
        "BOUNDARIES (lines the agent must not cross):\n"
        + _format_boundaries(workbook),
        "GRADING FRAMEWORK (score each criterion pass or fail, against its "
        "target):\n" + _format_framework(workbook),
        case_block,
        "AGENT OUTPUT TO GRADE:\n" + output_block,
    ]

    if has_process:
        trace = _format_trace(case)
        if trace:
            sections.append(
                "AGENT TRACE TO INSPECT (for process criteria):\n" + trace
            )

    sections.append(
        "INSTRUCTIONS:\n"
        "Grade every criterion in the framework against the artifact named by "
        "its target. You must return a verdict for each of these criterion "
        f"ids: {criterion_ids}.\n"
        "Respond with a single JSON object and nothing else, in this shape:\n"
        f"{schema_example}\n"
        'Set "passed" to true when the criterion is met and false when it is '
        "not. Keep each justification to one or two sentences, grounded in the "
        "relevant artifact."
    )

    return "\n\n".join(sections)


def render_prompt(workbook: Workbook, case: TestCase, agent_output: str) -> str:
    """Return the full prompt (system plus user) as readable text for verbose."""
    user = build_user_prompt(workbook, case, agent_output)
    return (
        "===== SYSTEM =====\n"
        f"{SYSTEM_PROMPT}\n\n"
        "===== USER =====\n"
        f"{user}\n"
    )


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response.

    Handles a bare object, a fenced code block, or an object embedded in prose.
    """
    text = text.strip()
    if text.startswith("```"):
        # Strip a leading fence line such as ```json and the trailing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GradingError(f"could not parse JSON from response: {exc}") from exc
    raise GradingError("no JSON object found in model response")


def parse_response(
    workbook: Workbook, case: TestCase, response_text: str, model: str
) -> GradingReport:
    """Turn Claude's raw text into a validated GradingReport.

    The canonical pass and fail labels come from the workbook, so the report
    never drifts from the rubric even if the model phrases things differently.
    """
    data = _extract_json(response_text)
    raw_grades = data.get("grades")
    if not isinstance(raw_grades, list):
        raise GradingError('response JSON is missing a "grades" list')

    by_id = {}
    for entry in raw_grades:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("criterion_id")
        if cid is not None:
            by_id[cid] = entry

    grades: List[CriterionGrade] = []
    missing = []
    for crit in workbook.framework:
        entry = by_id.get(crit.id)
        if entry is None:
            missing.append(crit.id)
            continue
        passed = bool(entry.get("passed"))
        grades.append(
            CriterionGrade(
                criterion_id=crit.id,
                criterion=crit.criterion,
                passed=passed,
                label=crit.pass_label if passed else crit.fail_label,
                justification=str(entry.get("justification", "")).strip(),
            )
        )

    if missing:
        raise GradingError(
            "model did not grade every criterion; missing: " + ", ".join(missing)
        )

    return GradingReport(
        agent_name=workbook.agent_name,
        case_id=case.id,
        model=model,
        grades=grades,
    )


def grade(
    workbook: Workbook,
    case: TestCase,
    agent_output: str,
    model: str = DEFAULT_MODEL,
    client: Optional[object] = None,
    max_tokens: int = 2000,
) -> GradingReport:
    """Grade one candidate output against the workbook framework.

    Pass a preconfigured Anthropic client to override the default, which reads
    ANTHROPIC_API_KEY from the environment. A client can also be a stub in
    tests as long as it exposes messages.create.
    """
    if client is None:
        from anthropic import Anthropic

        client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_user_prompt(workbook, case, agent_output)}
        ],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise GradingError("model returned an empty response")

    return parse_response(workbook, case, text, model)
