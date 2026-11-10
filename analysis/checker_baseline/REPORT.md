# Conventional document checkers vs claim-level auditing (offline head-to-head)

Question (external review): what does `kblint`'s reference rule (R9) — and the claim-level audit
around it — detect beyond a markdown link checker, a "30-line" path-existence script, or an extended
existence script that also checks make/npm targets? No model calls; everything below is offline.

## Method

Three deliberately literal baselines, implemented in `run_baseline.py` (stdlib only):

| method | what it checks |
|---|---|
| link | Markdown inline/auto links whose target is local; resolves doc-relative and root-relative; flags missing targets |
| path | backticked path tokens and prose tokens carrying a file extension; same resolution; flags missing |
| ext | path + link + `make <target>` against the root `Makefile` and `npm/pnpm/yarn run <script>` against root `package.json`; flags missing entries |

None has a claim/evidence model: no unknown/verified/stale disposition, no audit queue, no
incremental diff. They are our own implementations (deliberately stronger than a naive script:
doc-relative *and* root-relative resolution), not the lychee / markdown-link-check binaries.

## A. Real repositories (the 16 pinned checkouts / 28 adjudicated R9 findings of S6.28)

Same trees, same documents, same reference targets; adjudicated classes from
`analysis/natural_checkout_audit/adjudication.jsonl` (14 true stale, 8 false-positive-by-contract,
6 runtime-unavailable).

| method | candidates | confirmed stale caught (of 14) | FP / runtime flagged | extra candidates (unadjudicated) | runtime, 16 trees |
|---|---|---|---|---|---|
| Markdown link checker | 1 | 0 | 1 / 0 | 0 | <0.1 s |
| Path-token existence script | 30 | 14 | 8 / 6 | 2 | 0.1 s |
| Extended existence (paths+links+make+npm) | 30 | 14 | 8 / 6 | 2 | 0.1 s |
| kblint R9 (committed config) | 28 | 14 | 8 / 6 | — | 2.3 s (full scan; 0.069–0.463 s/repo) |

Reading: a markdown link checker sees only the inline-link subset — one candidate, and that one is a
false positive (a removal note), so 0/14 confirmed stale pointers. A short path-existence script
reproduces **all 28** R9 candidates (14/14 confirmed stale, the same 8+6 noise, plus 2 unadjudicated
extra targets). That is the honest bound: **the existence check itself is conventional, not the
increment.** An extended script additionally verifies the 10 `make` / 18 `npm` command references in
these KB documents, which link/path checkers cannot see at all.

## B. Controlled mutations (the 25 positive injected breakages of S6.17)

Each positive fixture is compared with its negative-control sibling (same repository state, no
mutation); a baseline "detects" a breakage only if it reports a newly missing target that `kblint`
attributes to the injection. This avoids counting pre-existing missing references.

| method | R9 path/link mutants (5) | R9 make/npm mutants (3) | other rules R1–R7 (17) | total (25) |
|---|---|---|---|---|
| Markdown link checker | 1 | 0 | 0 | 1 |
| Path-token existence script | 5 | 0 | 0 | 5 |
| Extended existence (paths+links+make+npm) | 5 | 3 | 0 | 8 |
| kblint (full rule set) | 5 | 3 | 17 | 25 |

The 17 invisible breakages are pin mismatches (R1, 2), number/artifact mismatches (R2, 3),
cross-document conflict (R3, 1), expiry of negative results (R5, 3), canonical/source-of-truth
declaration (R6, 1) and git provenance (R7, 7). They are structurally outside existence checking.
(The one link mutant is also visible to the path script because its target appears as a raw token.)

## Caveats

- The real-audit classes come from the single-annotator adjudication of S6.28; the 2 extra path-script
  candidates were not adjudicated. R9 candidates and baseline candidates are compared by normalized
  target; the path script is given both document-relative and root-relative resolution.
- The mutation comparison uses `kblint`'s own injected findings to identify the intended target; for
  non-R9 rules detection is impossible by construction (the script does not evaluate numbers, pins,
  conflicts, dates, or git state), which we verified by comparing positive and negative-control
  fixtures.
- Command-reference counts (10 make / 18 npm) are occurrences in the KB documents, not confirmed
  stale claims; none of the 16 audit's confirmed stale pointers were make/npm targets.
- The extended script is a fair upper bound on "conventional existence checking", but a motivated
  maintainer could keep extending it; the point is where the boundary lies, not that it cannot be
  coded.

## Reproduce

```
cd analysis/checker_baseline
python3 run_baseline.py         # reads ../natural_checkout_audit and ../kblint_mutation
cat results/real_repo_head_to_head.json results/mutation_coverage.json
```
