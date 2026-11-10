# kblint summary

- tool: `kblint 0.1.0` (deterministic, stdlib only, zero network)
- repo: `/REPOS_ROOT/R0`
- docs scanned: 11; claims extracted: 688; artifacts indexed: 554
- findings: **174** (confirmed 18, unresolved 12, provenance_gap 5, revalidation_due 139)
- waivers applied: 0
- audit queue (not defects): **241** claims
- **R4 (missing supersedes) is ENABLED but still experimental**: artifact-chronology flags can be cross-shape false positives; treat R4 findings as review candidates (see README honest limits).

## Findings by rule

| rule | name | findings |
|---|---|---:|
| R1 | pin/version consistency | 7 |
| R2 | number provenance | 103 |
| R3 | cross-doc conflict | 2 |
| R4 | missing supersedes/deprecation | 3 |
| R5 | negative-result/flag expiry | 45 |
| R6 | source-of-truth declaration | 5 |
| R7 | untracked/no-owner knowledge file | 9 |
| R8 | audit queue | 0 |

## Severity

- high: 8
- medium: 6
- low: 160

## Confirmed / unresolved findings (evidence, not usefulness)

- **R1 low unresolved** `runs/README.md#L34` — mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.14.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `docs/benchmarks.md#L63-L69` — mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.14.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `docs/optimization-playbook.md#L43-L55` — mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.14.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `README.md#L144-L147` — mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.14.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `docs/internal/W2-4090-baseline.md#L5-L7` — mixed artifact environments for pin '2.12.1': doc declares 2.12.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.12.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `README.md#L118` — mixed artifact environments for pin '2.12.1': doc declares 2.12.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.12.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R1 low unresolved** `docs/benchmarks.md#L29` — mixed artifact environments for pin '2.12.1': doc declares 2.12.1+cu130; pool contains 2.12.1×253, 2.14.1×269
  - observed: doc declares 2.12.1+cu130; matching artifacts record 2.12.1×253, 2.14.1×269
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R2 high confirmed** `docs/benchmarks.md#L117-L129` — artifact_mismatch: 0.54ms vs gain_native_vs_cat_ms = -0.0666667
  - observed: claim states 0.54ms (cat ms native i.e); runs/r57_native_param_fusion_5090.json :: gain_native_vs_cat_ms = -0.0666667
  - expected: the cited artifact field must agree within display precision (half last place 0.005) or relative tolerance 0.0005 (observed relative difference 1.12e+00)
- **R2 high confirmed** `docs/benchmarks.md#L154-L163` — artifact_mismatch: 35.18% vs mfu_fields.results.bf16_head_b16.discounted_mfu_pct = 38.41
  - observed: claim states 35.18% (gives ms raw bf16-mfu); runs/r54_precision_mix_5090.json :: mfu_fields.results.bf16_head_b16.discounted_mfu_pct = 38.41
  - expected: the cited artifact field must agree within display precision (half last place 0.005) or relative tolerance 0.0005 (observed relative difference 8.41e-02)
- **R2 high confirmed** `docs/optimization-playbook.md#L43-L55` — artifact_mismatch: 2.4% vs round4_stack_and_optimizer.moe_tile_delta_pct = -0.91
  - observed: claim states 2.4% (attn_dkv_bf16 moe_dws_inline moe_tile another); runs/r69_mfu_5090.json :: round4_stack_and_optimizer.moe_tile_delta_pct = -0.91
  - expected: the cited artifact field must agree within display precision (half last place 0.05) or relative tolerance 0.0005 (observed relative difference 1.38e+00)
- **R2 high confirmed** `docs/benchmarks.md#L99-L107` — artifact_mismatch: 227tflops vs full_v41_expert_shapes_graph_replay[0].fp8_tflops = 374
  - observed: claim states 227tflops (tokens expert fp8 faster); runs/r51_fp4_expert_microbench_5090.json :: full_v41_expert_shapes_graph_replay[0].fp8_tflops = 374
  - expected: the cited artifact field must agree within display precision (half last place 0.5) or relative tolerance 0.0005 (observed relative difference 3.93e-01)
- **R2 high confirmed** `docs/benchmarks.md#L208-L219` — artifact_mismatch: 4.53% vs torch214_upgrade.head_to_head_with_r69_flags.delta_pct = -1.7
  - observed: claim states 4.53% (r69 flag effect grows); runs/r69_mfu_5090.json :: torch214_upgrade.head_to_head_with_r69_flags.delta_pct = -1.7
  - expected: the cited artifact field must agree within display precision (half last place 0.005) or relative tolerance 0.0005 (observed relative difference 1.38e+00)
- **R2 medium confirmed** `docs/benchmarks.md#L230-L239` — artifact_mismatch: 358.8tflops vs results.dw13_tiles.128x128x64.triton_fp8_tflops = 358.093
  - observed: claim states 358.8tflops (variant best dw13 tile); runs/r59_grouped_fp8_proto_5090.json :: results.dw13_tiles.128x128x64.triton_fp8_tflops = 358.093
  - expected: the cited artifact field must agree within display precision (half last place 0.05) or relative tolerance 0.0005 (observed relative difference 1.97e-03)
- **R2 high confirmed** `docs/benchmarks.md#L137-L144` — artifact_mismatch: 28.5ms vs profile_bf16_head_ms.total = 38.999
  - observed: claim states 28.5ms (v3 bf16 profile gemms); runs/r60_head_isolation_5090.json :: profile_bf16_head_ms.total = 38.999
  - expected: the cited artifact field must agree within display precision (half last place 0.05) or relative tolerance 0.0005 (observed relative difference 2.69e-01)
- **R2 high confirmed** `docs/benchmarks.md#L50-L55` — artifact_mismatch: 236.93ms vs device_busy_ms = 201.73
  - observed: claim states 236.93ms (step tok s device-busy); runs/p0_b8.json :: device_busy_ms = 201.73
  - expected: the cited artifact field must agree within display precision (half last place 0.005) or relative tolerance 0.0005 (observed relative difference 1.49e-01)
- **R2 high confirmed** `docs/benchmarks.md#L145-L153` — artifact_mismatch: 4.85ms vs device_breakdown_ms.elementwise_copy_sort_fill = 5.8
  - observed: claim states 4.85ms (copy sort rms rope); runs/r55_tail_census_5090.json :: device_breakdown_ms.elementwise_copy_sort_fill = 5.8
  - expected: the cited artifact field must agree within display precision (half last place 0.005) or relative tolerance 0.0005 (observed relative difference 1.64e-01)
- **R3 medium confirmed** `docs/compare-nanochat.md#L34` — cross-doc conflict on 'R0 d12' (×): 1 vs 4.24
  - observed: docs/compare-nanochat.md states 4.24×; other doc(s) state different values: docs/compare-nanogpt.md:3, docs/compare-nanogpt.md:4.24, docs/compare-nanogpt.md:1, docs/compare-nanogpt.md:1
  - expected: the same subject must have one value across docs unless a claim/section is explicitly marked superseded/deprecated
- **R3 medium confirmed** `docs/compare-nanochat.md#L19` — cross-doc conflict on 'R0 d12' (%): 3 vs 72
  - observed: docs/compare-nanochat.md states 10.2%; other doc(s) state different values: docs/compare-nanogpt.md:10.2, docs/compare-nanogpt.md:5, docs/compare-nanogpt.md:59.4
  - expected: the same subject must have one value across docs unless a claim/section is explicitly marked superseded/deprecated
- **R4 medium confirmed** `runs/README.md#L18` — missing supersedes: newer artifact runs/r48_best_b8.json contradicts runs/r48_best_b16.json (60.92ms vs 35.76ms)
  - observed: claim cites runs/r48_best_b16.json (ms_candidates[1].v = 60.92) and states 60.92ms; newer artifact runs/r48_best_b8.json records 35.76 at step_ms (mtime 2026-10-22T20:49:54+08:00)
  - expected: a claim contradicted by a newer artifact must be marked superseded / deprecated (or scoped to its artifact date)
- **R4 medium confirmed** `runs/README.md#L19` — missing supersedes: newer artifact runs/r50_nopad.json contradicts runs/r50_base.json (60.94ms vs 60.44ms)
  - observed: claim cites runs/r50_base.json (ms_candidates[1].v = 60.94) and states 60.94ms; newer artifact runs/r50_nopad.json records 60.44 at step_ms (mtime 2026-10-22T21:43:46+08:00)
  - expected: a claim contradicted by a newer artifact must be marked superseded / deprecated (or scoped to its artifact date)
- **R4 medium confirmed** `runs/README.md#L20` — missing supersedes: newer artifact runs/r50_best_b8.json contradicts runs/r50_best_b16.json (60.43ms vs 34.87ms)
  - observed: claim cites runs/r50_best_b16.json (ms_candidates[1].v = 60.43) and states 60.43ms; newer artifact runs/r50_best_b8.json records 34.87 at step_ms (mtime 2026-10-22T21:48:04+08:00)
  - expected: a claim contradicted by a newer artifact must be marked superseded / deprecated (or scoped to its artifact date)
- **R6 low unresolved** `runs/README.md#L29` — missing canonical declaration for topic 'discounted wall'
  - observed: runs/README.md discusses 'discounted wall' without referencing the canonical docs/benchmarks.md
  - expected: claims about 'discounted wall' should declare the canonical source (docs/benchmarks.md) or link its locator
- **R6 low unresolved** `docs/optimization-playbook.md#L31` — missing canonical declaration for topic 'discounted wall'
  - observed: docs/optimization-playbook.md discusses 'discounted wall' without referencing the canonical docs/benchmarks.md
  - expected: claims about 'discounted wall' should declare the canonical source (docs/benchmarks.md) or link its locator
- **R6 low unresolved** `docs/optimization-playbook.md#L331-L332` — missing canonical declaration for topic 'acceptance target'
  - observed: docs/optimization-playbook.md discusses 'acceptance target' without referencing the canonical docs/benchmarks.md #L74
  - expected: claims about 'acceptance target' should declare the canonical source (docs/benchmarks.md) or link its locator
- **R6 low unresolved** `README.md#L8-L20` — missing canonical declaration for topic 'discounted wall'
  - observed: README.md discusses 'discounted wall' without referencing the canonical docs/benchmarks.md
  - expected: claims about 'discounted wall' should declare the canonical source (docs/benchmarks.md) or link its locator
- **R6 low unresolved** `docs/v41-scaling-check.md#L112` — missing canonical declaration for topic 'discounted wall'
  - observed: docs/v41-scaling-check.md discusses 'discounted wall' without referencing the canonical docs/benchmarks.md
  - expected: claims about 'discounted wall' should declare the canonical source (docs/benchmarks.md) or link its locator
- **R7 low confirmed** `docs/README.md#L3-L5` — uncommitted change to tracked knowledge doc: docs/README.md
  - observed: git status --porcelain reports ' M' for docs/README.md; the working-tree version differs from HEAD
  - expected: knowledge edits that change contracts should be committed (or explicitly scoped) so readers see a stable claim/provenance boundary
- **R7 low confirmed** `README.md#L1` — uncommitted change to tracked knowledge doc: README.md
  - observed: git status --porcelain reports ' M' for README.md; the working-tree version differs from HEAD
  - expected: knowledge edits that change contracts should be committed (or explicitly scoped) so readers see a stable claim/provenance boundary
- **R7 low confirmed** `runs/README.md#L3-L7` — uncommitted change to tracked knowledge doc: runs/README.md
  - observed: git status --porcelain reports ' M' for runs/README.md; the working-tree version differs from HEAD
  - expected: knowledge edits that change contracts should be committed (or explicitly scoped) so readers see a stable claim/provenance boundary
- **R7 low confirmed** `docs/benchmarks.md#L3-L5` — uncommitted change to tracked knowledge doc: docs/benchmarks.md
  - observed: git status --porcelain reports ' M' for docs/benchmarks.md; the working-tree version differs from HEAD
  - expected: knowledge edits that change contracts should be committed (or explicitly scoped) so readers see a stable claim/provenance boundary

## Queued (provenance gaps / revalidation due — not defects)

- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 1×
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 4.93ms
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 2.3×
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 1.7×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 113.2×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 226.5×
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 8×
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 4.33×
- R2 revalidation_due: `runs/README.md` — number not located in artifact index: 6.5×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 2854.1×
- R2 revalidation_due: `docs/optimization-playbook.md` — number not located in artifact index: 0.1ms
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 4.8s
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 4×
- R2 revalidation_due: `docs/optimization-playbook.md` — number not located in artifact index: 15variants
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 3x
- R2 revalidation_due: `README.md` — number not located in artifact index: 16×
- R2 revalidation_due: `README.md` — number not located in artifact index: 226.5×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 209.5tflop/s
- R2 revalidation_due: `README.md` — number not located in artifact index: 95.6%
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 16704steps
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 7s
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 4×
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 3x
- R2 revalidation_due: `docs/internal/W1-REPORT.md` — number not located in artifact index: 95.6%
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 1×
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 24gb
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 2×
- R2 revalidation_due: `docs/internal/W1-REPORT.md` — number not located in artifact index: 4.1s
- R2 revalidation_due: `docs/optimization-playbook.md` — number not located in artifact index: 2.43×
- R2 revalidation_due: `docs/optimization-playbook.md` — number not located in artifact index: 0.5ms
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 3hours
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 4days
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 8×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 2×
- R2 revalidation_due: `docs/internal/W1-REPORT.md` — number not located in artifact index: 4.1s
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 397tflops
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 2×
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 1×
- R2 revalidation_due: `docs/internal/W2-4090-baseline.md` — number not located in artifact index: 70%
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 226.5×
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 2.9×
- R2 revalidation_due: `docs/optimization-playbook.md` — number not located in artifact index: 1ms
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 8×
- R2 revalidation_due: `docs/compare-nanochat.md` — number not located in artifact index: 8×
- R2 revalidation_due: `docs/v41-scaling-check.md` — number not located in artifact index: 226.5×
- R2 revalidation_due: `docs/compare-nanogpt.md` — number not located in artifact index: 226.5×
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 117s
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 209.5tflops
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 16×
- R2 revalidation_due: `docs/benchmarks.md` — number not located in artifact index: 6s
- … 94 more in findings.jsonl

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-05).
