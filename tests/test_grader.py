"""Tests for the grading pipeline. No network; the Claude client is stubbed.

The stub returns a canned JSON response so prompt building, response parsing,
label canonicalization, and report logic are all exercised offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shipready import GradingError, format_report, grade, load_workbook
from shipready.grader import _extract_json, build_user_prompt, parse_response

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
            {"criterion_id": c.id, "passed": True, "justification": "looks fine"}
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
    payload["grades"][1]["passed"] = False
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
    payload["grades"][2]["passed"] = False
    client = StubClient(payload)
    report = grade(wb, wb.case("t1"), "out", model="test-model", client=client)
    assert report.ship_ready is False
    assert report.grades[2].label == wb.framework[2].fail_label
