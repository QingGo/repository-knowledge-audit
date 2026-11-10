# Repository Knowledge Audit: deterministic KB linter, benchmark, and analyses

Public, runnable artifact for the AGENTVERIFY 2027 paper
*Auditing Repository Knowledge for Coding Agents: Claim-Level Effects, Compositional Interference, and Evidence-Grounded Maintenance*.

The artifact contains the deterministic, stdlib-only knowledge-base linter **kblint** (rules R1–R9;
including its incremental PR-audit `diff` mode and a machine-readable claim schema), its
controlled-mutation evaluation, a 54-task convention benchmark with hidden pytest suites and
frozen per-condition results, a real-repository audit-workflow example, a pre-registered 2×2
verified-label experiment, the repair replay and coding counterfactual analyses, an all-task ITT
reanalysis, a pre-registered source-of-truth precedence experiment, a tool-loop agentic counterfactual
with a zero-API recovery-cost audit, a natural-checkout audit of 16 pinned public repositories, a historical replay of the
incremental PR gate on real commit events, an independent-model-family replication (MiMo), and the
full input/output token and cost accounting. Everything needed for the 5-minute quickstart is in this repository; **no
API key, network access, model call, or private repository is required for it**.

## Anonymity / review note

This is the **anonymous review version**. Five private repositories used by the repository-derived
experiments are anonymized as **R1–R5**; their fixed parent/fix git commit SHAs are retained so the
snapshots remain checkable, but repository names are withheld. No author identity, local absolute
paths, credentials, or private repository names are included. Raw model prompts/completions,
per-repository scan dumps, and the private KB repair diff are withheld or redacted because they embed
private KB text; frozen per-run outcome metrics and reports are retained (see `ANONYMIZATION.md`).
A camera-ready/public release may restore repository names and add a public link; this bundle contains
no invented URLs or DOIs.

**Benchmark hidden tests:** the 54 hidden pytest suites were hidden from the model at experiment time
and are released here **post hoc** for reproducibility. They must **not** be treated as a held-out
test set after this release, and any post-release re-run of the benchmark is not a pre-registered
held-out evaluation.

## Quick start (5 minutes)

```bash
python3 --version                  # Python 3.9+; stdlib only for kblint
PYTHONPATH=kblint python3 -m kblint rules
PYTHONPATH=kblint python3 -m kblint scan --repo examples/sample-repo \
  --config examples/example-config.yaml --out examples/out-before \
  --format json,md,sarif --now 2026-11-05 --fail-on none
sed -n '1,40p' examples/out-before/summary.md
```

For the one-page audit → classify → repair → re-audit path with a Verified/Stale/Unknown walk-through, see
[`docs/PRACTICAL_QUICKSTART.md`](docs/PRACTICAL_QUICKSTART.md). For the six-step flow, follow
[`docs/QUICKSTART.md`](docs/QUICKSTART.md): audit → inspect
JSON/Markdown/SARIF → fix one stale reference → re-audit (before/after reports included) → run the
linter tests (42) → grade a saved benchmark completion deterministically (no API).

## Layout

```
kblint/                    deterministic linter: source, pyproject, 42 tests, example configs, CI;
                           incremental PR audit (`python3 -m kblint diff --before ... --after ...`);
                           machine-readable claim schema (`schema/claim.schema.json`)
examples/                  runnable sample repository + example config + before/after reports
benchmark/                 54 task definitions (hidden tests released post hoc), conditions, grader, frozen results
analysis/                  kblint mutation eval, audit workflow, coding counterfactual, cost audit,
                           verified-label 2x2, repair replay, ITT reanalysis, precedence, agentic
                           counterfactual with recovery cost, MiMo replication, natural-checkout audit,
                           PR-gate replay, conventional-checker head-to-head, zero-cost flip-rate/family-LOO reanalysis
docs/                      QUICKSTART, PRACTICAL_QUICKSTART, RULES (R1-R9 + config keys/severity), MAINTENANCE_GUIDE
.github/workflows/         CI job: kblint tests + sample-repo audit + saved-completion grading
VERSION, MANIFEST.json, SHA256SUMS, SECURITY_CHECK.md, ANONYMIZATION.md,
LICENSE (code, Apache-2.0), LICENSE-DATA (data/docs, CC BY 4.0), LICENSE-NOTES.md
```

## Requirements

- Python 3.9+; `kblint` uses only the standard library.
- `pytest` for the linter tests and the benchmark grader; `numpy` for benchmark solutions.
- No network, API key, or model call for the quickstart or grader. Model runs are optional and were
  executed with the DeepSeek API during the study; no prompt/log contains a credential.

## Reproduce the frozen results

The JSONL/JSON result files under `benchmark/results/` and `analysis/*/results/` are the frozen
outputs used in the paper; the analysis reports explain each table. No benchmark re-run is needed to
reproduce the reported numbers. A full re-run of the model experiments needs the model API and is not
part of the quickstart; the saved-completion grader lets you score any saved completion offline.

## License

- **Code** (`kblint/`, analysis scripts, example configs, CI): **Apache License 2.0** --- see
  `LICENSE` (SPDX: `Apache-2.0`).
- **Benchmark data, frozen results, analyses, figures, and documentation**: **Creative Commons
  Attribution 4.0 International** (CC BY 4.0) --- see `LICENSE-DATA`; attribution is required
  ("the repository-knowledge-audit authors") and reuse should cite the accompanying paper.
- The 54 hidden pytest suites are released **post hoc** under CC BY 4.0 and must not be treated as a
  held-out test set after this release.

## Provenance

Built from the kb-health research workspace. `VERSION` records the artifact version, date, and a
content hash; `MANIFEST.json` and `SHA256SUMS` give per-file sha256 and sizes; `make_artifact.py`
rebuilds the same deterministic zip (fixed file order and timestamps, per-file hashes, prints the
zip sha256). Build: `python3 make_artifact.py` from this directory's parent.
