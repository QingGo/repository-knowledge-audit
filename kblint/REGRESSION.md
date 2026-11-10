# kblint — R0 regression (alpha v0.1, post precision-fix run)

Design-repo smoke + known-issue check. **Not a held-out evaluation**: the rules were generalized in
part from the same prototype that produced `analysis/linter/findings.jsonl`, so this is a
correctness smoke test on the design repo, not a precision/recall estimate (see README §Honest
limits and `analysis/linter/LINTER_V0_REPORT.md` §7 item 1).

Reproduce:

```bash
cd kb-health/kblint
python3 -m kblint scan --config examples/R0.kblint.json \
    --out regression/R0 --now 2026-11-05
# exit 1 (findings at --fail-on high), ~4 s, ~50 MB peak RSS
```

Config: docs `docs/**/*.md` + `README.md` + `runs/README.md`; artifacts `runs/*.json` + the pinned
`corpus/R0/runs_index.jsonl`; git enabled; tolerance 5e-4; expiry env-change 2026-10-28.
R4 (missing supersedes) is enabled explicitly in this config *for the regression only*; it is
**off by default** (still experimental — see below).

## Result summary (post FIX-1..4)

- 174 findings total:
  - **R1 7 unresolved** mixed-artifact-environment findings (low) — no "high confirmed" R1 defects
    (the artifact pool has 2.12.1×253 / 2.14.1×269, so every doc pin necessarily conflicts with some
    artifacts; that is a scope conflict, not a defect).
  - **R2 9 confirmed** (6 high-confidence direct-pointer + 3 medium inherited-pointer) and **94
    revalidation-due** queue items. The known 358.8→358.093 mismatch is confirmed (medium).
  - **R3 2 confirmed** (medium; review candidates — generic subject anchors; see precision notes).
  - **R4 3 confirmed** (medium; experimental rule, off by default; cross-shape false-positive class
    confirmed by manual review).
  - **R5 45 revalidation-due** (undated/stale negative claims — queue, not defects).
  - **R6 5 unresolved** missing-canonical-declaration findings (never guesses truth).
  - **R7 4 confirmed** uncommitted tracked docs + **5 provenance_gap** untracked knowledge docs.
  - **241 audit-queue items** (R8; never defects).
- Machine-readable evidence: `regression/R0/{findings.jsonl,audit_queue.jsonl,report.sarif,summary.md}`.
- Determinism: two independent runs produce byte-identical `findings.jsonl`, `audit_queue.jsonl`,
  `report.sarif`, `summary.md` (md5 pair check).
- Verified genuinely-correct findings (>= 5 required): 9 R7 git findings (4 uncommitted + 5
  untracked), the 358.8→358.093 R2 mismatch, and additional R2 artifact mismatches.

## Precision fixes landed in this run

- **FIX-1 (rounding-aware tolerance)**: R2 now derives half-a-unit-in-the-last-place from the doc
  number's displayed precision (`655→±0.5`, `358.8→±0.05`, `1.02→±0.005`) and treats within-half-unit
  as a match. Cases now non-findings: 13.5 vs 13.51, 105 vs 105.365, 7.5 vs 7.55, 9.9 vs 9.93,
  1.02 vs 1.017. 358.8 vs 358.093 (diff 0.707 > 0.05) remains a confirmed R2 finding. Tests cover
  both directions.
- **FIX-2 (pointer + best-candidate + target language)**: R2 emits `confirmed` only when the claim/
  paragraph carries an artifact pointer, the located field is a best candidate (>=2 matching
  non-generic context tokens, unit-compatible), and no threshold/target language (“target”,
  “reaching”, “budget”, “goal”, “ceiling”, …) surrounds the number; otherwise it queues
  `revalidation_due`. Target-language exclusion has a dedicated test. Effect: 15 -> 9 confirmed R2
  findings; the 60%-target vs `discounted_mfu_pct=38.41` style findings are now queued.
- **FIX-3 (R4 off by default)**: R4 is gated behind `rules.R4.enabled` (default false); enabling it
  prints an explicit warning in `summary.md`. `examples/sample.kblint.json` and
  `examples/R0.kblint.json` enable it explicitly for fixture/regression coverage; tests assert
  the default-off behaviour.
- **FIX-4 (mixed-pin honesty)**: when the configured artifact pool contains >=2 distinct pin values
  for a key, R1 emits ONE `unresolved` low-severity finding per doc pin (“mixed artifact
  environments: doc declares X; pool contains X×n, Y×m”) instead of many high confirmed defects;
  `confirmed` is kept only for single-environment pools. Nanov41 R1: 11 high confirmed -> 7
  unresolved.

## Known-issue table (from the existing prototype / casebook)

| # | known issue | kblint finding | verified? | why / why not |
|---|---|---|---|---|
| a | Committed-vs-worktree acceptance-target drift in `docs/benchmarks.md` (55.25 raw-60% diagnostic vs 35.83 discounted target; cf. `findings.jsonl` F-L1-001/002) | `R7 F-ff5d0b645df9dafd` — *uncommitted change to tracked knowledge doc: docs/benchmarks.md* (` M`) + 5 untracked knowledge docs (`R7` provenance_gap: optimization-playbook, compare-nanogpt, compare-nanochat, internal/W1-REPORT, internal/W2-4090-baseline) | **YES, at doc level** | The drift is real and detected: docs/benchmarks.md is edited in the working tree without commit. kblint reports the surface (uncommitted knowledge doc), not the value-level target edit: worktree text marks 55.25 as “raw-60% diagnostic (not the project target)” — a supersedes marker — so R3/R4 correctly do **not** raise a 55.25-vs-35.83 numeric conflict. Value-level committed-vs-worktree diffing is v0.2. |
| b | `358.8` vs `358.093` TFLOP/s typo (CC-03) | `R2 F-7913ebf9cab76bb8` (medium, confidence medium/inherited pointer) — claim cites paragraph-level `runs/r59…`; located field `results.dw13_tiles.128x128x64.triton_fp8_tflops = 358.093`; display precision ±0.05, diff 0.707 | **YES** | Survives FIX-1 (diff > half-last-place) and FIX-2 (direct paragraph pointer, >=2 context tokens `dw13`+`tile` match the key, unit-compatible, no target language). Confidence is medium because the run pointer is paragraph-inherited, not in the claim sentence. |
| c | `60.94` vs `61.93` unresolved R49 conflict (casebook R49) | none | **NO** | Rule-surface miss. `61.93` occurs only in **artifacts** (`runs/r48_moe_tb.json`, `runs/r49_best_b16.json`); the docs table states 60.94, which matches `runs/r50_base.json` within display precision, so R2 verifies it. R3 compares docs only. Table-row→artifact-row anchoring is v0.2; not hacked in. |
| d | `15` vs `17` variants (casebook R58) | none (only `R2 revalidation_due: number not located: 15variants`) | **NO** | Rule-surface miss: count claims are not linked to artifact row-counts; r58 has 17 sweep rows but no numeric `17` field. Queued, not confirmed; v0.2. |
| e | Missing supersedes where a newer run overturns an old claim | R4 (off by default; 3 confirmed with the regression config) | **NO (all 3 are false positives on manual verification)** | Two pairs compare b=8 vs b=16 artifacts (35.76 vs 60.92 ms; 34.87 vs 60.43 ms) — different workload, not supersession; the third flags the `r50_base` baseline row, which does not claim currency. Root cause: no shape/config guard + weak “best/current” heuristic. Hence FIX-3: R4 is off by default and labelled experimental; **not** tuned to the casebook. |

## Precision notes (honest, small-n)

- R2 confirmed after FIX-2: 9 findings. The 6 high-confidence ones have a direct artifact pointer in
  the claim text; for WS-2 strict accounting we recommend counting only `confidence=="high"` and
  treating `medium`/`inherited-pointer` + `revalidation_due` as review queue. Some remaining
  high-confidence R2 mismatches are still field-selection-ambiguous when a paragraph cites several
  runs (e.g. a step time paired with a `device_busy_ms` field); they are evidence-backed but require
  human confirmation. The 358.8 case is the benchmark for a correct inherited-pointer match.
- R3 confirmed 2 are review candidates: anchors `R0 d12 (×): 1 vs 4.24` and `R0 d12 (%):
  3 vs 72` are generic subject anchors across different metrics — likely false positives. R3 should
  gain unit-family and row-label guards in v0.2; keep R3 findings out of defect counts for WS-2.
- R4 findings are not trustworthy yet (above) — disabled by default.
- R1 is now an unresolved-scope signal on mixed environments; expected for a design repo with
  4090-era and 5090-era artifacts.
- Runtime: ~4 s wall, ~50 MB peak RSS (well under the 60 s bound); 174 findings + 241 queue items.

## Decisions for the Lead

1. WS-2 defect counting: count R1 `confirmed` (single-environment) + R2 `confirmed` with
   `confidence=="high"` only; treat R2 medium/inherited, R3, R5/R2 `revalidation_due`, R6 and the R8
   queue as review queues; R4 off.
2. v0.2 backlog: artifact-table-row anchoring (casebook c/d), shape/config guards for R4, R3
   unit-family/row-label guards, value-level committed-vs-worktree diffing (casebook a).
3. Keep `examples/R0.kblint.json` R4 enabled-with-warning only for regression; shipped example
   defaults stay R4-off.
