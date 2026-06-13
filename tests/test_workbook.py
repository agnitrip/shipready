"""Tests for workbook loading and validation. No network access."""

from __future__ import annotations

from pathlib import Path

import pytest

from shipready import load_workbook
from shipready.workbook import WorkbookError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "research_assistant.yaml"


def test_example_workbook_loads():
    wb = load_workbook(EXAMPLE)
    assert wb.agent_name == "research_assistant"
    assert len(wb.framework) == 5
    assert len(wb.data_set) == 3


def test_missing_workbook_raises():
    with pytest.raises(WorkbookError):
        load_workbook("does_not_exist.yaml")


def test_duplicate_criterion_id_raises(tmp_path):
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
    with pytest.raises(WorkbookError) as excinfo:
        load_workbook(bad)
    assert "duplicate" in str(excinfo.value).lower()


def test_missing_framework_raises(tmp_path):
    bad = tmp_path / "noframework.yaml"
    bad.write_text(
        "agent_name: x\n"
        "description: x\n"
        "data_set:\n"
        "  - {id: t1, input: a, expected_behavior: b}\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkbookError):
        load_workbook(bad)


TOOL_USING_EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "tool_using_research_assistant.yaml"
)


def test_existing_workbook_still_loads():
    # The v0 output-only workbook keeps loading and stays all-output.
    wb = load_workbook(EXAMPLE)
    assert wb.agent_name == "research_assistant"
    assert all(c.target == "output" for c in wb.framework)


def test_criterion_target_defaults_to_output(tmp_path):
    wb_path = tmp_path / "wb.yaml"
    wb_path.write_text(
        "agent_name: x\n"
        "description: x\n"
        "framework:\n"
        "  - {id: c1, criterion: a, grades_what: a, pass_label: p, fail_label: f}\n"
        "data_set:\n"
        "  - {id: t1, input: a, expected_behavior: b}\n",
        encoding="utf-8",
    )
    wb = load_workbook(wb_path)
    assert wb.framework[0].target == "output"


def test_workbook_loads_with_process_criterion(tmp_path):
    wb_path = tmp_path / "wb.yaml"
    wb_path.write_text(
        "agent_name: x\n"
        "description: x\n"
        "framework:\n"
        "  - {id: p1, criterion: tool_appropriateness, grades_what: a, "
        "pass_label: apt, fail_label: inapt, target: process}\n"
        "data_set:\n"
        "  - {id: t1, input: a, expected_behavior: b}\n",
        encoding="utf-8",
    )
    wb = load_workbook(wb_path)
    assert wb.framework[0].target == "process"


def test_workbook_loads_with_process_fields():
    # The shipped tool-using example carries tool_calls and reasoning on cases.
    wb = load_workbook(TOOL_USING_EXAMPLE)
    t1 = wb.case("t1")
    assert t1.tool_calls and t1.tool_calls[0].tool == "web_search"
    assert t1.reasoning_trace
    assert wb.case("t2").tool_calls[0].tool == "calculator"
