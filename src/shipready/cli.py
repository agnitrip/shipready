"""shipready command line interface."""

from __future__ import annotations

import sys

import click

from . import __version__
from .grader import DEFAULT_MODEL, GradingError, grade, render_prompt
from .report import format_report
from .workbook import WorkbookError, load_workbook


def _load_or_exit(workbook_path: str):
    try:
        return load_workbook(workbook_path)
    except WorkbookError as exc:
        raise click.ClickException(str(exc))


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
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the grading report as JSON instead of a text card.",
)
def grade_cmd(workbook_path, case_id, output, output_file, model, verbose, as_json):
    """Grade one candidate output for one test case."""
    workbook = _load_or_exit(workbook_path)
    try:
        case = workbook.case(case_id)
    except KeyError as exc:
        raise click.ClickException(str(exc))

    agent_output = _resolve_output(output, output_file, label=f"case {case_id}")

    if verbose:
        click.echo(render_prompt(workbook, case, agent_output), err=True)

    try:
        report = grade(workbook, case, agent_output, model=model)
    except GradingError as exc:
        raise click.ClickException(f"grading failed: {exc}")
    except Exception as exc:  # surface API and auth errors cleanly
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
