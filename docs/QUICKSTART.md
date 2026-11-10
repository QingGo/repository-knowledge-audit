# QUICKSTART — 5-minute, six-step walkthrough

Requirements: Python 3.9+ (stdlib only for kblint), `pytest` for tests/grader, `numpy` for the
benchmark grader examples. No API key, no network, no model call. Commands assume the repository root
(the directory containing `kblint/`, `examples/`, `benchmark/`); replace `/tmp/...` output paths freely.

## 1. Install / verify kblint (no network)

`kblint` is a stdlib package in `kblint/`. Either install it locally, or run it with `PYTHONPATH`:

```bash
# option A (no network, no install):
export PYTHONPATH="$PWD/kblint"
python3 -m kblint rules

# option B (editable install; needs local pip/setuptools):
# python3 -m pip install -e kblint && kblint rules
```

You should see the nine rules R1–R9. `python3 --version` must be 3.9+.

## 2. Audit the bundled sample repository

```bash
python3 -m kblint scan --repo examples/sample-repo --config examples/example-config.yaml \
  --out examples/out-before --format json,md,sarif --now 2026-11-05 --fail-on none
```

Expected: 10 docs scanned, findings incl. an **R9 broken evidence pointer** in
`examples/sample-repo/docs/stale_reference.md` (`scripts/tune_old.sh`, `artifacts/r50_v3.json`), plus
the R1/R2/R3/R4/R5/R6 sample findings. Exit code 0 because `--fail-on none`.

## 3. Inspect JSON / Markdown / SARIF findings

```bash
sed -n '1,60p' examples/out-before/summary.md
python3 - <<'PY'
import json, collections
rows = [json.loads(l) for l in open('examples/out-before/findings.jsonl')]
print('findings:', len(rows), 'by rule:', dict(collections.Counter(r['rule'] for r in rows)))
print('R9:', [(r['locator'], r['subject']) for r in rows if r['rule'] == 'R9'])
s = json.load(open('examples/out-before/report.sarif'))
print('SARIF results:', len(s['runs'][0]['results']))
PY
```

Pre-generated reports from this exact scan are in `examples/example-report.json` (JSON array),
`examples/example-report.md`, `examples/example-report.sarif`.

## 4. Fix one stale reference

The stale sample doc points at a removed script and a missing artifact. Fix both references to
existing files with the following one-liner (keeps a backup):

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('examples/sample-repo/docs/stale_reference.md')
t = p.read_text()
p.with_suffix('.md.bak').write_text(t)
p.write_text(t.replace('scripts/tune_old.sh', 'docs/clean.md')
             .replace('artifacts/r50_v3.json', 'artifacts/r50_v2.json'))
PY
```

## 5. Re-run the audit and compare before/after

```bash
python3 -m kblint scan --repo examples/sample-repo --config examples/example-config.yaml \
  --out examples/out-after --format json,md,sarif --now 2026-11-05 --fail-on none
python3 - <<'PY'
import json
def r9(path):
    return [(r['locator'], r['subject']) for r in map(json.loads, open(path)) if r['rule'] == 'R9']
print('R9 before:', r9('examples/out-before/findings.jsonl'))
print('R9 after :', r9('examples/out-after/findings.jsonl'))
PY
```

Expected: the two R9 findings for `docs/stale_reference.md` disappear; everything else is unchanged.
The shipped after-report is `examples/example-report-after.{json,md,sarif}`. Restore the original doc
(`mv examples/sample-repo/docs/stale_reference.md.bak ...`) if you want the initial state back.

## 6. Run the tests and the deterministic saved-completion grader (no API)

```bash
python3 -m pytest -q kblint/tests                 # 42 tests (some need optional deps/platform)
python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 \
  --code benchmark/grader/examples/saved_pass.py  # PASS, exit 0
python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 \
  --code benchmark/grader/examples/saved_fail.py  # FAIL, exit 1
```

The grader writes a temporary `solution.py` + the task's hidden pytest suite, runs pytest, and reports
pass/fail deterministically — no model call, no network. The same grader applied twice to the same
saved completion returns the same result. Benchmark hidden tests were **experiment-time hidden** and
are released here post hoc; do not treat them as a held-out set after this release.

## What next

- `docs/RULES.md` — rule/config reference (R1–R9, severities, dispositions, outputs).
- `docs/MAINTENANCE_GUIDE.md` — knowledge lifecycle, disposition recording, decision table by
  knowledge type, and the "executable sources of truth" principle.
- `benchmark/` — 54 task definitions + conditions + frozen results; `benchmark/grader/` for saved
  completions.
- `analysis/` — mutation evaluation, real-repository audit workflow (before/after figure), coding
  counterfactual, cost audit, pre-registered 2×2, repair replay, conventional-checker head-to-head, flip-rate/family-LOO reanalysis.
