# PRACTICAL QUICKSTART — audit → classify → repair → re-audit (one page)

Offline path (no API key, no network, no model call) on the bundled sample repository. Run in a copy
so the shipped sample stays intact: `cp -r repository-knowledge-audit /tmp/rka && cd /tmp/rka`.

## 1. Install / configure

`kblint` is stdlib-only Python 3.9+; no install needed — put the bundled package on the path:

```bash
export PYTHONPATH="$PWD/kblint"
python3 -m kblint rules        # v0.2.1, rules R1–R9
```

Minimal config (`examples/example-config.yaml`; kblint parses strict JSON, and JSON is a subset of YAML):

```json
{"repo": "sample-repo", "docs": ["docs/**/*.md"], "artifacts": ["artifacts/*.json"],
 "run_index": {"path": "sample-repo/artifacts/runs_index.jsonl", "format": "jsonl",
               "file_field": "file", "id_field": "run_id"},
 "now": "2026-11-05", "rules": {"R4": true},
 "references": {"enabled": true, "allow_missing": ["^(weights|runs|outputs|dist|build|node_modules)/"]}}
```

**Supported scope.** `docs` select the knowledge surface (Markdown; `AGENTS.md`, `CLAUDE.md`,
`docs/AGENTS.md`, `SKILL.md`, …); claims are checked against `artifacts` (JSON/JSONL/CSV) via optional
`run_index`, `pins`, `source_of_truth`. R9 checks local Markdown links, backticked repo-relative paths,
`make <target>` (root `Makefile`), `npm/pnpm/yarn run <script>` (root `package.json`). `--now` pins
expiry/chronology so reruns are identical.

## 2. Run the audit

```bash
python3 -m kblint scan --repo examples/sample-repo --config examples/example-config.yaml \
  --out out-before --format json,md,sarif --now 2026-11-05 --fail-on none
```

Actual output:

```text
- docs scanned: 11; claims extracted: 21; artifacts indexed: 3
- findings: **11** (confirmed 6, unresolved 2, provenance_gap 0, revalidation_due 3)
- audit queue (not defects): **3** claims
```

Writes `out-before/{findings.jsonl,summary.md,report.sarif}` (SARIF: 11 results). Exit is 0 because of
`--fail-on none`; drop that flag to gate CI on medium/high findings.

## 3. Classify the findings: Verified / Stale / Unknown

Classify **claims**, not rule names. The sample deliberately contains one of each class:

| class | sample claim | audit evidence | action |
|---|---|---|---|
| **Verified** | `docs/clean.md` "step time is 60.94 ms" | `artifacts/bench.json :: step_ms = 60.94`; audit emits **no** R2 finding | keep; pointer is resolved |
| **Stale** | `docs/stale_reference.md` cites `scripts/tune_old.sh`, `artifacts/r50_v3.json` | **R9 confirmed** `docs/stale_reference.md#L5`, `#L7` "file path does not exist" | repair; re-audit |
| **Unknown** | `docs/target.md` "acceptance target 35.83 ms" | **R2 `revalidation_due`** `docs/target.md#L3` (not in artifact index); R1 `unresolved` mixed torch pin | keep Unknown (owner/expiry); never relabel without evidence |

```bash
python3 - <<'PY'
import json
rows = [json.loads(l) for l in open('out-before/findings.jsonl')]
for r in rows:
    if r['rule'] in ('R9','R1') or ('target' in r['locator']):
        print(f"{r['locator']:30s} {r['rule']} {r['disposition']:15s} {r['subject'][:70]}")
print('clean.md findings:', [r['rule'] for r in rows if 'clean.md' in r.get('doc','')])
print('bench.json step_ms:', json.load(open('examples/sample-repo/artifacts/bench.json'))['step_ms'])
PY
```

```text
docs/pins.md#L3                R1 unresolved      mixed artifact environments for pin '2.14.1': doc declares 2.14.1+cu13
docs/target.md#L3              R2 revalidation_due number not located in artifact index: 35.83ms
docs/stale_reference.md#L5     R9 confirmed       file path does not exist: scripts/tune_old.sh
docs/stale_reference.md#L7     R9 confirmed       file path does not exist: artifacts/r50_v3.json
clean.md findings: []
bench.json step_ms: 60.94
```

## 4. Repair the knowledge file and re-audit (before/after diff)

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('examples/sample-repo/docs/stale_reference.md')
p.with_suffix('.md.bak').write_text(p.read_text())
p.write_text(p.read_text().replace('scripts/tune_old.sh', 'docs/clean.md')
                              .replace('artifacts/r50_v3.json', 'artifacts/r50_v2.json'))
PY
python3 -m kblint scan --repo examples/sample-repo --config examples/example-config.yaml \
  --out out-after --format json,md,sarif --now 2026-11-05 --fail-on none
python3 - <<'PY'
import json, collections
def n(p): return [json.loads(l) for l in open(p)]
b, a = n('out-before/findings.jsonl'), n('out-after/findings.jsonl')
print('before:', len(b), dict(collections.Counter(r['rule'] for r in b)))
print('after :', len(a), dict(collections.Counter(r['rule'] for r in a)))
print('R9 before/after:', [r['locator'] for r in b if r['rule']=='R9'], [r['locator'] for r in a if r['rule']=='R9'])
PY
```

Actual result: **11 → 9 findings** — the two R9 broken pointers disappear, everything else is
unchanged. Remaining R2 `revalidation_due` / R1 `unresolved` / R6 `unresolved` cells are still
**Unknown**: the repair removed stale pointers, it did **not** verify unverifiable claims.

## 5. What not to trust

- **Unknown ≠ Verified.** `revalidation_due`, `unresolved`, provenance gaps, and R8 audit-queue rows
  are not verified facts; only evidence that re-resolves (e.g. `clean.md` → `bench.json`) is Verified.
- **Surface-flagged % is not validation coverage.** Addressable-surface share, queue size, and R9 hit
  counts measure *reviewable surface*, not correctness; the audit queue is a hypothesis list, not a
  defect list.
- **Mutation recall is an upper bound.** Injected-mutant recall certifies rule wiring on crafted
  breakages, not field recall on natural staleness; read injected and natural results separately
  (`analysis/kblint_mutation/REPORT.md`).
- **The linter does not judge usefulness or correctness of a route.** Resolving references does not
  prove the surrounding claim true.

Next: `docs/RULES.md` (rules/config), `docs/MAINTENANCE_GUIDE.md` (lifecycle/dispositions),
`docs/QUICKSTART.md` (tests + offline benchmark grader), `README.md` (review vs public-release status).
