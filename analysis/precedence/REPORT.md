# REPORT — source-of-truth precedence rule experiment (deepseek-chat, 54 tasks)

**Status: COMPLETE.** Pre-registered [`PREREG.md`](PREREG.md) (sha256
`0600462d8e45464372ecf74098af4be16b846f0e32d277c9e46998ea006de793`, frozen
2026-11-09T19:21:20 +08:00, before the first completion at 19:23:00) executed without protocol
deviations. 540/540 new cells, 0 API errors, cost **¥0.6734** (cap ¥3.0). Controls `c1/c2/c2f` are
the frozen snapshot of the existing 54-task chat batch (`results/controls_used.jsonl`, sha256
`69d87d13…`; no new control calls).

## TL;DR (honest null)

The fixed precedence rule **did not measurably mitigate stale-note harm** and **did not establish
non-inferiority on correct notes**:

- **H1 (primary) NOT SUPPORTED.** Stale + rule (`p2`) 8/108 = **7.4%** vs stale (`c2`) 5/108 =
  **4.6%**: +2.78 pp, paired task bootstrap 95% CI **[+0.00, +6.48]**, one-sided exact sign test
  **p = .125**, 3 tasks improved / 0 worsened / 51 tied.
- **H2 (non-inferiority) NOT ESTABLISHED.** Correct + rule (`p1`) 82/108 = **75.9%** vs correct
  (`c1`) 87/108 = **80.6%**: −4.63 pp, 95% CI **[−12.04, +0.93]**; the pre-registered lower-bound
  rule (> −10 pp) fails (lower bound −12.04), driven by 5 worsened vs 2 improved tasks. The point
  estimate is a small **negative** effect; the run is too small to call it harm, but it is also not
  evidence of safety.
- **H3/H4 exploratory:** DiD `(p2−c2) − (p2f−c2f)` = +4.63 pp [−4.63, +12.96] (not interpretable
  as a confirmation); the specific rule is **not better than a generic warning** under full test
  disclosure (`p2f` − `w2f` = −2.78 pp [−9.26, +3.70]; warning slightly higher).
- What does move stale-arm outcomes is **test disclosure**, not advice: full visible suite lifts the
  stale arm from 4.6% to 45.4% (`c2f − c2` = +40.7 pp), and the rule adds nothing once the suite is
  shown (`p2f − c2f` = −1.85 pp [−10.19, +6.48]). This is an information upper bound, not a
  deployable maintenance fix.

## 1. Design (as frozen)

- 54 convention tasks (`outcome_bench/conventions.py`), `deepseek-chat` via `~/.has_pilot.env`,
  hidden-pytest grading unchanged (`run_bench.py::run_tests`), temperature 0.3, seeds 0/1 prompt
  variants, one completion per cell, 5 arms × 54 × 2 = 540 completions.
- Arms = one existing prompt (built by `run_bench.py::prompt_for`, unchanged) plus **one fixed
  paragraph inserted verbatim after the note bullets** (before any test block / seed sentence):
  `p2` = stale + rule; `p1` = correct + rule; `p2f` = stale + rule + full visible suite;
  `w2f` = stale + generic warning + full suite; `p1f` = correct + rule + full suite.
  Rule (fixed): *"When repository knowledge conflicts with independently observable evidence (the
  task requirements, visible tests, or the project's own code and manifests), do not follow the
  knowledge entry. Use the authoritative project source of truth and report the conflict. If no
  conflict is detectable, proceed normally."* Warning (fixed): *"Note: KB entries may be stale or
  wrong; verify claims against the code and tests when possible."*
- Prompt-integrity checks: 540/540 prompts differ from their base prompt **only** by the inserted
  paragraph (removal reproduces the base bytes); 540/540 insertion-count checks; controls snapshot
  hash verified. `run_tests("")` fails for all 54 tasks (grader sanity).

## 2. Results

### 2.1 Pass rates (n = 108 per arm = 54 tasks × 2 seeds; ITT)

| arm | note | extra text | pass | rate | seed 0 / seed 1 | prompt tok (mean) | completion tok (mean) | code len | cost ¥ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `p2` | stale | rule | 8/108 | 7.4% | 5 / 3 | 243.4 | 280.5 | 786 | 0.1464 |
| `p1` | correct | rule | 82/108 | 75.9% | 41 / 41 | 251.8 | 234.5 | 652 | 0.1274 |
| `p2f` | stale | rule + full suite | 47/108 | 43.5% | 24 / 23 | 726.8 | 163.9 | 393 | 0.1327 |
| `w2f` | stale | warning + full suite | 50/108 | 46.3% | 24 / 26 | 693.8 | 158.4 | 382 | 0.1268 |
| `p1f` | correct | rule + full suite | 92/108 | 85.2% | 46 / 46 | 735.2 | 163.9 | 404 | 0.1401 |
| `c1` (control) | correct | — | 87/108 | 80.6% | 44 / 43 | — | 222.3 | — | — |
| `c2` (control) | stale | — | 5/108 | 4.6% | 1 / 4 | — | 252.8 | — | — |
| `c2f` (control) | stale | full suite | 49/108 | 45.4% | 25 / 24 | — | 157.3 | — | — |

Controls are the frozen earlier chat run (same tasks, prompt builder, model, temperature 0.3);
`p1f` has no frozen `c1f` control, so it is reported descriptively only.

### 2.2 Pre-registered paired contrasts (54 tasks, per-task pass mean over 2 seeds)

| contrast | estimate | 95% bootstrap CI (1,000×) | sign test | improved / worsened / tied | decision |
|---|---:|---:|---:|---:|---|
| **H1: p2 − c2** | **+2.78 pp** | **[+0.00, +6.48]** | one-sided **p=.125** | 3 / 0 / 51 | **not supported** (α=.05) |
| **H2: p1 − c1** | **−4.63 pp** | **[−12.04, +0.93]** | two-sided p=.453 | 2 / 5 / 47 | **non-inferiority not established** (lower −12.04 ≤ −10) |
| **H3: DiD** `(p2−c2)−(p2f−c2f)` | +4.63 pp | [−4.63, +12.96] | two-sided p=.344 | 7 / 3 / 44 | exploratory, no confirmation |
| **H4: p2f − w2f** (rule vs warning) | −2.78 pp | [−9.26, +3.70] | two-sided p=.688 | 2 / 4 / 48 | exploratory: specific rule not better than warning |
| secondary: p2f − c2f | −1.85 pp | [−10.19, +6.48] | two-sided p=1.0 | 3 / 4 / 47 | rule adds nothing once suite is shown |

Task-level detail: H1's 3 improved tasks are all `*_next_valid_*` tasks in the `ce_grad` and
`shift_ce` families (G1, S1, S4; each +0.5); no task worsened. H2's harm is concentrated in 5 tasks
(K7 and M6 flip both seeds to fail, G4/M7 −0.5, K5 −0.5); 2 tasks improved (Q2, S4).

### 2.3 Per-family pass rates (descriptive; n = 16 cells per family per arm, 12 for stable_softmax)

| family | c1 → p1 | c2 → p2 | c2f → p2f | w2f | p1f |
|---|---|---|---|---|---|
| ce_grad | .562 → .500 | .062 → .125 | .188 → .188 | .188 | 1.000 |
| masked_mean | 1.000 → .812 | .000 → .000 | .375 → .375 | .438 | .938 |
| masked_softmax | 1.000 → 1.000 | .062 → .062 | .688 → .750 | .812 | 1.000 |
| quantize | .938 → 1.000 | .000 → .000 | .375 → .500 | .500 | 1.000 |
| shift_ce | .438 → .500 | .062 → .188 | .500 → .250 | .250 | .500 |
| stable_softmax | 1.000 → 1.000 | .167 → .167 | .667 → .833 | .667 | 1.000 |
| topk | .750 → .562 | .000 → .000 | .438 → .250 | .438 | .562 |

H1's gain is concentrated in `ce_grad`/`shift_ce`; H2's losses are concentrated in `masked_mean`
and `topk` (largest families). All per-family numbers are descriptive; only the pooled tests were
pre-registered.

## 3. Interpretation (honest)

1. **The one-sentence rule is not a sufficient fix in this benchmark.** Appended after a stale note,
   it moved 3 of 54 tasks (all `next_valid` edge cases) and left 51 tied; it did not rescue the
   convention-heavy failures. Under full test disclosure it added nothing over the suite alone
   (`p2f` ≈ `c2f`, and slightly below a generic warning).
2. **The correct-KB harm direction is not established as safe.** The rule lowered the correct-note
   point estimate by 4.6 pp (5 tasks worse, 2 better) and failed the pre-declared −10 pp
   non-inferiority margin. We therefore cannot say the rule is free of cost on correct KB; at most
   we can say the run does not prove a >10 pp harm (the CI still includes 0).
3. **Disclosure dominates advice here.** In these prompts, the full visible suite is the only
   ingredient that materially lifts stale-arm outcomes (+40.7 pp), and even that remains far below
   the correct-note level (45.4% vs 80.6%) — it is an information upper bound, not a maintenance
   intervention.
4. **Why this can coexist with arXiv:2610.30571.** That work operates on stale *instruction files*
   (AGENTS.md/CLAUDE.md-like rules) with Claude Code/Codex, measures stated code-following, and
   reports a one-sentence source-of-truth fix. Our setting embeds the rule *after a stale knowledge
   note inside the task prompt*, uses a chat model on 54 constructed convention tasks, and measures
   hidden-test outcomes. The two results can both be true: a precedence sentence can change stated
   choices and help when the conflict is framed as instruction-vs-code, yet be insufficient (and
   possibly mildly costly) for correct-note tasks in our prompt format. Our data do not contradict
   their stated-choice result; they add a scope boundary and the harm-direction check their design
   did not include. (Exact metadata: Xu & Wu, *Stale Instruction Files Override the Code in Coding
   Agents: A One-Sentence Fix*, arXiv:2610.30571, Oct 2026.)

## 4. Provenance and sanity

- PREREG sha256 `0600462d…`; frozen 19:21:20 +08:00; first completion 19:23:00 +08:00 (before: ✓).
- 540/540 cells; coverage 108/108 per arm; 0 API errors; 540/540 prompt diff-only checks; control
  snapshot 324 rows, hash frozen before calls; controls: c1 87/108, c2 5/108, c2f 49/108.
- Cost **¥0.6734** for the 540 cells (cap ¥3.0, stop ¥2.7; per-arm in `results/cost_log.json`).
  A connectivity ping (¥0.000063) preceded the run, is recorded in `results/ping.json`, and is not
  one of the 540 cells. Total API spend this experiment ≈ ¥0.6735. No API key in any output.
- Grading: hidden pytest via `run_bench.run_tests`; pass = returncode 0; no-code/API-error cells
  counted as failures (ITT), as pre-registered.

## 5. Limitations

1. **Cross-run controls.** `c1/c2/c2f` are a frozen snapshot of the earlier 54-task chat batch (same
   task set, prompt builder, model, and temperature), not same-session controls; the new arms used
   the same builder and decoding but a later API window. The frozen controls are still perfectly
   reproducible (`results/controls_used.jsonl`).
2. **One model family** (`deepseek-chat`); one prompt format; rule placed after the note. The result
   is about *this* sentence placement/format, not about precedence instructions in general.
3. **Small n**: 54 tasks, 2 seeds; the H1 CI is wide and the sign test had at most 3 non-tied tasks
   in the predicted direction; 51 ties mean the manipulation only plausibly affects a narrow slice
   of tasks.
4. **Stale manipulation is severe**: stale baseline 4.6%, so floor effects and task difficulty
   dominate; a subtler stale note could show a different rule effect.
5. **`p1f` has no frozen `c1f` control**, so correct-note + full-suite effects cannot be isolated
   from the rule; reported descriptively only.
6. **Per-family and per-seed numbers are descriptive** (not pre-registered inferential targets);
   family correlation is not modelled.
7. No adoption/decision probe: the experiment measures hidden-test outcomes only, by design.

## 6. Deviations / notes

No protocol deviations (design, arms, hypotheses, decision rules, and cost rules as frozen). A
pre-run connectivity ping is documented in §4. Two analysis-helper bugs (a missing-key guard for the
unregistered `c1f` secondary contrast and a keyword-call bug in the prompt-integrity recheck) were
fixed while preparing the analysis, before results were reported; they do not change the data, the
pre-registered contrasts, or the decision rules. No cells were added, dropped, or replaced.

## 7. Files and reproduce

| file | contents |
|---|---|
| `PREREG.md` | frozen design/hypotheses/analysis plan |
| `run_precedence.py` | runner + analyzer (`--dry-run`, `--ping`, `--run`, `--analyze`) |
| `results/precedence_chat.jsonl` | 540 per-cell rows (arm, seed, pass, tokens, cost, prompt hash, ts) |
| `results/precedence_prompts.jsonl` | 540 exact prompts (audit; no key material) |
| `results/controls_used.jsonl` | frozen control snapshot (324 rows) + `freeze.json` hashes |
| `results/summary.json` | arm rates, contrasts/CIs/p, decisions, per-family, sanity |
| `results/task_table.tsv` | per-task scores and diffs |
| `results/cost_log.json`, `results/dry_run.json`, `results/ping.json` | cost, prompt checks, connectivity |
| `REPORT.md` | this report |

```bash
cd kb-health
python3 analysis/precedence/run_precedence.py --dry-run
python3 analysis/precedence/run_precedence.py --run --ack-prereg
python3 analysis/precedence/run_precedence.py --analyze
```

## 8. Quotable sentences (paper-ready)

1. "A fixed one-sentence source-of-truth precedence rule appended to a stale knowledge note did not
   improve hidden-test outcomes: 8/108 (7.4%) vs 5/108 (4.6%) without it (paired task bootstrap 95%
   CI [+0.0, +6.5] pp, one-sided exact sign test p=.125; 3 tasks improved, 0 worsened, 51 tied)."
2. "The same rule did not establish non-inferiority on correct notes: 82/108 (75.9%) vs 87/108
   (80.6%) (Δ −4.6 pp, 95% CI [−12.0, +0.9]); the pre-registered −10 pp margin was not met, so we
   cannot claim the rule is harmless for correct KB in this benchmark."
3. "What moves stale-note outcomes in these prompts is disclosure, not advice: the full visible test
   suite lifts the stale arm from 4.6% to 45.4% (+40.7 pp), while the rule adds nothing once the
   suite is present (−1.9 pp, 95% CI [−10.2, +6.5]); this is an information upper bound, not a
   deployable maintenance fix."
4. "Our null does not contradict the stated-choice result of arXiv:2610.30571; it shows that in a
   54-task hidden-test chat benchmark with the rule embedded after the stale note, the sentence
   alone is not sufficient — and the correct-KB harm direction remains open rather than demonstrated
   safe."
