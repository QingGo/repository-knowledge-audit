# RULES — kblint rule reference (v0.2.1)

`kblint` is a deterministic, config-driven contract linter for engineering-agent knowledge artifacts
(`AGENTS.md`, `CLAUDE.md`, `docs/AGENTS.md`, `SKILL.md`, and other configured docs). It reports
**verifiable contract defects** plus an **unverifiable-risk audit queue**; it does not judge whether
knowledge is useful, correct as a route, or harmful, and findings are not a population measurement.
All rules are stdlib-only, offline, and deterministic for a fixed `--now`.

| ID | rule | what it checks | dispositions / severity |
|---|---|---|---|
| R1 | pin/version consistency | doc-declared environment pin vs configured artifact field (`artifact_keys`) | `confirmed` disagreement (medium); `provenance_gap` when the governed artifact field is absent (low) |
| R2 | number provenance | claim number with unit resolved in the artifact index (nested JSON/JSONL/CSV, relative tolerance, unit/key context) | `confirmed` `artifact_mismatch` when the cited field disagrees (high/medium); `revalidation_due` when not locatable (low) |
| R3 | cross-doc conflict | same normalized subject anchor (key/noun + unit) with conflicting values across ≥2 docs and no supersedes/deprecated marker | `confirmed`, one finding per subject group (medium) |
| R4 | missing supersedes | a newer artifact contradicts an artifact-backed claim and the claim/section has no supersedes/deprecated marker. **Off by default** (`rules.R4.enabled = true`); experimental artifact chronology | `confirmed` when enabled (low/medium; treat as review candidate) |
| R5 | expiry | negative-result / flag claims older than `expiry.env_change_date` or undated | `confirmed` / `revalidation_due` (medium) |
| R6 | source-of-truth | a claim about a configured topic outside its canonical doc without declaring it | `unresolved` "missing declaration" (medium; never guesses truth) |
| R7 | untracked / no owner | docs not in `git ls-files`; tracked docs with uncommitted changes; missing owner frontmatter | `provenance_gap` (untracked, medium), `confirmed` (uncommitted, medium), `unresolved` (owner, low) |
| R8 | audit queue | claims with no deterministic witness (numbers, pins, flags, contracts) | queue JSONL only — **never a defect** |
| R9 | reference check | local markdown links, backticked repo-relative paths, `make <target>` (root Makefile), `npm|pnpm|yarn run <script>` (root package.json) that do not exist in the scanned repo | `confirmed` broken evidence pointer (path/link medium; make/npm low) |

## Config keys (JSON; all optional)

```jsonc
{
  "repo": ".",
  "docs": ["AGENTS.md", "docs/**/*.md", "**/SKILL.md"],
  "exclude": ["**/node_modules/**", "**/dist/**", "**/build/**"],
  "artifacts": ["artifacts/*.json"],
  "run_index": {"path": "artifacts/runs_index.jsonl", "format": "jsonl",
                "file_field": "file", "id_field": "run_id"},
  "pins": [{"doc_glob": "docs/pins.md", "artifact_glob": "artifacts/r50_*.json",
            "artifact_keys": ["torch"], "doc_patterns": ["torch\\s+([0-9.]+\\+cu[0-9]+)"]}],
  "source_of_truth": [{"topic": "acceptance target", "canonical_doc": "docs/target.md"}],
  "expiry": {"env_change_date": "2026-10-01", "negative_flag_regex": []},
  "tolerance": {"relative": 0.0005},
  "git": {"enabled": false},
  "owner": {"frontmatter_keys": []},
  "rules": {"R4": false},
  "non_contract_patterns": [],
  "pin_patterns": {},
  "references": {
    "enabled": true, "check_paths": true, "check_links": true,
    "check_make": true, "check_npm": true,
    "allow_missing": ["^(artifacts|weights|runs|outputs|dist|build)/"],
    "inventory": ["assets/**"]
  },
  "now": "2026-11-05"
}
```

CLI: `kblint scan --repo PATH --config CONFIG.json|yaml [--out DIR] [--format json,md,sarif]
[--fail-on none|low|medium|high] [--now ISO-DATE] [--quiet]`. Exit codes: 0 no findings at/above
threshold, 1 findings at/above threshold, 2 error. `examples/example-config.yaml` is a
JSON-compatible YAML config (kblint parses JSON; JSON is a subset of YAML).

## Outputs

`findings.jsonl` (one JSON object per finding: rule, severity, disposition, locator, observed,
expected, verification_method, suggested_action), `audit_queue.jsonl` (R8 leads are hypotheses, not
defects), `summary.md` (headline counts and evidence), `report.sarif` (SARIF 2.1.0). Example reports
for the bundled sample repo are in `examples/example-report.{json,md,sarif}` (before) and
`examples/example-report-after.{json,md,sarif}` (after the one-reference repair in the quickstart).
