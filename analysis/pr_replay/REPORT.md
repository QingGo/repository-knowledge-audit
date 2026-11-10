# Historical PR replay: validating the kblint v0.3.0 incremental gate (task-87)

**Headline.** We replayed **21 real historical repository events** (4 small public repos) through
`kblint diff --fail-on-new medium`. Two panels are reported separately:

- **Ordinary 20-event replay (18 events after dedupe): 0 NEW findings, 0 blocking, exit 0 on every
  event; 3/3 unrelated-doc negative controls quiet; median scan+diff latency 0.197 s.** Ordinary
  commit events (KB edits, build changes, code-path changes, docs-only) introduced **no new broken
  KB pointers**, and pre-existing findings (1–2 per repo) were carried as PERSISTING and never
  blocked.
- **Targeted drift-introduction events (3 events, selected): 14 NEW findings, all 14 adjudicated
  true new stale pointers (precision 100%, exact Clopper–Pearson 95% CI [76.8, 100]); 14 blocking
  NEW; 2 events blocked (exit 1), 0 false-blocking events; 2 FIXED rows but 0 real repairs
  (document-move/reference-removal, not a repair); latency 0.196 s median.** The gate fires exactly
  on the restructure/migration commits the natural audit had identified: a package restructure with
  the root KB left on old paths (13 NEW) and a Node.js→Go helper migration with the KB still naming
  the removed `.js` (1 NEW).

**Interpretation.** The incremental gate is quiet when nothing reference-level changed (including
the case where 10 pre-existing findings persist) and blocks when a commit actually breaks KB
pointers — with no false blocking in this sample. The ordinary panel is a real null, not a
false-alarm guarantee; the targeted panel is selected for known/potential drift, so its 100%
precision is not a population rate.

## 1. Data

Four small repositories from the natural-checkout audit list (`kb-health/analysis/
natural_checkout_audit/`): **blader/humanizer** (AGENTS.md, 24 KB tarball), **mattpocock/skills**
(CLAUDE.md, 278 KB), **addyosmani/agent-skills** (AGENTS.md, 380 KB),
**modelcontextprotocol/servers** (AGENTS.md, 1.3 MB), plus targeted events from
**mvanhorn/last30days-skill** and **avelino/awesome-go** (the two repos with natural-audit-confirmed
drift; last30days tarballs 12 MB each).

Each event = (base tree with base KB, head tree with head KB), both materialised from pinned
full-SHA tarballs (`codeload.github.com/<owner>/<repo>/tar.gz/<sha>`); `git clone` is blocked.
Event set (see `events.json`, `raw/<event>/meta.json` for SHAs):

| panel | events | composition |
|---|---:|---|
| ordinary | 18 | 4 repos × (2–3 change events + ≥1 docs-only negative control) + 4 historical-range replays (oldest fetched commit → natural-audit HEAD) |
| targeted | 3 | awesome-go `f74f1806` (Node→Go quality-check migration); last30days `74fb2463` (hooks/quiet-start fix, KB unchanged); last30days restructure (`1f7e85a0` parent → `de9bf723` natural-audit HEAD) |

## 2. Method

Per event: scan the base tree with a per-repo config (docs scope = KB file + other agent docs present
in either endpoint; R9 references on; `allow_missing` for runtime/generated trees; `git.enabled=false`;
R4 off; `--now 2026-11-09`; `--fail-on none`) → baseline report; scan the head tree with the same
config → current report; run `python3 -m kblint diff --before <baseline-dir> --after <current-dir>
--out <diff-dir> --format json,md --fail-on-new medium`. Record NEW / PERSISTING / FIXED counts,
blocking NEW, exit code, scan and diff runtimes, and full JSON/MD/SARIF artifacts
(`raw/<event>/`). **R7 (git provenance) cannot run on tarballs (no `.git`) and is reported as
unavailable, not zero.** R1–R8 had no configured witnesses in this reference-focused config.

**Adjudication (single annotator).** Every NEW finding was re-opened against the head tree (and base
tree to confirm it was not already broken): `true_stale` (the event moved/removed a path the KB still
claims; root-relative pointer broken), `false_positive` (prose removal note, negative/forbidden
mention, illustrative template, package-relative path), `runtime_unavailable` (generated/machine-local
path absent by design). Moved paths are still stale from repo root unless the KB was updated; the new
location is recorded. Every FIXED row was checked the other way: `real_repair` iff the named target
was absent in the base tree and resolves in the head tree; otherwise `not_a_repair`.

Discovery note (documented deviation): the unauthenticated GitHub REST quota (60/h) was exhausted in
reconnaissance, so ordinary events were discovered with public atom commit feeds and compare `.diff`
endpoints (same pinned SHAs, no auth token); the three targeted events were then resolved via the
REST API after the quota reset. See `PROTOCOL.md` §7.

## 3. Results

### 3.1 Ordinary 18-event replay (null panel)

| metric | value |
|---|---|
| events replayed | 18 (4 repos) |
| events with ≥1 NEW (signal rate) | **0 / 18 = 0.0%** |
| NEW findings | 0 |
| blocking NEW / events blocked | 0 / 0 |
| PERSISTING findings carried per event | 0–2 (mattpocock 2; mcp-servers 1) |
| FIXED rows | 0 |
| negative-control events (docs-only) | 3 |
| negative-control quiet rate | **3/3 = 100%** |
| scan+diff latency (min / median / max) | 0.163 / **0.197** / 0.304 s |

The 10 events that changed build files, code paths, KB files or multi-commit ranges produced **no
new R9 findings**: either the changed paths were not named by the KB (so no claim was invalidated) or
the KB was edited consistently. PERSISTING findings (pre-existing, e.g. the skill-relative
`agents/openai.yaml` pointer in mattpocock) were listed as non-blocking, as designed: **exit 0 on all
18 events**.

### 3.2 Targeted drift-introduction events (signal panel)

| metric | value |
|---|---|
| events replayed | 3 (3 commits) |
| events with ≥1 NEW | **2 / 3 = 66.7%** |
| NEW findings | **14** |
| NEW true stale / false positive / runtime-unavailable | **14 / 0 / 0** |
| new-finding precision | **100%**, exact CP 95% CI **[76.8, 100.0]** |
| blocking NEW / events blocked | **14 / 2** |
| false-blocking events | **0 / 2 = 0%** |
| FIXED rows / real repairs | **2 / 0** (`not_a_repair`: reference removed/doc moved, named target still absent) |
| latency (min / median / max) | 0.175 / **0.196** / 0.263 s |

Per event:

| event | base → head | NEW | blocking | PERSISTING | FIXED | exit | latency |
|---|---|---:|---:|---:|---:|---:|---:|
| awesome-go `f74f1806` — “Migrate PR quality checks from Node.js to Go (#6055)” | `b004a842` → `f74f1806` | **1** | 1 | 0 | 0 | 1 | 0.17 s |
| last30days `74fb2463` — “fix(hooks): stop running last30days on every session start” | `30d47be7` → `74fb2463` | 0 | 0 | 10 | 0 | 0 | 0.20 s |
| last30days restructure — “Restructure as Codex plugin” window | `1f7e85a0` → `de9bf723` (HEAD) | **13** | 13 | 0 | 2 | 1 | 0.26 s |

**What the blocking findings are (all confirmed true stale against the head tree).**

1. `avelino/awesome-go`, AGENTS.md#L38: KB says the PR-quality workflow runs
   `.github/scripts/check-quality.js`; commit `f74f1806` removed that file and added the Go directory
   `.github/scripts/check-quality/` (`main.go`), and the workflow now runs
   `go run ./.github/scripts/check-quality/`. One NEW confirmed finding → exit 1.
2. `mvanhorn/last30days-skill` restructure: the root KB (AGENTS.md#L16–L86) still points at root-level
   `.github/scripts/prepare_release.py`, `.github/workflows/{validate,security}.yml`, `tests/*`,
   `docs/reference/...` and moved paths now only under `skills/last30days/`
   (`scripts/last30days.py`, `lib/__init__.py`, `references/setup-wizard.md`). 13 NEW confirmed
   findings → exit 1. This is the same drift the natural audit adjudicated at HEAD (S6.28); the
   replay shows the gate would have blocked the change window.
3. `last30days` `74fb2463` deleted hooks/tests referenced by the KB, but those findings already
   existed in the baseline: **10 PERSISTING, 0 NEW, exit 0** — the gate correctly does not block on
   pre-existing debt.
4. FIXED rows in the restructure window were two old `CLAUDE.md` references (`lib/__init__.py`,
   `docs/plans/2026-04-17-...md`) that disappeared from the current scan because the doc text changed
   / the doc was replaced; the named targets are still absent, so these are **not real repairs**
   (adjudicated `not_a_repair`). FIXED detection was therefore exercised but no genuine repair event
   appeared in this window.

## 4. What this adds

- The gate's **policy behavior** matches its design on real events: NEW confirmed findings block
  (2/2 targeted events with genuine drift), PERSISTING and Unknown-class findings never block
  (18/18 ordinary events and the 10-persisting targeted event all exit 0), unrelated docs stay quiet
  (3/3), and no false blocking occurred.
- **File move ≠ stale is a real failure mode:** a rename/restructure alone no longer counts as stale;
  it becomes a NEW finding only because the KB still names the old root-relative path. The replay
  shows both cases (accurate KB edit → quiet; stale KB after move → 13 blocking NEW).
- **Honest symmetry:** the ordinary replay is a null; the targeted replay is selected for drift.
  Together they show the gate is quiet by default and decisive when knowledge references actually
  break, but they do **not** estimate a false-alarm rate over all PRs.

## 5. Limits

1. Small convenience sample: 18 ordinary + 3 targeted events on 4 repositories (plus 2 targeted
   events on 2 more); not a false-alarm or prevalence rate over all historical PRs.
2. Targeted events were chosen because drift was known or expected (natural audit), so their signal
   rate (66.7%) and precision (100%) are not comparable to unselected PRs.
3. Tarballs have no `.git`: R7 unavailable; events are commit-parent pairs / historical windows, not
   GitHub PR merge bases; no review/CI metadata.
4. Single annotator (rule-assisted deterministic pass + hand review of every NEW and FIXED row); no
   inter-annotator agreement.
5. Zero LLM API calls; no repair or downstream coding outcome is claimed.
6. Discovery used public atom/compare endpoints because the REST quota was exhausted
   (`PROTOCOL.md` §7); SHAs are full pinned SHAs, trees come from codeload.
7. FIXED class was exercised (2 rows) but no real repair event was available in the windows; the
   0/2 `not_a_repair` result should not be read as a FIXED-precision estimate.

## 6. Files

```
analysis/pr_replay/
  PROTOCOL.md              # method + sampling + adjudication + documented execution deviations
  run_pr_replay.py         # details/fetch/scan/adjudicate/summarize pipeline
  targeted_drift.py        # targeted drift-introduction event discovery (API after quota reset)
  expand_events.py         # (exploratory) atom/compare event expansion
  find_signal_events.py    # (exploratory) signal-event search
  kb_edit_events.py        # (exploratory) KB-edit event discovery
  summarize_split.py       # ordinary vs targeted metrics -> results/summary.json
  events.json              # 21 events: base/head SHAs, kind, negative-control flag
  configs/<repo>.kblint.json
  raw/<event>/             # baseline/ and current/ scan reports, diff/diff.json+diff.md,
                           # meta.json (SHAs, counts, exit code, runtime), stdout/stderr
  adjudication.jsonl       # every NEW (14) and FIXED (2) row, class + evidence + manual notes
  manual_overrides.json    # single-annotator overrides for moved-path and historical-mention cases
  results/summary.json     # ordinary_events + targeted_events blocks, CP CIs, latency, limits
  REPORT.md                # this report
```

Paper fragment: `kb-health/paper_workshop/agentverify2027/fragments/pr_replay.md`
(S6.30 subsection + Table 36 with both panels, main-§4.6 candidate sentences, honest limits).
Zero paper/supplement edits; zero LLM API calls.
