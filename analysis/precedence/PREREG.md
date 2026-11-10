# PREREG — source-of-truth precedence rule experiment (chat, 54 tasks)

**Frozen:** 2026-11-09T19:21:00+08:00 (Asia/Shanghai), **before any API call of this experiment**.
The sha256 of this file is recorded in `results/freeze.json` immediately after freezing and messaged
to the Lead; that hash is the pre-run fingerprint. This file is not edited after the first completion;
deviations, if any, are appended in §10 with timestamps (the runner refuses API calls without
`--ack-prereg` unless `results/freeze.json` matches).

## 0. Question

Can one fixed sentence that establishes a **source-of-truth precedence rule** reduce the harm of a
stale KB entry without hurting performance on a correct KB entry? The existing benchmark already
shows a large stale-vs-correct gap and that tests alone do not neutralize a stale note; this
experiment adds the rule sentence to the existing prompts and measures hidden-test outcomes.

**Relation to arXiv:2610.30571** (Stale Instruction Files Override the Code, 2026): that work reports
40 projects × Claude Code/Codex, 320 runs, 90.1% following a stale instruction even when the model
noticed the conflict, and that a one-sentence precedence statement raised code-following from 4.2%
to 91.4% and test pass from 89.4% to 100%. Our experiment is complementary and stricter in two ways:
(i) it measures **hidden-test task outcomes** (not stated choices or code-following), and (ii) it
tests the **harm direction on correct KB entries** (H2 non-inferiority), which that work did not
test. It is not a replication: our tasks, prompts, and model differ.

## 1. Design (fixed)

- Tasks: all 54 tasks in `kb-health/outcome_bench/conventions.py::TASKS` (7 families), ITT.
- Model: `deepseek-chat` from `~/.has_pilot.env` (`DEEPSEEK_MODEL`), base URL from the same file;
  key read via `probe_screen/run_probes.py::load_env`, never printed or written.
- Prompt base: `outcome_bench/run_bench.py::prompt_for(task, cond, seed)` unchanged for the control
  conditions `c1` (correct note, verified header), `c2` (stale note, older-snapshot header) and
  `c2f` (stale + full visible test suite). Seed variants are the builder's seeds 0 and 1 ("no extra
  sentence" / "Keep the implementation minimal and robust; use only numpy."), unchanged.
- Five new arms, each = one existing base prompt with **one fixed extra text inserted verbatim**
  immediately after the last note bullet (before the seed-variant sentence and before any visible
  test block; for `c1` no test block exists):

  | arm | base | inserted text |
  |---|---|---|
  | `p2`  | `c2`  | PRECEDENCE RULE (below) |
  | `p1`  | `c1`  | PRECEDENCE RULE (below) |
  | `p2f` | `c2f` | PRECEDENCE RULE (below) |
  | `w2f` | `c2f` | GENERIC WARNING (below) |
  | `p1f` | `c1f` | PRECEDENCE RULE (below) |

  **PRECEDENCE RULE (fixed, not tuned; verbatim):**
  > When repository knowledge conflicts with independently observable evidence (the task requirements, visible tests, or the project's own code and manifests), do not follow the knowledge entry. Use the authoritative project source of truth and report the conflict. If no conflict is detectable, proceed normally.

  **GENERIC WARNING (fixed; verbatim, same string as `run_mitigation.py::WARN`):**
  > Note: KB entries may be stale or wrong; verify claims against the code and tests when possible.

  Insertion mechanics: rendered note block = header line + `- <fact>` bullet lines; the inserted
  text is joined with one blank line (`"\n\n"` + text) after the last bullet. Thus `p2` vs `c2`,
  `p1` vs `c1` and `p2f` vs `c2f` prompts must be **byte-identical except for the inserted
  paragraph**; this is checked programmatically for all 540 prompts in `--dry-run` (removing the
  inserted paragraph reproduces the base prompt exactly). Note bodies, headers, and seed sentences
  are unchanged.

- Decoding (fixed, matching the existing control run): temperature **0.3 for both seeds**,
  `max_tokens=2400`, JSON-object response format, one completion per cell (no retries on
  pass/fail; up to 5 transport retries inside `run_probes.chat`), `stream=false`.
- Cells: 54 tasks × 5 arms × 2 seeds = **540 completions**, expected cost ≈ RMB 0.6–1.0.
- Cost cap RMB **3.0**; runner stops submitting when cumulative `usage_cost` ≥ RMB **2.7**.
  Workers ≤ 8; resume-safe by `(tid, arm, seed)`; rows written as they arrive; deterministic
  task→arm→seed order.

## 2. Controls (pre-existing data; no new control calls)

Controls `c1`, `c2`, `c2f` are the already-run 54-task chat rows in
`outcome_bench/results/bench_chat.jsonl` (file sha256 `1edef615…`), filtered to those three
conditions (324 rows; 54 tasks × seeds {0,1} each; model `deepseek-chat`; temperature 0.3 hardcoded
by `run_bench.py::one`). A byte-stable snapshot is frozen **before any API call** at
`analysis/precedence/results/controls_used.jsonl` (sha256 `69d87d13…`); this snapshot is the only
source of control denominators. It is a **cross-run control** (same task set, prompt builder, and
model, earlier execution) — a pre-registered limitation, not a hidden choice. No new control
completions are run, and the 540-cell budget is fixed.

## 3. Outcomes

- Pass = the task's hidden pytest suite passes (`run_bench.run_tests(code, task["tests"])`,
  returncode 0 — same hidden grader as the paper's benchmark); code extracted by
  `run_bench.parse_code(parse_json(raw), raw)`. Binary; no partial credit.
- Primary metric per arm: pass rate over all 108 draws (54 tasks × 2 seeds) and, for paired
  analysis, the **per-task score = mean pass over the 2 seeds** (0, 0.5, or 1).
- ITT: every task enters; API errors and no-code responses count as failures (recorded with
  `error`/`code_len=0`); no post-hoc exclusions. If a cell is missing, it is not fabricated:
  coverage is reported and the analysis is flagged as partial (no selective dropping).

## 4. Hypotheses (pre-registered; no post-hoc condition changes)

- **H1 (primary):** the precedence rule improves stale-note outcomes: `p2 > c2`.
  Analysis: exact one-sided paired sign test on per-task differences (non-tied tasks; H1 direction
  positive) plus a 1,000-resample task-level paired bootstrap (percentile 95% CI of the mean
  difference). **Decision rule:** H1 supported iff the one-sided exact sign-test p < .05.
- **H2 (harm check):** the rule is non-inferior on correct notes: `p1` vs `c1` with a
  **non-inferiority margin of −0.10** (absolute pass-rate). **Decision rule:** H2 supported
  (non-inferiority) iff the lower bound of the 95% paired-bootstrap CI of `p1 − c1` is > −0.10.
- **H3 (exploratory):** the rule helps more **without** full-test disclosure than with it:
  `DiD = (p2 − c2) − (p2f − c2f)`, two-sided task bootstrap 95% CI + two-sided sign test;
  reported descriptively (no alpha claim).
- **H4 (exploratory, descriptive):** specific rule vs generic warning under full disclosure:
  `p2f − w2f`, task bootstrap 95% CI; reported descriptively (no alpha claim).
- Secondary descriptive: tokens (prompt/completion), cost, latency, code length, per-family pass
  rates, per-seed rates; no adoption/decision probe.

## 5. Analysis (fixed)

- Per-task mean over available seeds; all contrasts paired over the 54 tasks (ITT).
- Exact sign test: binomial with p=0.5 over non-tied tasks, `math.comb` exact one-way tail;
  report n_tasks, improved/worsened/tied counts, p (one-sided for H1; two-sided for exploratory).
- Bootstrap: 1,000 resamples over tasks (with replacement), percentile 2.5/97.5 CI for the mean
  difference; RNG seed **20261109**; exactly 1,000 draws as pre-registered.
- Pass rates reported as counts/108 and percentages to 1 decimal; exact p values to 3 decimals;
  per-family table with family n (16 or 12 cells per family per arm) descriptive only.
- Costs: `usage_cost` per call (DeepSeek off-peak hit 0.02 / miss 1.0 / out 4.0 CNY per M tokens),
  summed per arm; report total and cap check.
- No adjustment for multiplicity on the primary H1; H2 is a separate non-inferiority rule; H3/H4
  are exploratory and reported as such without binary "supported" claims.

## 6. Sanity / integrity checks (must pass before reporting)

1. Exactly 540 rows after the run; coverage 108/108 per arm; 54 tasks × seeds {0,1}; 0 API errors
   expected (report actual).
2. 540/540 prompt diff-only checks: each `p2`/`p1`/`p2f`/`p1f` prompt equals its base prompt with
   the inserted paragraph removed; `w2f` likewise for the WARN paragraph; note bodies, headers,
   and seed sentences unchanged; every insertion occurs exactly once and after the note block.
3. `run_tests("", tests)` fails for all 54 tasks (grading sanity), no API call.
4. Cost ≤ RMB 3.0; no API key string in any output file (programmatic check).
5. `PREREG.md` sha256 at freeze (recorded in `results/freeze.json`) equals the pre-run fingerprint
   and its mtime precedes the first completion timestamp.
6. Hidden-test grading unchanged (`run_bench.run_tests`); control snapshot hash unchanged from
   `results/freeze.json`.

## 7. Stopping / cost rules (fixed)

- Hard cap RMB 3.0; stop at cumulative ≥ RMB 2.7 (check after each completion chunk).
- If stopped early: report coverage and analyze completed cells without adding/replacing cells;
  H1/H2 decision rules apply only if all 54 tasks have both seeds for the relevant arms, otherwise
  the analysis is labeled partial and no "supported" claim is made.
- No extra prompt tuning, no reruns of failed cells, no model change.

## 8. Outputs (write scope `kb-health/analysis/precedence/` + one fragment file)

- `results/precedence_chat.jsonl` — 540 cell rows (fields: tid, family, arm, base_cond, seed,
  temperature, pass, code_len, output tail, model, tokens, cost_cny, latency_s, prompt_sha256,
  inserted_kind, ts, error).
- `results/precedence_prompts.jsonl` — all 540 exact prompts (audit; no key material).
- `results/controls_used.jsonl` — frozen control snapshot (324 rows, see §2).
- `results/freeze.json` — PREREG sha256, control snapshot sha256, freeze timestamp.
- `results/cost_log.json`, `results/summary.json`, `results/task_table.tsv`,
  `results/dry_run.json` (runner/analyzer artifacts).
- `REPORT.md` — exact counts, CIs, p values, per-family breakdown, honest interpretation.
- `kb-health/paper_workshop/agentverify2027/fragments/precedence.md` — paste-ready prose/table rows
  + honest null/positive interpretation + relation to arXiv:2610.30571. (Do not edit
  `paper.md`/`supplement.md`.)

## 9. Reporting rules

- Report the 5 new arms plus the frozen controls in a single table, with the H1/H2 decision-rule
  outcomes stated explicitly. If the rule does not help stale notes, say so plainly and do not
  spin; if it helps but H2 shows more than a 10 pp harm on correct notes, report that trade-off.
- A positive H1 means the fixed precedence sentence improves hidden-test outcomes on stale notes
  in this benchmark; it does not show the rule is sufficient in organic repositories. A null H1
  means the sentence did not rescue the tasks under this prompt format; the paper must say that.
- H2 protects the two-sided story: a rule that fixes stale harm but degrades correct-KB
  performance is not an unconditional improvement.

## 10. Deviations log

*(empty before the run; append timestamped entries only if execution deviates)*
