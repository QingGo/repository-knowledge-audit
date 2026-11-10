# Real-repo coding counterfactual — REPORT

**Pilot:** 24 single `deepseek-chat` calls (3 repos × 4 arms × 2 seeds), no tool loop, no LLM
judge. **Actual spend: ¥0.122517** (cap ¥3.0; stop threshold ¥2.7 was never reached); prompt/
completion tokens: **65,200 / 25,901**. API key loaded from the approved local env file and never
printed or stored.

**Pre-registration:** [`tasks.json`](tasks.json) was written before any API call; strict grading was
`git apply --check` + `git apply`. After seeing that several otherwise-correct diffs failed only on
diff *formatting* (missing repeated `diff --git` headers / wrong hunk line counts), I re-graded the
**same stored 24 diffs with no new model calls** using a deterministic repair
(`normalize_patch` + `git apply --recount`). Both views are reported below; the strict view is the
pre-registered primary, the repaired view is a sensitivity analysis and is **not** presented as a
clean pre-registered win.

## Repos and exact hidden checks

| case | repo | parent SHA | fix SHA | hidden check (deterministic; never in prompt) |
|---|---|---|---|---|
| R4 | R4 | `544ae6061549792de74e8ff89c5def91cb8888b1` | `70e71a62d7132d548ab079254d90028f1adec9bf` | XML-parse `docs/layouts/_partials/layouts/icons.html`; require `<symbol id="icon--terminal" viewBox=…>` with a nonempty `<path>`; pass only on the corrected path |
| R5 | R5 | `328f6da445ac176ddabc05c1ddd6563d5362598e` | `50a71b46e12bf9623b0667103fe225d51a24b5a9` | require `miniprogram/pages/stats/stats.{js,json,wxml,wxss}`; `miniprogram/app.json` `pages` contains `"pages/stats/stats"`; `node --check` on the JS; `Page(` present |
| R3 | R3 | `b674155f2b941b64e0b4110c2c7450badb2c28aa` | `07635ed1a8fb97ea17fee4c728788b2e89bfc590` | find a `.py` under `.agents/skills/short-term-memory/`; execute `--session-id s1 --output tmp.md`; require a `Gotchas & Context` section and a bullet containing `s1` |

Repo-test regression gates (run after a patch applies, recorded separately, never folded into the
hidden pass): R4 `go test ./common/hstrings -count=1`; wechat `npx jest
test/unit/cloud_function.test.js test/unit/track_event.test.js --runInBand`; engram `pytest
tests/unit/test_config.py tests/unit/test_hashing.py -q` (Python 3.13 + temp-only deps).

**Manipulation check.** Task prompts name no correct path/location. `no_kb` has no KB block; stale
and corrected arms receive the same KB file from the parent/fix commit and differ only in the
reference fact (R4: `layouts/_partials/icons.html` vs `layouts/_partials/layouts/icons.html`;
wechat: root `pages/` vs `miniprogram/`; engram: skill `memory-update` vs `short-term-memory`).
`stale_plus_report` adds the deterministic replay drift report. Existing-file content supplied to
R4/wechat is content only (filename/path withheld).

## Results — hidden-check passes (primary)

Cells are `passes/n`; `strict` is the pre-registered `git apply`; `repaired` is the deterministic
format-repair sensitivity.

| case | no_kb strict / repaired | stale_kb strict / repaired | corrected_kb strict / repaired | stale+report strict / repaired |
|---|---:|---:|---:|---:|
| R4 | 0/2 / 0/2 | 0/2 / 0/2 | **2/2 / 2/2** | 0/2 / 0/2 |
| R5 | 0/2 / 0/2 | 0/2 / 0/2 | 0/2 / **2/2** | 0/2 / 0/2 |
| R3 | 0/2 / 0/2 | 0/2 / 0/2 | 0/2 / **2/2** | 0/2 / 0/2 |
| **all** | **0/6 / 0/6** | **0/6 / 0/6** | **2/6 / 6/6** | **0/6 / 0/6** |

- **Strict (pre-registered):** corrected 2/6, all controls 0/18; Fisher exact 2/6 vs 0/18
  **p=0.0543** (not significant; n is tiny).
- **Format-repaired sensitivity:** corrected 6/6, all controls 0/18; Fisher exact 6/6 vs 0/18
  **p=7.43×10⁻⁶**; corrected vs each control arm 6/6 vs 0/6 gives **p=0.00216**. These are exact
  counts; no bootstrap, no independence claim (2 seeds per cell, 3 engineered cases).
- **Diff applies:** strict 2/24; repaired 10/24. **Repo-test subset passes:** strict 2/24; repaired
  10/24 (corrected 6/6; engram no_kb 2/2 and engram stale+report 2/2 pass only because the patch was
  written outside the real package tree and did not break the repo; those are not hidden passes).
- **No dual-path recovery:** no model wrote both the stale and the corrected path. The corrected
  cells wrote only the correct path; stale/no/report cells wrote only wrong locations. R3
  `stale+report` created the stale `.agents/skills/memory-update/` directory (flagged as a stale-dir
  recovery, not a correct path).

## Per-case evidence and failure modes

- **R4:** corrected patch modified exactly `docs/layouts/_partials/layouts/icons.html` and passed
  XML/symbol/viewBox/path checks; stale and no-KB patches targeted
  `docs/layouts/_partials/icons.html` / `docs/layouts/partials/icon-sprite.html`
  / `docs/data/icons.svg`, so they did not apply (nonexistent target). This is the cleanest
  path-load-bearing case because the corrected KB contains the rest of the path.
- **wechat:** corrected patch wrote exactly `miniprogram/app.json` plus
  `miniprogram/pages/stats/stats.{js,json,wxml,wxss}`; route registered, `node --check` and `Page(`
  checks pass. Stale/no/report wrote root `app.json` + root `pages/stats/…`, so the diff did not
  apply and the mini-program path was never loaded. The corrected diffs required the mechanical
  `diff --git` header repair (strict apply 0/2, repaired 2/2); this is a format artifact, not a
  content correction.
- **engram:** corrected patch wrote
  `.agents/skills/short-term-memory/scripts/append_gotcha.py`; execution rc=0, section and `s1`
  bullet present. no-KB wrote `skills/agent-memory-update/...` (outside `.agents`); stale and
  stale+report wrote `.agents/skills/memory-update/...`; hidden check finds no script under the
  corrected skill. The corrected diffs needed `--recount` (strict apply 0/2; repaired 2/2), again a
  format artifact.

## Is the effect concentrated in load-bearing cases?

**Yes in this pilot.** Every corrected-KB cell (all 3 cases × 2 seeds) passes the hidden check after
format repair; every stale-KB, no-KB, and stale-plus-report cell fails. The manipulated fact is the
only location source and directly determines the hidden path. The drift report does **not** rescue
the stale arm (0/6): the model still follows the stale KB line, so a deterministic “this path is
broken” report is not a substitute for correcting the reference. No-KB guesses also fail (0/6).

This is consistent with the intended mechanism — stale KBs are harmful precisely when a task needs
the referenced path/target — but it is **not** evidence that stale KBs generally harm coding agents.
The tasks were deliberately designed so the KB reference is load-bearing; the model had no tools
and no repository inventory; n=2 seeds/cell; the cases are not a random sample.

## Honest limits / what would be needed

- **Pre-registered strict result is weak** (2/6 vs 0/18, p=0.054). The 6/6 “win” depends on a
  post-hoc mechanical format repair; report the strict result, not only the repaired one.
- Single call, no tool loop, no repo inspection; this measures path retrieval/instruction following
  at a very small scale, not full coding ability. The context block helps R4/wechat but does not
  reveal paths.
- The hidden checks are path-sensitive and were designed by the pilot author; they are deterministic
  and executable, but “pass” means the required artifact exists/behaves, not that the surrounding
  code is idiomatic or complete.
- No bootstrap (per instruction); Fisher p-values are reported only as descriptive exact counts and
  ignore clustering by case/repo.
- To make a publication-grade claim: more repos/cases sampled independently of the stale-reference
  property, more seeds, model tool access, code-level tests beyond path/CLI checks, and a
  pre-registered format-repair policy.

## Artifacts

- [`results/raw_strict.jsonl`](results/raw_strict.jsonl) — pre-registered strict grading (24 rows).
- [`results/raw.jsonl`](results/raw.jsonl) — deterministic format-repair re-grade (24 rows; no new
  model calls).
- [`results/summary.json`](results/summary.json) — aggregate counts/cost.
- [`tasks.json`](tasks.json), [`coding_cf.py`](coding_cf.py), [`run_cf.py`](run_cf.py),
  [`DESIGN.md`](DESIGN.md), [`FEASIBILITY.md`](FEASIBILITY.md).
