"""Tests for the grading pipeline. No network; the Claude client is stubbed.

The stub returns a canned JSON response so prompt building, response parsing,
label canonicalization, and report logic are all exercised offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shipready import (
    Criterion,
    GradingError,
    TestCase,
    ToolCall,
    Workbook,
    format_report,
    grade,
    load_workbook,
    summarize,
)
from shipready.grader import _extract_json, build_user_prompt, parse_response

# TestCase is a domain model, not a pytest test class. Tell pytest not to try
# to collect it just because its name starts with "Test".
TestCase.__test__ = False

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "research_assistant.yaml"


class StubClient:
    """Mimics anthropic.Anthropic().messages.create for offline grading."""

    def __init__(self, payload):
        self._payload = payload
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        block = SimpleNamespace(type="text", text=json.dumps(self._payload))
        return SimpleNamespace(content=[block])


def _all_pass_payload(wb):
    return {
        "grades": [
            {"criterion_id": c.id, "status": "pass", "justification": "looks fine"}
            for c in wb.framework
        ]
    }


def test_build_user_prompt_contains_every_criterion_and_input():
    wb = load_workbook(EXAMPLE)
    case = wb.case("t1")
    prompt = build_user_prompt(wb, case, "some candidate output")
    for crit in wb.framework:
        assert crit.id in prompt
    assert "three largest contributors" in prompt  # the case input interpolated


def test_extract_json_bare():
    assert _extract_json('{"grades": []}') == {"grades": []}


def test_extract_json_fenced():
    assert _extract_json('```json\n{"grades": []}\n```') == {"grades": []}


def test_extract_json_embedded_in_prose():
    text = 'Here is my grading:\n{"grades": [{"criterion_id": "c1"}]}\nThat is all.'
    assert _extract_json(text) == {"grades": [{"criterion_id": "c1"}]}


def test_parse_response_missing_criterion_raises():
    wb = load_workbook(EXAMPLE)
    response = json.dumps({"grades": [{"criterion_id": "c1", "passed": True}]})
    with pytest.raises(GradingError) as excinfo:
        parse_response(wb, wb.case("t1"), response, "test-model")
    assert "missing" in str(excinfo.value).lower()


def test_parse_response_snaps_label_to_workbook():
    # The model phrases the label its own way; parse_response must ignore that
    # and use the canonical pass/fail label from the workbook.
    wb = load_workbook(EXAMPLE)
    payload = _all_pass_payload(wb)
    payload["grades"][0]["label"] = "totally_made_up_label"
    payload["grades"][1]["status"] = "fail"
    payload["grades"][1]["label"] = "another_made_up_label"
    response = json.dumps(payload)
    report = parse_response(wb, wb.case("t1"), response, "test-model")
    assert report.grades[0].label == wb.framework[0].pass_label
    assert report.grades[1].label == wb.framework[1].fail_label


def test_grade_with_stub_all_pass():
    wb = load_workbook(EXAMPLE)
    case = wb.case("t1")
    client = StubClient(_all_pass_payload(wb))
    report = grade(wb, case, "some output", model="test-model", client=client)
    assert report.ship_ready is True
    assert report.passed_count == 5
    assert report.grades[0].label == wb.framework[0].pass_label
    assert "SHIP-READY" in format_report(report)


def test_grade_with_one_failure():
    wb = load_workbook(EXAMPLE)
    payload = _all_pass_payload(wb)
    payload["grades"][2]["status"] = "fail"
    client = StubClient(payload)
    report = grade(wb, wb.case("t1"), "out", model="test-model", client=client)
    assert report.ship_ready is False
    assert report.grades[2].label == wb.framework[2].fail_label


def _process_workbook(case):
    return Workbook(
        agent_name="proc",
        description="d",
        framework=[
            Criterion(
                id="p1",
                criterion="tool_appropriateness",
                grades_what="right tools",
                pass_label="apt",
                fail_label="inapt",
                target="process",
            ),
            Criterion(
                id="o1",
                criterion="source_quality",
                grades_what="sources",
                pass_label="ok",
                fail_label="weak",
                target="output",
            ),
        ],
        data_set=[case],
    )


def test_grader_prompt_includes_trace_when_present():
    case = TestCase(
        id="t1",
        input="q",
        expected_behavior="b",
        tool_calls=[ToolCall(tool="web_search", args={"q": "x"}, step=1)],
    )
    prompt = build_user_prompt(_process_workbook(case), case, "answer")
    assert "TOOL CALLS:" in prompt
    assert "web_search" in prompt
    assert "AGENT TRACE TO INSPECT" in prompt


def test_grader_prompt_omits_empty_trace_sections():
    case = TestCase(id="t1", input="q", expected_behavior="b")  # no artifacts
    prompt = build_user_prompt(_process_workbook(case), case, "answer")
    for header in (
        "TOOL CALLS:",
        "REASONING TRACE:",
        "DECISIONS:",
        "ESCALATIONS:",
        "AGENT TRACE",
    ):
        assert header not in prompt


def test_criterion_target_labeled_in_prompt():
    case = TestCase(
        id="t1",
        input="q",
        expected_behavior="b",
        tool_calls=[ToolCall(tool="web_search", args={}, step=1)],
    )
    prompt = build_user_prompt(_process_workbook(case), case, "answer")
    assert "target: process" in prompt
    assert "target: output" in prompt


_SUMMARY_PAYLOAD = {
    "went_well": ["sources are solid", "stayed in scope"],
    "flags": ["uncertainty handling was borderline"],
    "watch": [],
    "verdict": "SHIP-READY: all criteria passed.",
}


def test_summarize_with_stub():
    wb = load_workbook(EXAMPLE)
    report = grade(
        wb, wb.case("t1"), "out", model="m", client=StubClient(_all_pass_payload(wb))
    )
    summary = summarize(
        wb, wb.case("t1"), report, model="m", client=StubClient(_SUMMARY_PAYLOAD)
    )
    assert summary.verdict.startswith("SHIP-READY")
    assert len(summary.went_well) == 2
    assert summary.watch == []


def test_summary_prepended_to_report_card():
    wb = load_workbook(EXAMPLE)
    report = grade(
        wb, wb.case("t1"), "out", model="m", client=StubClient(_all_pass_payload(wb))
    )
    assert "SUMMARY" not in format_report(report)
    report.summary = summarize(
        wb, wb.case("t1"), report, model="m", client=StubClient(_SUMMARY_PAYLOAD)
    )
    card = format_report(report)
    assert "SUMMARY" in card
    assert card.index("SUMMARY") < card.index("shipready report")


def test_summary_omitted_from_json_when_absent():
    wb = load_workbook(EXAMPLE)
    report = grade(
        wb, wb.case("t1"), "out", model="m", client=StubClient(_all_pass_payload(wb))
    )
    assert "summary" not in json.loads(report.model_dump_json(exclude_none=True))


def test_summarize_bad_json_raises():
    wb = load_workbook(EXAMPLE)
    report = grade(
        wb, wb.case("t1"), "out", model="m", client=StubClient(_all_pass_payload(wb))
    )

    class BadClient:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not json at all")]
            )

    with pytest.raises(GradingError):
        summarize(wb, wb.case("t1"), report, model="m", client=BadClient())


def _severity_workbook(c2_severity):
    return Workbook(
        agent_name="sev",
        description="d",
        framework=[
            Criterion(
                id="c1", criterion="a", grades_what="x",
                pass_label="ok", fail_label="bad",
            ),
            Criterion(
                id="c2", criterion="b", grades_what="y",
                pass_label="ok2", fail_label="bad2", severity=c2_severity,
            ),
        ],
        data_set=[TestCase(id="t1", input="q", expected_behavior="b")],
    )


def _status_payload(statuses):
    return {
        "grades": [
            {"criterion_id": cid, "status": st, "justification": "j"}
            for cid, st in statuses.items()
        ]
    }


def _grade_statuses(wb, statuses):
    client = StubClient(_status_payload(statuses))
    return grade(wb, wb.data_set[0], "o", model="m", client=client)


def test_warn_does_not_block_and_surfaces():
    report = _grade_statuses(_severity_workbook("hard"), {"c1": "pass", "c2": "warn"})
    assert report.ship_ready is True
    assert report.has_warnings is True
    assert report.grades[1].status == "warn"
    assert report.grades[1].passed is True
    card = format_report(report)
    assert "[WARN]" in card
    assert "SHIP-READY (with warnings)" in card


def test_soft_fail_does_not_block():
    report = _grade_statuses(_severity_workbook("soft"), {"c1": "pass", "c2": "fail"})
    assert report.ship_ready is True
    assert report.has_warnings is True
    card = format_report(report)
    assert "(soft, non-blocking)" in card
    assert "SHIP-READY (with warnings)" in card


def test_hard_fail_blocks():
    report = _grade_statuses(_severity_workbook("hard"), {"c1": "pass", "c2": "fail"})
    assert report.ship_ready is False
    assert "NOT READY" in format_report(report)


def test_warn_serializes_with_computed_passed():
    report = _grade_statuses(_severity_workbook("hard"), {"c1": "pass", "c2": "warn"})
    g2 = json.loads(report.model_dump_json())["grades"][1]
    assert g2["status"] == "warn"
    assert g2["passed"] is True


def test_legacy_passed_bool_still_parses():
    wb = _severity_workbook("hard")
    response = json.dumps(
        {
            "grades": [
                {"criterion_id": "c1", "passed": True, "justification": "j"},
                {"criterion_id": "c2", "passed": False, "justification": "j"},
            ]
        }
    )
    report = parse_response(wb, wb.data_set[0], response, "m")
    assert report.grades[0].status == "pass"
    assert report.grades[1].status == "fail"


def _scoped_workbook(expected_verdict):
    return Workbook(
        agent_name="dec",
        description="d",
        framework=[
            Criterion(
                id="c1", criterion="always", grades_what="x",
                pass_label="p", fail_label="f",
            ),
            Criterion(
                id="c2", criterion="stub_only", grades_what="y",
                pass_label="p", fail_label="f", applies_to=["stub"],
            ),
        ],
        data_set=[
            TestCase(
                id="t1", input="q", expected_behavior="b",
                expected_verdict=expected_verdict,
            )
        ],
    )


def test_applies_to_excludes_nonmatching_branch():
    wb = _scoped_workbook("produce")
    case = wb.data_set[0]
    # Only c1 applies; grading only c1 must not raise a missing-c2 error.
    report = grade(wb, case, "out", model="m", client=StubClient(_status_payload({"c1": "pass"})))
    assert [g.criterion_id for g in report.grades] == ["c1"]
    prompt = build_user_prompt(wb, case, "out")
    assert "id: c2" not in prompt
    assert "Expected verdict (decision branch): produce" in prompt


def test_applies_to_includes_matching_branch():
    wb = _scoped_workbook("stub")
    case = wb.data_set[0]
    report = grade(
        wb, case, "out", model="m",
        client=StubClient(_status_payload({"c1": "pass", "c2": "pass"})),
    )
    assert {g.criterion_id for g in report.grades} == {"c1", "c2"}


def test_process_no_trace_never_silent_passes():
    # A process criterion graded with no trace must not pass silently.
    case = TestCase(id="t1", input="q", expected_behavior="b")  # no trace
    wb = _process_workbook(case)
    report = grade(
        wb, case, "o", model="m",
        client=StubClient(_status_payload({"p1": "pass", "o1": "pass"})),
    )
    p1 = next(g for g in report.grades if g.criterion_id == "p1")
    assert p1.status == "warn"
    assert "no trace" in p1.justification.lower() or "self-report" in p1.justification.lower()
    # The output criterion is unaffected by the trace-integrity rule.
    o1 = next(g for g in report.grades if g.criterion_id == "o1")
    assert o1.status == "pass"


def test_process_with_trace_pass_stands():
    case = TestCase(
        id="t1", input="q", expected_behavior="b",
        tool_calls=[ToolCall(tool="web_search", args={}, step=1)],
    )
    wb = _process_workbook(case)
    report = grade(
        wb, case, "o", model="m",
        client=StubClient(_status_payload({"p1": "pass", "o1": "pass"})),
    )
    p1 = next(g for g in report.grades if g.criterion_id == "p1")
    assert p1.status == "pass"
    assert "no trace" not in p1.justification.lower()
