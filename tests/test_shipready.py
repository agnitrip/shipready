"""Tests for workbook loading and the grading parse pipeline.

These run without network access. The Claude call is replaced with a stub that
returns a canned JSON response, so the prompt building, response parsing, and
report logic are all exercised offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shipready import GradingError, format_report, grade, load_workbook
from shipready.grader import _extract_json, parse_response
from shipready.workbook import WorkbookError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "research_assistant.yaml"


def test_example_workbook_loads():
    wb = load_workbook(EXAMPLE)
    assert wb.agent_name == "research_assistant"
    assert len(wb.framework) == 5
    assert wb.case("t1").id == "t1"


def test_missing_workbook_raises():
    with pytest.raises(WorkbookError):
        load_workbook("does_not_exist.yaml")


def test_duplicate_ids_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "agent_name: x\n"
        "description: x\n"
        "framework:\n"
        "  - {id: c1, criterion: a, grades_what: a, pass_label: p, fail_label: f}\n"
        "  - {id: c1, criterion: b, grades_what: b, pass_label: p, fail_label: f}\n"
        "data_set:\n"
        "  - {id: t1, input: a, expected_behavior: b}\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkbookError):
        load_workbook(bad)


def test_extract_json_from_fenced_block():
    text = '```json\n{"grades": []}\n```'
    assert _extract_json(text) == {"grades": []}


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
            {"criterion_id": c.id, "passed": True, "justification": "looks fine"}
            for c in wb.framework
        ]
    }


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
    payload["grades"][2]["passed"] = False
    client = StubClient(payload)
    report = grade(wb, wb.case("t1"), "out", model="test-model", client=client)
    assert report.ship_ready is False
    failing = report.grades[2]
    assert failing.label == wb.framework[2].fail_label


def test_missing_criterion_raises():
    wb = load_workbook(EXAMPLE)
    response = json.dumps({"grades": [{"criterion_id": "c1", "passed": True}]})
    with pytest.raises(GradingError):
        parse_response(wb, wb.case("t1"), response, "test-model")
