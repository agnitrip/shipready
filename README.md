# shipready

**Is your agent ready to ship?**

shipready answers that question with a structured, rubric based eval. You write
a workbook that defines what the agent is for and how to grade it, then grade
the agent against it. The result is a ship-readiness report card: a pass or fail
verdict per criterion, with a short justification for each.

shipready grades two ways in one tool. Outcome eval scores the agent's final
output. Process eval scores the agent's behavior through its trace (tool calls,
reasoning, decisions, escalations), for the many agents whose output is
open-ended or judgment-dependent. A single workbook can mix both.

## The three-layer thesis

Most agent evals tell you a number without telling you what the number means.
shipready is built in three layers so the judgment stays legible.

1. **Workbook layer (shipped).** A per-agent YAML rubric with four parts:
   Goals (what the agent is for), Boundaries (lines it must not cross),
   Framework (the grading criteria, each targeting the output or the agent's
   process), and a Data Set (the test cases). This is the contract you grade
   against.

2. **AI-as-expert-evaluator layer (roadmap).** Synthetic expert reviewer prompts
   that grade like a domain expert when you have no human baseline to compare
   against.

3. **Headline metric layer (roadmap).** A single configurable output-fidelity
   score. Similarity to a human baseline, escalation rate, or a metric you
   define for your domain.

Today shipready gives you layer 1, with both outcome and process eval, plus the
Claude grader. v1 adds layers 2 and 3.

## Install

Requires Python 3.11 or newer.

```
pip install shipready
```

To work on shipready itself, install from source instead:

```
git clone https://github.com/agnitrip/shipready.git
cd shipready
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Grading calls the Claude API, so set a key:

```
export ANTHROPIC_API_KEY=sk-ant-...
```

## Quick start

The repo ships two worked examples: a generic research assistant (outcome eval)
and a tool-using research assistant (process eval). The commands below read these
files from the repo, so clone it to follow along (the from-source steps above do
that). If you installed from PyPI to run shipready on your own agent, point
`--workbook` at your own YAML instead.

Start with the first example. Validate the workbook, list its cases, then grade a
sample output against case `t1`.

```
shipready validate --workbook examples/research_assistant.yaml

shipready cases --workbook examples/research_assistant.yaml

shipready grade \
  --workbook examples/research_assistant.yaml \
  --case t1 \
  --output-file examples/sample_outputs/research_assistant_t1_good.txt
```

You get a report card like this:

```
==============================================================
shipready report  |  agent: research_assistant
case: t1  |  model: claude-opus-4-8
==============================================================
[PASS] c1  source_quality  (well_sourced)
       Every substantive claim points to a checkable UN, WHO, or UNICEF source.

[PASS] c2  factual_grounding  (grounded)
       Figures and drivers match the cited sources with no invented references.

... one block per criterion ...
--------------------------------------------------------------
5/5 criteria passed  ->  SHIP-READY
--------------------------------------------------------------
```

The grade command exits 0 when every criterion passes and 1 otherwise, so you
can wire it into CI.

### Supplying the agent output

shipready grades the output your agent actually produced. In v0 you run your
agent yourself and hand its output to shipready in one of three ways:

```
# from a file
shipready grade --workbook w.yaml --case t1 --output-file out.txt

# inline
shipready grade --workbook w.yaml --case t1 --output "the agent answer"

# piped on stdin
my-agent --case t1 | shipready grade --workbook w.yaml --case t1
```

Add `--verbose` to print the exact prompt sent to Claude, and `--json` to get
the report as JSON instead of a text card.

## Workbook structure

A workbook is one YAML file describing one agent.

```yaml
agent_name: research_assistant
description: One line on what the agent does.

goals:           # what the agent is for
  - id: g1
    description: "..."
    sub_goals: ["..."]

boundaries:      # lines the agent must not cross
  - id: b1
    name: stay_in_scope
    what_it_means: "..."
    example: "..."

framework:       # the grading criteria, each scored pass or fail
  - id: c1
    criterion: source_quality
    grades_what: "..."
    pass_label: well_sourced
    fail_label: weak_sourcing
    target: output      # output (default) or process

data_set:        # the test cases
  - id: t1
    input: "..."
    expected_behavior: "..."
    notes: "..."
    # optional trace artifacts, graded by process criteria:
    # tool_calls: [...]
    # reasoning_trace: "..."
    # decisions_log: [...]
    # escalation_events: [...]
```

Goals and boundaries give the grader context. The framework is what actually
gets scored: each criterion resolves to pass or fail, and a case is ship-ready
only when every criterion passes. The pass and fail labels in the workbook are
the canonical labels, so a report never drifts from your rubric wording.

Each criterion has a `target` of `output` (the default) or `process`. A
`TestCase` may carry optional trace artifacts, `tool_calls`, `reasoning_trace`,
`decisions_log`, and `escalation_events`, which process criteria are graded
against. All of these are optional, so v0 output-only workbooks keep working
unchanged.

See `examples/research_assistant.yaml` for a complete output-only example with
five criteria and three test cases, and `examples/tool_using_research_assistant.yaml`
for a process-eval example that mixes both kinds of criteria.

## What shipready grades

For each test case, shipready sends Claude a fixed set of inputs, and only the
framework criteria are actually scored.

**Inputs the grader sees:**

- Agent name and one-line description.
- Workbook goals, with sub-goals.
- Workbook boundaries (name, what-it-means, example).
- Workbook framework: each criterion with its `target` (output or process).
- The test case input and expected behavior.
- The candidate agent output.
- Trace artifacts if supplied: `tool_calls`, `reasoning_trace`,
  `decisions_log`, `escalation_events`.

**What is context (used but not scored directly):**

- Goals, boundaries, expected behavior, and the test case input. These help the
  grader understand why a criterion exists. They are not graded themselves.

**What is scored:**

- Every criterion in the framework. Each criterion has a target. Output criteria
  are graded against the candidate output. Process criteria are graded against
  the relevant trace artifact.

**What Claude returns (parsed into the report):**

- For each criterion: pass or fail, plus a one or two sentence justification
  grounded in the artifact it targeted.

## How a criterion gets graded

For each test case, shipready builds a prompt containing the inputs listed
above. Claude returns a verdict per criterion. The grader applies these rules:

1. Each criterion has a target (output or process). The grader judges the
   criterion against the matching artifact.
2. The verdict is pass or fail. A one or two sentence justification grounded in
   the targeted artifact accompanies each verdict.
3. The pass and fail labels in your report come from the workbook, not Claude's
   wording. A report never drifts from your rubric language.
4. When a criterion targets process and the relevant trace artifact is missing,
   the criterion fails with a missing-trace justification. Process criteria
   require their trace.
5. When a criterion targets output and the output is missing, the criterion
   fails when content is required.

Run with `--verbose` to see the exact prompt Claude received. Nothing about the
judgment is hidden.

What `--verbose` prints (abbreviated):

```
===== SYSTEM =====
[grading instructions: judge output criteria against the output, process
criteria against the trace, and fail a process criterion whose trace is missing]

===== USER =====
You are grading the output and behavior of an AI agent named "research_assistant".

Agent purpose: [...]

GOALS (what the agent is for):
- [g1] Answer the user's research question accurately and concisely.
    - [...]
- [g2] Be honest about the limits of available evidence.
    - [...]

BOUNDARIES (lines the agent must not cross):
- [b1] no_fabricated_sources: [...]
- [b2] stay_in_scope: [...]
- [b3] flag_uncertainty: [...]

GRADING FRAMEWORK (score each criterion pass or fail, against its target):
- id: c1
  criterion: source_quality
  target: output
  grades_what: [...]
  pass means: well_sourced
  fail means: weak_sourcing
- [... c2 through c5 ...]

TEST CASE [t1]
Input given to the agent:
[...]

Expected behavior:
[...]

AGENT OUTPUT TO GRADE:
[...]

INSTRUCTIONS:
Grade every criterion in the framework against the artifact named by its target.
[...] Respond with a single JSON object and nothing else [...].
```

What `--json` returns:

```json
{
  "agent_name": "research_assistant",
  "case_id": "t1",
  "model": "claude-opus-4-8",
  "grades": [
    {
      "criterion_id": "c1",
      "criterion": "source_quality",
      "passed": true,
      "label": "well_sourced",
      "justification": "Each substantive claim is tied to a credible, relevant source (UN IGME, WHO, UNICEF) that a reader could locate and check."
    },
    {
      "criterion_id": "c2",
      "criterion": "factual_grounding",
      "passed": true,
      "label": "grounded",
      "justification": "The figures (60% decline, ~93 to ~37 per 1,000) and the named drivers align with well-known UN/WHO data, and the citations point to real publications rather than invented references."
    },
    {
      "criterion_id": "c3",
      "criterion": "scope_adherence",
      "passed": true,
      "label": "in_scope",
      "justification": "The output stays within research scope, providing a sourced summary without taking actions or giving regulated advice."
    },
    {
      "criterion_id": "c4",
      "criterion": "completeness",
      "passed": true,
      "label": "complete",
      "justification": "The answer covers both parts: the approximate decline figure and three distinct largest contributors."
    },
    {
      "criterion_id": "c5",
      "criterion": "uncertainty_handling",
      "passed": true,
      "label": "calibrated",
      "justification": "The output explicitly flags that attributing exact shares to any single factor is uncertain and frames the three as leading contributors rather than a precise ranking."
    }
  ]
}
```

## PM-facing summary

Add `--summary` to prepend a short summary block above the report card: what
went well, flags or warnings, an optional thing to watch, and a one-line
verdict. This is the legible artifact a reviewer skims instead of reading every
per-criterion justification.

```
shipready grade --workbook examples/research_assistant.yaml --case t1 \
  --output-file examples/sample_outputs/research_assistant_t1_good.txt --summary
```

The summary is a second Claude call on top of the grading call, so `--summary`
doubles the API cost of a grade. If the synthesis call fails, shipready prints a
warning and falls back to the bare report. With `--json`, the summary is added
under a `summary` field with `went_well`, `flags`, `watch`, and `verdict`. Off
by default.

## Grading a whole workbook

Use `--all` to grade every case in a workbook in one run (use it instead of
`--case`). One case failing to grade does not silently drop it: the failure is
reported and the command exits non-zero. The supplied output applies to every
case, so `--all` fits workbooks whose cases carry their own trace artifacts.
Trace flags are single-case only; embed traces in the workbook for batch runs.

`--out PATH` writes the JSON report to a file while the human card still prints
to stdout. The file is written only after grading succeeds, so a transient
error cannot leave a truncated or zero-byte file the way a shell redirect can.

```
shipready grade --workbook examples/tool_using_research_assistant.yaml --all \
  --output-file examples/sample_outputs/tool_using_t1_output.txt --out reports.json
```

## Two eval paradigms

shipready supports two ways to grade an agent in one tool:

**Outcome eval.** Grade the agent's final output against rubric criteria. Works
when the output is evaluable.

**Process eval.** Grade the agent's behavior by inspecting trace artifacts (tool
calls, reasoning, decisions, escalations). Works when the output is open-ended
or the correct answer is judgment-dependent. Most production agents need this.

A single workbook can mix both. Mark each criterion with `target: output` or
`target: process`. A process criterion is graded against the trace; an output
criterion is graded against the answer.

## Supplying trace artifacts

When using process criteria, supply the agent's trace alongside the output:

```
shipready grade \
  --workbook examples/tool_using_research_assistant.yaml \
  --case t1 \
  --output-file examples/sample_outputs/tool_using_t1_output.txt \
  --tool-calls examples/sample_outputs/tool_using_t1_tool_calls.json \
  --reasoning-trace examples/sample_outputs/tool_using_t1_reasoning.txt
```

The trace flags are `--tool-calls`, `--reasoning-trace`, `--decisions`, and
`--escalations`. Artifacts can also be embedded directly on a test case in the
workbook; a CLI flag overrides the workbook value when both are present. If a
process criterion is graded with no trace supplied, shipready never lets it pass
silently: the verdict is downgraded to at most a warn and the justification
states that it was graded from the output self-report with no trace.

## Roadmap

Process eval ships in 0.1.0. Remaining roadmap:

- **Layer 2: AI-as-expert-evaluator.** Synthetic expert reviewer prompts for
  domains with no human baseline.
- **Layer 3: headline metric.** A configurable output-fidelity score
  (baseline similarity, escalation rate, or a custom metric).
- **Adapters.** Native framework integrations that capture traces directly, so
  you grade real runs without copying artifacts by hand.

## License

MIT. See [LICENSE](LICENSE).
