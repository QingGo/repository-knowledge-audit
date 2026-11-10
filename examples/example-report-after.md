# kblint summary

- tool: `kblint 0.3.0` (deterministic, stdlib only, zero network)
- repo: `/SCRATCH_NOT_SHIPPED
- docs scanned: 11; claims extracted: 21; artifacts indexed: 3
- findings: **9** (confirmed 4, unresolved 2, provenance_gap 0, revalidation_due 3)
- waivers applied: 0
- audit queue (not defects): **3** claims
- **R4 (missing supersedes) is ENABLED but still experimental**: artifact-chronology flags can be cross-shape false positives; treat R4 findings as review candidates (see README honest limits).

## Findings by rule

| rule | name | findings |
|---|---|---:|
| R1 | pin/version consistency | 1 |
| R2 | number provenance | 4 |
| R3 | cross-doc conflict | 1 |
| R4 | missing supersedes/deprecation | 1 |
| R5 | negative-result/flag expiry | 1 |
| R6 | source-of-truth declaration | 1 |
| R7 | untracked/no-owner knowledge file | 0 |
| R8 | audit queue | 0 |
| R9 | reference check | 0 |

## Severity

- high: 1
- medium: 3
- low: 5

## Confirmed / unresolved findings (evidence, not usefulness)

- **R1 low unresolved** `docs/pins.md#L3` — mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu130; pool contains 2.12.1×1, 2.14.1×1
  - observed: doc declares 2.14.1+cu130; matching artifacts record 2.12.1×1, 2.14.1×1
  - expected: a doc pin is only verifiable when the governed artifact pool has a single environment, or the pin is scoped per round/device; mixed pools are an unresolved scope conflict
- **R2 high confirmed** `docs/numbers.md#L3` — artifact_mismatch: 400tflops vs dw13_tile_tflops = 358.093
  - observed: claim states 400tflops (best dw13 tile reaches); artifacts/bench.json :: dw13_tile_tflops = 358.093
  - expected: the cited artifact field must agree within display precision (half last place 0.5) or relative tolerance 0.0005 (observed relative difference 1.05e-01)
- **R3 medium confirmed** `docs/conflict_a.md#L3` — cross-doc conflict on 'r49 configuration best step' (ms): 60.94 vs 61.93
  - observed: docs/conflict_a.md states 60.94ms; other doc(s) state different values: docs/conflict_b.md:61.93
  - expected: the same subject must have one value across docs unless a claim/section is explicitly marked superseded/deprecated
- **R4 medium confirmed** `docs/supersede.md#L3` — missing supersedes: newer artifact artifacts/r50_v2.json contradicts artifacts/r50_v1.json (60.94ms vs 60.43ms)
  - observed: claim cites artifacts/r50_v1.json (step_ms = 60.94) and states 60.94ms; newer artifact artifacts/r50_v2.json records 60.43 at step_ms (mtime 2026-11-01T00:00:00Z)
  - expected: a claim contradicted by a newer artifact must be marked superseded / deprecated (or scoped to its artifact date)
- **R5 medium confirmed** `docs/negative.md#L3` — negative/flag claim predates environment change 2026-10-01
  - observed: claim dated 2026-09-01 (negative_marker) is older than environment-change date 2026-10-01
  - expected: negative results and flags must be revalidated after an environment change or carry a date/expiry
- **R6 low unresolved** `docs/other_target.md#L3` — missing canonical declaration for topic 'acceptance target'
  - observed: docs/other_target.md discusses 'acceptance target' without referencing the canonical docs/target.md #L3
  - expected: claims about 'acceptance target' should declare the canonical source (docs/target.md) or link its locator

## Queued (provenance gaps / revalidation due — not defects)

- R2 revalidation_due: `docs/target.md` — number not located in artifact index: 35.83ms
- R2 revalidation_due: `docs/other_target.md` — number not located in artifact index: 35.83ms
- R2 revalidation_due: `docs/conflict_b.md` — number not located in artifact index: 61.93ms

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-05).
