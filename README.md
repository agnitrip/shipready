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

```
git clone https://github.com/agnitrip/shipready.git
cd shipready
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Grading calls the Claude API, so set a key:

```
export ANTHROPIC_API_KEY=sk-ant-...
```

## Quick start

The repo ships two worked examples: a generic research assistant (outcome eval)
and a tool-using research assistant (process eval). Start with the first.
Validate the workbook, list its cases, then grade a sample output against case
`t1`.

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

## How grading works

For each test case, shipready builds a prompt that contains the workbook goals,
boundaries, and framework, the test case input and expected behavior, and the
candidate output. It asks Claude to return a pass or fail verdict per criterion
with a one or two sentence justification, then parses that into the report. Run
with `--verbose` to see the full prompt. Nothing about the judgment is hidden.

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
process criterion has no relevant trace artifact, it fails with a missing-trace
justification.

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
