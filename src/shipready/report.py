"""Render a GradingReport as a plain-text ship-readiness card."""

from __future__ import annotations

import textwrap

from .models import GradingReport


def _wrap(text: str, indent: str) -> str:
    wrapped = textwrap.fill(
        text,
        width=78,
        initial_indent=indent,
        subsequent_indent=indent,
    )
    return wrapped


def format_report(report: GradingReport) -> str:
    """Return a human-readable report card for one graded case."""
    lines = []
    lines.append("=" * 62)
    lines.append(f"shipready report  |  agent: {report.agent_name}")
    lines.append(f"case: {report.case_id}  |  model: {report.model}")
    lines.append("=" * 62)

    for g in report.grades:
        mark = "PASS" if g.passed else "FAIL"
        lines.append(f"[{mark}] {g.criterion_id}  {g.criterion}  ({g.label})")
        if g.justification:
            lines.append(_wrap(g.justification, indent="       "))
        lines.append("")

    verdict = "SHIP-READY" if report.ship_ready else "NOT READY"
    lines.append("-" * 62)
    lines.append(
        f"{report.passed_count}/{report.total_count} criteria passed  ->  {verdict}"
    )
    lines.append("-" * 62)
    return "\n".join(lines)
