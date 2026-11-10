# kblint mutation evaluation

Controlled mutation evaluation of the deterministic contract linter `kblint`
(`kb-health/kblint`, v0.2.1), for the KB-hygiene paper. Offline, deterministic, no LLM/API.

## Quickstart

```bash
cd kb-health/analysis/kblint_mutation
python3 mutate.py build      # deterministic fixture build (synthetic R1-R7 + R9/R7 real-repo copies)
python3 run_eval.py          # full eval: injected mutants + natural scans (x3 timing), ~28 s
python3 r7_recheck.py --tag after   # R7 non-ASCII git-path bug before/after check
```

Outputs land in `results/`: `cases.jsonl`, `findings_injected.jsonl`, `natural_findings.jsonl`,
`natural_verification.jsonl`, `summary.json` (incl. `paper_numbers` + frozen linter hashes),
`RESULTS_TABLE.md`, `r7_recheck_before.json` / `r7_recheck_after.json`.

## Reading the results

* **Injected mutants are a controlled upper bound**: each mutant breaks (positive) or preserves
  (hard negative/control) exactly one referenced truth, so recall/precision certify rule wiring,
  not field performance.
* **Natural sample is the realism check**: read-only scans of the 5 local repos, every confirmed
  finding manually verified (`results/natural_verification.jsonl`), with injected and natural
  results always reported separately.
* **R9 scope matters**: the recommended AGENTS-style KB surface is the paper-facing natural
  sample; README/product-documentation scope is a transparency sample whose product-example
  references are out of contract.
* See `REPORT.md` for methods, scope definitions, the R7 bug found-and-fixed during evaluation,
  runtime tables and the honest-limitations list.

## Files

| file | role |
|---|---|
| `mutate.py` | builds synthetic fixture families + mutants; `fixtures/MANIFEST.json` |
| `real_specs.py` | R9 mutants on minimal copies of the local repos; R7 git-copy mutants |
| `run_eval.py` | scans fixtures + natural corpora, computes metrics, writes `results/` |
| `r7_recheck.py` | before/after re-check for the R7 non-ASCII git-path bug |
| `REPORT.md` | full report, scope definitions, limitations, paper-quotable sentences |
| `results/RESULTS_TABLE.md` | paper-ready tables A-D |
