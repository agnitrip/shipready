#!/usr/bin/env python3
"""Convert a SWE-bench .traj file into shipready trace inputs.

Dogfood tooling, not a shipped feature. It exists so a public SWE-bench
trajectory can be graded by shipready in one command instead of being reshaped
by hand each time. It does one job: read a SWE-bench .traj and write the three
files shipready grades from.

Scope is deliberately narrow. This handles the SWE-bench .traj shape only, the
format produced by SWE-agent and the SWE-bench-Live harness. It is not a
universal trace adapter and should not grow into one. If you need to grade a
trajectory in a different format, write the small reshaper for that format
instead of generalizing this one.

Input shape (verified against the real files, both sources share it):
  {
    "trajectory": [ {"action": str, "observation": str, "thought": str, ...}, ... ],
    "info": {"submission": str, ...},
    ...
  }
SWE-bench-Live adds per-step "query" and "extra_info" keys that we ignore.

Output (written into --out-dir):
  tool_calls.json   list of {tool, args, returned, step}
  reasoning.txt     "Step N: <thought>" blocks joined by blank lines
  output.txt        the final patch, from info.submission
  ground_truth.json optional, only when a sibling report.json is present

Usage:
  python dogfood/traj_to_shipready.py <input.traj> --out-dir <dir>
"""

import argparse
import json
import os
import sys

# Truncation caps. These keep the grader prompt bounded while preserving the
# action, tool output, and reasoning signal the criteria are judged against.
# Derived from the existing hand-converted files. The hand conversions used
# slightly tighter caps on one of the two sources; these are the looser of the
# two so no grading signal is lost.
ACTION_CAP = 300
RETURNED_CAP = 400
THOUGHT_CAP = 600


def load_traj(path):
    """Load a .traj and return its trajectory list and info dict."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "trajectory" not in data or not isinstance(data["trajectory"], list):
        sys.exit(f"error: {path} has no 'trajectory' list; not a SWE-bench .traj")
    if "info" not in data or not isinstance(data["info"], dict):
        sys.exit(f"error: {path} has no 'info' object; not a SWE-bench .traj")
    return data["trajectory"], data["info"]


def build_tool_calls(trajectory):
    """Map each trajectory step to a {tool, args, returned, step} record.

    tool is the first whitespace token of the shell action. args.command is the
    full action, capped. returned is the observation with newlines flattened to
    spaces so each tool result stays on one line, capped. Carriage returns are
    left as-is to match the source observations.
    """
    tool_calls = []
    for i, step in enumerate(trajectory, start=1):
        action = (step.get("action") or "").strip()
        observation = (step.get("observation") or "").strip()
        tool = action.split()[0] if action else "noop"
        returned = observation[:RETURNED_CAP].replace("\n", " ")
        tool_calls.append(
            {
                "tool": tool,
                "args": {"command": action[:ACTION_CAP]},
                "returned": returned,
                "step": i,
            }
        )
    return tool_calls


def build_reasoning(trajectory):
    """Join the per-step thoughts into one reasoning trace.

    Steps with no thought are skipped, so the trace reads as the agent's own
    reasoning chain without empty entries.
    """
    blocks = []
    for i, step in enumerate(trajectory, start=1):
        thought = (step.get("thought") or "").strip()
        if thought:
            blocks.append(f"Step {i}: {thought[:THOUGHT_CAP]}")
    return "\n\n".join(blocks)


def build_output(info):
    """Return the agent's final patch from info.submission, CRLF normalized.

    info.submission is the agent's own submitted patch and is self-contained in
    the .traj, so we read it rather than a sibling patch.diff. Line endings are
    normalized to LF.
    """
    submission = info.get("submission")
    if not submission:
        return "(no submission recorded)"
    return submission.replace("\r\n", "\n")


def build_ground_truth(report_path):
    """Summarize a sibling SWE-bench report.json, or return None if absent.

    Emits the resolved flag and the FAIL_TO_PASS / PASS_TO_PASS success and
    failure counts, which is what a calibration comparison needs. The report is
    keyed by instance id with one entry per run.
    """
    if not os.path.exists(report_path):
        return None
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    if not isinstance(report, dict) or not report:
        return None
    instance_id = next(iter(report))
    entry = report[instance_id]
    tests = entry.get("tests_status", {})

    def counts(key):
        block = tests.get(key, {})
        return {
            "success": len(block.get("success", [])),
            "failure": len(block.get("failure", [])),
        }

    return {
        "instance_id": instance_id,
        "resolved": entry.get("resolved"),
        "fail_to_pass": counts("FAIL_TO_PASS"),
        "pass_to_pass": counts("PASS_TO_PASS"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert a SWE-bench .traj into shipready trace inputs."
    )
    parser.add_argument("input", help="path to the input .traj file")
    parser.add_argument(
        "--out-dir",
        required=True,
        help="directory to write tool_calls.json, reasoning.txt, output.txt",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"error: input not found: {args.input}")

    trajectory, info = load_traj(args.input)
    os.makedirs(args.out_dir, exist_ok=True)

    tool_calls = build_tool_calls(trajectory)
    reasoning = build_reasoning(trajectory)
    output = build_output(info)

    tool_calls_path = os.path.join(args.out_dir, "tool_calls.json")
    reasoning_path = os.path.join(args.out_dir, "reasoning.txt")
    output_path = os.path.join(args.out_dir, "output.txt")

    with open(tool_calls_path, "w", encoding="utf-8") as f:
        json.dump(tool_calls, f, indent=2)
    with open(reasoning_path, "w", encoding="utf-8") as f:
        f.write(reasoning)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    written = [tool_calls_path, reasoning_path, output_path]

    # A report.json sits beside the .traj in SWE-bench-Live pulls. When it is
    # there, emit the ground truth so calibration is one step.
    report_path = os.path.join(os.path.dirname(os.path.abspath(args.input)), "report.json")
    ground_truth = build_ground_truth(report_path)
    if ground_truth is not None:
        ground_truth_path = os.path.join(args.out_dir, "ground_truth.json")
        with open(ground_truth_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, indent=2)
        written.append(ground_truth_path)

    print(f"converted {args.input}")
    print(f"  steps: {len(trajectory)}")
    for path in written:
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
