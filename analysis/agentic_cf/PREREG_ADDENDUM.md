# Pre-registration addendum 1 — harness JSON-action parser defect + full re-run

**Written:** 2026-11-09T~11:55Z (before any *v2* model call). **PREREG.md frozen sha256:**
`e71e1d2f6b94e700ab4140306e76c98de0f4926321be9132eb26ad1b22d4e3b7` (unchanged; prompts, cases,
conditions, seeds, temperature, model, step budget, cost cap and analysis plan are unchanged).

## What happened

After scaling the first 18 runs (v1) I inspected transcripts because two `R5/stale_kb` runs
reported a submitted state with **no changed files** while their transcripts contained intended
`write_file` actions. Root cause is a **harness defect**, not a model/condition effect:

- the v1 action decoder used a greedy `{.*}` JSON match. deepseek-chat frequently wraps its one
  action in short prose or emits several JSON objects in one turn; those replies failed to parse
  and were answered with an "invalid JSON" nudge, so the intended tool action was **discarded**.
- consequence: v1 has mechanical, condition-asymmetric action loss (e.g. `invalid_json` counts
  5–6 in several wechat/engram runs; some runs "submitted" without the writes their transcripts
  show they intended). v1 also under-counted agent-created files in git-ignored trees
  (engram `.gitignore` ignores the skill-script directory), so v1 `changed_files` is not usable.

## Fix (before any v2 call)

1. `parse_action()` in `harness.py`: deterministic recovery of the **first complete JSON object**
   (fenced or plain, prose tolerated); one action still executed per turn, protocol violation
   nudged but not silently dropped.
2. Change accounting switched from `git status/diff` to a **filesystem manifest** baseline
   (`file_manifest`/`manifest_delta`, sha256 for files ≤2 MB) so files in git-ignored trees are
   recorded; the final diff force-stages only the changed paths (node_modules excluded).
3. No prompt template, task, case, condition, seed, temperature, model, step/token cap, stop rule
   or analysis-plan change. Secondary metric `kb_seen_in_tool_output` (added before this defect,
   after the v1 validation run) is unchanged.

## Decision: complete re-run of all 18 cells (v2)

Because the v1 loss is mechanical and not random across arms, **v1 is not used for the condition
comparison**. All **18** pre-registered cells are re-run under the identical frozen design after
the parser/tooling fix (not only failed cells; no selective re-run, no prompt/case tuning).
- v2 = `results/runs.jsonl` (primary), `results/transcripts/`, `results/diffs/`.
- v1 = `results_v1/runs_v1_parser_greedy.jsonl` (+ v1 transcripts/diffs/summary), retained for
  transparency as an instrument-robustness sensitivity, not as a condition result.
- Expected extra cost well inside the pre-registered ¥20 cap (v1 actual: ¥0.398).
- REPORT.md reports both versions, marks the v1 limitation explicitly, and uses v2 for all
  pre-registered outcomes/CIs/Fisher tests.

This addendum is frozen (sha256 in `PREREG_ADDENDUM.sha256`) before the first v2 call.
