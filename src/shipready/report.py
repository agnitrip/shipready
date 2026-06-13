"""Render a GradingReport as a plain-text ship-readiness card."""

from __future__ import annotations

import textwrap

from .models import GradingReport, Summary


def _wrap(text: str, indent: str) -> str:
    wrapped = textwrap.fill(
        text,
        width=78,
        initial_indent=indent,
        subsequent_indent=indent,
    )
    return wrapped


def format_summary(summary: Summary) -> str:
    """Render the PM-facing summary block that sits above the report card."""
    lines = []
    lines.append("=" * 62)
    lines.append("SUMMARY")
    lines.append("=" * 62)

    lines.append("What went well:")
    for bullet in summary.went_well:
        lines.append(_wrap(f"- {bullet}", indent=""))

    lines.append("")
    lines.append("Flags or warnings:")
    for bullet in summary.flags:
        lines.append(_wrap(f"- {bullet}", indent=""))

    if summary.watch:
        lines.append("")
        lines.append("What to watch:")
        for bullet in summary.watch:
            lines.append(_wrap(f"- {bullet}", indent=""))

    lines.append("")
    lines.append(_wrap(f"Verdict: {summary.verdict}", indent=""))
    return "\n".join(lines)


def format_report(report: GradingReport) -> str:
    """Return a human-readable report card for one graded case.

    When a summary is attached it is prepended above the per-criterion card.
    """
    card_lines = []
    card_lines.append("=" * 62)
    card_lines.append(f"shipready report  |  agent: {report.agent_name}")
    card_lines.append(f"case: {report.case_id}  |  model: {report.model}")
    card_lines.append("=" * 62)

    for g in report.grades:
        mark = "PASS" if g.passed else "FAIL"
        card_lines.append(f"[{mark}] {g.criterion_id}  {g.criterion}  ({g.label})")
        if g.justification:
            card_lines.append(_wrap(g.justification, indent="       "))
        card_lines.append("")

    verdict = "SHIP-READY" if report.ship_ready else "NOT READY"
    card_lines.append("-" * 62)
    card_lines.append(
        f"{report.passed_count}/{report.total_count} criteria passed  ->  {verdict}"
    )
    card_lines.append("-" * 62)

    card = "\n".join(card_lines)
    if report.summary is not None:
        return format_summary(report.summary) + "\n\n" + card
    return card
