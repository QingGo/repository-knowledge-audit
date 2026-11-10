# REPORT — 2×2 experiment: verified header × correct/stale note (deepseek-chat, 54 tasks)

**Status: COMPLETE (pre-registered; frozen protocol executed without deviations).**
PREREG: [`PREREG.md`](PREREG.md), sha256 `e59c6fba22f8cf34aed52dbe494c7a466641a55bd588ac4381d8656e408d57cc`,
frozen 2026-11-09T01:23:05+08:00, **before** the first completion (2026-11-09T01:25:16+08:00);
first completion row and all sanity checks are in [`results/summary.json`](results/summary.json) and
[`results/cost_log.json`](results/cost_log.json).

## TL;DR

Clean same-run 2×2 on the 54-task convention benchmark (`deepseek-chat`, 432 completions,
¥0.4994, 0 API errors): the verified header raised pass rate on **correct** notes from
**75.0% (81/108)** to **80.6% (87/108)** (+5.56 pp; paired task bootstrap 95% CI
**[0.00, +12.04]**, sign-flip p=.154; 5 tasks improved, 1 worsened, 48 tied) — directionally
positive but **not supported** under the pre-registered CI rule. Stale notes collapsed to
**0/108 in both header arms**, so the "verified header amplifies stale harm" hypothesis is
**not supported and not estimable** in this design (floor effect). H3 (difference-in-differences)
is numerically identical to H1 because the stale arms have zero variance.

## 2×2 table (paper-ready)

| note truth | neutral header | verified header | Δ (verified − neutral) |
|---|---:|---:|---:|
| **correct** (`useful` conventions) | 81/108 = **75.0%** | 87/108 = **80.6%** | **+5.56 pp** [0.00, +12.04], p=.154 |
| **stale** (`stale` conventions) | 0/108 = **0.0%** | 0/108 = **0.0%** | 0.00 pp [0.00, 0.00], p=1.0 |

Cells are hidden-pytest pass counts / 108 cells (54 tasks × 2 prompt-variant seeds; deepseek-chat;
seed 0 T=0.2, seed 1 T=0.3). Header strings: neutral `Project knowledge note:`;
verified `Project knowledge note (verified conventions from the current repo):`.

LaTeX (for the paper):

```latex
\begin{table}[t]
\centering\small
\begin{tabular}{llrr}
\toprule
note content & header & pass rate & paired $\Delta$ (95\% CI) \\
\midrule
correct & neutral & 81/108 (75.0\%) & \multirow{2}{*}{$+5.56$ pp $[0.00,+12.04]$, $p=.154$} \\
correct & verified & 87/108 (80.6\%) & \\
stale & neutral & 0/108 (0.0\%) & \multirow{2}{*}{$0.00$ pp (floor)} \\
stale & verified & 0/108 (0.0\%) & \\
\bottomrule
\end{tabular}
\caption{Clean 2$\times$2 (header $\times$ note truth; 54 tasks $\times$ 2 seeds $\times$
4 arms = 432 chat completions, deepseek-chat). The verified header does not measurably help
correct notes and does not measurably worsen stale notes; stale notes fail regardless
(0/108, floor). Paired task-level bootstrap, 10,000 resamples, seed 20261109.}
\end{table}
```

## Pre-registered contrasts (paired over 54 tasks)

Per-task score = mean pass over the two prompt-variant seeds; contrast = mean over the 54
task-level differences; bootstrap = 10,000 task resamples (seed 20261109); sign-flip p = 100,000
two-sided paired sign flips.

| hypothesis | contrast | estimate | 95% CI | sign-flip p | improved / worsened / tied | verdict |
|---|---|---|---:|---:|---:|---|---|
| **H1** label helps correct notes | c1ver − c1 | **+5.56 pp** | [0.00, +12.04] | .154 | 5 / 1 / 48 | **not supported** (CI not entirely > 0) |
| **H2** label on stale amplifies harm | c2ver − c2 | **0.00 pp** | [0.00, 0.00] | 1.000 | 0 / 0 / 54 | **not supported** (both arms 0/108) |
| **H3** harm asymmetry (DiD) | (c1ver−c1) − (c2ver−c2) | **+5.56 pp** | [0.00, +12.04] | .154 | 5 / 1 / 48 | **not supported**; equals H1 because stale arm has zero variance |

Exact values (unrounded, as computed from the 432 cells): H1 mean `+5.555556 pp`, bootstrap 95% CI
`[0.000000, +12.037037]`, sign-flip `p=.154338`, improved/worsened/tied `5/1/48`; H2 mean `0.0`,
CI `[0.0, 0.0]`, p=1.0, `0/0/54`; H3 identical to H1 (`+5.555556`, `[0.000000, +12.037037]`,
`p=.154338`, `5/1/48`). The H1 CI's lower bound is exactly 0.0 because 48/54 task differences are
ties; the pre-registered rule ("CI entirely above 0") is therefore not met.

Improved tasks (H1): `A3_inf_uniform_f32` (+0.5), `G7_prev_valid_keep` (+0.5),
`K8_low_asc_list` (+1.0), `M7_BS_zeros_f32` (+1.0), `Q8_channel_127_trunc` (+0.5);
worsened: `Q6_channel_448_trunc` (−0.5). Draw-level discordance on correct arms:
both pass 79, only c1 passes 2, only c1ver passes 8, neither 19.

**Honest null statement (H2):** *In this run the verified header did **not** measurably worsen
stale-note performance; stale notes failed the hidden tests in every one of 108 cells regardless
of the header. The null is not evidence that verification labels are harmless — with the stale arms
at a 0% floor, this design cannot test amplification below the floor.*

## Secondary outcomes (descriptive, not hypotheses)

| arm | pass | completion tokens (mean) | prompt tokens (sum) | code len (mean) | latency (mean) | cost (CNY) |
|---|---:|---:|---:|---:|---:|---:|
| c1 (correct, neutral) | 81/108 | 226.7 | 20,718 | 610.2 | 3.84 s | 0.1186 |
| c1ver (correct, verified) | 87/108 | 222.7 | 21,474 | 615.0 | 3.90 s | 0.1177 |
| c2 (stale, neutral) | 0/108 | 260.5 | 19,482 | 705.1 | 4.21 s | 0.1320 |
| c2ver (stale, verified) | 0/108 | 256.4 | 20,238 | 707.6 | 4.21 s | 0.1310 |
| total | 168/432 | — | 81,912 | — | — | **0.4994** |

- Prompt tokens rise by 756 tokens across 108 verified-header calls (+7 tokens/prompt, the header
  length); completion tokens fall 1.7% for correct notes and 1.6% for stale notes; code length
  changes <1%. The pass-rate difference is therefore not an output-length artefact.
- Per seed (temperature): c1 41/54 (T=.2) → c1ver 44/54; c1 40/54 (T=.3) → c1ver 43/54.
  The H1 direction is identical (+3 passing cells in each seed), so the pooled estimate is not
  driven by one temperature.
- Per family (pass rate, neutral → verified, correct note): masked_mean 87.5%→100%,
  masked_softmax 93.8%→100%, topk 56.3%→68.8%, ce_grad 50.0%→56.3%, quantize 93.8%→93.8%,
  shift_ce 50.0%→50.0%, stable_softmax 100%→100%; all stale-family cells were 0/16 (or 0/12).
  The H1 gain is concentrated in 3 families; the pooled test is the only pre-registered one.
- API errors: 0/432; no-code responses: 6 cells (4 in stale arms, 2 in c1), all counted as fails
  per the pre-registered rule.

**Corroboration (descriptive, different run, not pre-registered):** the new verified-header
correct-note arm reproduces the existing outcome-bench `c1` condition exactly — 87/108 in both
runs — and the old "older repo snapshot" header arm (5/108) vs the new neutral-header stale arm
(0/108) suggests the old, hedged provenance header was slightly less destructive than no provenance
cue at all, but this cross-run comparison is confounded by time/temperature and is not used in the
hypothesis tests.

## Protocol and provenance

- Design and analysis fixed in `PREREG.md` before any API call (sha256 above; file mtime
  01:23:05+08:00 < connectivity-ping timestamp 01:25:09+08:00 < first completion timestamp
  01:25:16+08:00; see `results/ping.json`, `results/cost_log.json`).
- 54 tasks × 4 arms × 2 prompt-variant seeds = **432/432 cells**, per-arm coverage 108/108/108/108.
- Hidden grading unchanged: `outcome_bench/run_bench.py::run_tests` (pytest returncode == 0); code
  extraction via `run_bench.py::parse_code`; prompts built by `run_bench.py::prompt_for` unchanged,
  with only the module-level header string swapped per arm (216/216 header-only prompt checks and
  432/432 note-body checks passed; every header appears exactly once).
- Model `deepseek-chat` via `~/.has_pilot.env` (key never printed/logged; programmatic check: key not
  present in any output file). Temperature 0.2 (seed 0) / 0.3 (seed 1), max_tokens 2400,
  JSON-object response format, one completion per cell, 0 API errors.
- Cost: **¥0.4994** for the 432 cells (cap ¥1.5, respected; per-arm cost above). One extra
  connectivity call before the run cost ¥0.000063 and is recorded in `results/ping.json`; it is not
  one of the 432 cells and is excluded from all analyses.
- Timing: cells written 01:25:16–01:29:12 (+08:00).

## Limitations (also in PREREG §8)

1. **One model family** (`deepseek-chat`); no reasoner/other provider replication.
2. **Constructed, curated convention tasks** (54 tasks, 7 families), not organic repositories;
   task-level bootstrap treats tasks as exchangeable but family correlation is not modelled.
3. **Header-only manipulation**: no document authority cues, no source links, no freshness
   metadata — the verified header is a short phrase, not a verified *pipeline*.
4. **Floor effect in the stale arms** (0/108 both) means H2/H3 cannot detect harm amplification;
   a subtler stale manipulation (partially wrong notes, low-salience conflicts) is needed to test
   amplification. This is the main design limitation and the reason the H2 null is only a null.
5. **Two prompt-variant seeds only**; temperature is confounded with the seed variant
   (0.2 vs 0.3) and cannot be separated.
6. **Binary hidden-test grading**, no partial credit; pass/fail is the only outcome (no
   decision-adoption probe, as pre-registered).
7. Single run, no replications; the H1 estimate (+5.56 pp, CI touching 0) is compatible with both
   a small positive effect and no effect.

## Deviations

None to the pre-registered protocol or analysis. (An analysis-helper bug in the
`prereg_frozen_before_first_call` sanity computation was fixed before results were reported; it does
not touch the data, hypotheses, or estimates. The pre-run connectivity ping is documented above and
in `results/ping.json`.)

## Files

| file | contents |
|---|---|
| `PREREG.md` | frozen design/hypotheses/analysis plan (sha256 above) |
| `run_x.py` | runner + analyzer (`--dry-run`, `--ping`, `--run`, `--analyze`, `--all`) |
| `results/bench_x.jsonl` | 432 per-cell rows (condition, seed, temperature, pass, tokens, cost, latency, code length, prompt hash, error) |
| `results/prompts.jsonl` | exact 432 prompts (audit; no key material) |
| `results/cost_log.json` | cell count, per-arm cost, cap check, prereg hash/mtime, first/last row timestamps |
| `results/summary.json` | arm rates, 2×2 table, paired contrasts + CIs + p, counts, per-family table, tokens, sanity checks |
| `results/task_table.tsv` | per-task pass rates per arm + H1/H2/H3 differences |
| `results/dry_run.json`, `results/ping.json` | pre-run prompt/grading checks; connectivity check |
| `REPORT.md` | this report |

Reproduce (from `kb-health/`):

```bash
python3 analysis/verified_x_stale/run_x.py --dry-run                  # no API
python3 analysis/verified_x_stale/run_x.py --run --ack-prereg          # 432 cells, cap ¥1.5
python3 analysis/verified_x_stale/run_x.py --analyze                  # summary + tables
```

## Quotable sentences (for the paper)

1. "In a clean same-run 2×2 on the 54-task convention benchmark (deepseek-chat, 432 completions),
   the verified header raised pass rate on correct notes from 75.0% (81/108) to 80.6% (87/108):
   +5.6 pp (paired task bootstrap 95% CI [0.0, +12.0], p=.15), not distinguishable from zero at the
   pre-registered threshold."
2. "Stale notes collapsed performance to 0/108 with or without the verified header, so a verified
   header did not measurably amplify stale harm in this run — and the 0% floor means the
   amplification hypothesis is untestable in this design rather than rejected."
3. "The header manipulation changed prompt length by ~7 tokens per prompt but completion length by
   less than 2% and code length by less than 1%, so the null/weak effects are not explained by
   verbosity changes."
4. "A verified label is not a substitute for verification: the label did not make stale notes worse
   here, but staleness alone destroyed task success (0/108 vs 75–81/108 for correct notes)."
