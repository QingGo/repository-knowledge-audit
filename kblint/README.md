# kblint — deterministic contract linter for engineering-agent knowledge artifacts

`kblint` audits markdown knowledge artifacts (docs, `AGENTS.md`, `SKILL.md`, run notes) against
the artifacts they describe and emits **verifiable findings**, not usefulness judgements.

- **Deterministic**: same repo + config + `--now` -> byte-identical outputs. No wall clock, no
  randomness, no network, no LLM/API calls. Python standard library only.
- **Config-driven**: rules only run when their data is declared (pins, artifacts, run index,
  source-of-truth, expiry, git). Defaults are safe on a docs-only repo.
- **Evidence-first**: every finding carries a claim locator, expected/observed, evidence locators,
  a verification method, a disposition and a suggested action.
- **Honest boundaries**: the **audit queue is not a defect list**; findings are not a population
  measurement; `kblint` does not judge whether knowledge is useful, correct as a route, or harmful.

## Install / run

```bash
cd kb-health/kblint
python3 -m kblint rules                     # list rules (R1-R9)
python3 -m kblint scan --repo /path/to/repo --config examples/R0.kblint.json \
    --out /tmp/kblint-out --format json,md,sarif --fail-on high
# reference-check quickstart (R9) on an agent knowledge file:
python3 -m kblint scan --repo /path/to/repo --config examples/references.kblint.json \
    --out /tmp/kblint-ref --format json,md,sarif --fail-on medium
# or, after `pip install -e .`:
kblint scan --repo ... --config ...
```

Python >= 3.9. Tests: `python3 -m pytest -q` (pytest 8.x; 29 tests, incl. R9).

### CLI

```
kblint scan --repo PATH --config CONFIG.json [--out DIR] [--format json,md,sarif]
            [--fail-on none|low|medium|high] [--now ISO-DATE] [--quiet]
kblint diff --before REPORT --after REPORT [--out DIR] [--format md,json]
            [--fail-on-new none|low|medium|high] [--quiet]
```

Scan exit codes: `0` no findings at/above `--fail-on` threshold, `1` findings at/above threshold,
`2` error (bad config, missing repo/run_index). `--fail-on none` never fails on findings.
Diff exit codes: `0` clean or only non-blocking changes, `1` NEW confirmed findings at/above
`--fail-on-new`, `2` error (missing report path, bad format). See
[Incremental PR audit](#incremental-pr-audit-baseline-diff).

## Config schema (JSON; all keys optional)

```jsonc
{
  "repo": ".",                                  // default root; CLI --repo overrides
  "docs": ["**/*.md"],                          // markdown globs (skip .git etc.)
  "artifacts": ["runs/*.json"],                 // JSON/JSONL/CSV files indexed (nested numeric+string fields)
  "exclude": ["archive/**"],
  "run_index": {                                // optional table of runs
    "path": "corpus/runs_index.jsonl",          // relative to this config file
    "format": "jsonl",                          // jsonl | json
    "file_field": "file", "id_field": "run_id"
  },
  "pins": [{                                    // R1
    "doc_glob": "docs/**/*.md", "artifact_glob": "runs/*.json",
    "artifact_keys": ["torch", "cuda"],         // artifact field suffixes (string values)
    "doc_patterns": ["torch\\s+([0-9.]+\\+cu[0-9]+)"],   // capture group 1 = declared pin
    "names": ["torch"]                          // optional: only these pin names
  }],
  "tolerance": {"relative": 0.0005},            // R2 relative match tolerance (5e-4 = 0.05%)
  "source_of_truth": [{                         // R6; never guesses truth
    "topic": "acceptance target",
    "canonical_doc": "docs/benchmarks.md",
    "canonical_locator": "#L74"
  }],
  "expiry": {                                   // R5
    "env_change_date": "2026-10-28",
    "negative_flag_regex": ["NANOV41_[A-Z_]+", "V4_MODE"]
  },
  "owner": {"frontmatter_keys": ["owner"]},     // R7 owner check (off by default)
  "git": {"enabled": true},                     // R7 needs a real git repo; self-skips otherwise
  "waivers": [                                   // suppress findings (audit trail in summary)
    {"finding_id": "F-…"}, {"rule": "R2", "doc": "docs/old.md"},
    {"rule": "R1", "claim_id": "c_…"}
  ],
  "rules": {"R3": false, "R4": {"enabled": true}}, // per-rule switches; R4 is OFF by default
  "now": "2026-11-05",                          // fixed date for deterministic expiry checks
  "pin_patterns": {"custom": "v(\\d+\\.\\d+\\.\\d+)"},  // extra/override pin regexes
  "references": {                               // R9 (all keys optional; safe defaults shown)
    "enabled": true,
    "check_paths": true,                        // backticked repo-relative file paths
    "check_links": true,                        // local markdown links [text](relpath)
    "check_make": true,                         // `make <target>` if root Makefile exists
    "check_npm": true,                          // `npm|pnpm|yarn run <script>` if package.json exists
    "allow_missing": ["^vendor/"],              // regex list: suppress known external/generated refs
    "inventory": ["generated/**"]               // repo-relative globs treated as present if absent
  }
}
```

Unknown keys are rejected (exit 2) so a typo cannot silently disable a rule. `tolerance.relative`
defaults to `5e-4`; doc numbers that are rounded (e.g. `105` vs `105.365`) can exceed it — configure
per repo; `revalidation_due`/`provenance_gap` are queue dispositions, not defects.

## Rules

| ID | rule | what it checks | dispositions |
|---|---|---|---|
| R1 | pin/version consistency | doc-declared env pin vs configured artifact field (`artifact_keys`) | `confirmed` (disagree), `provenance_gap` (field absent) |
| R2 | number provenance | claim number with unit resolved in the artifact index (nested JSON/JSONL/CSV; relative tolerance; unit/key context) | `confirmed` `artifact_mismatch` when the cited artifact field disagrees; `revalidation_due` when not locatable |
| R3 | cross-doc conflict | same normalized subject anchor (key/noun + unit), conflicting values across >=2 docs, no supersedes/deprecated marker | `confirmed` (one finding per subject group; confidence medium) |
| R4 | missing supersedes | newer artifact contradicts an artifact-backed claim; claim/section has no supersedes/deprecated marker. **Off by default** (`rules.R4.enabled = true`); experimental artifact-chronology without shape/config guards | `confirmed` (when enabled; experimental) |
| R5 | expiry | negative-result / flag claims older than `expiry.env_change_date` or undated | `confirmed` / `revalidation_due` |
| R6 | source-of-truth | claim about a configured topic outside the canonical doc without declaring it | `unresolved` "missing declaration" (never guesses truth) |
| R7 | untracked/no-owner | docs not in `git ls-files`; tracked docs with uncommitted changes; missing owner frontmatter | `provenance_gap` (untracked), `confirmed` (uncommitted), `unresolved` (owner) |
| R8 | audit queue | claims with no deterministic witness (numbers/pins/flags/contracts) | **queue JSONL only — never a defect** |
| R9 | reference check | local markdown links, backticked repo-relative paths, `make <target>` (root Makefile), `npm|pnpm|yarn run <script>` (root package.json) that do not exist in the repo | `confirmed` (broken evidence pointer; `medium` path/link, `low` make/npm) |

Determinism: claim-attached findings are deduped to one per `(rule, claim_id)`; claimless findings
(R9 attaches doc+locator directly) dedupe per occurrence, sorted, and ids are content hashes
(`c_…`/`F-…`/`a_…`); pass `--now` for reproducible expiry checks.

## R9 reference check (v0.2)

R9 answers one narrow question: **does a KB claim point at a repository artifact that exists in the
scanned repo state?** It does not judge whether the knowledge is correct or useful, and a passing
reference is not evidence that the surrounding claim is true.

Surfaces checked (each can be disabled under `references`):

- **local markdown links** `[text](docs/foo.md)` — relative targets only; anchors/queries stripped;
  bare-word stubs like `[Language](g)` are not treated as paths;
- **backticked repo-relative paths** `` `docs/foo.md` ``, `` `compiler/pipeline/__init__.py` `` —
  must contain a `/` and a recognised file extension (bare filenames/dir names are ignored);
- **`make <target>`** — only when the repo has a root `Makefile`; targets are parsed from rule
  lines and `.PHONY`;
- **`npm run <script>` / `pnpm run <script>` / `yarn run <script>`** — only when the repo has a root
  `package.json`; names are parsed from its `scripts` object.

Resolution is deterministic and conservative: doc-directory-relative first, then repo-root-relative
(so a repo-root path written from a nested doc is not a false positive); paths that escape the repo,
URLs, absolute paths, globs, placeholders (`{}` `<` `>` `$`), shell variables, URL-encoded targets,
and configured `exclude` globs are ignored. **Fenced code is never trusted for paths** (tree diagrams
and pasted output are the dominant noise source), but run commands (`make`/package-manager) inside
fences *are* checked; lines with box-drawing characters are skipped. Lines carrying illustrative
markers (`e.g.`, `for example`, `such as`, `例如`, …) are skipped for path/link checks: convention
docs cite *other projects'* paths as examples, which was the largest real-world FP class (see
[`R9_REPORT.md`](R9_REPORT.md)).

Suppression / configuration recipes:

```jsonc
"references": {
  "allow_missing": ["^(artifacts|weights|runs|outputs|dist|build|node_modules)/",
                    "generated/"],
  "inventory": ["assets/**"]      // externally fetched but known-valid references
}
```

R9 findings carry `doc` + `locator` (the occurrence line) and `evidence` (which candidates were
checked, plus parsed manifest size for make/npm). They are **not** claim-attached, so one claim may
produce several findings (one per missing reference) and the same missing target cited in two docs
produces two findings.

## Incremental PR audit (baseline diff)

Reviewers need to distinguish *newly introduced* breakage from pre-existing noise. `kblint diff`
compares a current report against a stored baseline report and classifies every finding as
**NEW / PERSISTING / FIXED**, with an exit policy designed for PRs:

```bash
# on the base commit (or main), store a baseline report
python3 -m kblint scan --repo . --config kblint.json --out baseline-report --format json,md --now 2026-11-05 --fail-on none
# on the PR tree, scan again
python3 -m kblint scan --repo . --config kblint.json --out current-report --format json,md --now 2026-11-05 --fail-on none
# classify and gate: only NEW confirmed findings at/above the threshold fail
python3 -m kblint diff --before baseline-report --after current-report \
    --out kblint-diff --format md,json --fail-on-new medium
```

**Finding identity.** The key is content-based — `(rule, doc, observed, expected, subject)` with the
`locator` line number stripped — so editing unrelated lines above a finding keeps it PERSISTING;
a finding in a *different doc* is NEW by design. (The key is available as
`kblint.diff.finding_key` for tooling.)

**Exit policy.** Only **NEW findings with `disposition == confirmed`** and severity at/above
`--fail-on-new` fail CI. Pre-existing findings never block, and Unknown-class findings
(`unresolved`, `provenance_gap`, `revalidation_due`) are listed as non-blocking review items — a
passing incremental check means "this PR introduced no new confirmed contract defect", not "the KB
is verified". `FIXED` is reported for reviewer context (it can also mean the doc moved).

Outputs: `diff.json` (schema `kblint-diff/1`, with per-classification items and blocking flags) and
`diff.md` (human-readable tables). An existing empty baseline directory is a valid empty baseline
(all current findings are NEW). A GitHub Actions example that checks out the PR base commit as the
baseline is in [`ci/incremental.yml`](ci/incremental.yml).

## Machine-readable claim schema

`kblint` knowledge entries can be serialized with a small, tool-agnostic JSON Schema
([`schema/claim.schema.json`](schema/claim.schema.json), JSON Schema 2020-12). Fields:
`claim_id`, `claim`, `scope{repository,version,environment?}`,
`evidence{type: test|path|artifact|command|doc, path?, command?, test?}`,
`invalidation{condition}`, `status` (`verified|stale|unknown|removed`), `last_checked`.

**Status is produced by the audit, never self-asserted.** A `verified` status means the configured
evidence re-resolved against the current repository (e.g. an artifact field matched a pin/number, a
test witness exists, a path resolves); `stale` means the evidence contradicts the claim; `unknown`
means the claim has no deterministic witness in the scanned repo state; `removed` marks a retired
claim. **`last_checked` is not verification**: it records *when* an audit last looked, so a claim can
be `last_checked` today and still `unknown` or `stale` — only `status` carries the evidence result.
The schema is reusable by other KB tools: emit/consume the same entry shape without depending on
kblint's internals. Examples: [`examples/claims.example.json`](examples/claims.example.json)
(one verified with a test/artifact witness, one stale with a path witness, one unknown) and
[`examples/claim-audit.example.md`](examples/claim-audit.example.md) (a Markdown claim mapped to the
schema). This complements (and does not replace) the audit outputs: findings say what the linter
found, while a claim entry records the claim's scope, evidence pointer, invalidation condition and
audit-produced status.

## Outputs

`--out` (default `./.kblint-out`) receives, per `--format`:

- `findings.jsonl` — one finding per line, sorted: `finding_id, rule, severity, disposition,
  claim_id, doc, locator, subject, observed, expected, evidence[], verification_method,
  confidence, suggested_action, tags[]`.
- `audit_queue.jsonl` — R8 queue (`audit_id, rule, claim_id, doc, locator, reason, subject, …`);
  **review list, not defects**.
- `summary.md` — counts by rule/severity/disposition, confirmed findings, honest-limits section.
- `report.sarif` — SARIF 2.1.0 (`$schema`, `version`, `runs[0].tool.driver{name,version,rules[]}`,
  `results[]` with `ruleId/level/message/locations[].physicalLocation{artifactLocation.uri,
  region.startLine}`, plus `properties`).

Severity -> SARIF level: high=`error`, medium=`warning`, low=`note`.

## Quickstart: an actionable audit report

```bash
cd kb-health/kblint
# 1) point the docs globs at the knowledge surface you own (AGENTS.md / SKILL.md / docs/AGENTS.md)
#    and run the deterministic scan. --now pins expiry checks for byte-identical reruns.
python3 -m kblint scan --repo /path/to/repo --config examples/references.kblint.json \
    --out /tmp/kblint-audit --format json,md,sarif --now 2026-11-05 --fail-on medium

# 2) read the summary first: it lists counts by rule/severity and every confirmed finding
#    with `observed` / `expected` / locator.
sed -n '1,80p' /tmp/kblint-audit/summary.md

# 3) act on R9 findings: each is `doc#Lline — reference does not exist`. Fix the link/path, or
#    if the target is external/generated, add it to references.allow_missing / inventory and rerun
#    until the gate is green (exit 0). The SARIF file uploads to GitHub code scanning.
```

The committed [`examples/audit_report.md`](examples/audit_report.md) is a real generated summary
(R2 KB scan, R9 with runtime/model dirs allow-listed): 3 confirmed stale references, all
actionable line pointers.

## CI integration

Full-scan gate: see [`ci/github-actions.yml`](ci/github-actions.yml). Incremental PR gate: see
[`ci/incremental.yml`](ci/incremental.yml) (scan the pre-PR base commit, scan the PR tree, then run
`kblint diff --fail-on-new medium`; pre-existing Unknowns are listed but do not block).

Copy [`ci/github-actions.yml`](ci/github-actions.yml) to `.github/workflows/kblint.yml`. It runs the
deterministic scan on every push/PR, uploads `findings.jsonl` + `summary.md` as artifacts, and
uploads the SARIF report to GitHub code scanning (so findings appear inline in the PR).

```yaml
name: kblint
on: [push, pull_request]
permissions: {contents: read, security-events: write}
jobs:
  kblint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - name: kblint (R9 reference check)
        run: |
          cd kb-health/kblint
          python3 -m kblint scan --repo "$GITHUB_WORKSPACE" \
            --config examples/references.kblint.json \
            --out "$RUNNER_TEMP/kblint-out" --format json,md,sarif \
            --now 2026-11-05 --fail-on medium
      - uses: actions/upload-artifact@v4
        if: always()
        with: {name: kblint, path: ${{ runner.temp }}/kblint-out}
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: {sarif_file: ${{ runner.temp }}/kblint-out/report.sarif}
```

Notes: `--fail-on medium` fails the job on R9 path/link findings; use `--fail-on high` to report
without blocking (R9 is medium by design — a broken evidence pointer is not a data-integrity defect).
The scan is offline and stdlib-only; no API keys or network are needed.

## Example: R0 (design repo, allowed)

```bash
cd kb-health/kblint
python3 -m kblint scan --config examples/R0.kblint.json --out regression/R0 \
    --now 2026-11-05
```

`examples/R0.kblint.json` indexes `docs/**/*.md`, `README.md`, `runs/README.md`, the
`runs/*.json` artifact store and the pinned `corpus/R0/runs_index.jsonl` (R4 enabled
explicitly for the regression run only). Run time ~4 s, ~50 MB peak RSS, crash-free; 174 findings
+ 241 audit items: R1 7 unresolved (mixed artifact environments), R2 9 confirmed + 94
revalidation-due, R3 2 (review candidates), R4 3 experimental, R5 45 queue, R6 5 unresolved,
R7 4 confirmed + 5 provenance-gap. Known-issue verification is in [`REGRESSION.md`](REGRESSION.md):
the 358.8-vs-358.093 artifact mismatch and the committed-vs-worktree drift are reproduced at doc
level; the 60.94/61.93 R49 conflict, the 15-vs-17 variant count, and one missing-supersedes class
are **not** reproduced (documented why — rule surface vs artifact-level data, no rule hacking).

## Honest limits (v0.2 alpha)

1. **Doc surface only.** kblint reads markdown + configured artifact fields. Defects that live only
   inside artifact stores, git history, or session logs are out of scope unless they reach a
   configured field/pointer.
2. **No semantics.** It cannot tell whether a route/decision is substantively right, only whether a
   claim's contract with a documented artifact is violated. `unresolved` is not "false".
3. **Design-repo calibration.** The rules were generalized from a R0-specific prototype; the
   R0 numbers in REGRESSION.md are not a held-out precision/recall estimate.
4. **R4 is off by default and experimental.** Artifact-chronology supersession needs shape/config
   guards; enabling it can flag cross-shape "newer value" pairs (regression: 3/3 manually checked
   R4 findings were false positives). Treat R4 findings as review candidates only.
5. **R2 is rounding-aware but still field-ambiguity-limited.** Display precision (half last place)
   is treated as a match, and `confirmed` requires an artifact pointer + a best-candidate field +
   no target language; nevertheless, when one paragraph cites several runs, field selection can be
   ambiguous — count only `confidence=="high"` R2 confirmed findings for strict accounting and keep
   `inherited-pointer`/`revalidation_due` in the review queue.
6. **R3 is low-precision in v0.1.** Generic subject anchors can pair different metrics/rows; treat
   R3 confirmed findings as review candidates until unit-family/row-label guards land (v0.2).
7. **The audit queue is not a defect list**, and the count of findings is not a population metric.
8. **R9 checks existence, not intent or correctness.** References to other projects' artifacts
   (illustrative examples, user-project paths in product docs) are out of contract; scope `docs`
   to your knowledge surface and/or use `allow_missing`/`inventory`. Fenced tree diagrams and
   illustrative-marker lines are deliberately not checked (conservative; can miss real defects),
   and bare filenames/directory names are never checked.
9. **No network/API/LLM at runtime**; stdlib only. Artifacts are read locally; nothing is uploaded.

## Layout

```
kblint/
  pyproject.toml  README.md  CHANGELOG.md  REGRESSION.md
  kblint/{__init__,__main__,cli,model,config,extract,report}.py
  kblint/rules/{__init__,base,r1_version,r2_number,r3_conflict,r4_supersedes,
                r5_expiry,r6_source_of_truth,r7_untracked,r8_audit_queue,
                r9_references}.py
  ci/github-actions.yml               # copy to .github/workflows/kblint.yml (full scan)
  ci/incremental.yml                  # PR job: base-commit baseline + `kblint diff` gate
  schema/claim.schema.json            # machine-readable claim entry (2020-12)
  examples/claims.example.json        # verified / stale / unknown claim entries
  examples/claim-audit.example.md     # Markdown claim mapped to the schema
  kblint/diff.py                      # NEW/PERSISTING/FIXED baseline classifier
  R9_REPORT.md                        # real-repo R9 scan + manual FP assessment
  tests/test_kblint.py
  tests/test_diff.py                  # incremental diff: classification, key stability, exit codes
  tests/test_claim_schema.py          # schema/examples consistency
  examples/sample_repo/            # synthetic fixtures: one defect per R1-R6 + clean controls
                                   # (R7 is exercised on R0, a real git repo, and in tests
                                   #  via a monkeypatched git; R8 always queues)
  examples/sample.kblint.json
  examples/R0.kblint.json
  examples/references.kblint.json     # R9 quickstart config (KB surface + safe allow_missing)
  examples/audit_report.md            # real generated scan summary (R2 R9)
```
