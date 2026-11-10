# Pre-registration — real-repo agentic coding counterfactual (tools + stale/corrected KB)

**Status:** `preregistered-before-any-model-call` (frozen sha256 in `PREREG.sha256`, written before
the first API call). Time-box ~3 h. Model: `deepseek-chat` via the approved local helper
(`probe_screen/run_probes.py`: `load_env` / `chat` / `usage_cost`). No LLM judge, no network beyond
the model API, deterministic grading.

**Motivation.** The paper's current real-repo coding bridge (S6.18 / `analysis/coding_cf`) is a
single-call, no-tools pilot with a weak pre-registered strict result (2/6 corrected vs 0/18 controls,
Fisher p=0.054) and a post-hoc format-repair sensitivity (6/6). The open question (REVISION_202609
open item 1/2) is whether the effect survives a **multi-step agent with repository tools**: tool
access could let an agent *self-correct* a stale reference (checking the filesystem, running tests),
in which case a stale KB may be much less harmful. A null is a valid, useful calibration result.

## 1. Design (fixed before any model call)

**3 repositories × 3 KB conditions × 2 prompt seeds = 18 runs.** One run = one tool-loop episode,
`deepseek-chat`, max **25 steps** (one JSON action per step), workers ≤ 2 (all runs logged to
`results/runs.jsonl`; one fresh workspace per run).

Cases are the three existing `analysis/coding_cf/tasks.json` cases (same parent/fix commits, same
tasks, same deterministic hidden checks, same repo-test subsets). Parent→fix diffs were re-verified
to be **docs-only** and to touch only the designated KB file:

| case | repo | parent → fix (short) | KB file | stale fact | corrected fact | hidden check (deterministic, never in prompt) |
|---|---|---|---|---|---|---|
| R4 | R4 | `544ae6061549` → `70e71a62d713` | `docs/AGENTS.md` | `layouts/_partials/icons.html` | `layouts/_partials/layouts/icons.html` | XML-parse `docs/layouts/_partials/layouts/icons.html`; `<symbol id="icon--terminal" viewBox=…>` with nonempty `<path>` |
| R5 | R5 | `328f6da445ac` → `50a71b46e12b` | `CLAUDE.md` | root `pages/`, `static/`, `user/`, `pay/` | `miniprogram/` root + `miniprogram/app.json` | `miniprogram/pages/stats/stats.{js,json,wxml,wxss}`; `pages/stats/stats` in `miniprogram/app.json`; `node --check`; `Page(` |
| R3 | R3 | `b674155f2b94` → `07635ed1a8fb` | `AGENTS.md` | skill `memory-update` | skill `short-term-memory` | executable `.py` under `.agents/skills/short-term-memory/`; `--session-id s1 --output out.md` produces `Gotchas & Context` + bullet containing `s1` |

KB content hashes (sha256, first 16 hex; full hashes reproducible with the command in §8):

| case | parent (stale) KB sha256 | fix (corrected) KB sha256 | bytes parent/fix |
|---|---|---|---|
| R4 | `4b7844261e418055` | `491e27280a179e5b` | 1043 / 1051 |
| R5 | `422486529722aff2` | `2ed677c864df689d` | 4502 / 4913 |
| R3 | `afe3c66012f10e00` | `a1297fc882ea0bce` | 14286 / 14301 |

**Conditions (the ONLY manipulated difference is the designated KB file's presence/content):**
- `no_kb`: the designated KB file is **absent** from the fresh workspace (no KB text anywhere in the
  prompt; other repository files are untouched).
- `stale_kb`: the workspace contains the designated KB file exactly as at the **parent** commit.
- `corrected_kb`: the workspace contains the designated KB file exactly as at the **fix** commit
  (byte-identical to the parent archive except that file).

**Seeds:** seed 0 → temperature 0.2; seed 1 → temperature 0.3 (same convention as the pilot).
Each (case, condition, seed) is run exactly once; the validation run (R4/corrected_kb/seed 0)
is part of the 18 and is not excluded from analysis.

## 2. Workspace and prompt contract

**Workspace.** Per run: `git archive <parent_sha>` from the read-only clone at
`/HOME/code/<repo>` into a fresh `/tmp/agentic_cf/work/<run_id>` directory; apply the
condition's KB mutation; `git init` + single base commit (so the agent can run `git status`/`git
diff`); for `R5` only, symlink `/tmp/cf-phase1/R5/node_modules` (for the
repo-test subset) and add `node_modules` to `.git/info/exclude`. Source clones are never modified.
The repository name, parent SHA, and task text are identical across conditions.

**Prompt (identical across conditions except the KB file itself).** System: JSON-action protocol and
tool list. User: repository name + parent SHA, the `tasks.json` **task text verbatim** (names no
hidden/correct path), a neutral single sentence that repository knowledge files may be present
(AGENTS.md / CLAUDE.md / docs/AGENTS.md) and can be consulted, and the step budget. The hidden check
code and the corrected/stale reference strings are never shown. The KB is **not** inlined in the
prompt (unlike the pilot): with tools, the agent must discover it in the workspace; this is the
manipulation under test.

**Tool API** (one JSON object per assistant turn; unknown/invalid actions are rejected with a
message and consume a step):
`{"action":"ls","path":"."}` · `{"action":"read_file","path":"rel"}` ·
`{"action":"grep","pattern":"regex","path":"."}` ·
`{"action":"write_file","path":"rel","content":"..."}` ·
`{"action":"apply_patch","patch":"<unified diff>"}` ·
`{"action":"run","cmd":"..."}` (allowlist below) · `{"action":"submit"}`.
Paths must resolve inside the workspace (traversal rejected). Tool output is truncated (≤1800 chars)
and `read_file`/`grep` are size-capped. Step budget 25; at step 25 the current state is graded and the
run is marked `auto_submit=true` (no more calls).

**`run` allowlist:** the case's exact repo-test command; `git status`, `git diff` (optionally
`--stat`); `python -m py_compile <rel>`; `node --check <rel>`; `gofmt -l <rel>`. No shell, no
network commands, no arbitrary binaries. Timeout 120 s. Any other command is rejected with a message.

## 3. Outcomes

**Primary:** deterministic **hidden-check pass** on the final workspace (`coding_cf.py` check_hugo /
check_wechat / check_engram reused unchanged; pass = check returns True). A failed/unapplied patch
is a fail; a run that edits only the stale location is a fail unless the check independently passes.

**Secondary (recorded, never folded into the primary):** pre-declared repo-test subset pass
(R4 `go test ./common/hstrings -count=1`; wechat `npx jest test/unit/cloud_function.test.js
test/unit/track_event.test.js --runInBand`; engram `python3.13 -m pytest tests/unit/test_config.py
tests/unit/test_hashing.py -q` with the preinstalled `/tmp/cf-phase1/engram-deps313` PYTHONPATH);
toolchain/deps unavailable is recorded as `unavailable`, not as fail; steps to submit; tool-call
counts by type; **stale-path inspections** (actions whose path/pattern/content mentions the stale
reference token or stale directory; also whether the stale path was ever created/edited);
**wrong-path final edits** (final changed files matching the stale reference); `dual_path` recovery
(stale and corrected location both created/edited); whether the designated KB file was read
(KB arms); tokens (prompt/completion/cache), estimated cost CNY, wall time; final diff (full diff
stored under `results/diffs/`, truncated `diff` in runs.jsonl), changed files, and
unrelated-file changes (changed files outside the pre-declared expected paths of the case).

## 4. Analysis plan (fixed)

- Per (case, condition) exact counts (n=2) and per-condition totals (n=6, 3 repos × 2 seeds);
  per-repo 3×3 table. **No pooling beyond descriptive totals**; repos are 3 engineered
  load-bearing cases, not a random sample.
- Clopper-Pearson 95% CIs per condition (exact, computed from the binomial CDF; n=6).
- One-sided Fisher exact tests (hypergeometric, exact) for `corrected_kb` vs `stale_kb` and
  `corrected_kb` vs `no_kb` on the primary outcome; report as descriptive exact counts with
  clustering by repo ignored (n=3 repos).
- Secondary outcomes reported as exact counts/medians; costs summed.
- **No exclusion of runs**; API failures are retried once before the first action (harness-level
  retry, not outcome-based); a persistent failure is recorded as `error` and counts as a primary
  fail. No re-runs after seeing outcomes. No prompt or case tuning after the first model call.
- A null (e.g. all conditions pass, or stale_kb ≈ corrected_kb) is reported as a valid result and
  bounds the harm claim; the paper fragment must state that tool access can make stale references
  self-correctable.

## 5. Cost, stopping, operations

- Hard cost cap **¥20**; stop issuing new runs at cumulative estimated cost **≥ ¥18** (usage cost
  estimated with the same `usage_cost` off-peak price table as the pilot; actual provider billing
  may differ). Exactly **18** runs; **workers ≤ 2**; each run ≤ 25 steps.
- Flow: (1) write/freeze this PREREG (sha256) **before any model call**; (2) no-model `--dry-run`
  (workspace construction + KB arms + tool API + grading mechanics, zero API calls);
  (3) one end-to-end validation run (R4/corrected_kb/seed0), inspect transcript/grades, report
  to Lead; (4) scale to the remaining 17 runs; (5) analysis + REPORT.md + paper fragment.
  Deviations after freeze (if any) are listed in REPORT.md with timestamp and reason; none is made
  to change the estimand after outcomes are seen.

## 6. Known limits (pre-declared)

- Three engineered cases where the KB reference is load-bearing; n=2 seeds per cell; one model
  family; one tool API. Hidden checks are path/artifact existence+behavior, not full code quality.
- The no-KB arm may still guess the correct path from repository inspection/convention; the stale
  arm may recover by inspecting the filesystem. These are exactly the mechanisms of interest.
- Tool sanctions are a usability guard, not a security boundary. The 25-step cap and output
  truncation may truncate long debugging behavior.
- Secondary repo tests are a regression signal, not the primary outcome; they may be
  toolchain-dependent, and that is recorded honestly.

## 7. Artifacts

`analysis/agentic_cf/{PREREG.md, PREREG.sha256, harness.py, results/runs.jsonl,
results/summary.json, results/diffs/*.diff, results/dry_run.json, REPORT.md}` and
`paper_workshop/agentverify2027/fragments/agentic_cf.md`. Key loaded from `~/.has_pilot.env` at
runtime; never printed or persisted.

## 8. Reproduce case metadata (no model call)

```bash
cd /REPOS_ROOT/kb-health/analysis/agentic_cf
python3 - <<'PY'
import subprocess, hashlib
for cid, repo, parent, fix, kb in [
 ("R4","R4","544ae6061549792de74e8ff89c5def91cb8888b1","70e71a62d7132d548ab079254d90028f1adec9bf","docs/AGENTS.md"),
 ("R5","R5","328f6da445ac176ddabc05c1ddd6563d5362598e","50a71b46e12bf9623b0667103fe225d51a24b5a9","CLAUDE.md"),
 ("R3","R3","b674155f2b941b64e0b4110c2c7450badb2c28aa","07635ed1a8fb97ea17fee4c728788b2e89bfc590","AGENTS.md")]:
    def show(r,p): return subprocess.run(["git","-C",f"/HOME/code/{repo}","show",f"{r}:{p}"],capture_output=True).stdout
    print(cid, hashlib.sha256(show(parent,kb)).hexdigest(), hashlib.sha256(show(fix,kb)).hexdigest())
PY
```
