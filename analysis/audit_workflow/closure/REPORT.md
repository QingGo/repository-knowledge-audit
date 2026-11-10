# Closure of the R2 audit-repair loop: 4 → 3 → 0 (task-81)

**Status:** closed in a fresh temp copy; **R2 R9 4 → 3 → 0**, audit queue 31, one KB file
(`AGENTS.md`), KB-only repair, source repository read-only. No model calls, no network.
`kblint 0.2.1`; committed workflow config `../configs/R2.kblint.json`;
`--fail-on medium --now 2026-11-05`.

This directory is the evidence for the paper's Table 3 / §4.6 / S6.19 closure update. It extends the
workflow trace in [`../REPORT.md`](../REPORT.md) (see its "Closure" section) and does not replace it.

## 1. Result

| state | tree | claims | audit queue | R9 findings | exit | scan wall time | rerun byte-identical |
|---|---|---:|---:|---:|---:|---:|---|
| parent (stale KB) | `2bc2feb` | 77 | 31 | **4** | 1 | 0.090 s | yes |
| human fix (residual) | `29a0bc7` | 77 | 31 | **3** | 1 | 0.072 s | yes |
| **follow-up KB-only repair** (this task) | `29a0bc7` + KB edit | 77 | 31 | **0** | 0 | 0.071 s | yes |

The four parent findings were R9: three stale `docs/*.md` paths (`AGENTS.md#L124`–`#L126`) plus one
missing `make profile-deep` target (`#L23`). The human fix commit `29a0bc7` removed only the make-target
reference (and a volatile test count), leaving the three path findings — this is the paper's "human fix
left residuals" example. The follow-up repair repoints those three references to the real in-repo
documentation artifact and the rescan is clean.

## 2. Exact commands

```bash
cd kb-health/analysis/audit_workflow
python3 closure/run_closure.py            # 3 git-archive copies + 3 scans + diff + summaries (~1 s)
```

Per-state scan (recorded verbatim in `raw/<state>/meta.json`):

```bash
cd kb-health/kblint
python3 -m kblint scan \
  --repo /tmp/kb-audit-closure/<parent|fix|repaired> \
  --config /REPOS_ROOT/kb-health/analysis/audit_workflow/configs/R2.kblint.json \
  --out /REPOS_ROOT/kb-health/analysis/audit_workflow/closure/raw/<state> \
  --format json,md,sarif --fail-on medium --now 2026-11-05
```

Trees: `git archive 2bc2feba97ca5ca1e920bab57413b99779402e0a` (parent),
`git archive 29a0bc7e06aefb615eb5c07a46f56480a9bef0af` (human fix), repaired = fix tree with the KB
edit below. The source clone was never modified (`git status --porcelain` identical before/after;
`source_repo_unchanged: true` in `before_after/closure_summary.json`).

## 3. True-target verification and the minimal KB repair

The three residual findings (`raw/fix/meta.json.r9_findings`):

| locator | kblint subject | stale reference |
|---|---|---|
| `AGENTS.md#L124` | file path does not exist | `docs/paper.md` |
| `AGENTS.md#L125` | file path does not exist | `docs/arch_design.md` |
| `AGENTS.md#L126` | file path does not exist | `docs/implementation_notes.md` |

Verification that no true target exists under the claimed paths:

- `git log --all -- docs/` in the source repository returns **no commits** — no `docs/` tree was ever
  tracked in any branch/tag, and `git ls-tree -r 29a0bc7 | grep '^docs/'` = 0 entries. The three
  claimed files do not exist on disk either.
- The repository's tracked markdown is exactly `AGENTS.md`, `README.md`, `README_EN.md`. The real
  in-repo documentation artifact is **`README.md`**: it contains `## <private KB text removed>` (L11),
  `## <private KB text removed>` (L30), `## <private KB text removed>` (L240), `## <private KB text removed> ✅` (L265), `## <private KB text removed> ❌` (L283), and
  `## <private KB text removed>` (L300) — i.e. exactly the architecture and implementation-record content the KB
  entries point at. The project's public artifact named by `README.md#L350` is the Hugging Face model
  `R3-maintainer/R2`; there is **no standalone paper file** in the repository's history.

Minimal KB edit (`KB_REPAIR.diff`, 3 lines replaced, claim text preserved — no deletion):

```diff
-- <private KB text removed>: `weights/` (46 safetensors, ~150GB); <private KB text removed>: `docs/paper.md`
-- <private KB text removed>: `hot_experts.json`; <private KB text removed>: `docs/arch_design.md`
-- <private KB text removed>: `docs/implementation_notes.md`
+- <private KB text removed>: `weights/` (46 safetensors, ~150GB); <private KB text removed>: `README.md`（<private KB text removed>/<private KB text removed>；<private KB text removed>）
+- <private KB text removed>: `hot_experts.json`; <private KB text removed>: `README.md`（<private KB text removed>）
+- <private KB text removed>: `README.md`（<private KB text removed> / <private KB text removed> / <private KB text removed>）
```

Each stale path is replaced by the repository artifact that actually holds that content (README
sections), and the paper claim keeps its text with an explicit note that no standalone paper exists
in-repo. Rescan: **3 → 0** confirmed findings, exit 0, queue unchanged at 31.

**Honest alternative (not forced).** If the paper claim must denote a *standalone paper file*, then no
current target exists and the third finding is genuinely unfixable in-repo; the honest Table 3 value
would stay **4 → 3 → 1**. We chose the README repoint because it is a real, resolvable, in-repo
documentation artifact and the claim text is preserved (not deleted); this is stated in the fragment
so an author can choose the conservative row. (For comparison, the `weights/` model store and
`artifacts/` outputs are declared runtime/external paths and are handled by `allow_missing`, not by
this repair.)

## 4. Per-finding: deterministic detection vs human review

| class | finding | detected by | needs human review for |
|---|---|---|---|
| stale path (3) | `docs/paper.md`, `docs/arch_design.md`, `docs/implementation_notes.md` | **R9 deterministically**: the path is absent from the checkout | adjudicating *why* (no target ever existed vs moved) and choosing the correct replacement target |
| stale make target (1) | `make profile-deep` | **R9 deterministically**: target absent from the root Makefile (15 targets parsed) | — (removed by the human fix commit) |
| runtime/external paths (2, generic config only) | `artifacts/last_profile.json`, `weights/tokenizer.json` | detected deterministically, but **classified by a human** as false-positive-by-contract (generated output / external model store) and suppressed by config `allow_missing` | contract classification stays human |
| bare skill name (R3, non-R9) | `memory-update` → `short-term-memory` | **not detected**: a bare name is not a path/link/target witness; it sits in the 25-claim audit queue as `Unknown` | human review only |

So deterministic rules close the *reference* layer; human review is still required to (i) classify
runtime/external references, (ii) choose replacement targets when a path was never valid, and
(iii) catch stale bare identifiers that have no path witness.

## 5. Artifacts

```
closure/
  run_closure.py                 # re-runnable: archive copies + 3 scans + diff + summaries
  KB_REPAIR.diff                 # the minimal KB edit (fix-commit KB → repaired KB)
  raw/parent/    findings.jsonl audit_queue.jsonl summary.md report.sarif stdout.txt stderr.txt meta.json
  raw/fix/       (same)
  raw/repaired/  (same; findings.jsonl empty set, 0 R9)
  before_after/closure_summary.json   # states, findings, commands, hashes, table
  before_after/closure_summary.md     # compact Markdown table
  REPORT.md                      # this file
```

All three states reran byte-identically (`deterministic_rerun_byte_identical: true`); output sha256
per file are in `raw/<state>/meta.json.output_sha256`.

## 6. Limits

- This closure repair is **authored by us**, not by the project maintainers; it is a KB-only edit in a
  throwaway temp copy and the source repository remains read-only. It demonstrates that the residual
  is repairable, not that maintainers made the repair.
- One repository, KB file only, reference-level (R9) only; no coding or behavioural outcome; no
  population claim.
- The "paper" claim's replacement is a semantic judgement (the repo has no standalone paper); the
  conservative alternative row 4→3→1 is documented in §3 and in the paper fragment.
- Temp trees have no `.git`, so R7 is not exercised; the committed config sets `git.enabled=false`.
- Determinism uses fixed `--now 2026-11-05`, stdlib-only, offline; scan times (0.07–0.09 s) are
  machine-dependent.
