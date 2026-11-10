# kblint summary

- tool: `kblint 0.3.0` (deterministic, stdlib only, zero network)
- repo: `/tmp/pr_replay/repos/addyosmani__agent-skills/8b376edc5488221c75c1c7c229cdec26aeab3c9b`
- docs scanned: 2; claims extracted: 79; artifacts indexed: 0
- findings: **0** (confirmed 0, unresolved 0, provenance_gap 0, revalidation_due 0)
- waivers applied: 0
- audit queue (not defects): **26** claims
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
| R9 | reference check | 0 |

## Severity

- high: 0
- medium: 0
- low: 0

## Confirmed / unresolved findings (evidence, not usefulness)

_none_

## Queued (provenance gaps / revalidation due — not defects)

_none_

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-09).
