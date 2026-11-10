# kblint summary

- tool: `kblint 0.3.0` (deterministic, stdlib only, zero network)
- repo: `/tmp/pr_replay/repos/mvanhorn__last30days-skill/1f7e85a03f262345e992ddebd7b0c121c2f2862e`
- docs scanned: 1; claims extracted: 14; artifacts indexed: 0
- findings: **2** (confirmed 2, unresolved 0, provenance_gap 0, revalidation_due 0)
- waivers applied: 0
- audit queue (not defects): **3** claims
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
| R9 | reference check | 2 |

## Severity

- high: 0
- medium: 2
- low: 0

## Confirmed / unresolved findings (evidence, not usefulness)

- **R9 medium confirmed** `CLAUDE.md#L19` — file path does not exist: lib/__init__.py
  - observed: CLAUDE.md#L19: file path `lib/__init__.py` not found (checked: lib/__init__.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `CLAUDE.md#L25` — file path does not exist: docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md
  - observed: CLAUDE.md#L25: file path `docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md` not found (checked: docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state

## Queued (provenance gaps / revalidation due — not defects)

_none_

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-09).
