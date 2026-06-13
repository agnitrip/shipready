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
