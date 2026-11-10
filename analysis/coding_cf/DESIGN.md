# Coding counterfactual — design and pre-registration

**Status:** Phase 2 pre-registered in [`tasks.json`](tasks.json) before any model call; runner
[`coding_cf.py`](coding_cf.py) is deterministic and resume-safe. Results go to `results/` and
[`REPORT.md`](REPORT.md).

## Question

Does a stale agent KB reference change a real repository code change when the reference is
load-bearing for the task, and does a corrected KB reduce the error? Primary outcome:
deterministic hidden-check pass. Secondary: diff applies, changed files, repo-test subset pass,
tokens/cost. No LLM judge, no bootstrap (exact counts; Fisher where meaningful).

## Cases (parent commit is identical across arms; only the KB text differs)

| case | repo: parent → fix | KB | stale fact | corrected fact | hidden check |
|---|---|---|---|---|---|
| R4 | R4 `544ae606…` → `70e71a62…` | `docs/AGENTS.md` | `layouts/_partials/icons.html` | `layouts/_partials/layouts/icons.html` | symbol `icon--terminal` in `docs/layouts/_partials/layouts/icons.html`, `viewBox` + nonempty path |
| R5 | R5 `328f6da4…` → `50a71b46…` | `CLAUDE.md` | root `pages/`, `static/`, `user/`, `pay/` | `miniprogram/` root | four `miniprogram/pages/stats/stats.*` files; route in `miniprogram/app.json`; `node --check`; `Page(` |
| R3 | R3 `b674155f…` → `07635ed1…` | `AGENTS.md` | skill `memory-update` | skill `short-term-memory` | executable `.py` under `.agents/skills/short-term-memory/`; appends `Gotchas & Context` bullet for `--session-id s1` |

The task prompt never names the correct path/location. It contains only the task, an
existing-file content block where needed (content only, no filename/path), and the arm's KB text.
`no_kb` has no KB text; `stale_kb` uses the parent KB; `corrected_kb` the fix KB;
`stale_plus_report` adds the deterministic drift report from `analysis/replay/cases.json`. The
stale/corrected arms differ only in the reference fact. The no-KB arm contains no location text.

## Protocol

- 3 cases × 4 arms × 2 seeds (temperature 0.2/0.3) = **24 single calls**, `deepseek-chat`,
  `max_tokens=4000`, JSON output `{"diff": "..."}` (unified diff), no tool loop.
- Apply with `git apply --check` then `git apply` in a fresh `git archive` of the parent commit;
  hidden checks are deterministic and never in the prompt; the pre-declared repo-test subset runs
  separately (not folded into the hidden pass).
- Repo-test subsets: R4 `go test ./common/hstrings`; wechat `npx jest
  test/unit/cloud_function.test.js test/unit/track_event.test.js --runInBand`; engram `pytest
  tests/unit/test_config.py tests/unit/test_hashing.py -q` (explicit Python 3.13 + temp deps).
- Cost: cap ¥3.0 total, stop issuing at ¥2.7; usage/cost logged per run (API key never logged).
- A cell is `hidden_pass` only if the patch applies and the hidden check passes; if the model writes
  both stale and correct paths, the cell still passes but is flagged as dual-path/trivially
  recoverable in the report.
- Honest null: if all arms pass, report a null; no case is tuned to force a difference.

## Why this is a real coding counterfactual

The parent/fix commits are docs-only for these repositories; the code tree is the same in every
arm. The manipulated fact is the KB's location/reference statement, and the task requires a real
file/code change at that location (not a doc-repair checker). The hidden checks are directly
variable on the stale/corrected fact and are executable.

## Known limits

- Single call, no tools: the model cannot inspect the repository; for R4/wechat the existing-file
  content is supplied without a path, for engram the skill directory convention is not stated
  beyond the KB skill name (intentional: only the KB carries location). A model that guesses the
  stale path is being measured, not a full coding agent.
- Path following is a narrow slice of coding ability; a null would not prove stale KBs are harmless.
- The API key is loaded at runtime from `~/.has_pilot.env` via `probe_screen.run_probes.load_env`;
  it is never printed or stored in results.
