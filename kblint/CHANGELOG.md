# Changelog — kblint

## v0.3.0 (2026-11-09) — incremental PR audit + machine-readable claim schema

- **`kblint diff` (incremental baseline audit).** Compare a current scan report against a stored
  baseline and classify findings as NEW / PERSISTING / FIXED with a content-based, line-shift-tolerant
  finding key; emits `diff.json` + `diff.md`. Exit policy: only NEW `confirmed` findings at/above
  `--fail-on-new` fail CI; pre-existing findings and Unknown-class findings are listed but
  non-blocking. `scan` is unchanged/backward compatible. Adds `ci/incremental.yml` and 9 tests.
- **Machine-readable claim schema.** `schema/claim.schema.json` (JSON Schema 2020-12) for a claim
  entry with scope/evidence/invalidation/audit-produced status/last_checked; examples
  (`examples/claims.example.json`, `examples/claim-audit.example.md`) and 3 tests. Status is generated
  by the audit; `last_checked` is not verification.

## v0.2.1 (2026-11-09) — R7 non-ASCII git path fix

- **R7 bugfix (mutation-eval report):** `git ls-files` / `git status --porcelain` were invoked
  without `-c core.quotepath=false`, so git C-escaped non-ASCII paths (`docs/商业计划.md` ->
  `"docs/\\345..."`) and every tracked non-ASCII knowledge doc was misreported as
  "not tracked in git" (6 false findings on `R5@50a71b4`); uncommitted edits to such
  docs were also missed. Both invocations now use `-c core.quotepath=false`, and remaining quoted
  status paths (spaces/special characters still quoted by `git status`) are decoded by a new
  `_unquote_git_path` helper. New real-git regression test with non-ASCII tracked/untracked/dirty
  docs (`test_r7_non_ascii_git_paths_real_repo`); 30 tests pass.

## v0.2.0 (2026-11-09) — R9 reference check + CI quickstart

- **R9 reference check** (deterministic, stdlib-only, offline): local markdown links, backticked
  repo-relative file paths, `make <target>` against a root Makefile, `npm|pnpm|yarn run <script>`
  against root `package.json` scripts. Doc-relative then repo-root resolution; URLs, anchors,
  absolute paths, globs, placeholders, escapes and configured excludes ignored; fenced tree
  diagrams not trusted (run commands inside fences are checked); illustrative-marker lines
  (`e.g.`, `for example`, `such as`, …) skipped for path/link checks; links must look path-like.
- Config block `references` (`enabled`, `check_paths`, `check_links`, `check_make`, `check_npm`,
  `allow_missing` regex list, `inventory` globs), validated with exit 2 on unknown keys/bad regex;
  checks self-skip when the repo has no root `Makefile`/`package.json` or no local references.
- Claimless-finding dedupe fix: R9 findings (doc+locator attached directly) are no longer collapsed
  across docs by `(rule, subject)`; one finding per occurrence.
- Report/SARIF/summary integration: R9 row + counts, `--fail-on` thresholds, machine-readable
  findings; `examples/references.kblint.json`, `examples/audit_report.md` (real R2 scan),
  `ci/github-actions.yml`, README CI/quickstart/R9 sections.
- 13 new pytest cases (positives/negatives/edge cases); 29 tests total; real-repo FP assessment and
  tightening log in `R9_REPORT.md` (3 repos: R2, R3, R4).

## v0.1.0 (2026-11-05) — alpha

First package extracted from the R0-specific linter prototype (`kb-health/analysis/linter/`).

- Config-driven, deterministic, stdlib-only CLI: `kblint scan`, `kblint rules`; exit codes 0/1/2.
- Generic markdown extractor: headings/bullets/blockquotes/table rows/sentences -> claim records
  with stable content-hash ids, `doc#Lx-y` locators, section path, and deterministic features
  (numbers+units+key context, artifact/path refs, configurable version pins, ISO dates,
  negative/expiry/supersedes/contract markers, counts). Skips frontmatter, code fences,
  link-only lines; paragraph-level artifact-pointer inheritance.
- Eight rules: R1 pin/version consistency, R2 number provenance against a nested artifact index
  (relative tolerance, unit/key context), R3 cross-doc conflict on normalized subject anchors,
  R4 missing supersedes (artifact chronology), R5 negative-result/flag expiry, R6 source-of-truth
  declaration missing, R7 untracked/no-owner knowledge files (git optional), R8 audit queue
  (never defects).
- Outputs: `findings.jsonl`, `audit_queue.jsonl`, `summary.md`, SARIF 2.1.0 `report.sarif`;
  waivers; per-rule enable/disable; `--now` for deterministic expiry checks.
- Synthetic `examples/sample_repo/` (one defect per rule + clean controls), sample config,
  R0 regression config, pytest suite (12 tests), REGRESSION.md.
- Precision pass before release (Lead-review FIX-1..4):
  - R2 rounding-aware matching: half-last-displayed-place tolerance (655->±0.5, 358.8->±0.05,
    1.02->±0.005); rounding cases (13.5/13.51, 105/105.365, 7.5/7.55, 9.9/9.93, 1.02/1.017) are now
    matches while 358.8 vs 358.093 stays a finding.
  - R2 confirmed only with an artifact pointer + best-candidate field (>=2 matching non-generic
    context tokens) and no threshold/target language; otherwise `revalidation_due`. Confirmed 15->9
    on R0; inherited-pointer findings tagged `confidence=medium` + `inherited-pointer`.
  - R4 (missing supersedes) is now **off by default** (`rules.R4.enabled`), experimental, with a
    summary.md warning when enabled.
  - R1 mixed-artifact-environment honesty: >=2 distinct pin values in the artifact pool produce one
    `unresolved` low finding per doc pin ("mixed artifact environments ..."), not many confirmed
    defects; `confirmed` only for single-environment pools (R0: 11 high confirmed -> 7
    unresolved).
  - Tests 12 -> 16 (rounding both ways, target-language queueing, R4 default-off, mixed pins);
    R0 regression rerun and REGRESSION.md/README counts updated (174 findings + 241 queue).
- Known limitations documented in README: doc surface only, no semantics, R4 off/experimental,
  R2/R3 precision needs (field ambiguity, generic anchors), design-repo calibration is not a
  held-out estimate.
