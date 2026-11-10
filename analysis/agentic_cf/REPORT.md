# Real-repo agentic coding counterfactual — multi-step tools + stale/corrected KB

**Model:** `deepseek-chat`; **18 runs** (3 repos × 3 KB conditions × 2 seeds), **max 25 steps**,
JSON-action tool loop. **Actual spend: ¥0.358668** for the primary (v2) pass (pre-registered hard
cap ¥20, stop-at ¥18); prompt/completion tokens **1,154,825 / 58,011**. The pre-registered result
is a **descriptive null**: with repository tools, a stale KB reference did **not** reduce
hidden-check passes relative to a corrected KB (corrected 4/6 vs stale 5/6 vs no-KB 3/6; one-sided
Fisher corrected>stale p=0.909, corrected>no-KB p=0.500). Tool access let agents self-correct stale
references in 2 of 3 repositories; the main contrast in the data is noise + action-protocol
fragility, not KB condition.

Pre-registration: [`PREREG.md`](PREREG.md) sha256
`e71e1d2f6b94e700ab4140306e76c98de0f4926321be9132eb26ad1b22d4e3b7` (frozen before any call);
one instrument addendum [`PREREG_ADDENDUM.md`](PREREG_ADDENDUM.md) sha256
`ce7d047774f6e0bfe1b10294efd1f018a67babdee0a39743a6a9c47cdaa8fdb2` (JSON-action parser defect,
full 18-cell re-run; v1 kept in `results_v1/` as a sensitivity, not a condition result).
API key loaded from the approved local env file; never printed or persisted.

## Design (frozen)

Cases are the three `analysis/coding_cf/tasks.json` cases (same parent/fix commits; parent→fix is
docs-only and changes only the designated KB file). One fresh `git archive <parent>` workspace per
run + base git commit; the **only** manipulated difference is the designated KB file:

| case | repo | KB file | stale (parent) reference | corrected (fix) reference | deterministic hidden check |
|---|---|---|---|---|---|
| R4 | R4 | `docs/AGENTS.md` | `layouts/_partials/icons.html` | `layouts/_partials/layouts/icons.html` | XML symbol `icon--terminal` + viewBox/path in the real sprite |
| R5 | R5 | `CLAUDE.md` | root `pages/`, `static/`, … | `miniprogram/` root + app.json | 4 `miniprogram/pages/stats/stats.*`; route in `miniprogram/app.json`; `node --check`; `Page(` |
| R3 | R3 | `AGENTS.md` | skill `memory-update` | skill `short-term-memory` | runnable `.py` under `.agents/skills/short-term-memory/` with `Gotchas & Context` bullet |

Conditions: `no_kb` (KB file absent), `stale_kb` (parent KB bytes), `corrected_kb` (fix KB bytes).
**The KB is not inlined in the prompt** — prompt = repo name, parent SHA, verbatim task text, tool
protocol, one neutral sentence that repository knowledge files may exist. Tools: `ls`, `read_file`,
`grep`, `write_file`, `apply_patch`, `run` (allowlist: case repo-test, `git status/diff`,
`python -m py_compile`, `node --check`, `gofmt -l`), `submit`; one JSON action per turn. Hidden
check code and corrected/stale strings never appear in the prompt. Seeds 0/1 = temperatures 0.2/0.3.

## Primary result (v2)

Per cell n=2; per condition n=6 (3 repos × 2 seeds). Exact counts; Clopper-Pearson 95% CIs per
condition; one-sided Fisher exact where named (descriptive only — 3 engineered repos, not a sample).

| case | no_kb | stale_kb | corrected_kb |
|---|---:|---:|---:|
| R4 | 2/2 | 2/2 | 2/2 |
| R5 | 0/2 | 1/2 | 0/2 |
| R3 | 1/2 | 2/2 | 2/2 |
| **all** | **3/6** | **5/6** | **4/6** |

- Clopper-Pearson 95% CI: no_kb [0.118, 0.882], stale_kb [0.359, 0.996], corrected_kb [0.223, 0.957].
- Fisher exact (one-sided): corrected > stale **p=0.909**; corrected > no_kb **p=0.500**.
  Reverse direction: stale ≥ corrected p=0.500; no_kb ≥ corrected p=0.879. **No arm ordering.**
- Secondary: pre-declared repo-test subset passed **18/18** on every arm — it is a regression gate
  for an *additive* change, so it is insensitive here and weak evidence by design.
- Steps (median): no_kb 20, stale 16, corrected 21; submitted 3/6, 5/6, 5/6; auto-submit-at-cap
  3/6, 1/6, 1/6. No wrong-path final edits and no dual-path (stale+corrected) edits in any arm.
- KB exposure: the designated KB appeared in tool output 0/6 (no_kb, by construction), 4/6 (stale),
  4/6 (corrected). Stale-path inspections (actions mentioning the stale token) 3 / 9 / 6.

## Mechanisms (what actually happened)

- **R4 (all 6 pass, KB never used).** Every arm ran `grep "icon--" docs` (or listed
  `docs/layouts/...`) and found the real sprite directly; the designated KB never appeared in tool
  output (kb_seen 0/6 even in `corrected_kb`). The stale reference cannot bite when the filesystem
  is one grep away.
- **engram (stale 2/2, corrected 2/2, no_kb 1/2).** Both stale-KB runs read the stale KB and still
  listed `.agents/skills/`, saw the real `short-term-memory` package directory, and wrote the helper
  there — the stale skill *name* was self-corrected by repository inspection. The no-KB failure was
  an action-format loop (repeated malformed `write_file` JSON at the step cap), not a location miss.
- **wechat (0/2, 1/2, 0/2 — noise + protocol fragility).** This task needs five artifacts plus a
  route edit; this is at the edge of the 25-step JSON-action budget. Failures: unescaped newlines in
  long `write_file` JSON contents made the action unparseable (dropped), a 25-step auto-submit
  mid-task, and one stale run that submitted after inspection without writing. The corrected arm
  failed more often than the stale arm — the opposite of the single-call pilot — which is best read
  as protocol/step-cap noise at n=2, not as evidence for stale harm.

## Instrument defect and v1 sensitivity (disclosed)

The first 18-run pass (v1) used a greedy `{.*}` JSON decoder: prose-wrapped or multi-object model
replies were rejected, silently dropping intended tool actions (mechanical, not condition-random),
and change accounting missed files under git-ignored trees. Fixed before the first v2 call
(first-complete-JSON parser; filesystem-manifest change accounting); **all 18 cells were re-run**
(not only failed cells), identical frozen prompts/cases/seeds. v1 is retained in `results_v1/`
(`runs_v1_parser_greedy.jsonl`, ¥0.39819) and is **not** used for the condition comparison:

| pass | no_kb | stale_kb | corrected_kb | note |
|---|---:|---:|---:|---|
| v1 (parser defect, sensitivity only) | 3/6 | 4/6 | 6/6 | instrument loss visible in transcripts |
| **v2 (primary, reported)** | **3/6** | **5/6** | **4/6** | corrected ≥ stale not supported |

Across both passes the corrected arm is never *worse* than stale by a consistent margin, but the
differences are within noise. Action-format failures remain substantial in v2 (30 `invalid_json`
turns across 18 runs: 11/11/8 by arm), spread across all arms.

## What this establishes / does not establish

**Does:** in three real repositories, with a 25-step tool loop (filesystem inspection, patch/write,
allowlisted tests) and the KB reference load-bearing for the target location, a **stale KB did not
measurably reduce task success**; agents that consult the repository self-corrected stale paths, and
the corrected KB gave no detectable advantage. This is a useful calibration result: the
location-disclosure effect measured in the single-call pilot (S6.18) **does not automatically
translate into agentic outcome harm**, which bounds the paper's harm claim.

**Does not:** show stale KBs are harmless in general, or that tools always rescue them; establish a
positive effect for corrected KBs; estimate a population effect. Limits: 3 engineered
location-load-bearing cases, not a random sample; n=2 seeds/cell (seeds are prompts, not independent
replicates); one model family (deepseek-chat); one ad-hoc JSON-action harness whose formatting
failures (30 invalid-JSON turns, 5 auto-submits at the 25-step cap) add outcome noise and make the
wechat cell especially fragile; hidden checks are path/artifact-level (existence + run), not full
code quality; the repo-test regression subset is insensitive to additive changes (18/18 pass); no
dual-path or wrong-path final edits occurred, so our stale-path-edit metric is uninformative here.

**Next step that would strengthen it:** native tool-calling (no JSON-string writes for file
content), repo-test-sensitive tasks, 3–5 tasks with more seeds, and a repo-test primary grader.

## Artifacts and reproducibility

- `PREREG.md` + `PREREG.sha256`, `PREREG_ADDENDUM.md` + `PREREG_ADDENDUM.sha256`.
- `harness.py` — `--dry-run` (zero API: 9 workspaces, KB arms, tool API, grading, parser checks),
  `--run [--cells ID,…] [--limit N] [--workers ≤2]`, `--summarize`.
- `results/runs.jsonl` (18 v2 rows: condition, cell, steps, tool counts, kb exposure, stale-path
  inspections, changed files, hidden check, repo test, tokens/cost/latency, final-diff path),
  `results/summary.json`, `results/diffs/*.diff` (full final diffs), `results/transcripts/*.json`,
  `results/dry_run.json`, `results_v1/` (+`summary_v1.json`).
- Reproduce: `python3 harness.py --dry-run && python3 harness.py --run && python3 harness.py
  --summarize` (API key required for `--run`).
- Behavioral / recovery-cost analysis of the same 18 runs (zero new calls): [`RECOVERY_COST.md`](RECOVERY_COST.md),
  [`results/recovery_cost.json`](results/recovery_cost.json), paper fragment
  `../../paper_workshop/agentverify2027/fragments/recovery_cost.md`.
- Paper fragment: `../../paper_workshop/agentverify2027/fragments/agentic_cf.md`.

**Cost total (v1+v2): ¥0.756858** (cap ¥20); API key never logged.
