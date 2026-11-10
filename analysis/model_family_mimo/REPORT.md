# REPORT — independent model-family replication on MiMo (c0/c1/c2, 54 tasks)

**Status: COMPLETE.** Pre-registered [`PREREG.md`](PREREG.md) (sha256
`2776385b2c86a458515cd855feafd5e267c7d084355a76b3bebd4aa313b0b498`, frozen
2026-11-09T20:47:31 +08:00, before the first completion 20:49:17) executed without protocol
deviations. **162/162 core cells + 108/108 optional boundary cells = 270 rows**, 0 API errors,
model `mimo-v2.6-flash` (API echoed the same alias on every call), all finish reasons `stop`,
cost **¥0.2716** (cap ¥10) — well under the ¥4 optional-stage gate, so the pre-registered c0f/c2f
boundary arms ran.

## TL;DR — direction replicates on an independent model family

| condition | MiMo pass (54 tasks, seed 0) | DeepSeek seed-0 reference |
|---|---:|---:|
| c0 no KB | 9/54 = **16.7%** | 9/54 = 16.7% |
| c1 correct note | 35/54 = **64.8%** | 44/54 = 81.5% |
| c2 stale note | 1/54 = **1.9%** | 1/54 = 1.9% |
| c0f no KB + full suite | 32/54 = **59.3%** | 32/54 = 59.3% |
| c2f stale + full suite | 12/54 = **22.2%** | 25/54 = 46.3% |

- **H1 supported:** useful note `c1 − c0` = **+48.15 pp**, 95% bootstrap CI **[+35.19, +61.11]**,
  one-sided exact sign test **p = 1.5×10⁻⁸**, 26 improved / 0 worsened / 28 tied.
- **H2 supported:** stale note `c2 − c0` = **−14.81 pp**, 95% CI **[−25.93, −3.70]**, one-sided
  exact sign test **p = .0107**, 1 improved / 9 worsened / 44 tied.
- **H3 (same direction as DeepSeek) holds:** both signs match the DeepSeek all-54 ITT effects
  (+0.648 useful, −0.111 stale). Magnitudes: useful is **16.65 pp smaller** on MiMo; stale is
  **3.71 pp more negative** (descriptive; DeepSeek is a different run/model family, not a paired
  control).
- **Boundary (optional arms, descriptive):** with the full visible suite, MiMo's stale arm reaches
  22.2% vs 59.3% without a note (`c2f − c0f` = **−37.04 pp** [−51.85, −24.07]); the suite helps
  stale (c2f − c2 = +20.37 pp) and no-KB (c0f − c0 = +42.59 pp) but **does not neutralize the stale
  note** on MiMo. On DeepSeek the same seed-0 rows give c2f = 46.3% vs c0f = 59.3% (c2f − c0f
  ≈ −13.0 pp) — descriptively, disclosure closes less of the stale gap on MiMo (c0f result from a
  separate earlier run; see limitations).

## 1. Design and provenance (as frozen)

- 54 tasks × {c0, c1, c2} × prompt-variant seed 0 = 162 core completions; optional pre-registered
  stage added c0f + c2f (108) because spend after the core was ¥0.15 < the ¥4 gate.
- Prompts/grading unchanged: `run_bench.prompt_for(task, cond, 0)`, hidden pytest
  `run_bench.run_tests(code, task["tests"])`, `run_bench.parse_code(parse_json(raw), raw)`;
  temperature 0.3, `max_completion_tokens=2400`, `thinking={"type":"disabled"}`, stream=false,
  no `response_format` (the has-pilot MiMo convention).
- Model: `mimo-v2.6-flash` via `MIMO_BASE_URL` from `~/.mimo.env` (`https://api.xiaomimimo.com/v1`);
  key read at runtime, never printed or stored. Request format and model id copied from
  `/REPOS_ROOT/has-pilot/signal_bank/run_pilot.py`.
- Validation first: 5 calls (c0, first 5 tasks; part of the 162) — 5/5 API success, 5/5 code
  extracted, 2/5 pytest pass, finish reasons all `stop`, spend ¥0.0049. Then the remaining cells.
- Integrity: 270/270 prompt checks (stored prompts equal `prompt_for` byte-for-byte), 0 API errors,
  162/162 core coverage and 108/108 optional coverage, PREREG sha matches freeze, PREREG mtime
  20:47:31 < first completion 20:49:17, no API key in any output, cost ¥0.2716 ≤ ¥10.

## 2. Core ITT results (all 54 tasks, seed 0)

| contrast (all-54 ITT) | MiMo estimate | 95% CI | exact sign p | improved / worsened / tied | DeepSeek all-54 ITT |
|---|---:|---:|---:|---:|---:|
| **c1 − c0** (useful) | **+48.15 pp** | [+35.19, +61.11] | 1.5×10⁻⁸ | 26 / 0 / 28 | +0.648 [+0.528, +0.759] |
| **c2 − c0** (stale) | **−14.81 pp** | [−25.93, −3.70] | .0107 | 1 / 9 / 44 | −0.111 [−0.194, −0.037] |

Bootstrap: 1,000 task-level resamples, seed 20261109. Both hypotheses were one-sided and
pre-registered; both are supported, i.e. the direction of the paper's core entry-level effects is
**not DeepSeek-specific** in this one-alias test.

## 3. Optional boundary arms (descriptive, pre-registered order c0f → c2f)

| contrast | MiMo estimate | 95% CI | p (two-sided sign) | improved / worsened / tied |
|---|---:|---:|---:|---:|
| c0f − c0 (full suite, no note) | +42.59 pp | [+27.78, +57.41] | 2×10⁻⁶ | 24 / 1 / 29 |
| c2f − c2 (full suite, stale note) | +20.37 pp | [+9.26, +31.48] | .0034 | 12 / 1 / 41 |
| c2f − c0f (stale + suite vs no-KB + suite) | **−37.04 pp** | [−51.85, −24.07] | 1.1×10⁻⁵ | 1 / 21 / 32 |

Boundary reading: on MiMo, the full hidden suite is a large information intervention
(c0f − c0 = +42.6 pp) and helps the stale arm (c2f − c2 = +20.4 pp), but **showing the grading suite
does not remove the stale-note disadvantage** (c2f − c0f = −37.0 pp). Each of these is an
information upper bound, not a maintenance fix.

## 4. Descriptive cross-family comparison (DeepSeek seed-0 rows vs MiMo seed-0)

| stat (54 tasks, seed 0) | DeepSeek | MiMo |
|---|---:|---:|
| c0 / c1 / c2 pass | 9 / 44 / 1 | 9 / 35 / 1 |
| c0f / c2f pass | 32 / 25 | 32 / 12 |
| c1 − c0 | +35/54 = +64.81 pp | +26/54 = +48.15 pp |
| c2 − c0 | −8/54 = −14.81 pp | −8/54 = −14.81 pp |
| c0f − c0 | +23/54 = +42.59 pp | +23/54 = +42.59 pp |
| c2f − c2 | +24/54 = +44.44 pp | +11/54 = +20.37 pp |
| c2f − c0f | −7/54 = −12.96 pp | −20/54 = −37.04 pp |

DeepSeek numbers are frozen existing rows (`outcome_bench/results/bench_chat.jsonl`, seed-0 cells;
c0f from `bench_c0tests_chat.jsonl`, seed 0 only, a separate run), not a same-run paired control;
this table is descriptive. The identical c0/c2/c0f counts are a small-sample coincidence of the frozen runs; the
meaningful comparison is the contrast pattern, not the level of any single cell. The reliable contrast is directional:
same signs, smaller useful effect on MiMo, and a larger residual stale disadvantage under full
disclosure.

## 5. Per-family pass rates (descriptive; n = 8 cells per family, 6 for stable_softmax)

| family | c0 | c1 | c2 | c0f | c2f |
|---|---:|---:|---:|---:|---:|
| ce_grad | .000 | .625 | .000 | .250 | .000 |
| masked_mean | .125 | .500 | .000 | .500 | .125 |
| masked_softmax | .250 | 1.000 | .000 | .750 | .500 |
| quantize | .125 | .625 | .000 | .750 | .250 |
| shift_ce | .250 | .500 | .000 | .625 | .000 |
| stable_softmax | .167 | 1.000 | .000 | 1.000 | .667 |
| topk | .250 | .375 | .125 | .375 | .125 |

The direction c1 > c0 holds in all 7 families; c2 < c0 holds in 6/7 (in ce_grad both are 0/8, a tie) and no family shows c2 > c0. No inferential claims per family.

## 6. Tokens / cost / latency

| cond | n | prompt tok | completion tok | total tok | cost ¥ | mean latency s | finish reasons | model_returned |
|---|---:|---:|---:|---:|---:|---:|---|---|
| c0 | 54 | 5,894 | 21,325 | 27,219 | 0.0485 | 11.71 | stop ×54 | mimo-v2.6-flash ×54 |
| c1 | 54 | 9,311 | 20,774 | 30,085 | 0.0509 | 9.56 | stop ×54 | mimo-v2.6-flash ×54 |
| c2 | 54 | 8,875 | 21,223 | 30,098 | 0.0513 | 11.42 | stop ×54 | mimo-v2.6-flash ×54 |
| c0f | 54 | 30,866 | 13,594 | 44,460 | 0.0581 | 7.14 | stop ×54 | mimo-v2.6-flash ×54 |
| c2f | 54 | 33,847 | 14,471 | 48,318 | 0.0628 | 6.97 | stop ×54 | mimo-v2.6-flash ×54 |
| **total** | **270** | **88,793** | **91,387** | **180,180** | **0.2716** | — | — | — |

Pricing copied from has-pilot `run_pilot.py` (`provider="mimo"`: CNY 1.0/M input, 2.0/M output).
Full raw usage objects are retained per row (`usage_raw`).

## 7. Interpretation (honest)

1. **The paper's core directions replicate on a non-DeepSeek model family.** A correct note
   substantially improves hidden-test pass rates (+48 pp, 26 tasks up, none down, p<1e-7) and a
   stale note substantially harms them (−14.8 pp, 9 tasks down, p=.011), same signs as the DeepSeek
   all-54 ITT numbers (+0.648 / −0.111). This weakens the "DeepSeek-specific" threat for direction.
2. **Magnitude is not identical.** The useful effect is ~16.7 pp smaller on MiMo (48.1 vs 64.8 pp),
   and the stale penalty is slightly larger in absolute terms (−14.8 vs −11.1 pp). Direction
   replication is not effect-size replication; one alias, one prompt seed, 54 constructed tasks.
3. **Disclosure behaves differently on this family.** Unlike the DeepSeek snapshot (where
   fresh-note and no-KB arms with the full suite are close), MiMo still loses 37 pp when a stale
   note is shown alongside the full grading suite (c2f 22.2% vs c0f 59.3%). A plausible reading is
   that MiMo adheres more strongly to the given note even when the tests contain the specification;
   the experiment does not measure mechanism, and the DeepSeek c0f comparison is cross-run. This is
   a descriptive cross-family hint, not a claim.
4. **This is not a family-general claim.** One model alias (no provider-side version pin; every
   response echoed the alias), one prompt-variant seed, constructed convention tasks, binary hidden
   grading, single run. It supports direction robustness across two model families, not
   generalisation to "models".

## 8. Limitations

1. **One alias, one seed, one run**: MiMo `mimo-v2.6-flash`, seed 0 only; no provider-side version
   pin/snapshot; seed-1 prompt variant not run.
2. **Constructed tasks**: 54 curated convention tasks in 7 families; not organic repositories; 8
   tasks/family (6 for stable_softmax); per-family numbers descriptive only.
3. **DeepSeek comparisons are cross-run**: all-54 ITT reference numbers from the paper's existing
   run; seed-0 table uses frozen existing rows, with c0f from a separate earlier run. No same-run
   paired DeepSeek control was collected in this experiment (budget/time).
4. **Boundary arms are information upper bounds**: c0f/c2f show the full grading suite, so they
   measure specification information, not a deployable maintenance intervention.
5. **Binary pass/fail** with hidden tests; no partial credit, no adoption/decision probe.
6. **Cost accounting** uses the has-pilot MiMo real-time price table (CNY 1.0/M input, 2.0/M
   output); cached-token discounts are not applied, so ¥0.2716 is a conservative estimate.

## 9. Deviations

None. The optional c0f/c2f stage ran exactly as pre-registered (triggered because core-stage spend
¥0.1507 < ¥4.0); optional order c0f → c2f; no cells were added/dropped/replaced; analysis rules as
frozen. Validation calls were the first 5 core c0 cells (part of the 162), as pre-registered.

## 10. Files and reproduce

| file | contents |
|---|---|
| `PREREG.md` | frozen design/hypotheses/analysis plan (sha256 in freeze.json) |
| `run_mimo.py` | runner + analyzer (`--dry-run`, `--validate`, `--run`, `--analyze`) |
| `results/mimo_chat.jsonl` | 270 per-cell rows (cond, seed, pass, tokens, raw usage, cost, latency, attempts, finish reason, model_returned) |
| `results/mimo_prompts.jsonl` | 270 exact prompts (audit; no key) |
| `results/freeze.json`, `results/c0v_validation.json`, `results/cost_log.json` | fingerprint, 5-call validation, cost log |
| `results/summary.json`, `results/task_table.tsv` | rates, contrasts/CIs/p, per-family, per-task |
| `REPORT.md` | this report |

```bash
cd kb-health
python3 analysis/model_family_mimo/run_mimo.py --dry-run
python3 analysis/model_family_mimo/run_mimo.py --validate
python3 analysis/model_family_mimo/run_mimo.py --run
python3 analysis/model_family_mimo/run_mimo.py --analyze
```

## 11. Quotable sentences

1. "On an independent model family (MiMo `mimo-v2.6-flash`; one prompt seed, all 54 tasks,
   162 completions, ¥0.27), the paper's core directions replicate: a correct note raises hidden-test
   pass rate by +48.15 pp (95% CI [+35.19, +61.11]; 26 tasks improved, 0 worsened; exact sign
   p=1.5×10⁻⁸) and a stale note lowers it by −14.81 pp (95% CI [−25.93, −3.70]; 1 improved,
   9 worsened; p=.011) — the same signs as the DeepSeek all-54 ITT effects (+0.648 / −0.111)."
2. "The useful effect is smaller on MiMo (48.1 pp vs 64.8 pp on DeepSeek), so direction replicates
   while magnitude does not; a single alias and a single prompt seed do not support a
   family-general claim."
3. "On MiMo the full visible grading suite lifts the stale arm to 22.2% but does not remove the
   stale-note disadvantage (c2f − c0f = −37.0 pp), whereas the DeepSeek snapshot's seed-0 rows put
   that gap at ≈−13 pp; disclosure helps less on this family, descriptively."
