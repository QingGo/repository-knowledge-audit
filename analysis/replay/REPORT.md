# Real-repo replay pilot: repairing visible KB reference drift

**One-paragraph paper-ready result (anonymized repos R1–R5).** 
We replayed five real documentation-consistency fixes from five private repositories (R1–R5) at the commit before the fix, giving a model only the stale KB file (arm A), the stale KB plus a deterministic drift report (arm B), or no KB text (arm C), with a single model call and no tool loop (inventory supplied). Exact repair of the visible stale references succeeded in 9/10 (90%), 10/10 (100%), and 1/10 (10%) of runs for arms A/B/C respectively; the fix-commit KB itself scores 5/5 under the same checker (oracle, not deployable). A cheap deterministic report added a small, non-negative repair gain on visible drift (9/10 to 10/10 runs; the single gain was the largest-drift case), while the stale-only arm already repaired almost every reference, consistent with visible drift being largely self-recoverable from an inventory when the task is framed. In an exploratory hint control (same KB and inventory but no stale/repair instruction), success was 5/10, isolating instruction-driven from inventory-driven repair: roughly half of the stale-only success depends on being told that staleness is possible. We read this as weak support for lint-assisted repair as a marginal aid on visible drift, not as evidence that stale KBs are harmful for this maintenance task; hidden-convention harm remains untested. All arms are graded by deterministic path/target resolution, not an LLM judge; the outcome is a documentation-maintenance outcome, not a coding outcome, and no claim is made about hidden-convention harm.

## Setup

- Cases: 5 (parent commit vs. the docs-fix commit authored by us; KB path in `cases.json`). All five commits were usable; no cases were dropped.
- Arms: `stale_only` (parent KB), `stale_plus_report` (parent KB + deterministic drift report), `no_kb` (inventory only; writes KB from scratch); `stale_no_hint` is an exploratory 4th control, not a main arm.
- 2 prompt-variant seeds per arm/case; single model call per run; `steps=1`; no tool loop.
- Model: `deepseek-chat`; temperature 0.2/0.3; max_tokens 8000.
- Runs completed: 40 = 30 main (5 cases x 3 arms x 2 seeds) + 10 exploratory hint-control; tokens 327933; cost ¥0.4635 (cap ¥3.0).
- Controls (before API): PASS — parent stale KB must fail, fix-commit KB must pass, truncated KB must fail preservation.
- Grading: all curated gold stale reference units removed; no newly introduced unresolved path/make-target; preservation (A/B: ≥50% parent chars + anchors; C: ≥40% gold-fix chars + anchors). No LLM judge.

## Results by arm (deterministic grading)

| arm | n | success | success rate | refs fixed (mean frac) | new unresolved (mean) | chars vs parent (mean) | tokens/run | ¥/run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stale_only | 10 | 9 | 90% | 1.00 | 0.10 | 1.14 | 9046 | ¥0.0140 |
| stale_plus_report | 10 | 10 | 100% | 1.00 | 0.00 | 1.00 | 9333 | ¥0.0107 |
| no_kb | 10 | 1 | 10% | 1.00 | 0.60 | 0.86 | 5234 | ¥0.0071 |

**Exploratory hint control (`stale_no_hint`, not a main arm):** same parent KB + inventory as `stale_only`, but the stale/repair hint sentences are removed (task only says keep the KB accurate and useful, and the KB block is labelled neutrally). Result: 5/10 (50%) vs `stale_only` 9/10; mean refs-fixed frac 0.60, mean new unresolved 0.10. This separates hint-driven repair from inventory-driven self-recovery.

Per-case success (A/B/C; D = exploratory hint control):

| case | family | KB | stale units | A | B | C | D | oracle (fix KB) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| R1 | config/agent-docs drift (removed Path B + local-only setup) | `AGENTS.md` | 22 | 2/2 | 2/2 | 0/2 | 1/2 | PASS |
| R2 | removed make target + volatile test count | `AGENTS.md` | 1 | 2/2 | 2/2 | 1/2 | 1/2 | PASS |
| R3 | renamed skill + stale doc path | `AGENTS.md` | 2 | 2/2 | 2/2 | 0/2 | 2/2 | PASS |
| R4 | moved partial path | `docs/AGENTS.md` | 1 | 2/2 | 2/2 | 0/2 | 1/2 | PASS |
| R5 | restructured project layout (subpackage/cloud-function loss) | `CLAUDE.md` | 3 | 1/2 | 2/2 | 0/2 | 0/2 | PASS |

## What this does and does not show

**Supports (weak/marginal):** visible reference drift can be repaired from an inventory at near-zero cost; a deterministic drift report adds a small non-negative repair gain under a single-call, no-tool setting (9/10 -> 10/10), and the no-KB arm (1/10) shows the KB text/inventory context is doing real work.

**Does not support:** a strong positive bridge for lint-assisted repair (one additional case out of ten), or a claim that stale KBs are harmful for documentation-maintenance tasks (stale-only already repairs 90% when framed); the hint control (5/10) shows much of the recovery is instruction-driven.

**Does not support / limitations:**
- Outcome is **documentation maintenance**, not coding outcome; no task completion or KB-use effect is measured.
- Only **visible reference drift** (paths/targets/skill names) is graded; hidden convention staleness is out of scope.
- **Single model** (`deepseek-chat`), single call, temperature 0.2/0.3; seeds are prompt variants, not independent samples.
- **No tool loop**: models see a deterministic inventory + (B) report, not the repository; this tests edit-from-evidence, not agentic exploration.
- Five **private repos**, anonymized (R1–R5); fix commits were authored by us, so gold repair style is ours.
- Grading is curated token resolution (paths/make targets) with lenient suffix resolution; it can miss semantic staleness and can reward deleting content. Preservation thresholds mitigate but do not eliminate deletion.
- No LLM judge; no claim about hidden-convention harm or general KB quality.
- The fix-commit KB oracle is an upper bound, not a deployable method.

## Files

- `cases.json` / `replay_cases.json`: cases, commits, curated stale units/anchors, drift report.
- `run_replay.py`: checker, controls, prompts, API runner, summary.
- `results/controls.json`, `results/replay.jsonl`, `results/summary.json`, `results/raw/<case>/`.
