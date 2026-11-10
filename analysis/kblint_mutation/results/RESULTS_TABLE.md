# kblint mutation evaluation — paper tables

## Table A. Injected mutation results (controlled; one mutant = one scan)

| rule | mutants (pos/neg) | TP | FN | FP | TN | recall | precision | FPR | FP / 100 claims | TP dispositions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| R1 | 5 (2/3) | 2 | 0 | 0 | 3 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×1, unresolved×1 |
| R2 | 8 (3/5) | 3 | 0 | 0 | 5 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×2, revalidation_due×1 |
| R3 | 4 (1/3) | 1 | 0 | 0 | 3 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×1 |
| R5 | 8 (3/5) | 3 | 0 | 0 | 5 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×2, revalidation_due×1 |
| R6 | 4 (1/3) | 1 | 0 | 0 | 3 | 100.0% | 100.0% | 0.0% | 0.00 | unresolved×1 |
| R7 | 15 (7/8) | 7 | 0 | 0 | 8 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×4, provenance_gap×2, unresolved×1 |
| R9 | 21 (8/13) | 8 | 0 | 0 | 13 | 100.0% | 100.0% | 0.0% | 0.00 | confirmed×8 |
| **all** | 65 | 25 | 0 | 0 | 40 | 100.0% | 100.0% | 0.0% | 0.00 | |

Notes: (i) injected mutants are *controlled* — each breaks (positive) or preserves (hard negative/control) exactly one referenced truth; (ii) audit-queue dispositions (`revalidation_due`, `unresolved`) count as detected but are not `confirmed` defects; (iii) R4 is off by default/experimental and excluded; (iv) FP/100 claims uses the claims scanned in the control/hard-negative mutants for that rule.

## Table B. Runtime (kblint CLI; deterministic, stdlib-only)

| scope | scans | median | p90 | max | median docs / claims |
|---|---:|---:|---:|---:|---|
| injected mutant scans | 65 | 0.065 s | 0.132 s | 0.184 s | 4 / 14 |

### Natural scan runtime (median of 3 runs per repo; read-only local repos)

| repo | R9 primary scope | R9 extended scope | R7 git scope |
|---|---:|---:|---:|
| R2 | 0.081 s | 0.108 s | 0.127 s |
| R3 | 0.073 s | 0.219 s | 0.236 s |
| R5 | 0.071 s | 0.178 s | 0.185 s |
| R4 | 0.091 s | 1.666 s | 1.72 s |
| R1 | 0.084 s | 0.114 s | 0.141 s |
| **median across repos** | 0.08 s | 0.18 s | |

## Table C. Natural scans — manually verified precision (natural vs injected kept separate)

| scope | findings | verified | TP | FP | verified precision | claims | FP / 100 claims |
|---|---:|---:|---:|---:|---:|---:|---:|
| R9 primary (AGENTS-style KB surface) | 3 | 3 | 3 | 0 | 100.0% | 294 | 0.00 |
| R9 extended (README/docs surface) | 72 | 72 | 4 | 68 | 5.6% | 13917 | 0.49 |
| R7 git provenance | 2 | 2 | 2 | 0 | 100.0% | 13917 | 0.00 |
| R0 corpus snapshot (aux) | 26 | 26 | 0 | 26 | 0.0% | 402 | 6.47 |
| shipped sample_repo (known defects) | 9 | 9 | 9 | 0 | 100.0% | 18 | 0.00 |

R9 primary scope follows the recommended `references.kblint.json` deployment (AGENTS.md / CLAUDE.md / docs/AGENTS.md / SKILL.md, allow_missing for generated/external artifact classes). The extended scope adds README/docs and is reported for transparency (product-documentation example paths are counted as FPs for the KB claim surface). 'shipped-fixture' is the synthetic sample_repo with its designed known defects; it is a sanity check, not a natural sample.

## Table D. Shipped sample_repo known-defect check (sanity)

- known-defect recall: 100.0% (5/5 designed defects detected)
- rules detected: R1, R2, R3, R4, R5, R6
- R4 experimental (off by default, excluded): 1 finding(s)
- clean-control docs (docs/clean.md, docs/numbers_clean.md): 0 findings

