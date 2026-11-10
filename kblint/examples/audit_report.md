<!-- Generated example report: kblint scan on a real repo (R2).
     Command: cd kb-health/kblint && python3 -m kblint scan --repo /HOME/code/R2
              --config examples/references.kblint.json --out /tmp/kblint-audit --format json,md,sarif
              --now 2026-11-05 --fail-on medium
     Deterministic: no network, no wall clock; rerun gives byte-identical output. -->

# kblint summary

- tool: `kblint 0.2.1` (deterministic, stdlib only, zero network)
- repo: `/HOME/code/R2`
- docs scanned: 1; claims extracted: 77; artifacts indexed: 0
- findings: **3** (confirmed 3, unresolved 0, provenance_gap 0, revalidation_due 0)
- waivers applied: 0
- audit queue (not defects): **31** claims
- R4 (missing supersedes) is disabled by default (experimental; enable with `"rules": {"R4": true}`).

## Findings by rule

| rule | name | findings |
|---|---|---:|
| R1 | pin/version consistency | 0 |
| R2 | number provenance | 0 |
| R3 | cross-doc conflict | 0 |
| R4 | missing supersedes/deprecation | 0 |
| R5 | negative-result/flag expiry | 0 |
| R6 | source-of-truth declaration | 0 |
| R7 | untracked/no-owner knowledge file | 0 |
| R8 | audit queue | 0 |
| R9 | reference check | 3 |

## Severity

- high: 0
- medium: 3
- low: 0

## Confirmed / unresolved findings (evidence, not usefulness)

- **R9 medium confirmed** `AGENTS.md#L124` — file path does not exist: docs/paper.md
  - observed: AGENTS.md#L124: file path `docs/paper.md` not found (checked: docs/paper.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L125` — file path does not exist: docs/arch_design.md
  - observed: AGENTS.md#L125: file path `docs/arch_design.md` not found (checked: docs/arch_design.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L126` — file path does not exist: docs/implementation_notes.md
  - observed: AGENTS.md#L126: file path `docs/implementation_notes.md` not found (checked: docs/implementation_notes.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state

## Queued (provenance gaps / revalidation due — not defects)

_none_

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-05).
