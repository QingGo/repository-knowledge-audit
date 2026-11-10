# PROTOCOL — Historical PR replay of the kblint incremental gate (task-87)

Status: pre-declared protocol, with a documented execution-deviation note (§7) added after the
discovery phase. Analysis uses **zero LLM/API calls**; the only network use is public GitHub
metadata/tarball fetches to materialise pinned trees.

## 1. Question

kblint v0.3.0 ships an incremental PR gate:

```bash
python3 -m kblint diff --before <baseline-report-dir> --after <current-report-dir> \
    --format json,md --fail-on-new medium
```

It classifies findings as **NEW / PERSISTING / FIXED** with a content-based, line-shift-tolerant
key and blocks only NEW findings whose `disposition == confirmed` and severity is at or above
`--fail-on-new`. The controlled-mutation evaluation establishes detection on injected breaks; the
natural-checkout audit establishes that R9 fires on natural drift. This experiment asks the
deployment-facing question the review raised: **on real historical repository events, does the
incremental gate block on genuine new broken knowledge-base (KB) pointers, and stay quiet on
reference-irrelevant changes?**

## 2. Data

Source repositories: 4 small repositories from the natural-checkout audit list, chosen for small
pinned tarballs and active KB/history:

| repo | KB file | natural-audit HEAD | tarball |
|---|---|---|---|
| blader/humanizer | AGENTS.md | `0ef9fe5bc3…` | 24 KB |
| mattpocock/skills | CLAUDE.md | `4ae2317ddb…` | 278 KB |
| addyosmani/agent-skills | AGENTS.md | `301b02b12b…` | 380 KB |
| modelcontextprotocol/servers | AGENTS.md | `36380287ed…` | 1.3 MB |

Events are historical commit events on the default branch. For each event, `base` is the commit
parent (or the older endpoint of a historical range) and `head` is the event commit; both trees are
materialised from `codeload.github.com/<owner>/<repo>/tar.gz/<sha>` (full pinned SHAs recorded in
`events.json` and each `raw/<event>/meta.json`). `git clone` is blocked.

**Sampling rule (16 consecutive commit events).** Recent default-branch commits from the public
commit atom feed; per repo 2–3 events whose changed files include the KB file or build/code/command
paths, plus 1 unrelated-doc commit as a negative control. File lists come from public compare
`.diff` endpoints. **Plus 4 historical-range replays** (oldest fetched commit → natural-audit HEAD)
to exercise multi-commit drift windows. **Plus 2 API-discovered KB-referenced path-deletion events**
(after the REST quota reset; §7) where the head commit deleted a path the KB still names. Total:
**21 events in two reported panels: 18 ordinary replay events + 3 targeted drift-introduction events**, 4+2 repos (targeted additions requested by the Lead after the ordinary replay produced a clean null; see §7).

## 3. Per-event scan and diff

Same per-repo kblint config for baseline and current scans (docs scope = the KB file plus other
agent docs present in either endpoint tree; R9 references on; `allow_missing` for common
runtime/generated trees and lock/log/pid files; `git.enabled=false`; R4 off; `--now 2026-11-09`;
`--fail-on none`). Commands:

```bash
python3 -m kblint scan --repo <base-tree>  --config configs/<slug>.kblint.json \
    --out raw/<event>/baseline --format json,md,sarif --fail-on none --now 2026-11-09
python3 -m kblint scan --repo <head-tree>  --config configs/<slug>.kblint.json \
    --out raw/<event>/current  --format json,md,sarif --fail-on none --now 2026-11-09
python3 -m kblint diff --before raw/<event>/baseline --after raw/<event>/current \
    --out raw/<event>/diff --format json,md --fail-on-new medium
```

Recorded per event: NEW / PERSISTING / FIXED counts, blocking NEW count, diff exit code, scan
runtimes and total latency, and full `findings.jsonl` / `diff.json` / `diff.md` / SARIF artifacts.
**R7 (git provenance) cannot run on tarballs (no `.git`); it is reported as unavailable, not zero.**
R1–R8 had no configured witnesses in this reference-focused config, so their zero counts are not
evidence of absence.

## 4. Adjudication (single annotator)

Every **NEW** finding is re-opened against the head tree (and the base tree to confirm the pointer
was not already broken): `true_new_stale` (the event removed/moved a path, command or dependency the
KB still claims; the head KB is wrong), `false_positive` (target absent but the line is a prose
removal note, negative/forbidden mention, illustrative template, or skill-package-relative path the
root-relative check cannot express), or `runtime_unavailable` (generated/machine-local path that is
absent by design). Every **FIXED** row is checked the other way: `real_repair` iff the named target
was absent in the base tree and resolves in the head tree; otherwise `not_a_repair` (e.g. the scan
doc set changed, or the finding was a false positive that the edit removed). **File move ≠ stale**:
a path that exists only under a new prefix is still a broken root-relative pointer unless the KB was
updated; the moved location is recorded in the evidence.

Single annotator (rule-assisted deterministic first pass + manual review of every NEW and FIXED
row); no inter-annotator agreement is claimed.

## 5. Metrics and statistics

- **Events replayed**, per repo and total; **PR/commit events with ≥1 NEW finding (signal rate)**.
- **NEW TP / FP / runtime-unavailable**, and new-finding precision `TP/(TP+FP)` with an exact
  Clopper–Pearson 95% CI (scipy `beta.ppf`); runtime-unavailable reported separately.
- **Blocking NEW**: total, TP, FP; **events blocked**; **false-blocking rate** = events whose
  blocking NEW rows are all adjudicated non-TP, divided by blocked events.
- **FIXED detection**: FIXED rows, real repairs, real-repair rate.
- **Latency**: baseline scan + current scan + diff wall-clock per event (min/median/max/total).
- **Negative-control quiet rate**: unrelated-doc events with 0 blocking NEW ÷ negative-control
  events.
- **Surface-flagged vs stale** kept separate; the diff's NEW/PERSISTING/FIXED classes are the
  unit of analysis, and adjudication decides correctness.

## 6. Limits (pre-declared)

1. Small convenience sample (4 repos, 22 events), selected for reference-relevant changes; **not a
   false-alarm rate over all PRs**.
2. Tarballs have no `.git`: R7 unavailable; events are commit-parent pairs / historical ranges, not
   GitHub PR merge bases; no PR review metadata.
3. Single annotator; contract judgements (removal notes, package-relative paths) are stated in
   `adjudication.jsonl`.
4. Zero LLM API calls; no repair or downstream coding outcome is claimed.
5. The sample spans a short recent window (atom feed depth ≈ 20 commits/repo) plus two
   path-deletion events; older drift may be underrepresented.

## 7. Execution deviations (documented, not silent)

1. **Discovery endpoint deviation.** The unauthenticated GitHub REST API quota (60/h) was exhausted
   during reconnaissance (commit-list + commit-detail calls). The 16 consecutive events and 4 range
   events were therefore discovered with the public **atom commit feeds**
   (`github.com/<repo>/commits/<branch>.atom`) and **compare `.diff` endpoints**
   (`github.com/<repo>/compare/<base>...<head>.diff`), which use the same pinned full SHAs and no
   auth token. After the quota reset, the targeted drift-introduction events were discovered via
   `GET /repos/<repo>/commits?path=<path>` + commit detail (path history + parent resolution).
2. **Event count and panels.** Target was 10–20 events; the final set is 21 in two separately
   reported panels: 18 ordinary replay events (consecutive commit events + negative controls + 4
   historical-range windows) and 3 targeted drift-introduction events (awesome-go Node→Go quality-
   check migration; last30days hooks fix; last30days restructure window). The targeted panel was
   added after the ordinary 18-event panel produced no NEW findings (a real null, kept as its own
   block in results/summary.json).
3. **Negative controls.** Four unrelated-doc commit events were included, but only three qualified
   as strict docs-only negatives (one KB-edit event was initially mislabeled docs-only and is
   reported as a KB-edit event in `events.json`).
4. **Diff policy.** `--fail-on-new medium` throughout; exit code 1 means the gate would block CI,
   0 means it would not. The gate was never run with `--fail-on-new none` for the recorded exit.
