# Real-repo coding counterfactual — Phase 1 feasibility

**Status:** Phase 1 complete. **Task design/testability: GO for 3 cases. Phase-2 execution is
blocked in this environment: `DEEPSEEK_API_KEY` is unset (no chat-model access), so no model calls
were made and none can be made until the Lead provides a key or an approved alternative.**
No repository was modified: all probes used `git archive <parent-commit>` into `/tmp/cf-phase1/`;
test-only dependency installs live under `/tmp`.

## 1. Why these 3 repos/tasks

The five replay cases differ only in **documentation drift**; the code trees are otherwise the
docs-fix commits' parent trees. A defensible coding counterfactual must make the KB's
path/target name **load-bearing for a code change** and grade the resulting repository with
executable checks. Three cases meet that bar; each condition changes only the KB text supplied to
the model, not the repo commit:

| case | repo / commits | stale KB line (parent) | corrected KB line (fix) | actual parent-tree path |
|---|---|---|---|---|
| R4 | R4 `544ae606…` → `70e71a62…`; `docs/AGENTS.md` | `layouts/_partials/icons.html` | `layouts/_partials/layouts/icons.html` | `docs/layouts/_partials/layouts/icons.html` |
| R5 | R5 `328f6da4…` → `50a71b46…`; `CLAUDE.md` | root `pages/`, `static/`, `user/`, `pay/` | `miniprogram/` root, single package | `miniprogram/app.json`, `miniprogram/pages/*` |
| R3 | R3 `b674155f…` → `07635ed1…`; `AGENTS.md` | skill `memory-update`; `docs/performance.md` | skill `short-term-memory`; `docs/paper_alignment.md` | `.agents/skills/short-term-memory/SKILL.md` |

## 2. Runnable test subsets (executed locally)

| repo | command (temp parent tree) | result | notes |
|---|---|---|---|
| R4 | `go test ./common/hstrings -count=1` | **PASS** `ok … 0.564s` | Go 1.25.6; modules downloaded; no repo writes |
| R5 | `npm ci --ignore-scripts` then `npx jest test/unit/cloud_function.test.js` | **PASS** 2/2 tests | Node v24.8; 1,528 packages installed in temp only |
| R5 | `npx jest test/unit/track_event.test.js` | **PASS** 8/8 tests | same install; no repo edits |
| R3 | `pytest tests/unit/test_config.py tests/unit/test_hashing.py -q` | **PASS** 13 passed in 9.38s | temp-only deps: `peft accelerate trl jaxtyping typeguard` + newer `typing_extensions`; Python 3.13.2 + torch 2.9.0 |
| R2 | `pytest tests/test_quantization.py -q` | **3 skipped** | `tests/conftest.py` skips everything without CUDA; not usable as a repo-test arm |
| R1 | — | not probed | Python 3.10 + MLIR/Rust/C++ build chain; too heavy/outside the phase-1 budget |

The passing subsets above are the **repo-test arm** for Phase 2. They are deliberately narrow and
fast (<15 s each after setup); they are health checks, not the task-specific grader.

## 3. Candidate tasks (3; same task text across all KB arms)

**T-C4 (R4).** *Task:* "Add a `terminal` icon symbol to the documentation site's SVG icon sprite
(`<symbol id="icon--terminal" viewBox="0 0 20 20">` with a valid path)." The only source of the
sprite's location is `docs/AGENTS.md`; stale points at `docs/layouts/_partials/icons.html`
(nonexistent), corrected at `docs/layouts/_partials/layouts/icons.html` (the real file).
*Hidden executable checks:* XML-parse the corrected path, assert `<symbol id="icon--terminal">` and
a nonempty `<path>`; fail if only the stale path is edited. *Why instrumental:* a model that trusts
the stale KB writes the patch to a path that does not exist in the repo.

**T-C5 (R5).** *Task:* "Add a `stats` page to the mini-program and register it in the
app configuration." `CLAUDE.md` is the only structure source: stale says root `pages/` and root
`app.json`; corrected says the mini-program root is `miniprogram/` with `miniprogram/app.json`.
*Hidden executable checks:* require `miniprogram/pages/stats/{stats.js,stats.json,stats.wxml,stats.wxss}`,
`miniprogram/app.json` `pages` contains `"pages/stats/stats"`, and `node --check` passes for the JS
(and `Page(` present). *Why instrumental:* stale placement produces `pages/stats/…` at repo root,
which the mini-program never loads.

**T-C3 (R3).** *Task:* "Add a deterministic short-term-memory helper at
`scripts/update_memory.py` inside the skill directory that `AGENTS.md` names for memory updates; it
must append a `Gotchas & Context` bullet for `--session-id` to `--output`." Stale names the skill
`memory-update`; corrected names `short-term-memory`; the real directory is
`.agents/skills/short-term-memory/`.
*Hidden executable checks:* require `.agents/skills/short-term-memory/scripts/update_memory.py`,
execute it on a temp markdown output with `--session-id s1 --output tmp.md`, and assert the
`## Gotchas & Context` section/bullet exists; fail if the stale `memory-update` directory is used.
*Why instrumental:* skill-directory placement is the only answer the KB supplies.

## 4. Phase-2 design (only after Lead go)

- **Arms:** `no_kb`, `stale_kb` (parent `AGENTS.md`/`CLAUDE.md`), `corrected_kb` (fix-commit KB),
  `stale_plus_report` (stale KB + the deterministic drift report from `replay/cases.json`).
- **Repo:** parent-commit `git archive` for all arms; corrected KB is the fix-commit file. The fixes
  are docs-only, so code content is identical across arms by construction.
- **Model protocol:** one `deepseek-chat` call per (case, arm, seed); no tool loop. Prompt contains
  only the task text + the arm's KB text (+ drift report); model returns a unified diff. Seeds 0/1,
  2 seeds; 3 repos × 4 arms × 2 seeds = **24 calls**. No hidden checks in the prompt.
- **Apply/grade:** `git apply` into a fresh temp copy; hidden checks above; then the repo-test subset
  from §2; record `patch_applies`, `hidden_pass`, `repo_test_pass`, `changed_files`. Invalid/extra
  paths fail the "allowed files" check.
- **Budget:** cap **3.0 CNY** total; log prompt/completion tokens + estimated cost; if the cap would
  be exceeded, stop and report the partial run (no silent overspend). API key currently missing.
- **Deliverables:** `tasks.json` (SHAs, stale/corrected texts, hidden-check IDs), `run_cf.py`
  (deterministic, rerunnable), `results/`, `REPORT.md` with per-cell table, exact counts, Fisher/
  bootstrap where meaningful, and an honest null if that is what happens.

## 5. Go/no-go

- **Design + local testability: GO** — three independent repos, three path-load-bearing tasks, each
  with a passing repo-test subset and a deterministic hidden executable check; zero repo writes.
- **Execution now: NO-GO** — `DEEPSEEK_API_KEY` (and alternative provider keys) are **unset**; no
  chat-model call can be made, and a fabricated/simulated model run would violate the task. The
  Lead must either provide the key (and approve the ≤3.0 CNY cap) or accept a no-go/DESIGN-only
  outcome. No model spend has occurred.
- **Scope exclusions:** R2's pytest suite is CUDA-gated on this host (all skipped),
  CompileForge needs Python 3.10 + MLIR/Rust/C++ builds — both would make the repo-test arm
  non-informative or too expensive for the cap. The replay cases' KBs are otherwise docs-only, which
  is why only the three path-load-bearing tasks above are defensible.

## 6. Local evidence / non-interference

- Parent trees: `/tmp/cf-phase1/{R4,R5,R3,...}` from `git archive`; repos
  under `/HOME/code/` were never edited/checkpointed/reset.
- Test dependency installs: `/tmp` only (npm `node_modules` in the temp copy; Python `--target`
  directories in `/tmp`).
- The `run_replay.py` prompt/grader conventions (single-turn, no tool loop, deterministic checks,
  exact counts) were read and will be reused where applicable.
