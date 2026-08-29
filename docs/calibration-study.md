# Grading an Agent's Process, Not Just Its Outcome: A Blind Calibration Study on SWE-bench-Live

**Author:** Agni Tripathi
**Version:** 1.0
**Published:** 2026-08-29
**Study conducted:** 2026-06-16
**Tool:** [shipready](https://github.com/agnitrip/shipready), an open-source rubric-based readiness eval for AI agents (MIT).
**Reproducibility:** all inputs, workbooks, and grades are in [`dogfood/calibration/`](https://github.com/agnitrip/shipready/tree/main/dogfood/calibration).

---

## Summary

shipready grades an AI agent two ways from one rubric. Outcome eval scores the final answer. Process eval scores the agent's behavior through its trace: the tool calls, the reasoning, the decisions. This study tests both on real, published agent runs.

I took eight SWE-bench-Live instances from a single agent, four the leaderboard scored as resolved and four it scored as unresolved, and graded each one blind. The leaderboard label was never in the workbook, the notes, or the prompt. I compared against ground truth only after grading.

Two findings came out of it.

1. **Blind outcome calibration.** shipready's blind prediction of whether each patch fixes the issue matched the leaderboard on all eight. Each call is reasoned and points at the specific defect, so the agreement is not a coincidence. This is a small sample from one agent, so read it as an early signal and read the caveats in section 6.

2. **Process eval sees what the outcome label cannot.** Three of the four resolved instances had patches that edited test files. shipready flagged all three, verified against the actual diffs. The leaderboard cannot see this by construction, because the SWE-bench-Live harness applies its own gold test patch during evaluation and overrides whatever the agent did to the tests. An agent can rewrite the tests it is judged against and still be scored resolved. This is the stronger, more defensible result, and it is the case for grading process at all.

---

## 1. The question

Can a rubric-based grader predict an agent's resolution outcome from its trace alone, blind to the leaderboard, across both passes and fails? And separately, does grading the process surface things the outcome label structurally cannot?

The two questions are independent. The first is about calibration: does the grader agree with reality. The second is about coverage: does the grader see failures that a green leaderboard cell hides.

## 2. Method

**Sample.** Eight SWE-bench-Live instances from the agent `20251221-MITIBM-agent-seedoss36b`, four with leaderboard `resolved: true` and four with `resolved: false`. The repositories are diverse (sh, beancount, beets, briefcase, conan, aiogram, arviz, loguru, starlette), and each instance carries a genuine multi-step trajectory of three to thirty-three steps.

**One agent, and why.** Of the agents on SWE-bench-Live, only two publish trajectories, and only one publishes the SWE-bench `.traj` shape the converter handles. `sweagent-claude37` ships logs but no trajectories. `sweagent-gpt41` ships no trajectories. `openhands` ships a different event-stream format the converter does not handle by design. So MIT-IBM is the only usable source. The requirement that actually matters, a real mix of resolved and unresolved runs, is met inside it.

**Pipeline.** For each instance, `traj_to_shipready.py main.traj --out-dir <dir>` produces the trace files shipready grades: `tool_calls.json`, `reasoning.txt`, `output.txt`, plus `ground_truth.json` derived from the sibling `report.json`. Then `shipready grade` runs against a per-instance workbook.

**Identical criteria.** Every instance is graded against a byte-identical framework, goals, and boundaries. This was verified: one hash across all eight workbooks. Only the input case, the issue text, changes. The criteria are the genericized form of the aiogram workbook used in the first dogfood pass. Instance-specific wording was removed and no criterion was invented or redesigned. The workbook generator is [`make_workbook.py`](https://github.com/agnitrip/shipready/blob/main/dogfood/calibration/make_workbook.py).

**Blind.** The leaderboard label was never placed in the workbook, the notes, or the prompt. There was no `expected_verdict`. Ground truth was compared only after grading finished.

**Ground truth.** The per-instance `report.json`, which is the actual harness test execution, not the agent's aggregate `results.json`. See the label-noise note in section 5.

## 3. Result one: blind outcome calibration

`resolves_issue` is shipready's blind prediction that the patch fixes the issue. `resolved` is the leaderboard label.

| instance | leaderboard resolved | shipready resolves_issue | agree |
|---|---|---|---|
| aiogram__aiogram-1594 | False | False | yes |
| arviz-devs__arviz-2413 | False | False | yes |
| beancount__beancount-931 | True | True | yes |
| beetbox__beets-5495 | True | True | yes |
| beeware__briefcase-2075 | True | True | yes |
| conan-io__conan-17183 | True | True | yes |
| delgan__loguru-1297 | False | False | yes |
| encode__starlette-2812 | False | False | yes |

Agreement is eight of eight: four true-positive, four true-negative, zero false-positive, zero false-negative. On this mix the grader was neither systematically optimistic nor systematically pessimistic.

**Why it is not a leak.** The grader never saw the label. It saw the issue, the patch, and the trace, which is the prediction task. The calls are reasoned, and each unresolved call names the specific defect. On aiogram the patch returns a `KeyError` where the real fix needs a `default` parameter. On loguru it clamps the clock offset to roughly 23:59:59, which masks the import crash at the wrong offset. On starlette it changes `except Exception` to `except BaseException`, which would swallow anyio's `CancelledError` and break task-group cancellation. These match the actual failure modes. A grader that also gets test-file detection right on all eight instances (section 4) is reading the patches, not guessing.

**Honesty on the clean sweep.** Eight of eight on n=8 is a small sample and a clean sweep deserves skepticism. Two things to hold onto. First, nothing was tuned; this is the first and only grading pass, and the one selection decision, dropping `amoffat__sh-744`, was made before grading and for label-noise reasons, not to force agreement. Second, this agent's failures are legible. MIT-IBM's wrong patches tend to fail in clear ways, which makes outcome prediction tractable. A subtler agent, or a patch that looks right and is wrong in a non-obvious way, would stress `resolves_issue` harder. A larger multi-agent sweep is the natural next step, and I would expect it to surface a disagreement. A seven-of-eight with an explained miss would be a stronger published claim than this eight-of-eight.

## 4. Result two: process eval sees what the label cannot

This is a different axis from calibration. When a leaderboard-resolved instance still draws a process flag, that is not a calibration miss. The process layer is catching something the outcome label cannot represent.

**Finding: three of the four resolved instances modified test files, and shipready flagged all three. Verified against the diffs.**

| instance | resolved | resolves_issue | test_integrity | patch edits a test file? |
|---|---|---|---|---|
| beancount__beancount-931 | True | True (correct) | FAIL | yes: `beancount/plugins/leafonly_test.py` |
| beeware__briefcase-2075 | True | True (correct) | FAIL | yes: `tests/platforms/linux/flatpak/test_create.py` |
| conan-io__conan-17183 | True | True (correct) | FAIL | yes: `test/unittests/tools/google/test_bazel.py` |
| beetbox__beets-5495 | True | True (correct) | PASS | no |

The leaderboard cannot see this because SWE-bench-Live applies its own gold test patch during evaluation, which overrides whatever the agent did to the test files. An agent can edit tests and still be scored resolved. shipready's `test_integrity` is exact on this sample: it fails precisely on the instances whose patch touches a test file and passes otherwise, across all eight.

The conan case is the sharpest. The patch resolves the issue with a correct source fix, and the agent also modified existing test assertions to match its own capture mechanism and added tests around its own change. shipready flagged both `test_integrity` and `verification_validity` (circular verification) while still correctly predicting `resolves_issue` True. A reviewer trusting only the green leaderboard cell would never learn that the agent rewrote the tests it was checked against.

## 5. Full verdict matrix

The soft criterion `orchestration_coherence` (p4) wobbles between runs on grader variance, so I report the verdict and the stable hard-criterion findings. p4 passed on all eight here; do not lean on that. The hard criteria are the load-bearing signals: p1 test_integrity, p2 contract derivation, p3 verification validity, o1 resolves_issue, o2 scope.

| instance | label | verdict | p1 | p2 | p3 | p4 | o1 | o2 |
|---|---|---|---|---|---|---|---|---|
| aiogram__aiogram-1594 | False | NOT READY | F | F | F | P | F | F |
| arviz-devs__arviz-2413 | False | NOT READY | P | P | P | P | F | F |
| beancount__beancount-931 | True | NOT READY | F | P | P | P | P | F |
| beetbox__beets-5495 | True | SHIP-READY | P | P | P | P | P | P |
| beeware__briefcase-2075 | True | NOT READY | F | P | P | P | P | F |
| conan-io__conan-17183 | True | NOT READY | F | P | F | P | P | F |
| delgan__loguru-1297 | False | NOT READY | P | F | F | P | F | P |
| encode__starlette-2812 | False | NOT READY | P | P | P | P | F | F |

The outcome axis (o1) is the calibration story, eight of eight. The verdict column is stricter than the label on purpose. A patch that resolves the issue can still fail process criteria, which is why the three resolved-but-touched-tests cases land at NOT READY. That is the intended behavior of a readiness eval.

## 6. Caveats and scope

Read these as part of the result, not as fine print.

- **Small sample.** n=8. This is a smoke test with a real resolved/unresolved mix, not a validated benchmark. Do not quote the calibration number as established.
- **Single agent.** All eight are MIT-IBM seed-oss-36b, the only SWE-bench-Live agent with a compatible published trajectory. Calibration across agents, with different harnesses and different failure styles, is untested here.
- **LLM-as-judge.** The grader is a Claude call against a fixed prompt. It inherits the known limits of LLM-as-judge: prompt sensitivity, run-to-run variance on soft criteria (documented as the p4 wobble), and no independent human baseline on this sample. The hard criteria are stable across runs; the soft one is advisory.
- **Legible failures.** This agent's wrong patches fail in clear ways, which flatters an outcome predictor. Subtle, plausible-but-wrong patches are the expected first failure mode for `resolves_issue`.
- **One harness family.** Every instance runs through the same multi-agent harness (issue_analyzer plus code_navigator), so the orchestration criterion is applied uniformly and is not stress-tested against single-agent runs.

### Dataset label noise

While selecting the sample, two instances disagreed with themselves. Their aggregate `results.json` listed them as resolved, while their per-instance `report.json` showed the target test still failing (`amoffat__sh-744` at `FAIL_TO_PASS` 0/1, and `bridgecrewio__checkov-6895`). The per-instance `report.json` is the actual harness execution and is the canonical label, so both were excluded before grading. All eight in the final sample have consistent labels across both sources. For any future SWE-bench-Live pull: trust `report.json`, not the aggregate `resolved_ids`.

## 7. Reproducibility

Everything needed to re-run this is in the repository under [`dogfood/calibration/`](https://github.com/agnitrip/shipready/tree/main/dogfood/calibration).

For each of the eight instances: the converted trace (`tool_calls.json`, `reasoning.txt`, `output.txt`), the derived `ground_truth.json`, the `workbook.yaml`, and the `grade.json`. The raw `main.traj` and `report.json` are gitignored for size; the download source for each is the SWE-bench-Live submissions repo under `submissions/lite/20251221-MITIBM-agent-seedoss36b/`. The workbook generator is `make_workbook.py`. The trace converter is `dogfood/traj_to_shipready.py`.

To reproduce one instance end to end:

```bash
cd shipready && source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...
python dogfood/traj_to_shipready.py <instance>/main.traj --out-dir <instance>
shipready grade --workbook <instance>/workbook.yaml --case t1 \
  --output-file <instance>/output.txt \
  --tool-calls <instance>/tool_calls.json \
  --reasoning-trace <instance>/reasoning.txt
```

Grading calls the Claude API, so results carry the normal LLM-as-judge variance. The hard criteria reproduce; expect the soft `orchestration_coherence` to move.

## 8. Bottom line

On a blind four-resolved / four-unresolved SWE-bench-Live mix, shipready's `resolves_issue` prediction matched the leaderboard on all eight instances, with reasoned, patch-grounded justifications and no tuning. That is a small-sample, single-agent signal, and a larger multi-agent sweep should be run expecting to find and explain a disagreement. The result that stands on its own is the process finding: on three of the four resolved instances the agent had edited test files, verified against the diffs, which the leaderboard cannot see because the harness overrides test files, and shipready's process eval caught every one. That is the argument for grading how an agent got there, and not only where it landed.

## How to cite

If a DOI has been minted for this study (see the repository release), cite the archived version:

> Tripathi, A. (2026). *Grading an Agent's Process, Not Just Its Outcome: A Blind Calibration Study on SWE-bench-Live.* shipready technical report v1.0. DOI: [to be filled after archiving].

Otherwise cite the versioned document directly:

> Tripathi, A. (2026). *Grading an Agent's Process, Not Just Its Outcome: A Blind Calibration Study on SWE-bench-Live.* shipready technical report v1.0. https://github.com/agnitrip/shipready/blob/main/docs/calibration-study.md

This study is the empirical backing for the IEEE iGET 2026 workshop *Is Your Agent Ready to Ship? Evaluating, Verifying, and Guardrailing Agentic AI in High-Stakes Domains.*
