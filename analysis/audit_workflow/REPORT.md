# End-to-end real-repository KB audit workflow (kblint v0.2.1)

Task-72 / AGENTVERIFY 2027 revision. **No model calls, no network.** This directory is a complete,
re-runnable trace of the audit workflow on **two real repositories**: a stale knowledge file is
audited against its own checkout, a minimal KB repair is applied in a throwaway temp copy, and both
states are re-audited. Everything here is produced by
[`run_audit_workflow.py`](run_audit_workflow.py) and [`make_figure.py`](make_figure.py); raw kblint
outputs are kept under [`raw/`](raw/).

Source repositories were **read-only** throughout: only `git archive`, `git show` and `git ls-tree`
were used, and `git status --porcelain` was recorded identical before and after the run
(`raw/summary.json.source_repos_unchanged = true`). Temp trees live in `/SCRATCH_NOT_SHIPPED/`.
The workspace is not a git checkout; the "committed example configs" are the shipped JSON files in
[`configs/`](configs/) (per-repo `*.kblint.json` workflow config + `*.generic.json` sensitivity config).

## 1. Repositories, commits and KB repair

| repo | parent commit (stale KB) | fix commit | KB file changed | repair diff |
|---|---|---|---|---|
| `R2` | `2bc2feba97ca5ca1e920bab57413b99779402e0a` | `29a0bc7e06aefb615eb5c07a46f56480a9bef0af` | `AGENTS.md` (only file in fix diff) | 2 insertions / 2 deletions: `make profile-deep` → `make profile-chrome`; volatile "316 pass" test count → "<private KB text removed> pytest <private KB text removed>" |
| `R3` | `b674155f2b941b64e0b4110c2c7450badb2c28aa` | `07635ed1a8fb97ea17fee4c728788b2e89bfc590` | `AGENTS.md` (only file in fix diff) | 5 insertions / 5 deletions: `docs/performance.md` → `docs/paper_alignment.md`; stale skill name `memory-update` → `short-term-memory` (×4) |

For each repo the workflow materializes:
`parent/` = `git archive <parent>`; `repaired/` = parent tree with the KB file replaced by
`git show <fix>:AGENTS.md`. The script **proves** `repaired/` is byte-identical to
`git archive <fix>` (`minimal_repair_equals_fix_tree: true` in `raw/summary.json`), so the only
difference between the two conditions is the KB repair.

## 2. Configurations

Two configs per repo (identical except `allow_missing`), docs scope = the repo's real KB file
(`AGENTS.md`; `CLAUDE.md`/`docs/AGENTS.md` are also in scope but absent in both repos), references
enabled (`check_paths`, `check_links`, `check_make`, `check_npm`), `git.enabled=false` (temp trees
have no `.git`), `now=2026-11-05`:

- **workflow config** `configs/<repo>.kblint.json` — committed example config with
  `allow_missing` for declared runtime/generated/external dirs
  (`artifacts|weights|runs|outputs|dist|build|node_modules|data|checkpoints|cache|logs|profiles`);
- **generic config** `configs/<repo>.generic.json` — same but **without** `allow_missing`, used only
  for the false-positive-by-contract sensitivity scan.

## 3. Exact commands

For every (repo, condition, config) the workflow runs (recorded verbatim in each
`raw/<repo>/<condition>__<config>/meta.json`):

```bash
cd kb-health/kblint
python3 -m kblint scan \
  --repo /SCRATCH_NOT_SHIPPED/<repo>/<parent|repaired> \
  --config /REPOS_ROOT/kb-health/analysis/audit_workflow/configs/<repo>.<kblint|generic>.json \
  --out  /REPOS_ROOT/kb-health/analysis/audit_workflow/raw/<repo>/<condition>__<config> \
  --format json,md,sarif --fail-on medium --now 2026-11-05
```

Plus a second identical run into a scratch dir to verify determinism (all four output files are
byte-identical, `deterministic_rerun_byte_identical=true` for all 8 scans). Reproduce all of it:

```bash
cd kb-health/analysis/audit_workflow
python3 run_audit_workflow.py          # git archive extraction + 8 scans + raw/summary.json
python3 make_figure.py                # figures/before_after_repair.{pdf,png} + raw/figure_data.json
```

## 4. Before/after results (workflow config)

All findings in these scans are **R9 reference-check** findings; `--fail-on medium` exit code `1`
means at least one medium finding. The **audit queue is not a defect list** and its count is
unchanged by the repair.

| repo | state | docs | claims | audit queue | R9 findings | severity | exit | scan wall time |
|---|---|---:|---:|---:|---:|---|---:|---:|
| R2 | parent (stale KB) | 1 | 77 | 31 | **4** | 3 medium + 1 low | 1 | 0.084 s |
| R2 | repaired (fix KB) | 1 | 77 | 31 | **3** | 3 medium | 1 | 0.067 s |
| R3 | parent (stale KB) | 1 | 79 | 25 | **1** | 1 medium | 1 | 0.065 s |
| R3 | repaired (fix KB) | 1 | 79 | 25 | **0** | — | 0 | 0.069 s |
| **total** | | 2 | **156** | **56** | **5 → 3** | | | **0.578 s for all 8 scans** |

**The task's "expect 0 R9 after repair" holds for R3 (1 → 0) but not for R2
(4 → 3).** The actual fix commit is minimal: it removes the one `make profile-deep` reference
(and a volatile test count) and does **not** touch the three stale `docs/*.md` pointers, which stay.
This is a measured result, not a workflow failure: a complete R2 repair needs three more
line edits that are outside the given fix commit.

### 4.1 Generic-config sensitivity (false positives by contract)

| repo | state | R9 findings (generic) | difference vs workflow config |
|---|---|---:|---|
| R2 | parent | 6 | +`artifacts/last_profile.json`, +`weights/tokenizer.json` (runtime/generated/external) |
| R2 | repaired | 5 | same two |
| R3 | parent | 1 | 0 |
| R3 | repaired | 0 | 0 |

## 5. Manual adjudication of every finding

All 7 unique R9 findings (across both configs and both conditions) were opened in the KB file and
checked against the extracted tree; recorded in [`adjudication.json`](adjudication.json).
Classes: **true-stale** = referenced repository artifact is absent and the line is an actionable
KB defect under the declared contract; **false-positive-by-contract** = the reference is a declared
runtime/generated/external location and is not a defect under the committed config.

| # | repo | locator | KB claim (line text, shortened) | reference | sev | adjudication | evidence | after repair |
|---|---|---|---|---|---|---|---|---|
| 1 | R2 | `AGENTS.md#L124` | `- <private KB text removed>: … <private KB text removed>: `docs/paper.md`` | `docs/paper.md` | med | **true-stale → Verified** | both commits have **no `docs/` directory**; line unchanged by fix | persists (residual) |
| 2 | R2 | `AGENTS.md#L125` | `- <private KB text removed>: …; <private KB text removed>: `docs/arch_design.md`` | `docs/arch_design.md` | med | **true-stale → Verified** | no `docs/` directory; line unchanged | persists (residual) |
| 3 | R2 | `AGENTS.md#L126` | `- <private KB text removed>: `docs/implementation_notes.md`` | `docs/implementation_notes.md` | med | **true-stale → Verified** | no `docs/` directory; line unchanged | persists (residual) |
| 4 | R2 | `AGENTS.md#L23` | `make profile-deep  # nsys + torch.profiler <private KB text removed> trace` | `make profile-deep` | low | **true-stale → Removed** | parent root `Makefile` has no `profile-deep` (has `profile-chrome`); fix replaces the line | removed |
| 5 | R2 | `AGENTS.md#L196` | `- Profile <private KB text removed>: `make profile` <private KB text removed> JSON <private KB text removed> `artifacts/last_profile.json`` | `artifacts/last_profile.json` | med | **false-positive-by-contract** (generic config only) | KB itself says `make profile` writes JSON there; generated runtime artifact | suppressed by `allow_missing` |
| 6 | R2 | `AGENTS.md#L205` | `… <private KB text removed> `weights/tokenizer.json` <private KB text removed>. <private KB text removed>.` | `weights/tokenizer.json` | med | **false-positive-by-contract** (generic config only) | external ~150 GB model store, deliberately not in the repo | suppressed by `allow_missing` |
| 7 | R3 | `AGENTS.md#L111` | `3. <private KB text removed> → <private KB text removed> `docs/performance.md` <private KB text removed> `docs/paper_alignment.md`` | `docs/performance.md` | med | **true-stale → Removed** | `docs/` has `paper_alignment.md` but no `performance.md`; fix rewrites the pointer | removed (R9 = 0) |

The full kblint `expected`/`observed`/`subject` strings and finding ids for every row are in each `raw/<repo>/<condition>__<config>/meta.json` (`r9_rows`) and in the raw `findings.jsonl`.

Adjudication totals: **7 findings reviewed; 5 true-stale, 2 false-positive-by-contract;
2 removed by the minimal repair; 3 residual true-stale after repair.**

**Manually recorded non-R9 stale repair:** the R3 fix also renames the stale skill name
`memory-update` → `short-term-memory` (4 occurrences; `.agents/skills/short-term-memory/SKILL.md`
exists, no `memory-update` directory). R9 does not report it because a bare skill name is not a
path-like reference — a rule-surface limit, not a missed reference defect.

## 6. Maintenance-time proxy

- **Findings to review per stale KB:** 4 for R2 (workflow config; 6 if the operator uses the
  generic config and must adjudicate the 2 runtime/model-store references), 1 for R3.
  The 3 R2 residual `docs/*.md` findings remain after the minimal repair.
- **Scan wall-clock:** 0.578 s for all 8 scans (4 workflow-config scans: 0.285 s total;
  0.065–0.084 s each) — i.e. sub-second audit cost per repo/state; the human review of the
  5 workflow-config findings and 2 sensitivity findings is the dominant cost.
- **Minimal repair size:** R2 2 changed lines (2+/2−), R3 5 changed lines (5+/5−),
  1 KB file each. No source repo was modified.

## 7. Figure

[`figures/before_after_repair.pdf`](figures/before_after_repair.pdf) and
[`figures/before_after_repair.png`](figures/before_after_repair.png), generated from
`raw/figure_data.json` by `make_figure.py`:

- **Panel A** — audit funnel on the parent (stale) state, workflow config: claims extracted
  (77 / 79) → rule-addressable audit queue (31 / 25; *not* a defect list) → confirmed R9 findings
  (4 / 1); values from `raw/summary.json`.
- **Panel B** — before vs after the minimal KB repair: R9 findings with the workflow config
  (R2 4→3, R3 1→0) and with the generic sensitivity config (6→5, 1→0); audit-queue
  counts unchanged (31→31, 25→25) and annotated as non-defects.

Numbers in the figure and this report come from the same `raw/summary.json` snapshot
(`raw/figure_data.json` is the plotted subset).

## 8. Raw outputs (kept, not summarised away)

`raw/<repo>/<parent-stale|repaired>__<config>/` each contains the kblint outputs
`findings.jsonl`, `audit_queue.jsonl`, `summary.md`, `report.sarif`, plus `stdout.txt`,
`stderr.txt` and `meta.json` (exact command, tree path, exit code, wall time, parsed counts,
per-rule counts, output sha256, determinism flag, and the full R9 rows used for adjudication).
Machine-readable aggregate: `raw/summary.json` (24 KB; 8 scans, prepared trees, source-repo
`git status` before/after). Total raw footprint ≈336 KB.

## 9. Honest limits

1. **Two repositories, one KB doc each** (the repos' other KB skills are outside the scanner's doc
   surface — see item 5). This is a demonstration of the workflow, not a precision/recall or population
   estimate.
2. **Reference-level only.** All findings are R9 reference checks. R1 pin/version, R2 number
   provenance, R3 cross-doc conflict, R5 expiry, R6 source-of-truth and R7 tracked/owner rules were
   not exercised: no artifacts/pins/run indexes were configured, and the temp `git archive` trees
   have no `.git`, so R7 self-skips. The audit queue (56 claims) is unverified-risk, not defects.
   There is **no coding or behavioural outcome** — kblint checks contract evidence only.
3. **Post-repair R2 R9 is 3, not 0.** The provided fix commit is a minimal KB repair that
   removes the stale `make profile-deep` reference (and a volatile test count) but leaves the three
   stale `docs/*.md` references. The workflow reports this as a residual true-stale set; a complete
   repair would require three more line edits (not in the given fix commit).
4. **Rule-surface limits.** kblint cannot see semantic staleness: the same fix commit removes a
   volatile "316 pass" test count and renames a stale skill name, neither of which is R9-detectable
   (no artifact-index for R2; a skill name is not a path). It also checks local references only
   (paths/links/`make`/`npm`), not URLs or external resources.
5. **Doc surface.** `docs` is scoped to the real KB files (`AGENTS.md`; `CLAUDE.md`,
   `docs/AGENTS.md` if present). R3's hidden `.agents/skills/**/SKILL.md` KB files were not
   matched by the `**/SKILL.md` glob on the copied tree (docs scanned = 1 in both conditions), so
   seven skill docs are outside this demonstration; a fuller surface would need explicit handling.
6. **Determinism.** Fixed `--now 2026-11-05`, stdlib-only, offline. Reruns into a scratch dir
   produced byte-identical `findings.jsonl`/`audit_queue.jsonl`/`summary.md`/`report.sarif` for all
   8 scans. Runtimes are tiny and machine-dependent; counts and findings are the stable quantities.
7. **Exit codes** are `--fail-on medium`: medium findings fail (1), clean scans pass (0); the
   R2 `make profile-deep` finding is low severity and does not drive the exit code.

## 11. Closure (task-81): R2 4 → 3 → 0

The follow-up closure lives in [`closure/`](closure/); it does not modify the workflow trace above.

| R2 state | claims | audit queue | R9 | exit | scan time |
|---|---:|---:|---:|---:|---:|
| parent (stale KB, `2bc2feb`) | 77 | 31 | 4 | 1 | 0.090 s |
| human fix commit (`29a0bc7`) | 77 | 31 | 3 | 1 | 0.072 s |
| follow-up KB-only repair (temp copy) | 77 | 31 | **0** | 0 | 0.071 s |

The three residual `docs/*.md` references were verified to have no in-repo target (`git log --all -- docs/`
= 0 commits; the repo's tracked markdown is `AGENTS.md`, `README.md`, `README_EN.md`), then repointed to the
real in-repo documentation artifact `README.md` (`## <private KB text removed>`, `## <private KB text removed>`, `## <private KB text removed>`,
`## <private KB text removed>`) with the claim text preserved — a KB-only edit in a fresh `git archive` copy, no source
repo change, one KB file, 3 lines replaced. All three scans reran byte-identically; source repo
`git status --porcelain` unchanged.

See [`closure/REPORT.md`](closure/REPORT.md) for the diff, true-target evidence, per-finding
deterministic-vs-human review table, artifacts (`closure/raw/<state>/` JSON+Markdown+SARIF,
`KB_REPAIR.diff`, `before_after/`) and limits; the paper fragment is
`paper_workshop/agentverify2027/fragments/audit_closure.md`. Reproduce with
`python3 closure/run_closure.py`.
