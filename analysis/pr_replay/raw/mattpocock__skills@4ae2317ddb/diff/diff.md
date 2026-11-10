# kblint incremental audit

- tool: `kblint diff 0.3.0`
- baseline: `/REPOS_ROOT/kb-health/analysis/pr_replay/raw/mattpocock__skills@4ae2317ddb/baseline`
- current: `/REPOS_ROOT/kb-health/analysis/pr_replay/raw/mattpocock__skills@4ae2317ddb/current`
- fail-on-new: **medium** (only NEW confirmed findings at/above this severity block; pre-existing Unknowns never block)

| classification | findings |
|---|---:|
| NEW (blocking) | 0 |
| NEW (Unknown-class, listed, non-blocking) | 0 |
| PERSISTING (pre-existing; non-blocking) | 2 |
| FIXED | 0 |
| before / after totals | 2 / 2 |

## NEW findings

_none_

## PERSISTING findings (pre-existing; listed, never blocking)

| rule | severity | disposition | locator | subject |
|---|---|---|---|---|
| R9 | medium | confirmed | `AGENTS.md#L19` | file path does not exist: agents/openai.yaml |
| R9 | medium | confirmed | `CLAUDE.md#L19` | file path does not exist: agents/openai.yaml |

## FIXED findings (present in baseline, absent now)

_none_

## Honest limits

- Classification is content-based and line-shift tolerant; the same finding appearing in a **different doc** is NEW, by design.
- Unknown-class findings (`unresolved`, `provenance_gap`, `revalidation_due`) are not verified defects and never block CI; they are carried for review.
- `FIXED` means the finding is absent from the current scan (e.g. the reference was repaired); it does not by itself prove the underlying claim is true.
