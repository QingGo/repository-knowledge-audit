# PREREG — 2×2 "verified label × actual truth" experiment (chat model)

**Frozen:** 2026-11-09T01:22:48+08:00 (Asia/Shanghai), **before any API call of this experiment**.
This file and its analysis plan may not be changed after the first completion; any deviation is
recorded in §9 with a timestamp and reason. The runner refuses to start unless this file exists and
`--ack-prereg` is passed.

## 0. Why this experiment

External review of the AGENTVERIFY 2027 paper: the existing KB experiments show a verified header
hurting *stale* notes in some conditions, but existing data confounds the header with note
provenance (correct notes always carried a "verified" header; stale notes carried an
"older snapshot" header). This experiment runs a clean same-run 2×2 on the 54-task benchmark:
the **same two note bodies** (correct vs stale) are shown with either a **neutral header** or the
**verified header**, header being the only manipulation.

## 1. Design (fixed)

- Tasks: all 54 tasks in `kb-health/outcome_bench/conventions.py::TASKS` (7 families:
  masked_mean 8, shift_ce 8, topk 8, quantize 8, masked_softmax 8, ce_grad 8, stable_softmax 6).
- Arms (factor A = truth of note body, factor B = header):
  - `c1`    = correct (useful) note + **neutral** header `Project knowledge note:\n`
  - `c1ver` = correct (useful) note + **verified** header `Project knowledge note (verified conventions from the current repo):\n`
  - `c2`    = stale note + **neutral** header (same neutral string)
  - `c2ver` = stale note + **verified** header (same verified string)
  - Note bodies are exactly `TASKS[i]["useful"]` (correct) and `TASKS[i]["stale"]` (stale) rendered
    as `- <fact>` bullet lines. No other text is added or removed between arms.
- Cells: 54 tasks × 4 arms × 2 prompt-variant seeds = **432 completions**, one completion per cell.
- Seeds: `seed=0` → temperature **0.2**; `seed=1` → temperature **0.3**. The seed also controls the
  standard prompt-variant suffix already implemented by the reused builder (seed 0 → no extra
  sentence; seed 1 → "Keep the implementation minimal and robust; use only numpy.").
- Prompt construction: reuse `kb-health/outcome_bench/run_bench.py::prompt_for(task, cond, seed)`
  unchanged, with the module-level header map overridden per arm at call time:
  correct arms call `cond="c1"`, stale arms call `cond="c2"`; `HEAD["c1"]`/`HEAD["c2"]` are set to the
  arm's header (neutral or verified) for the duration of the call and restored afterwards. No other
  prompt text differs between the four arms; the hidden-test snippet paths of the existing
  `c1v`/`c2v`/`*f` variants are **not** used. `run_bench.py` itself is not edited.
- Model: `deepseek-chat` from `~/.has_pilot.env` (`DEEPSEEK_MODEL`), base URL from the same env file;
  API key is read via `probe_screen/run_probes.py::load_env` and never written to any output.
- Decoding: `temperature` as above, `max_tokens=2400`, JSON object response format, `stream=false`,
  one completion per cell, up to 5 transport-error retries (identical request; no re-prompting for
  a failing grade). Warm-up/cost: none.

## 2. Grading (fixed)

- Code is extracted exactly as in `run_bench.py`: `parse_json(raw)` then `parse_code(parsed, raw)`.
- Pass = hidden pytest suite of the task passes (`run_bench.run_tests(code, task["tests"])` returns
  `returncode == 0`), i.e. the same hidden grading as the paper's benchmark. No manual grading, no
  partial credit.
- Failure modes: empty code → fail; pytest non-zero → fail; runner error → fail. A cell with an
  unrecoverable API error is recorded with `pass=false, error=<msg>` and reported; a sensitivity
  analysis excluding API-error cells is reported as secondary.
- **Primary metric:** arm pass rate = mean pass over all cells in the arm (n=108 per arm).
- **Paired task-level metric:** for task `i`, `p_arm(i) = mean over the 2 seeds of pass ∈ {0, 0.5, 1}`.

## 3. Hypotheses (pre-registered; no post-hoc arm/condition changes)

Directional, two-sided 95% CIs + one-sided interpretation as stated:

- **H1 (label helps correct entries):** `c1ver − c1 > 0` on the paired task-level metric.
  Supported if the 95% bootstrap CI is entirely above 0; otherwise reported as not supported
  (estimate and CI always reported).
- **H2 (label on stale amplifies harm):** `c2ver − c2 < 0` on the paired task-level metric.
  Supported if the 95% bootstrap CI is entirely below 0; otherwise `H2` is **not** supported and the
  null is reported as such ("the verified header did not measurably worsen stale-note performance
  in this run").
- **H3 (harm asymmetry / difference-in-differences):** `DiD = (c1ver − c1) − (c2ver − c2)`.
  Supported as asymmetry if the 95% CI of `DiD` excludes 0; direction of the point estimate is
  reported literally (negative DiD = the label helps correct notes less/ hurts stale notes more than
  the reverse).
- **Secondary (descriptive, not hypothesis tests):** tokens per completion, total cost, latency,
  code length, per-family pass rates, per-seed (temperature) pass rates, and how many tasks change
  class (improved/worsened/tied). No adoption/decision probe is run.

## 4. Inference (fixed)

- Paired nonparametric bootstrap over the **54 tasks**: for each of 10,000 resamples, draw 54 task
  indices with replacement; compute the resampled mean of the per-task paired difference. Report the
  2.5/97.5 percentiles as the 95% CI, plus the point estimate (mean over the 54 task differences).
  RNG seed **20261109**, Python `random.Random`.
- Secondary exact-ish test: two-sided paired sign-flip permutation over task differences (100,000
  draws, same seed family) reported alongside the CI; the CI is the pre-registered decision rule.
- Counts improved/worsened/tied: per task, `improved` if diff > 0, `worsened` if diff < 0, `tied` if
  diff == 0 (this includes tasks where both arms score 0.5 etc.). Report counts for H1, H2, H3.
- Exact arithmetic: no rounding before analysis; report pass rates to 1 decimal pp and CIs in pp.

## 5. Cost cap and stopping (fixed)

- Hard cap: **¥1.5 total** (`run_probes.usage_cost`, DeepSeek off-peak prices hit 0.02 / miss 1.0 /
  out 4.0 CNY per M tokens). Projected cost from the existing chat benchmark ≈ ¥0.0012/completion,
  so the full 432 cells are expected to cost ≈ ¥0.5; the cap is a guard rail.
- Runner submits in a deterministic task/arm/seed order with 8 workers, writes each row as it
  arrives (resume-safe by `(tid, arm, seed)`), and stops submitting when cumulative cost ≥ ¥1.45.
- If stopped early: all analyses use completed cells only; coverage per arm is reported; no cell is
  added, dropped, or replaced after seeing its outcome.
- No API call may occur before this file's timestamp. If the API is unavailable the experiment is
  reported as not run (Lead is messaged immediately) and no result is fabricated.

## 6. Outputs (all under `analysis/verified_x_stale/`)

- `results/bench_x.jsonl` — one row per cell: `tid, family, arm, note_truth, header, seed,
  temperature, pass, tokens{...}, cost_cny, latency_s, code_len, error, prompt_sha256,
  prompt_chars, ts`.
- `results/prompts.jsonl` — the exact prompt text per cell (for audit; no key material).
- `results/cost_log.json` — cumulative cost, calls, per-arm cost; written after the run.
- `results/summary.json` — arm pass rates, paired contrasts, CIs, p, counts, tokens/cost,
  per-task table, sanity checks, prereg hash.
- `REPORT.md` — paper-ready 2×2 table, exact quotable sentences, limitations, cost, deviations.
- `run_x.py` — runner + analyzer (`--dry-run`, `--ping`, `--run`, `--analyze`, `--all`).

## 7. Sanity checks (must pass before the numbers are reported)

1. 54 tasks × 4 arms × 2 seeds = 432 expected cells; report actual row count and per-arm coverage.
2. Each arm's prompt contains exactly one header line (neutral or verified) and the intended note
   body; c1 vs c1ver prompts differ only in that header line (verified programmatically on a sample
   or all prompts via sha256 sets); likewise c2 vs c2ver.
3. c1versus-c2 same header? (factorial: headers match across truth arms) — programmatic check on all
   prompts.
4. Total cost ≤ ¥1.5; no API key string in any output file (grep for key length/prefix pattern and
   for the loaded key value; abort/report if found).
5. Per-arm n and total completions reported; API-error rows counted and listed.
6. Hidden-test grading on a known-good code snippet is out of scope; `run_tests("", tests)` must
   return False for every task (grading sanity, no API).

## 8. Reporting rules (fixed)

- The 2×2 table reports pass rate ± count (n=108) for each cell, with the paired contrasts and CIs.
- If H1/H2/H3 are not supported, the report states the null plainly (no spin, no subgroup rescue
  claimed as confirmation). Directional point estimates and CIs are always reported.
- Limitations are stated in `REPORT.md`: one model family (`deepseek-chat`), constructed/curated
  convention tasks (not organic repos), header-only manipulation (no document authority cues),
  temperature differs between the two prompt variants (0.2 vs 0.3), 2 seeds only, pass/fail binary
  grading with no partial credit, tasks clustered in 7 families (family correlation not modelled),
  and single run with no replications.

## 9. Deviations log

*(empty before the run; append timestamped entries only if execution deviates from the above)*
