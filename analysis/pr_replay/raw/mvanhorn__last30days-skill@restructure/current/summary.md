# kblint summary

- tool: `kblint 0.3.0` (deterministic, stdlib only, zero network)
- repo: `/tmp/pr_replay/repos/mvanhorn__last30days-skill/de9bf7232b37a18df034b1165a45a41daadef7e2`
- docs scanned: 2; claims extracted: 66; artifacts indexed: 0
- findings: **13** (confirmed 13, unresolved 0, provenance_gap 0, revalidation_due 0)
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
| R9 | reference check | 13 |

## Severity

- high: 0
- medium: 13
- low: 0

## Confirmed / unresolved findings (evidence, not usefulness)

- **R9 medium confirmed** `AGENTS.md#L110` — file path does not exist: tests/test_plugin_contract.py
  - observed: AGENTS.md#L110: file path `tests/test_plugin_contract.py` not found (checked: tests/test_plugin_contract.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L114` — file path does not exist: docs/reference/xai-marketplace-submission.md
  - observed: AGENTS.md#L114: file path `docs/reference/xai-marketplace-submission.md` not found (checked: docs/reference/xai-marketplace-submission.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L16` — file path does not exist: .github/scripts/prepare_release.py
  - observed: AGENTS.md#L16: file path `.github/scripts/prepare_release.py` not found (checked: .github/scripts/prepare_release.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L21` — file path does not exist: scripts/last30days.py
  - observed: AGENTS.md#L21: file path `scripts/last30days.py` not found (checked: scripts/last30days.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L51` — file path does not exist: .github/workflows/validate.yml
  - observed: AGENTS.md#L51: file path `.github/workflows/validate.yml` not found (checked: .github/workflows/validate.yml)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L61` — file path does not exist: tests/test_changelog_workflow.py
  - observed: AGENTS.md#L61: file path `tests/test_changelog_workflow.py` not found (checked: tests/test_changelog_workflow.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L64` — file path does not exist: lib/__init__.py
  - observed: AGENTS.md#L64: file path `lib/__init__.py` not found (checked: lib/__init__.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L68` — file path does not exist: tests/test_source_log_visibility.py
  - observed: AGENTS.md#L68: file path `tests/test_source_log_visibility.py` not found (checked: tests/test_source_log_visibility.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L69` — file path does not exist: docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md
  - observed: AGENTS.md#L69: file path `docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md` not found (checked: docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L70` — file path does not exist: references/setup-wizard.md
  - observed: AGENTS.md#L70: file path `references/setup-wizard.md` not found (checked: references/setup-wizard.md)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L70` — file path does not exist: tests/test_grok_bot_host_contract.py
  - observed: AGENTS.md#L70: file path `tests/test_grok_bot_host_contract.py` not found (checked: tests/test_grok_bot_host_contract.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L70` — file path does not exist: tests/test_onboarding_contract.py
  - observed: AGENTS.md#L70: file path `tests/test_onboarding_contract.py` not found (checked: tests/test_onboarding_contract.py)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state
- **R9 medium confirmed** `AGENTS.md#L86` — file path does not exist: .github/workflows/security.yml
  - observed: AGENTS.md#L86: file path `.github/workflows/security.yml` not found (checked: .github/workflows/security.yml)
  - expected: references in a knowledge artifact must resolve to repository artifacts that exist in the scanned repository state

## Queued (provenance gaps / revalidation due — not defects)

_none_

## Honest limits

- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. It does not judge whether knowledge is useful, correct as a route, or harmful; the audit queue is not a defect list; findings are not a population measurement.
- The doc surface is markdown only; artifact-internal, git-history, and session-history defects are out of scope unless they reach a configured doc/artifact field.
- Each finding carries a claim locator, evidence locators, a verification method and a disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.
- Generated deterministically; no wall-clock or network input (now=2026-11-09).
