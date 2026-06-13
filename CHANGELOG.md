# Changelog

## Unreleased

- `--dry-run` flag on grade to print the assembled prompt without calling Claude.
- Cleaner errors for a missing or invalid `ANTHROPIC_API_KEY`, with distinct
  messages for rate-limit and network failures.
- Minimal pytest suite covering workbook validation and the grading pipeline.
- Additional sample outputs: t2 overconfident and t3 compliant.

## 0.0.1 (2026-06-12)

Initial release.

- Workbook YAML schema (Goals + Boundaries + Framework + Data Set).
- Claude grading pipeline with structured prompt and JSON response parsing.
- CLI with grade, validate, cases sub-commands.
- One worked example: research_assistant.
