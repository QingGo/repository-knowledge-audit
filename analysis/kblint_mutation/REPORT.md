# kblint mutation evaluation — report

**Task:** controlled mutation evaluation of the deterministic contract linter `kblint`
(`kb-health/kblint`), for the AGENTVERIFY 2027 KB-hygiene paper (tool-validation experiment).
**No LLM calls; no network; deterministic; stdlib-only.** Full eval runtime **~28 s**.

Tool under test: `kblint` **0.2.1** (30 tests passing); exact rule/config hashes are frozen in
`results/summary.json::kblint.rule_hashes` (also copied into `paper_numbers`). The evaluation was
run after the final R9 integration; rerunning the same command reproduces the results given the
recorded hashes.

Deliverables in this directory:

| file | content |
|---|---|
| `mutate.py` | builds the synthetic fixture families (R1,R2,R3,R5,R6,R7) and their mutants |
| `real_specs.py` | R9 reference-check mutants on minimal copies of the 5 read-only local repos + R7 git-copy mutants |
| `run_eval.py` | scans every fixture/natural corpus, computes TP/FP/FN/TN, precision/recall/FPR/FP-100, runtime, natural verification; writes `results/` |
| `r7_recheck.py` | targeted R7 before/after re-run for the non-ASCII git-path bug |
| `fixtures/` | deterministic fixture repos + configs + `MANIFEST.json` |
| `results/cases.jsonl` | one row per mutant scan (outcome, target findings, dispositions, runtime) |
| `results/findings_injected.jsonl` | findings from mutant scans |
| `results/natural_findings.jsonl` | natural findings + manual verification verdicts |
| `results/natural_verification.jsonl` | manual verification rows (verdict + note) |
| `results/summary.json` | all metrics + `paper_numbers` block + frozen linter hashes |
| `results/RESULTS_TABLE.md` | paper-ready tables A (injected), B (runtime), C (natural), D (sanity) |
| `results/r7_recheck_before.json` / `_after.json` | R7 bug before/after evidence |

---

## 1. What was evaluated

`kblint` emits **verifiable contract findings** (claim locator + observed/expected + evidence +
verification method + disposition), not usefulness judgements. This evaluation asks, for the
rules that can be exercised on the available corpora:

* **R1** pin/version consistency; **R2** number provenance against an artifact index;
  **R3** cross-doc numeric conflict; **R5** negative-result/flag expiry;
  **R6** source-of-truth declaration; **R7** untracked/uncommitted/missing-owner docs;
  **R9** reference check (relative markdown links, backticked repo-relative paths,
  `make <target>`, `npm|pnpm|yarn run <script>`).

R4 (missing supersedes) is **off by default and experimental**, and R8 is an **audit queue that
is never a defect**; both are excluded from the detection metrics (R8 is reported through the
queue/manual-review fraction only).

## 2. Method

### 2.1 Corpora

1. **Synthetic contract fixtures** (`mutate.py`, built in the style of the shipped
   `examples/sample_repo`): a small KB where every claim starts *valid*, plus an artifact index
   and a git fixture. Used for R1, R2, R3, R5, R6, R7.
2. **Minimal copies of the 5 read-only local repos** (`/HOME/code/{R2,
   R3,R5,R4,R1}`, currently at docs-fix commits):
   for R9, each mutant copies only the target KB document + the referenced artifacts + root
   `Makefile`/`package.json`; for R7, full `git` copies of three repos (R2,
   R1, R5) preserve `.git` so `git ls-files`/`git status` work.
   The source repos were never checked out/reset or modified.

### 2.2 Mutation protocol (per claim)

Every claim/mutant triplet is one scan:

* **negative control** — unchanged repo; the rule must **not** fire on the target document;
* **positive mutation** — break the referenced truth: delete/move a referenced file, delete a
  make target, rename an npm script, change a manifest/artifact version, alter a conflicting
  doc value, re-date/remove a negative-result date, remove a canonical declaration, untrack or
  edit a doc, etc. The rule **must** fire on the target document;
* **hard negative** — a benign edit that keeps the claim valid (prose edit elsewhere,
  rounding inside display precision, supersedes marker added, new valid reference, external
  URL, fenced illustrative path, committed edit, untracked non-markdown file). The rule must
  **not** fire.

Detection is delta-based: a mutant is a TP/FN only if a finding for the target rule appears on
the target document **and** its subject names the mutated target token; baseline/other findings
in the same fixture are ignored (they are not what the mutant changed). Outcomes are classified
per mutant; positives are `TP`/`FN`, negative controls and hard negatives are `TN`/`FP`.
Dispositions are recorded separately: `confirmed` is a defect; `unresolved`,
`revalidation_due` and `provenance_gap` are **queue/review dispositions**, not confirmed
defects.

### 2.3 Mutant counts (main suite; 65 scans + 2 bug probes = 67)

| rule | positives | negative controls | hard negatives | total |
|---|---:|---:|---:|---:|
| R1 pin/version | 2 | 2 | 2 | 6 |
| R2 number provenance | 3 | 2 | 3 | 8 |
| R3 cross-doc conflict | 1 | 1 | 2 | 4 |
| R5 expiry | 3 | 2 | 3 | 8 |
| R6 source-of-truth | 1 | 1 | 2 | 4 |
| R7 git provenance | 7 | 3 | 5 | 15 |
| R9 reference check | 8 | 5 | 8 | 21 |
| **total** | **25** | **16** | **24** | **65** (+2 bug probes) |

### 2.4 Metrics

TP/FP/FN/TN per rule; precision = TP/(TP+FP); recall = TP/(TP+FN); false-positive rate =
FP/(FP+TN); **FP per 100 claims** = 100·FP / claims scanned in the control+hard-negative mutants
of that rule. Runtime is measured per scan (wall clock around `python3 -m kblint scan`), median
over the suite; natural-repo runtimes are medians of 3 runs per config.

### 2.5 Natural sample vs injected mutations (kept strictly separate)

**Injected mutations are a controlled upper bound on detection ability**, not a realistic
precision/recall estimate: each mutant breaks exactly one referenced truth, so the claim,
locator and expected disposition are unambiguous by construction. The **natural sample** is the
realism check: the 5 read-only repos scanned *without any injected edits*, with every confirmed
finding manually verified against the working tree / git state.

Two natural scopes were evaluated for R9 to measure scope sensitivity:

* **R9 primary (recommended deployment scope)** — `AGENTS.md`, `CLAUDE.md`, `docs/AGENTS.md`,
  `SKILL.md`, `**/SKILL.md`, with the example config's `allow_missing` classes for
  generated/external artifacts (`artifacts/`, `weights/`, `runs/`, `outputs/`, `dist/`, `build/`,
  `node_modules/`). **This is the paper-facing natural R9 sample.**
* **R9 extended (transparency sample)** — the same rule over README/docs trees, including
  product/user-facing documentation. This is *out of the contract surface* for a KB-artifact
  audit (those docs describe user sites/products), and the numbers show why scope must be
  declared.

R7 natural is scanned separately on the broad KB docs surface (git enabled; references/R3 off),
and manual verification checks tracked/untracked status with `git -c core.quotepath=false`.

Manual verification: each natural finding was read against the referenced line/target and the
repository state. Verdicts and notes are in `results/natural_verification.jsonl`; for the
product-documentation tree (R4, extended scope) verification is by scope classification plus
line spot-checks, and those rows are explicitly marked as out-of-KB-surface FPs. The
`R0` corpus snapshot (5 files only) is reported as an auxiliary corpus; its findings
are snapshot-incompleteness FPs (the referenced repo files are intentionally not in the
snapshot), not KB defects.

## 3. Injected mutation results (controlled; upper bound)

| rule | mutants (pos/neg) | TP | FN | FP | TN | recall | precision | FPR | FP/100 claims | TP dispositions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| R1 | 2/3 | 2 | 0 | 0 | 3 | 100% | 100% | 0% | 0.00 | confirmed×1, unresolved×1 |
| R2 | 3/5 | 3 | 0 | 0 | 5 | 100% | 100% | 0% | 0.00 | confirmed×2, revalidation_due×1 |
| R3 | 1/3 | 1 | 0 | 0 | 3 | 100% | 100% | 0% | 0.00 | confirmed×1 |
| R5 | 3/5 | 3 | 0 | 0 | 5 | 100% | 100% | 0% | 0.00 | confirmed×2, revalidation_due×1 |
| R6 | 1/3 | 1 | 0 | 0 | 3 | 100% | 100% | 0% | 0.00 | unresolved×1 |
| R7 | 7/8 | 7 | 0 | 0 | 8 | 100% | 100% | 0% | 0.00 | confirmed×3, provenance_gap×3, unresolved×1 |
| R9 | 8/13 | 8 | 0 | 0 | 13 | 100% | 100% | 0% | 0.00 | confirmed×8 |
| **all** | **25/40** | **25** | **0** | **0** | **40** | **100%** | **100%** | **0%** | **0.00** | |

*Upper-bound caveat:* 25/25 positives and 0/40 false positives is what a rule should do on
unambiguous single-truth mutants; it certifies that each rule's evidence path is wired correctly
(changed truth → specific finding with the right locator/disposition), **not** field precision.
The 2 bug probes are excluded from this table and reported separately (§5).

## 4. Natural-sample results (realism check; manual verification)

### 4.1 R9 scope contrast

| scope | findings | verified n | TP | FP | verified precision | claims | FP/100 claims |
|---|---:|---:|---:|---:|---:|---:|---:|
| **R9 primary** (AGENTS-style KB surface; R2 3, others 0) | 3 | 3 | **3** | **0** | **100%** | **294** | **0.00** |
| R9 extended (README + product docs; R4 65, engram 1, wechat 2, home 3, LLM 1) | 72 | 72 | 4 | 68 | 5.6% | 13,917 | 0.49 |
| R7 natural (git provenance, broad KB docs; **after the v0.2.1 fix**) | 2 | 2 | **2** | **0** | **100%** | 13,917 | **0.00** |

R9 primary reproduces the linter developer's smoke test: R2 has **3 genuinely stale
references** (`docs/paper.md`, `docs/arch_design.md`, `docs/implementation_notes.md` are listed
as key paths in `AGENTS.md` but the repo has no `docs/` directory); R3, R5,
R4 and R1 produce 0 confirmed R9 findings on that surface.

R9 extended FPs are diagnostic classes, all manually verified:

* **product/user documentation examples** (R4 docs/content: `config/_default/…`,
  `content/posts/…`, `layouts/…` describe *user* R4 sites, not this repo) — 64 FPs + 1 R3 FP;
* **prose idiom** (`make backbone behavior predictable` matched as `make backbone`) — 1 FP;
* **future/planned artifact** (`utils/tracker.js` is a TODO item to create) — 1 FP;
* **explicitly local/gitignored plan** (`.omo/plans/…` says it is local and not distributed) — 1 FP.

### 4.2 R7 git-provenance natural sample

* R3: **2 TP** — `docs/PRD.md` and `docs/checklist.md` exist as knowledge docs but are
  absent from `git ls-files` (genuine provenance gap; verified with
  `git -c core.quotepath=false ls-files docs`).
* R2 / R4 / R1: 0 findings.
* R5: **6 findings before the fix — all 6 false positives** caused by git's
  non-ASCII path quoting (see §5); **0 findings after the v0.2.1 fix**, and the uncommitted-edit
  repro now fires 1 correct confirmed finding.

### 4.3 Shipped-fixture sanity check (`examples/sample_repo`)

Known-defect recall **5/5** (R1 unresolved, R2 confirmed, R3 confirmed, R5 confirmed,
R6 unresolved; R4 experimental enabled only in the shipped config: 1 finding, excluded from
this evaluation). Clean-control docs (`docs/clean.md`, `docs/numbers_clean.md`) produce **0**
findings. Queue: 3 items / 18 claims; this is the designed synthetic sanity fixture, not a
natural sample.

## 5. Bugs found during the evaluation (legitimate evaluation evidence)

### R7 — non-ASCII filenames misread because git output is C-quoted

* **Repository:** `/HOME/code/R5` @ `50a71b4`.
* **Observed:** `git -c core.quotepath=false ls-files docs` lists all six non-ASCII docs
  (`docs/<private KB text removed>.md`, `<private KB text removed>.md`, `<private KB text removed>.md`, `<private KB text removed>prd.md`, `<private KB text removed>.md`,
  `<private KB text removed>.md`) as tracked, but R7 reported each as
  "knowledge doc not tracked in git" (`provenance_gap`, low) → **6 false positives**.
  Conversely, appending an uncommitted line to `docs/<private KB text removed>.md` produced **no** uncommitted
  finding → **1 false negative**.
* **Cause:** R7 runs `git ls-files` / `git status --porcelain` without
  `-c core.quotepath=false`; non-ASCII paths are emitted C-escaped/quoted, so raw doc paths
  never match.
* **Fix:** linter-dev added the quotepath handling (routed by Lead). Before/after evidence:
  `results/r7_recheck_before.json` / `results/r7_recheck_after.json`; the two wechat bug-probe
  mutants are in `results/summary.json::injected.bug_probes` and `paper_numbers.bug_probes`.
  | state | wechat natural R7 findings | NC probe (tracked non-ASCII doc) | uncommitted-edit probe | R7 natural verified precision |
|---|---:|---:|---:|---:|
| **before** (v0.2.0) | 6 — all FP (`provenance_gap` on tracked docs) | 1 FP | 0 findings (FN) | 2 TP / 6 FP = **25%** |
| **after** (v0.2.1) | **0** | **0** | **1 confirmed finding (TP)** | 2 TP / 0 FP = **100%** |

  The v0.2.1 fix adds `-c core.quotepath=false` to both git calls plus a quoted-path unquoter
  (30 tests pass). The bug and its fix are reported as a finding of the evaluation, not hidden: a
  real bug was found and fixed during the natural check (6 FP + 1 FN → 0 FP + 1 TP).

*(If the fix had not landed before freeze, this section records the pre-fix state and the
re-check as pending; the frozen-linter hashes in `summary.json` identify which build was
evaluated.)*

## 6. Runtime

| scope | n scans | median | p90 | max | notes |
|---|---:|---:|---:|---:|---|
| injected mutant scan | 65 | **0.065 s** | 0.13 s | 0.18 s | deterministic, stdlib-only |
| natural, R9 primary, 5 repos | 15 (×3 runs) | **0.081 s** | — | 0.091 s | home 0.081, engram 0.073, wechat 0.071, R4 0.091, LLM 0.084 |
| natural, R9 extended, 5 repos | 15 (×3 runs) | **0.18 s** | — | 1.67 s | R4 1,026 docs / 11,094 claims = 1.67 s |
| natural, R7 git, 5 repos | 15 (×3 runs) | **0.19 s** | — | 1.72 s | R4 largest |
| full mutation suite (`run_eval.py`, incl. natural ×3) | — | **~28 s** | — | — | well under the 15-min budget |

## 7. Honest limitations

1. **Injected ≠ natural staleness.** Mutants are mechanically injected, single-truth breaks;
   100% recall / 0 FP is an upper bound on rule wiring, not field performance. Natural
   prevalence/recall cannot be estimated here: there is no independent natural defect gold set,
   and the natural sample is tiny (3 R9-primary findings).
2. **Rule coverage is not semantic coverage.** The linter checks declarative contracts
   (pins, numbers, conflicts, expiry, provenance, references); it does not judge whether a
   route/decision is semantically right. Findings are not a population measurement.
3. **Scope determines precision.** Declaring the audited doc scope is required: the same R9
   rule is 3/3 correct on the AGENTS-style KB surface but 4/71 (5.6%; 67 FP) on
   README/product-documentation trees (4 TP/68 FP if the one product-doc R3 match is included). This is a property of the corpus surface, not a contradiction.
4. **Small per-rule n.** 1–8 positives per rule; per-rule precision/recall cells are coarse and
   should be read with the raw counts.
5. **R4 excluded, R8 not a defect rule.** R4 is off by default/experimental; R8 is the review
   queue (queue/manual-review fraction is reported, but queue items are not defects).
6. **Fixtures are minimal copies.** R9 mutants copy the target doc + referenced artifacts + root
   manifests, not the full repos; R7 git mutants are full copies of three repos only (the other
   two were covered naturally only). The 2 bug probes are excluded from headline metrics.
7. **One machine/timing.** Runtime is wall-clock on this machine; the linter is deterministic
   in output (same repo+config+`--now` → byte-identical), but timing is not a benchmark of
   hardware.
8. **Frozen build.** The evaluated build is **kblint 0.2.1**; version + SHA-256 rule/config
   prefixes are frozen in `summary.json::kblint` and `paper_numbers`. If the linter changes after
   this report, the numbers apply to the frozen build only and must be re-run.

## 8. Paper-quotable sentences

1. "On 65 controlled mutants (25 positive breaks, 40 negative/hard-negative controls), the
   linter detected every injected contract break with no false positives (25/25; 0/40; 0 FP per
   100 claims), an upper bound on detectability because mutants are unambiguous by construction."
2. "On the natural sample, the reference check over the declared AGENTS-style KB surface produced
   3 confirmed findings and all 3 were manually verified correct (3/3, 0 FP) across 294 claims;
   the git-provenance check found 2 genuine untracked knowledge docs (2/2 after the fix)."
3. "Precision depends on the declared documentation scope: the same reference rule was 3/3
   correct on agent-facing KB docs but only 4/71 R9 findings (5.6%; 67 FP) on README/
   product-documentation trees (68 FP including one product-doc R3 match), which describe
   user-site examples rather than repository-internal artifacts; audits must declare their scope."
4. "Mutation testing validates rule mechanics and evidence paths, not semantic defect coverage:
   R4 is disabled/experimental, the audit queue is not a defect list, and no natural recall
   estimate is possible without an independent natural defect gold set."
5. "The full mutation suite (65 mutant scans + 17 natural scans ×3 runs) completes in ~28 s
   (median 0.065 s per mutant scan; 0.081 s median per repo on the AGENTS-style scope), and the
   natural check found and fixed a real non-ASCII git-path bug in R7 (6 false positives and 1
   false negative before the fix; 0 false positives and 1 correct finding after)."

## 9. Reproduce

```bash
cd kb-health/analysis/kblint_mutation
python3 mutate.py build          # deterministic fixture build
python3 run_eval.py              # full eval (~28 s): injected + natural ×3 runs
python3 r7_recheck.py --tag after     # R7 non-ASCII bug re-check
```

Requirements: Python ≥3.9, git (for R7 fixtures), the repo-local `kb-health/kblint` package
(no install needed; `run_eval.py` invokes `python3 -m kblint` with `cwd=kb-health/kblint`).
