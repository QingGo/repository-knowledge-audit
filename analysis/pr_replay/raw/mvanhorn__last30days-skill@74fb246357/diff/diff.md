# kblint incremental audit

- tool: `kblint diff 0.3.0`
- baseline: `/REPOS_ROOT/kb-health/analysis/pr_replay/raw/mvanhorn__last30days-skill@74fb246357/baseline`
- current: `/REPOS_ROOT/kb-health/analysis/pr_replay/raw/mvanhorn__last30days-skill@74fb246357/current`
- fail-on-new: **medium** (only NEW confirmed findings at/above this severity block; pre-existing Unknowns never block)

| classification | findings |
|---|---:|
| NEW (blocking) | 0 |
| NEW (Unknown-class, listed, non-blocking) | 0 |
| PERSISTING (pre-existing; non-blocking) | 10 |
| FIXED | 0 |
| before / after totals | 10 / 10 |

## NEW findings

_none_

## PERSISTING findings (pre-existing; listed, never blocking)

| rule | severity | disposition | locator | subject |
|---|---|---|---|---|
| R9 | medium | confirmed | `AGENTS.md#L133` | file path does not exist: docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md |
| R9 | medium | confirmed | `AGENTS.md#L16` | file path does not exist: .github/scripts/prepare_release.py |
| R9 | medium | confirmed | `AGENTS.md#L20` | file path does not exist: scripts/last30days.py |
| R9 | medium | confirmed | `AGENTS.md#L54` | file path does not exist: tests/test_changelog_workflow.py |
| R9 | medium | confirmed | `AGENTS.md#L57` | file path does not exist: lib/__init__.py |
| R9 | medium | confirmed | `AGENTS.md#L61` | file path does not exist: tests/test_source_log_visibility.py |
| R9 | medium | confirmed | `AGENTS.md#L62` | file path does not exist: docs/solutions/integration-issues/digg-cli-agent-path-setup-wizard.md |
| R9 | medium | confirmed | `AGENTS.md#L63` | file path does not exist: tests/test_onboarding_contract.py |
| R9 | medium | confirmed | `AGENTS.md#L69` | file path does not exist: .github/workflows/security.yml |
| R9 | medium | confirmed | `AGENTS.md#L93` | file path does not exist: tests/test_plugin_contract.py |

## FIXED findings (present in baseline, absent now)

_none_

## Honest limits

- Classification is content-based and line-shift tolerant; the same finding appearing in a **different doc** is NEW, by design.
- Unknown-class findings (`unresolved`, `provenance_gap`, `revalidation_due`) are not verified defects and never block CI; they are carried for review.
- `FIXED` means the finding is absent from the current scan (e.g. the reference was repaired); it does not by itself prove the underlying claim is true.
