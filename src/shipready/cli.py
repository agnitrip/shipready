"""shipready command line interface."""

from __future__ import annotations

import json
import os
import sys

import click
from anthropic import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import ValidationError

from . import __version__
from .grader import DEFAULT_MODEL, GradingError, grade, render_prompt, summarize
from .models import TestCase
from .report import format_report
from .workbook import WorkbookError, load_workbook


def _load_or_exit(workbook_path: str):
    try:
        return load_workbook(workbook_path)
    except WorkbookError as exc:
        raise click.ClickException(str(exc))


def _read_text_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise click.ClickException(f"could not read {label} file: {exc}")


def _load_json_list(path: str, label: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{label} file is not valid JSON: {exc}")
    except OSError as exc:
        raise click.ClickException(f"could not read {label} file: {exc}")
    if not isinstance(data, list):
        raise click.ClickException(f"{label} file must contain a JSON array")
    return data


def _attach_trace(case: TestCase, tool_calls, reasoning_trace, decisions, escalations) -> TestCase:
    """Attach trace artifacts from CLI files onto the test case.

    Supplied flags override any artifact the workbook already carried for this
    case. The merged case is re-validated so malformed trace data fails with a
    clean message.
    """
    overrides = {}
    if tool_calls is not None:
        overrides["tool_calls"] = _load_json_list(tool_calls, "--tool-calls")
    if reasoning_trace is not None:
        overrides["reasoning_trace"] = _read_text_file(reasoning_trace, "--reasoning-trace")
    if decisions is not None:
        overrides["decisions_log"] = _load_json_list(decisions, "--decisions")
    if escalations is not None:
        overrides["escalation_events"] = _load_json_list(escalations, "--escalations")

    if not overrides:
        return case

    data = case.model_dump()
    data.update(overrides)
    try:
        return TestCase.model_validate(data)
    except ValidationError as exc:
        raise click.ClickException(f"trace artifact failed validation:\n{exc}")


def _friendly_api_error(exc: Exception) -> str:
    """Map an SDK or grading exception to a readable one-line message."""
    if isinstance(exc, AuthenticationError):
        return (
            "ANTHROPIC_API_KEY is invalid (authentication failed). "
            "See the README install section for setup."
        )
    if isinstance(exc, RateLimitError):
        return "Claude API rate limit reached. Wait a moment and retry."
    if isinstance(exc, APIConnectionError):
        return "Could not reach the Claude API. Check your network connection and retry."
    if isinstance(exc, GradingError):
        return f"grading failed: {exc}"
    return f"Claude API call failed: {exc}"


def _grade_case(workbook, case, agent_output, model, summary):
    """Grade one case and optionally attach a summary. Raises on grade failure."""
    report = grade(workbook, case, agent_output, model=model)
    if summary:
        try:
            report.summary = summarize(workbook, case, report, model=model)
        except Exception as exc:
            click.echo(
                f"warning: summary synthesis failed for case {case.id}: {exc}",
                err=True,
            )
    return report


def _write_out(path: str, content: str) -> None:
    """Write content to path, only after grading has produced it.

    This replaces a shell redirect, so a transient grading error cannot leave a
    truncated or zero-byte file behind.
    """
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        raise click.ClickException(f"could not write --out file: {exc}")
    click.echo(f"wrote {path}", err=True)


def _resolve_output(output: str, output_file, label: str) -> str:
    """Resolve the candidate agent output from flag, file, or stdin.

    Precedence: --output (inline) over --output-file over stdin.
    """
    if output is not None:
        return output
    if output_file is not None:
        return output_file.read()
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data
    raise click.ClickException(
        f"no agent output supplied for {label}. Pass --output, --output-file, "
        "or pipe the output on stdin."
    )


@click.group()
@click.version_option(version=__version__, prog_name="shipready")
def cli() -> None:
    """Rubric based ship-readiness evals for AI agents."""


@cli.command(name="grade")
@click.option(
    "--workbook",
    "workbook_path",
    required=True,
    type=click.Path(exists=False, dir_okay=False),
    help="Path to the workbook YAML file.",
)
@click.option(
    "--case", "case_id", default=None, help="Test case id to grade (or use --all)."
)
@click.option(
    "--all", "grade_all", is_flag=True, help="Grade every case in the workbook."
)
@click.option(
    "--output",
    default=None,
    help="Candidate agent output as an inline string.",
)
@click.option(
    "--output-file",
    type=click.File("r", encoding="utf-8"),
    default=None,
    help="Path to a file holding the candidate agent output.",
)
@click.option(
    "--tool-calls",
    "tool_calls",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a JSON file with the tool call trace (process eval).",
)
@click.option(
    "--reasoning-trace",
    "reasoning_trace",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a text file with the agent's reasoning (process eval).",
)
@click.option(
    "--decisions",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a JSON file with the decisions log (process eval).",
)
@click.option(
    "--escalations",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a JSON file with escalation events (process eval).",
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Claude model id used for grading.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print the exact prompt sent to Claude before grading.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Print the assembled prompt and exit without calling Claude.",
)
@click.option(
    "--summary",
    is_flag=True,
    help="Add a PM-facing summary block (makes a second Claude call, so this "
    "doubles the API cost of a grade).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the grading report as JSON instead of a text card.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the JSON report(s) to this file (the human card still prints "
    "to stdout). Written only after grading succeeds, so no fragile redirect.",
)
def grade_cmd(
    workbook_path,
    case_id,
    grade_all,
    output,
    output_file,
    tool_calls,
    reasoning_trace,
    decisions,
    escalations,
    model,
    verbose,
    dry_run,
    summary,
    as_json,
    out_path,
):
    """Grade one test case, or every case in a workbook with --all."""
    workbook = _load_or_exit(workbook_path)

    if grade_all and case_id:
        raise click.ClickException("use --case or --all, not both.")
    if not grade_all and not case_id:
        raise click.ClickException("provide --case CASE_ID or --all.")

    trace_flags = (tool_calls, reasoning_trace, decisions, escalations)
    if grade_all and any(f is not None for f in trace_flags):
        raise click.ClickException(
            "trace flags apply to a single --case. For --all, embed each case's "
            "trace in the workbook."
        )

    if grade_all:
        cases = list(workbook.data_set)
        label = "the run"
    else:
        try:
            cases = [workbook.case(case_id)]
        except KeyError as exc:
            raise click.ClickException(str(exc))
        cases = [
            _attach_trace(cases[0], tool_calls, reasoning_trace, decisions, escalations)
        ]
        label = f"case {case_id}"

    agent_output = _resolve_output(output, output_file, label=label)

    if dry_run:
        # Build and print the prompt(s) without spending API credits.
        for case in cases:
            click.echo(render_prompt(workbook, case, agent_output))
        sys.exit(0)

    if verbose:
        for case in cases:
            click.echo(render_prompt(workbook, case, agent_output), err=True)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.ClickException(
            "ANTHROPIC_API_KEY is not set. See the README install section for setup."
        )

    # Single case: fail loud with a friendly message.
    if not grade_all:
        case = cases[0]
        try:
            report = _grade_case(workbook, case, agent_output, model, summary)
        except Exception as exc:
            raise click.ClickException(_friendly_api_error(exc))
        if out_path:
            _write_out(out_path, report.model_dump_json(indent=2, exclude_none=True))
            click.echo(format_report(report))
        elif as_json:
            click.echo(report.model_dump_json(indent=2, exclude_none=True))
        else:
            click.echo(format_report(report))
        sys.exit(0 if report.ship_ready else 1)

    # --all: grade every case, never drop one silently.
    reports = []
    failures = []
    for case in cases:
        try:
            report = _grade_case(workbook, case, agent_output, model, summary)
        except Exception as exc:
            failures.append((case.id, _friendly_api_error(exc)))
            continue
        reports.append(report)
        click.echo(format_report(report))
        click.echo("")

    for case_id_failed, message in failures:
        click.echo(f"FAILED to grade case {case_id_failed}: {message}", err=True)

    if out_path:
        payload = (
            "[\n"
            + ",\n".join(
                r.model_dump_json(indent=2, exclude_none=True) for r in reports
            )
            + "\n]"
        )
        _write_out(out_path, payload)

    not_ready = [r.case_id for r in reports if not r.ship_ready]
    click.echo(
        f"graded {len(reports)}/{len(cases)} cases, "
        f"{len(failures)} failed, {len(not_ready)} not ready",
        err=True,
    )
    sys.exit(1 if (failures or not_ready) else 0)


@cli.command()
@click.option(
    "--workbook",
    "workbook_path",
    required=True,
    type=click.Path(exists=False, dir_okay=False),
    help="Path to the workbook YAML file.",
)
def validate(workbook_path):
    """Load a workbook and report whether it is valid."""
    workbook = _load_or_exit(workbook_path)
    click.echo(
        f"ok: {workbook.agent_name} "
        f"({len(workbook.framework)} criteria, {len(workbook.data_set)} cases)"
    )


@cli.command()
@click.option(
    "--workbook",
    "workbook_path",
    required=True,
    type=click.Path(exists=False, dir_okay=False),
    help="Path to the workbook YAML file.",
)
def cases(workbook_path):
    """List the test cases defined in a workbook."""
    workbook = _load_or_exit(workbook_path)
    for tc in workbook.data_set:
        first_line = tc.input.strip().splitlines()[0] if tc.input.strip() else ""
        preview = first_line[:70]
        click.echo(f"{tc.id}\t{preview}")


if __name__ == "__main__":
    cli()
