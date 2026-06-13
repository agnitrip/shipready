"""shipready command line interface."""

from __future__ import annotations

import json
import os
import sys

import click
from anthropic import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import ValidationError

from . import __version__
from .grader import DEFAULT_MODEL, GradingError, grade, render_prompt
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
@click.option("--case", "case_id", required=True, help="Test case id to grade.")
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
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the grading report as JSON instead of a text card.",
)
def grade_cmd(
    workbook_path,
    case_id,
    output,
    output_file,
    tool_calls,
    reasoning_trace,
    decisions,
    escalations,
    model,
    verbose,
    dry_run,
    as_json,
):
    """Grade one candidate output for one test case."""
    workbook = _load_or_exit(workbook_path)
    try:
        case = workbook.case(case_id)
    except KeyError as exc:
        raise click.ClickException(str(exc))

    case = _attach_trace(case, tool_calls, reasoning_trace, decisions, escalations)

    agent_output = _resolve_output(output, output_file, label=f"case {case_id}")

    if dry_run:
        # Build and print the prompt without spending API credits.
        click.echo(render_prompt(workbook, case, agent_output))
        sys.exit(0)

    if verbose:
        click.echo(render_prompt(workbook, case, agent_output), err=True)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.ClickException(
            "ANTHROPIC_API_KEY is not set. See the README install section for setup."
        )

    try:
        report = grade(workbook, case, agent_output, model=model)
    except GradingError as exc:
        raise click.ClickException(f"grading failed: {exc}")
    except AuthenticationError:
        raise click.ClickException(
            "ANTHROPIC_API_KEY is invalid (authentication failed). "
            "See the README install section for setup."
        )
    except RateLimitError:
        raise click.ClickException(
            "Claude API rate limit reached. Wait a moment and retry."
        )
    except APIConnectionError:
        raise click.ClickException(
            "Could not reach the Claude API. Check your network connection and retry."
        )
    except Exception as exc:  # any other API or runtime error
        raise click.ClickException(f"Claude API call failed: {exc}")

    if as_json:
        click.echo(report.model_dump_json(indent=2))
    else:
        click.echo(format_report(report))

    sys.exit(0 if report.ship_ready else 1)


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
