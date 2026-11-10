# Recovery cost of a stale KB in the 18 tool-loop coding runs (zero new model calls)

**Question.** When a coding agent can inspect the repository and run commands, what does a stale
knowledge-base reference actually cost in **behavior**: KB consultation, stale-path inspections,
dead-end lookups, extra steps/tool calls, tokens and money? This analysis re-uses the 18
pre-registered v2 tool-loop runs (`deepseek-chat`, max 25 steps, 3 repos × 3 KB conditions × 2
seeds; **no new API calls**). Primary outcome data: [`REPORT.md`](REPORT.md); raw artifact:
[`results/recovery_cost.json`](results/recovery_cost.json).

**Headline.** In this harness the stale KB produced a **small, recoverable inspection overhead, not
an outcome cost**: the stale arm made 6 stale-path tool calls *after* seeing the KB (corrected arm:
3), but attempted **0 edits at the stale path** and **0 wrong-path final files** in all 18 runs, and
its step/tool-call/token/cost totals were not higher than the corrected arm (median steps 16 vs 21;
median tool calls 13 vs 18; ¥0.119 vs ¥0.113). The stale reference cost a handful of dead-end
inspections (median 5 actions from first KB exposure to the first correct edit among the four
KB-exposed stale runs), not a recovery spiral. `R4` is a mechanically KB-free case: **no arm read
the KB** (0/6), all six runs pass.

## Data and transcript parsing (documented before counting)

`results/transcripts/<run_id>.json` is a list of chat messages:
`[system, user task prompt, assistant raw reply (truncated 1800 chars), user tool-output|invalid-JSON
nudge, ...]`. `results/runs.jsonl` is authoritative for per-run aggregates (steps, tool counts,
kb_read/kb_seen, stale_inspections, usage/cost, hidden pass). Analysis (`analyze_recovery.py`, zero
model calls) recovers each action with the harness's first-complete-JSON parser, aligns it with the
following user message (`tool output:` = executed; nudges = rejected; `state submitted` = submit
acknowledgement), and classifies it. Transcript- and record-derived invalid-JSON counts reconcile
**exactly** (11 / 11 / 8 per arm; mismatch list empty). Assistant replies are truncated at 1800
chars in the transcript, so content-level flags on very long write payloads can under-count; that is
noted where it matters.

Definitions: **KB read** = explicit read/ls/grep of the designated KB file (record); **KB seen** = a
distinctive KB line appeared in a tool output (record); **stale-touch action** = tool action whose
payload mentions the stale reference token (C5 `pages/` only when not preceded by `miniprogram/`);
**stale-path read** = a stale-touch action that is a read/ls/grep; **invalid lookup** = read/ls/grep
whose output was an error or `(no matches)`; **stale-path edit attempt** = write/apply_patch whose
target path is the stale reference path; **recovery overhead** = (index of the first edit at the
expected location) − (index of the first KB exposure, or the first stale-touch action if the KB was
never seen).

## Table 1 — per-arm behavioral / recovery cost (n=6 per arm)

| metric | no_kb | stale_kb | corrected_kb |
|---|---:|---:|---:|
| hidden-check passes | 3/6 | 5/6 | 4/6 |
| KB read (explicit) | 0/6 | **4/6** | **4/6** |
| KB seen in tool output | 0/6 | 4/6 | 4/6 |
| stale-touch actions, total (median/run) | 4 (0.5) | **9 (0.5)** | 6 (1.0) |
| stale touches **after** KB exposure | 0 | **6** | 3 |
| stale-path reads (read/ls/grep) | 3 | **5** | 4 |
| stale-path edit attempts (strict) | 0 | **0** | 0 |
| stale edit actions, payload-token count* | 1 | 4 | 2 |
| invalid lookups (error/no-match), total | 7 | 2 | 2 |
| stale-targeted invalid lookups | 1 | 1 | 1 |
| steps, mean (median) | 17.2 (20) | 15.8 (**16**) | 17.2 (**21**) |
| tool calls, total (median/run) | 89 (14.5) | 80 (**13**) | 90 (**18**) |
| invalid-JSON action turns | 11 | 11 | 8 |
| prompt / completion tokens | 338.8k / 21.4k | 382.3k / 19.3k | 433.7k / 17.3k |
| cost ¥, total (median/run) | 0.1265 (0.02) | 0.1193 (0.02) | 0.1129 (0.02) |
| latency, median (s) | 29.0 | 32.5 | 33.3 |
| auto-submit at 25-step cap | 3/6 | 1/6 | 1/6 |
| wrong-path final edits | 0 | **0** | 0 |
| repo-test subset pass | 6/6 | 6/6 | 6/6 |

\* `runs.jsonl`'s `stale_edit_actions` field scans the **payload text**, so it counts correct-path
writes whose file text mentions the stale token (e.g. an engram helper docstring saying "for the
memory-update skill", or a wechat `app.json` patch whose context contains `"pages"`). The strict
transcript metric (target path = stale path) is **0 in every arm**; no run ever wrote the stale
location.

## Table 2 — per repository × arm (n=2 per cell)

| repo (case) | arm | hidden pass | KB read | KB seen | stale-touch actions | steps mean |
|---|---|---:|---:|---:|---:|---:|
| R4 (C4) | no_kb | 2/2 | 0 | 0 | 0 | 6.5 |
| R4 (C4) | stale_kb | 2/2 | 0 | 0 | 0 | 8.5 |
| R4 (C4) | corrected_kb | 2/2 | 0 | 0 | 0 | 6.0 |
| R5 (C5) | no_kb | 0/2 | 0 | 0 | 1 | 20.0 |
| R5 (C5) | stale_kb | 1/2 | 2 | 2 | 1 | 16.0 |
| R5 (C5) | corrected_kb | 0/2 | 2 | 2 | 2 | 21.5 |
| R3 (C3) | no_kb | 1/2 | 0 | 0 | 3 | 25.0 |
| R3 (C3) | stale_kb | 2/2 | 2 | 2 | 8 | 23.0 |
| R3 (C3) | corrected_kb | 2/2 | 2 | 2 | 4 | 24.0 |

## Recovery overhead in the stale arm (the four KB-exposed runs)

| stale run | hidden | steps | KB idx | first stale idx | first correct edit idx | recovery (KB→edit) | steps after KB | stale touches after KB | stale-path reads |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R5 s0 | fail | 7 | 2 | — | — | — | 6 | 0 | 0 |
| R4 s0 | pass | 11 | — | — | 4 | — | — | 0 | 0 |
| R4 s1 | pass | 6 | — | — | 4 | — | — | 0 | 0 |
| R5 s1 | pass | 25 | 2 | 17 | 11 | 9 | 24 | 1 | 0 |
| R3 s0 | pass | 21 | 8 | 2 | 11 | 3 | 14 | 3 | 2 |
| R3 s1 | pass | 25 | 7 | 2 | 12 | 5 | 19 | 2 | 3 |

Among the four stale runs that consulted the KB: **median 16.5 actions after KB exposure, median 5
actions from KB exposure to the first correct-location edit**, 6 stale-touch detours, 1 stale-path
read that returned `(no matches)`, and 0 stale-path edit attempts. The comparable KB-exposed
**corrected** runs had median 19 actions after KB exposure and median 7.5 actions to the first
correct edit — i.e. in this small set the corrected references were not cheaper. `R4` stale runs
never consulted the KB (`kb_read`/`kb_seen` false); the one longer R4 stale run (11 vs 6 steps)
explored the repo without KB exposure and still passed, so its difference is not KB-attributable.

**Reading.** Within this harness the stale reference's behavioral footprint is *local and cheap*: a
few stale-path inspections, essentially no dead-end filesystem lookups (agents list the real
directory and find the target), no stale-path writes, and no growth in steps/tool calls/tokens/cost.
This is the behavioral counterpart of the null outcome in [`REPORT.md`](REPORT.md): the stale
reference is noticed and self-corrected rather than obeyed.

## `R4`: the KB is never consulted (quantified)

Across all three arms and both seeds, **0/6 R4 runs read the designated KB and 0/6 saw a KB line in
a tool output**; all 6 runs pass. The icon sprite is one `grep icon--` / `ls docs/layouts` away, and
every R4 run took that route (steps 6–11). The R4 KB manipulation is therefore mechanically
inert for behavior: no arm-level R4 difference can be attributed to the KB condition. This is an
important scope bound for the paper: KB effects require the KB to be consulted.

## Relation to independent concurrent evidence

Mehtiyev et al., *When Instruction Files Go Stale: Documentation Debt and Hidden Cost in Coding
Agents* ([arXiv:2611.09802](https://arxiv.org/abs/2611.09802), 6 Nov 2026) study three real stale
instructions (test command, code location, component procedure) under stale/corrected/removed
versions across 22 maintenance tasks and 732 trajectories. They find agents follow stale guidance
when relevant, with **~2 extra tool calls per run (~1/3 more) for the stale test command** and no
detectable difference for the other two guidance kinds; agents recover from immediate failures but
never repair the instruction file. Our 18-run analysis is **independent concurrent evidence in the
same direction** — stale KB adds stale-path tool calls (6 post-KB stale touches vs 3 with the
corrected KB) — and adds a calibration point: for these three real-repo location references the
detours were cheap, self-corrected and did not convert into outcome harm. That is consistent with
their negative results for the code-location/procedure cases and with "task success alone can hide
behavioral cost": here the behavioral cost exists but is small.

## Caveats (read before citing)

- **Custom JSON-action harness** (not native tool calling); long write payloads had to be JSON-string
  encoded, and 11/11/8 turns per arm failed that encoding (protocol noise, not KB cost).
- **KB not auto-injected**: the KB is a workspace file the agent must discover; in `R4` it never is,
  so KB-condition behavioral effects are absent by construction there.
- **n=6 per arm** (3 engineered repos × 2 prompt seeds; 2 per repo×arm cell), one model family
  (deepseek-chat); not a random sample; counts are descriptive, no inference.
- **Transcript-derived counts** with assistant messages truncated to 1800 chars; strict stale-path
  edit attempts are 0 in every run, so the payload-token "stale edit" counts are over-counts.
- The repo-test subset passes 18/18 (it is insensitive to additive changes) and is not a behavioral
  cost measure here.
- This is **behavioral cost within this harness**, not a claim about native agent behavior.

## Reproduce

```bash
cd kb-health/analysis/agentic_cf
python3 analyze_recovery.py      # zero API calls -> results/recovery_cost.json
python3 -m json.tool results/recovery_cost.json | head
```

Artifacts: `results/recovery_cost.json` (definitions, per-arm/per-repo aggregates, per-run rows,
stale-run recovery table, R4 block, external-evidence note), `results/runs.jsonl`,
`results/transcripts/*.json` (18). Paper fragment: `paper_workshop/agentverify2027/fragments/
recovery_cost.md`.
