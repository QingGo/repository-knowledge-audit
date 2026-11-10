# Flip rates, family leave-one-out, and cluster-bootstrap intervals (zero-cost reanalysis)

**No API calls.** All numbers are re-derived from the frozen per-cell completion store; the
authoritative store is the same one that reproduces the S2 all-task ITT effects and the S6.25 MiMo
point estimates (verified in `results.json`: `data_provenance`).

## What is computed

- **Flip rates.** A *stale flip* is a cell (task x prompt-variant seed) where the no-KB condition
  passes and the stale condition fails. A *useful flip* is a cell where no-KB fails and the correct
  note passes. Wilson 95% intervals.
- **Family leave-one-out.** For each main all-task ITT contrast, recompute the point estimate with
  each of the seven task families removed in turn; report the min-max range.
- **Seven-family cluster bootstrap.** Resample families (not tasks) 10,000 times for the same
  contrasts; percentile 95% intervals. This is coarser than the task-level bootstrap and is a
  sensitivity check, not a replacement.
- **Adoption classification: infeasible from this store.** The frozen rows retain pass/usage, not
  generated code, and the benchmark has no executable stale-convention test, so a three-way
  "copied stale / correct / neither" classification cannot be computed without new collection. It is
  reported as infeasible rather than approximated.

## Results

Flip rates (cell = task x seed):

| model | stale flip | rate [95% CI] | useful flip | rate [95% CI] |
|---|---|---|---|---|
| deepseek-chat | 13/17 | 76.5% [52.7, 90.4] | 71/91 | 78.0% [68.5, 85.3] |
| deepseek-reasoner | 5/9 | 55.6% [26.7, 81.1] | 32/45 | 71.1% [56.6, 82.3] |
| MiMo (descriptive) | 9/9 | 100% [70.1, 100] | 26/45 | 57.8% [43.3, 71.0] |

Main all-task ITT contrasts (chat, 54 tasks):

| contrast | estimate | leave-one-family-out range | 7-family cluster 95% CI |
|---|---:|---:|---:|
| useful - no KB | +0.648 | +0.609 to +0.728 | [0.463, 0.808] |
| stale - no KB | -0.111 | -0.141 to -0.087 | [-0.179, -0.029] |
| stale + full suite - (no KB + full suite) | -0.139 | -0.163 to -0.109 | [-0.213, -0.071] |
| correct + full suite - (stale + full suite) | +0.398 | +0.326 to +0.467 | [0.183, 0.607] |

All four contrasts keep their sign under every leave-one-family-out refit, and both the per-family
ranges and the coarser family-cluster intervals exclude zero. The per-cell flip rate explains why an
all-task mean of -0.11 can hide a frequent loss: 13/17 chat cells that the no-KB model already passed
fail once a stale note is present.

## Caveats

- Cells are not independent (17 chat cells come from 9 tasks x 2 paraphrase seeds).
- The chat flip rate is seed-sensitive (8/9 on seed 0, 5/8 on seed 1); small denominators.
- The flip estimand conditions on no-KB pass and is not an ITT harm estimate; the ITT contrast is the
  primary quantity.
- MiMo is a cross-family, cross-run descriptive replication (single seed).
- Seven clusters make the cluster bootstrap coarse; it is a sensitivity interval.

## Reproduce

```bash
python3 run.py          # writes results.json (~3 s; numpy only)
```

`results.json` carries all 1,782 per-cell rows (`model, condition, task_id, family, pass, seed`) plus
the flip/leave-one-out/cluster blocks and the source-store hashes.
