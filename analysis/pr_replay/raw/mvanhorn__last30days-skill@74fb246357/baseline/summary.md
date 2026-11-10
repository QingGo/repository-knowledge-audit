# kblint summary

- tool: `kblint 0.3.0` (deterministic, stdlib only, zero network)
- repo: `/tmp/pr_replay/repos/mvanhorn__last30days-skill/30d47be7020b542ade26eeb02d26a5abccbd3491`
- docs scanned: 2; claims extracted: 71; artifacts indexed: 0
- findings: **10** (confirmed 10, unresolved 0, provenance_gap 0, revalidation_due 0)
- waivers applied: 0
- audit queue (not defects): **35** claims
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
| R9 | reference check | 10 |

## Severity

- high: 0
- medium: 10
- low: 0

## Confirmed / unresolved findings (evidence, not usefulness)

- **R9 medium confirmed** `AGENTS.md#L133` — file path does not exist: docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md
  - observed: AGENTS.md#L133: file path `docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md` not found (checked: docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L16` — file path does not exist: .github/scripts/prepare_release.py
  - observed: AGENTS.md#L16: file path `.github/scripts/prepare_release.py` not found (checked: .github/scripts/prepare_release.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L20` — file path does not exist: scripts/last30days.py
  - observed: AGENTS.md#L20: file path `scripts/last30days.py` not found (checked: scripts/last30days.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L54` — file path does not exist: tests/test_changelog_workflow.py
  - observed: AGENTS.md#L54: file path `tests/test_changelog_workflow.py` not found (checked: tests/test_changelog_workflow.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L57` — file path does not exist: lib/__init__.py
  - observed: AGENTS.md#L57: file path `lib/__init__.py` not found (checked: lib/__init__.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L61` — file path does not exist: tests/test_source_log_visibility.py
  - observed: AGENTS.md#L61: file path `tests/test_source_log_visibility.py` not found (checked: tests/test_source_log_visibility.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L62` — file path does not exist: docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md
  - observed: AGENTS.md#L62: file path `docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md` not found (checked: docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L63` — file path does not exist: tests/test_onboarding_contract.py
  - observed: AGENTS.md#L63: file path `tests/test_onboarding_contract.py` not found (checked: tests/test_onboarding_contract.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L69` — file path does not exist: .github/workflows/security.yml
  - observed: AGENTS.md#L69: file path `.github/workflows/security.yml` not found (checked: .github/workflows/security.yml)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L93` — file path does not exist: tests/test_plugin_contract.py
  - observed: AGENTS.md#L93: file path `tests/test_plugin_contract.py` not found (checked: tests/test_plugin_contract.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state

## Queued (provenance gaps / revalidation due — not defects)

_none_

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-09).
