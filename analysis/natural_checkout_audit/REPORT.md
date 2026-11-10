# Natural-checkout audit: does kblint find NATURAL KB drift in unseen repositories? (task-85)

**Headline.** We ran kblint v0.2.1 on **16 pinned public repository checkouts** (never-seen
`git archive`-equivalent tarballs; 1,290 extracted claims, 608 audit-queue claims). The reference rule
produced **28 R9 findings**; after adjudicating every one against the extracted tree,
**14 are confirmed natural stale pointers, 8 are false positives, and 6 are runtime/generated paths**
that the config contract cannot decide (`precision TP/(TP+FP) = 63.6%, exact Clopper–Pearson 95% CI
40.7–82.8%`; confirmed-stale rate among R9 = 50.0%, CI 30.7–69.4%). The natural drift is real but
**clustered**: **2/16 repositories** contain all 14 confirmed stale pointers, and one repo restructure
accounts for 13 of them. A deterministic random sample of **150 audit-queue claims** was adjudicated
against the trees: **9.3% Verified, 2.0% Stale (CI 0.4–5.7%), 88.7% Unknown** — the queue is an
Unknown-risk list, not a stale list. Zero LLM calls; kblint runs are deterministic (byte-identical
reruns on 3 checked repos; median scan 0.094 s).

**Why this complements the mutation evaluation.** The paper's current linter evidence is
controlled-mutation (S6.17: 25/25 injected breaks detected, 0/40 false alarms). This trace asks the
opposite question — would the rule fire on **naturally drifted** KBs it has never seen, and are its
natural findings correct? Answer: yes it fires (14 confirmed stale), but natural precision is lower
(63.6% vs 100% on unambiguous mutants) because real KB prose contains removal notes, generated paths,
package-relative paths, and illustrative templates that the rule cannot distinguish. That is exactly
why the workflow keeps a human adjudication layer between findings and repairs.

## 1. Data and sample

- **Frame:** the 76 public repositories of `analysis/real_scan/scan_rows.json` (root `AGENTS.md`/
  `CLAUDE.md`, popular-repo lower-bound sample). **Sample: 16 repositories**, selected stratified on
  manifest class (node 4 / python 3 / other 9), KB file type (AGENTS.md 13, CLAUDE/copilot 3), and
  prior claim band, then resampled small-first because `git clone` is blocked and codeload throughput
  made large tarballs infeasible (cap 15 MiB; skips recorded). Claims-band note: the fetched set is
  low/mid-band by the *prior* counts, but the current scan's wider docs scope yields four
  high-extraction repos (caveman 286, mcp-servers 186, HowToLiveBetter 107, ai-job-search 99), so
  high-claim KBs are represented at scan time. **Selection is a convenience sample, not a
  prevalence sample.**
- **Pinning:** every repo pinned to a default-branch HEAD SHA resolved once through
  `api.github.com/repos/<owner>/<repo>/commits?per_page=1`; tarball fetched by
  `codeload.github.com/<owner>/<repo>/tar.gz/<sha>`; SHA recorded in `fetch_meta.json`,
  `raw/<repo>/meta.json` and Table 1. Total tarball volume 49.8 MB.
- **Attempts/skips:** 2 repos were pre-fetched for the pipeline pilot; 34 candidates were attempted
  in two fetch waves. 14 additional repos failed (codeload `curl rc=63` oversize cap or `rc=28`
  timeout) and were replaced by later small candidates; the final 16 are the successful pins. The
  killed second wave means the complete skip log is partial (4 explicit `no extracted tree` records
  in `fetch_meta.json`; the rest are in the shell logs). This biases the sample toward small repos and
  is stated as a limit, not corrected silently.

## 2. Method

Per repo: generate `configs/<slug>.kblint.json` — docs = the repo's KB file plus any existing
`AGENTS.md`/`CLAUDE.md`/`docs/AGENTS.md`/`.github/copilot-instructions.md`/`GEMINI.md`; R9 references
on (paths, links, make targets, npm scripts); `allow_missing` for common runtime/generated trees and
lock/log/pid files; `git.enabled=false` (**tarballs have no `.git`, so R7 cannot run — reported as
unavailable, not zero**); R4 off; `now=2026-11-09`; `--fail-on none`. Full scan JSON+Markdown+SARIF
per repo under `raw/<slug>/`. Only **R9 fired** (28 findings); R1–R6/R8 have no configured
artifacts/pins/run-index/source-of-truth in this reference-focused config, so their zero counts mean
"no witness configured", not "no issue".

**Adjudication (single annotator).** Every R9 finding was re-checked against the extracted tree by
hand (target at doc-relative and root-relative resolution; make/npm manifests; context line read for
mention type) and labelled:

- `true_stale` — pointer target removed/moved and the KB is wrong at repo root;
- `false_positive` — target absent but the line is a historical removal note, a negative/forbidden
  mention, an illustrative template, or a skill-package-relative path the rule cannot resolve;
- `runtime_unavailable` — generated/machine-local path that is absent by design (config-contract gap).

A deterministic random sample of 150 audit-queue claims (seed 20261109, ≤10/repo) was adjudicated the
same way: `Verified` if the claim's named tree artifact resolves, `Stale` if it resolves nowhere, else
`Unknown` (numeric results, design judgments, negative results, procedural rules). The queue is
reported **separately** from confirmed findings.

Commands (reproduce):

```bash
cd kb-health/analysis/natural_checkout_audit
python3 run_pipeline.py select     # selection.json (stratified frame)
python3 run_pipeline.py fetch      # pinned tarballs -> /tmp/natural_audit/repos/<owner__repo>
python3 run_pipeline.py scan       # configs + raw/<slug>/{findings.jsonl,audit_queue.jsonl,summary.md,report.sarif,meta.json}
python3 run_pipeline.py adjudicate # adjudication.jsonl (R9 + queue sample; manual_overrides.json applied)
python3 run_pipeline.py summarize  # results/summary.json
```

## 3. Aggregate results

| metric | value | exact Clopper–Pearson 95% CI |
|---|---:|---|
| repositories | 16 | — |
| claims extracted | 1,290 | — |
| audit-queue claims (surface-flagged, **not** stale) | 608 (47.1%) | — |
| R9 findings | 28 | — |
| confirmed stale (`true_stale`) | **14** | — |
| false positives | **8** | — |
| runtime/generated (unavailable by contract) | **6** | — |
| precision `TP/(TP+FP)` | **63.6%** | **[40.7, 82.8]** |
| confirmed-stale rate among R9 | **50.0%** | **[30.7, 69.4]** |
| repos with ≥1 confirmed stale | **2 / 16** | — |
| scan runtime (min / median / max) | 0.069 / 0.094 / 0.463 s | — |
| determinism (3 repos rerun) | byte-identical | — |
| **audit-queue sample** (n=150) | Verified 14 (9.3%), Stale 3 (2.0%), Unknown 133 (88.7%) | stale rate [0.4, 5.7]% |

R9 findings by kind: 27 `path`, 1 `markdown link`; no make/npm findings in this sample.
Natural drift is **clustered**: `mvanhorn/last30days-skill` contributes 13 confirmed pointers
(after a packaging restructure) and `avelino/awesome-go` 1 (JS helper replaced by a Go directory);
the other 14 repos are clean at the reference layer (13 with zero R9, one with only
false-positive/runtime findings).

## 4. Per-repository results

| repository | pinned SHA | KB | claims | queue | R9 | TP | FP | runtime-unavail. | scan |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| JuliusBrussee/caveman | `3dc497a7f8` | AGENTS.md | 286 | 129 | 8 | 0 | 3 | 5 | 0.46 s |
| abi/screenshot-to-code | `a8139779f7` | AGENTS.md | 54 | 22 | 0 | 0 | 0 | 0 | 0.10 s |
| addyosmani/agent-skills | `301b02b12b` | AGENTS.md | 79 | 26 | 0 | 0 | 0 | 0 | 0.24 s |
| ai-job-search-dev/ai-job-search | `2b3f613fda` | AGENTS.md | 99 | 49 | 0 | 0 | 0 | 0 | 0.09 s |
| avelino/awesome-go | `499762cd36` | AGENTS.md | 23 | 15 | 1 | **1** | 0 | 0 | 0.08 s |
| ayghri/i-have-adhd | `1ecea1993b` | AGENTS.md | 48 | 16 | 0 | 0 | 0 | 0 | 0.10 s |
| blader/humanizer | `0ef9fe5bc3` | AGENTS.md | 37 | 22 | 0 | 0 | 0 | 0 | 0.28 s |
| eternity4719/HowToLiveBetter | `dff814dcbb` | AGENTS.md | 107 | 77 | 1 | 0 | 1 | 0 | 0.25 s |
| github/spec-kit | `a60bd9bad5` | AGENTS.md | 23 | 6 | 0 | 0 | 0 | 0 | 0.10 s |
| modelcontextprotocol/servers | `36380287ed` | AGENTS.md | 186 | 105 | 1 | 0 | 1 | 0 | 0.14 s |
| multica-ai/andrej-karpathy-skills | `2c60614193` | CLAUDE.md | 45 | 10 | 0 | 0 | 0 | 0 | 0.09 s |
| mvanhorn/last30days-skill | `de9bf7232b` | AGENTS.md | 66 | 31 | 13 | **13** | 0 | 0 | 0.09 s |
| rtk-ai/rtk | `08a261a0d0` | CLAUDE.md | 70 | 27 | 0 | 0 | 0 | 0 | 0.08 s |
| ultraworkers/claw-code | `f51a33a896` | AGENTS.md | 60 | 38 | 2 | 0 | 1 | 1 | 0.08 s |
| usestrix/strix | `215482eb22` | AGENTS.md | 35 | 17 | 0 | 0 | 0 | 0 | 0.07 s |
| mattpocock/skills | `4ae2317ddb` | CLAUDE.md | 72 | 18 | 2 | 0 | 2 | 0 | 0.07 s |
| **total** | — | — | **1,290** | **608** | **28** | **14** | **8** | **6** | **2.30 s** |

## 5. What natural drift looks like — and what the rule cannot tell apart

**Confirmed natural stale (14, all in 2 repos).**

1. `mvanhorn/last30days-skill` (13 findings; AGENTS.md#L16–L86). The repository was restructured into
   a package at `skills/last30days/` while the root KB still points at root-level targets:
   `.github/scripts/prepare_release.py`, `.github/workflows/{validate,security}.yml`, `tests/*`, and
   `docs/reference/…` (absent at root), plus `scripts/last30days.py`, `lib/__init__.py`,
   `references/setup-wizard.md` which now exist **only under `skills/last30days/`**. In-tree evidence:
   `skills/last30days/scripts/last30days.py` etc.; no `.github/`, `tests/`, or `docs/` tree at root.
2. `avelino/awesome-go` (1 finding; AGENTS.md#L38). The KB says the PR quality workflow runs
   `.github/scripts/check-quality.js`, but the implementation is now the Go directory
   `.github/scripts/check-quality/` (`main.go`, `output_test.go`) and the workflow runs
   `go run ./.github/scripts/check-quality/` — a genuine name/extension drift.

**False positives (8) and runtime-unavailable (6) — the classes a maintainer must filter.**

| class | count | example (real) |
|---|---:|---|
| historical/removal mentions | 5 | caveman CLAUDE.md L181 "We removed … `.github/copilot-instructions.md`"; mcp-servers sweep table "`.github/dependabot.yml` (deleted)"; claw-code "forbidden doc strings … `assets/clawd-hero.jpeg`" |
| runtime/generated/machine-local paths | 6 | caveman repo-local `.caveman/config.json`, installer-generated `.windsurf/rules/…`/`.clinerules/…`, eval output `snapshots/fidelity.json`; claw-code `.claude/settings.local.json` |
| skill-package-relative paths | 2 | mattpocock/skills `agents/openai.yaml` — exists at `skills/*/agents/openai.yaml`; root-relative check cannot express the per-skill base |
| illustrative template | 1 | HowToLiveBetter `[x](docs/x.md)` — format example for adding docs, not a link |

Natural precision is therefore **63.6% (14/22 decidable)** versus **100% (25/25)** on the injected
mutation suite: real KB prose carries tense/negation, generated paths and package-relative idioms
that a lexical reference check cannot resolve. This is a property of *natural* findings, not a rule
bug, and it is why every natural finding in this trace was human-adjudicated before being called
stale.

**Audit-queue sample (n=150).** 14 Verified (named tree artifact resolves), 3 Stale (a named artifact
is absent — all three are last30days paths already covered by the R9 findings), 133 Unknown
(88.7%): numeric results, design/rationale claims, negative results and procedural rules with no
tree witness. This matches the paper's position that the queue is an Unknown-risk list, not a defect
list, and that surface-flagged ≠ stale (608 queued claims, 14 confirmed stale pointers).

## 6. Natural vs mutation: what this adds

- **It answers the reviewer's question:** kblint does fire on natural drift in unseen checkouts —
  14 confirmed stale pointers, including a 13-pointer cluster caused by a real repository
  restructure and a helper-language migration. Mutation tests establish sensitivity on unambiguous
  breakages; this trace establishes that natural drift exists, is detectable in practice, and can be
  repaired from the extracted tree.
- **It quantifies the human layer:** natural precision 63.6% [40.7, 82.8] means roughly one in three
  natural findings needs human adjudication before repair; the classes are stable and filterable
  (historical mention, generated path, package-relative, illustrative).
- **It keeps coverage honest:** 47.1% of claims surface-flag into the queue, 88.7% of the sampled
  queue claims are Unknown, and reference drift concentrates in restructured/edited repositories —
  consistent with a maintenance layer, not a completeness claim.
- **R7 remains unavailable** on tarballs; a full natural audit should run on a git checkout to add
  tracked/owner provenance. R1–R6/R8 were configured but had no witnesses in this reference-focused
  scan; their zero counts are not evidence of absence.

## 7. Limits

1. Convenience sample (16 of 76 popular repos, small-first after the 15 MiB cap); not a prevalence or
   population estimate; the size cap and fetch failures bias toward smaller repos and are recorded.
2. Tarballs have **no `.git`**: R7 git-provenance cannot run; "when did the reference break?" is out of
   scope. (The last30days cluster is consistent with a restructure, but the checkout cannot date it.)
3. R9 scope depends on the generated config (KB docs only; `allow_missing` runtime contract); the
   precision is conditional on that declared scope and on the annotator's contract judgement
   (e.g. if the three last30days moved-paths were judged package-relative false positives instead,
   TP=11, precision=11/19=57.9% — one sensitivity, reported not hidden).
4. Single annotator (rule-assisted deterministic pass + hand review of every R9 finding and the
   non-Unknown queue rows); no inter-annotator agreement.
5. Zero LLM calls; adjudication is deterministic/manual, not model-assisted; no coding or behavioural
   outcome and no repair experiment are claimed here.
6. The second fetch wave was interrupted; the skip log is partial (see §1).

## 8. Files

```
analysis/natural_checkout_audit/
  PROTOCOL.md                 # pre-declared sampling/method/adjudication/statistics + amendments
  run_pipeline.py             # select/fetch/scan/adjudicate/summarize (re-runnable)
  selection.json              # stratified frame sample (20 slots + reserves)
  fetch_targets.json          # small-first fetch list actually used
  fetch_meta.json             # pinned SHAs, tarball bytes, files, KB file, tree paths, skips
  configs/<slug>.kblint.json  # 16 per-repo configs
  raw/<slug>/                 # findings.jsonl, audit_queue.jsonl, summary.md, report.sarif,
                              # stdout.txt, stderr.txt, meta.json (command/exit/runtime/counts/hashes)
  adjudication.jsonl          # every R9 finding (28) + 150 queue claims, class + evidence + notes
  manual_overrides.json       # single-annotator adjudication notes applied to every R9 finding
  results/summary.json        # aggregate + per-repo metrics, CIs, determinism, composition
  REPORT.md                   # this report
```

Paper fragment: `kb-health/paper_workshop/agentverify2027/fragments/natural_audit.md`
(S6.28 subsection + Table 34, main-§4.6 candidate sentences, honest limits). Zero paper/supplement
edits; zero API calls.
