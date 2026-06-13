# Changelog

## Unreleased

- `--summary` flag on grade. Adds a PM-facing summary block (what went well,
  flags, optional watch item, one-line verdict) above the report card, and a
  `summary` field in `--json` output. It is a second Claude call, so it doubles
  the API cost of a grade, and falls back to the bare report on failure. Off by
  default.

## 0.1.1 (2026-06-12)

Documentation transparency polish.

- New section: "What shipready grades" with a structured inputs, context,
  scored, and outputs breakdown.
- Expanded "How a criterion gets graded" subsection consolidating the grading
  rules.
- Sample --verbose prompt fragment in the README.
- Sample --json output block in the README.

## 0.1.0 (2026-06-12)

Process-based eval support (Path A).

- Workbook schema accepts optional process artifacts on TestCase: tool_calls,
  reasoning_trace, decisions_log, escalation_events.
- Criterion gets a target field (output | process). Defaults to output for
  backward compat.
- Grader prompt includes trace artifacts when present and grades process
  criteria against them.
- CLI flags: --tool-calls, --reasoning-trace, --decisions, --escalations.
- New example: tool_using_research_assistant with process criteria and sample
  artifacts.
- Tests for the new schema and grader behavior.

Also in this release, polish carried from the 0.0.1 line and not previously
tagged:

- --dry-run flag on grade to print the assembled prompt without calling Claude.
- Cleaner errors for a missing or invalid ANTHROPIC_API_KEY, with distinct
  messages for rate-limit and network failures.
- Split pytest suite covering workbook validation and the grading pipeline.
- Additional sample outputs: t2 overconfident and t3 compliant.

## 0.0.1 (2026-06-12)

Initial release.

- Workbook YAML schema (Goals + Boundaries + Framework + Data Set).
- Claude grading pipeline with structured prompt and JSON response parsing.
- CLI with grade, validate, cases sub-commands.
- One worked example: research_assistant.
