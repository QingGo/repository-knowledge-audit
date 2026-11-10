# PREREG — independent model-family replication on MiMo (c0/c1/c2, 54 tasks)

**Frozen:** 2026-11-09T20:47:30+08:00 (Asia/Shanghai), **before any API call of this experiment**.
The sha256 of this file is recorded in `results/freeze.json` immediately after freezing and messaged
to the Lead; that hash is the pre-run fingerprint. This file is not edited after the first
completion; deviations (if any) are appended in §9 with timestamps.

## 0. Question and scope

The paper's core entry-level effects (a correct note improves hidden-test pass rate; a stale note
hurts it) were measured on DeepSeek (all-54-task ITT chat: useful−no-KB **+0.648**
[+0.528, +0.759], stale−no-KB **−0.111** [−0.194, −0.037]). External review asks whether these are
DeepSeek-specific. This experiment repeats the three core conditions on an **independent model
family** (MiMo, Xiaomi) with the benchmark unchanged, one prompt-variant seed, all 54 tasks ITT.
It is a **one-alias, one-seed replication**, not a family-general claim.

## 1. Design (fixed)

- Tasks: all 54 tasks in `kb-health/outcome_bench/conventions.py::TASKS` (all-task ITT; no
  KB-responsive subset).
- Conditions (3): `c0` = no knowledge note; `c1` = correct convention note (verified header);
  `c2` = stale note (older-snapshot header). Exactly the existing `run_bench.py::prompt_for(task,
  cond, seed)` prompts, unchanged.
- Seed: prompt-variant **seed 0 only** (no extra seed-1 sentence); one completion per cell.
- Cells: 54 tasks × 3 conditions × 1 seed = **162 completions**.
- Model: **MiMo** Xiaomi OpenAI-compatible endpoint. Env from `~/.mimo.env`
  (`MIMO_API_KEY`, `MIMO_BASE_URL`; never printed or stored). Model id copied from
  `/REPOS_ROOT/has-pilot/signal_bank/run_pilot.py`: **`mimo-v2.6-flash`**.
  Request format copied from the same file's `provider="mimo"` path: OpenAI chat-completions body
  with `thinking: {"type": "disabled"}`, `stream: false`, `max_completion_tokens: 2400`;
  base URL from `MIMO_BASE_URL` + `/chat/completions`. No `response_format` (the has-pilot MiMo
  path does not set one); code is extracted with `run_bench.parse_code(parse_json(raw), raw)`,
  which accepts a JSON `{"code": ...}` object or a fenced code block, unchanged.
- Decoding: temperature **0.3**, `max_completion_tokens=2400`, one completion per cell; up to 5
  transport-error retries inside the runner (identical request); no retry for a failing grade.
- Optional stage (pre-registered order, budget-gated): after the 162 core cells are complete, if
  **cumulative spend so far < RMB 4.0**, run `c0f` then `c2f` (54 × 2 = **108** more completions)
  for the visible-test-control boundary on this model family. If spend ≥ RMB 4.0, stop after the
  core and report the optional stage as not run. The optional arms are descriptive boundary
  analyses only; they are not part of H1/H2.

## 2. Grading (fixed)

- Hidden pytest via `run_bench.run_tests(code, task["tests"])`, returncode 0 = pass; code extracted
  by `run_bench.parse_code/parse_json`; no manual grading, no partial credit.
- API-error cells are recorded (`pass=false`, `error=...`) and included as failures (ITT);
  no-code responses are failures. No post-hoc exclusions.
- Primary metric: pass rate per condition over 108 draws (54 tasks × 1 seed).
- Paired metric: per-task pass ∈ {0,1}; contrasts per task (c1−c0, c2−c0).

## 3. Hypotheses (pre-registered; two co-primary directional tests, one-sided α=.05 each)

- **H1 (useful):** `c1 − c0 > 0` on all-54 ITT per-task pass differences.
- **H2 (stale harm):** `c2 − c0 < 0` on all-54 ITT per-task pass differences.
- **H3 (same direction as DeepSeek):** the signs of both estimates match the existing DeepSeek
  all-54 ITT effects (`+0.648` useful, `−0.111` stale); this is a direction-consistency statement,
  not a formal test. Magnitudes are compared descriptively (MiMo − DeepSeek), with the caveat that
  the DeepSeek numbers are from a different run/model family and are not a paired control.
- **Optional-arm descriptive (only if the optional stage runs):** `c2f − c0f`, `c2f − c2`,
  `c0f − c0` as the visible-test boundary for this family; no alpha claim.
- No multiplicity adjustment for H1/H2 (both pre-declared, one-sided, independent directions);
  exact p values always reported. Per-family and per-task breakdowns are descriptive.

## 4. Analysis (fixed)

- Exact one-sided paired sign test over the 54 task differences, non-tied tasks only (binomial
  p=0.5, exact tails; H1 greater, H2 less).
- Paired nonparametric bootstrap over tasks: 1,000 resamples (RNG seed **20261109**), percentile
  95% CI of the mean difference; report absolute pass-rate differences and pp.
- Report improved / worsened / tied counts per contrast; per-task table.
- Per-family pass rates per condition (descriptive, n = 16 cells per family, 12 for stable_softmax).
- Tokens and cost: MiMo real-time pricing copied from has-pilot `run_pilot.py::cost_cny`
  (provider="mimo"): **input CNY 1.0/M, output CNY 2.0/M**, cost = pt/1e6*1.0 + ct/1e6*2.0.
  Log prompt/completion/total tokens, latency, finish_reason, attempts, full raw usage object.
- No adjustment or subset selection; all 54 tasks, all cells.

## 5. Validation protocol (before the full run)

- **First 5 API calls** are the `c0` cells of the first 5 tasks in TASKS order (seed 0). They are
  part of the 162 cells (not extra): the runner is resume-safe by `(tid, cond, seed)`, so the full
  run continues from them.
- The validation pass must show: HTTP success from the MiMo endpoint, model id accepted,
  non-empty response, code extraction succeeds or is recorded, hidden pytest executes and returns a
  result, and cost/tokens logged. If the endpoint/model id fails after the retry budget: **stop and
  report immediately** (Lead message); no results are fabricated and no substitute model is used.
- Budget cap for the whole experiment: RMB **10.0** hard cap; stop submitting when cumulative spend
  ≥ RMB **8.0** (the expected cost is ≈ RMB 0.5–1.5 for core+optional). Core cells are submitted
  first, in deterministic task→condition order; optional arms only after the core is complete.

## 6. Sanity / integrity checks (must pass before reporting)

1. Exactly 162 core rows (or report coverage); 54 tasks; conditions c0/c1/c2; seed 0 only; 0 API
   errors expected (report actual).
2. Prompts: 162/162 prompt texts recorded in `results/mimo_prompts.jsonl` and equal to
   `run_bench.prompt_for(task, cond, 0)` byte-for-byte (recomputed at analysis time).
3. Grading sanity (no API): `run_tests("", tests)` fails for all 54 tasks.
4. Cost ≤ RMB 10; no API key string in any output file (programmatic check); key never printed.
5. `PREREG.md` sha256 at freeze (recorded in `results/freeze.json`) equals the file hash used before
   the first call, and PREREG mtime precedes the first completion timestamp.
6. Optional stage (if run): 108/108 rows, both arms complete, same checks; otherwise reported as
   not run.

## 7. Outputs (write scope only)

`kb-health/analysis/model_family_mimo/`: `PREREG.md`, `run_mimo.py`,
`results/mimo_chat.jsonl` (all cells), `results/mimo_prompts.jsonl`, `results/freeze.json`,
`results/cost_log.json`, `results/c0v_validation.json`, `results/summary.json`,
`results/task_table.tsv`, `REPORT.md`; and the single fragment
`kb-health/paper_workshop/agentverify2027/fragments/model_family_mimo.md`.
Do not edit `paper.md`/`supplement.md` or any other project file.

## 8. Reporting rules

- Report MiMo pass rates for c0/c1/c2, the paired ITT contrasts with 95% CIs and exact sign-test p,
  improved/worsened/tied counts, per-family descriptive table, tokens/cost/latency, and a direct
  comparison with the DeepSeek all-54 ITT numbers (+0.648 / −0.111).
- State honestly that this is **one model alias, one prompt-variant seed**, with no provider-side
  version pin (alias echoed by the API), and therefore evidence about direction for one additional
  model family, not a family-general claim.
- If H1 or H2 is not replicated, report the null honestly; do not substitute the KB-responsive
  subset or a different seed. If the optional boundary arms run, label them descriptive/information
  upper bounds, not maintenance interventions.

## 9. Deviations log

*(empty before the run; append timestamped entries only if execution deviates)*
