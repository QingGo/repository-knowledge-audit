#!/usr/bin/env python3
"""Pre-registered source-of-truth precedence experiment (chat, 54 tasks).

Pre-registration: `PREREG.md` in this directory (sha256 in `results/freeze.json`),
frozen before any API call. Reuses the existing benchmark without editing it:

  kb-health/outcome_bench/run_bench.py    prompt_for(), run_tests(), parse_code()
  kb-health/outcome_bench/conventions.py  TASKS (54 tasks)
  kb-health/probe_screen/run_probes.py    load_env(), chat(), parse_json(), usage_cost()

Five new arms, each one fixed paragraph inserted verbatim after the note bullet block
(before the seed-variant sentence and any visible-test block):
  p2  = stale note   + precedence rule
  p1  = correct note + precedence rule
  p2f = stale note   + precedence rule + full visible suite
  w2f = stale note   + generic warning  + full visible suite
  p1f = correct note + precedence rule + full visible suite
Controls c1/c2/c2f are the frozen snapshot of the existing 54-task chat run
(results/controls_used.jsonl); this experiment adds 540 completions (cap RMB 3.0).

Usage (from kb-health/):
  python3 analysis/precedence/run_precedence.py --dry-run
  python3 analysis/precedence/run_precedence.py --run --ack-prereg
  python3 analysis/precedence/run_precedence.py --analyze

Writes only under analysis/precedence/ (plus the fragment written separately).
The API key is loaded via run_probes.load_env and never printed or stored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
KB_HEALTH = HERE.parents[1]  # analysis/precedence -> kb-health
OUTCOME = KB_HEALTH / "outcome_bench"
PROBE = KB_HEALTH / "probe_screen"
for p in (str(OUTCOME), str(PROBE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_bench  # noqa: E402  (never edited)
from run_probes import load_env, chat, parse_json, usage_cost  # noqa: E402
from conventions import TASKS  # noqa: E402

RESULTS = HERE / "results"
PREREG = HERE / "PREREG.md"
FREEZE = RESULTS / "freeze.json"
ROWS = RESULTS / "precedence_chat.jsonl"
PROMPTS = RESULTS / "precedence_prompts.jsonl"
CONTROLS = RESULTS / "controls_used.jsonl"
SUMMARY = RESULTS / "summary.json"
TASK_TABLE = RESULTS / "task_table.tsv"
COST_LOG = RESULTS / "cost_log.json"
DRY_RUN = RESULTS / "dry_run.json"

RULE = ("When repository knowledge conflicts with independently observable evidence "
        "(the task requirements, visible tests, or the project's own code and manifests), "
        "do not follow the knowledge entry. Use the authoritative project source of truth "
        "and report the conflict. If no conflict is detectable, proceed normally.")
WARN = ("Note: KB entries may be stale or wrong; verify claims against the code and tests "
        "when possible.")

ARMS = {
    "p2":  {"base": "c2",  "kind": "rule"},
    "p1":  {"base": "c1",  "kind": "rule"},
    "p2f": {"base": "c2f", "kind": "rule"},
    "w2f": {"base": "c2f", "kind": "warn"},
    "p1f": {"base": "c1f", "kind": "rule"},
}
ARM_ORDER = ["p2", "p1", "p2f", "w2f", "p1f"]
CONTROL_CONDS = ["c1", "c2", "c2f"]
SEEDS = (0, 1)
TEMPERATURE = 0.3            # matches the existing control run (run_bench.one hardcodes 0.3)
MAX_TOKENS = 2400
COST_CAP_CNY = 3.0
COST_STOP_CNY = 2.7
BOOT_N = 1000
BOOT_SEED = 20261109
EXPECTED_CELLS = len(TASKS) * len(ARMS) * len(SEEDS)  # 540


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inserted_text(kind: str) -> str:
    return RULE if kind == "rule" else WARN


def note_facts(task: dict, base_cond: str) -> list[str]:
    return task["useful"] if base_cond in ("c1", "c1f") else task["stale"]


def make_prompt(task: dict, arm: str, seed: int) -> dict:
    """Build the arm prompt: run_bench prompt_for() with one paragraph inserted after the note."""
    base_cond = ARMS[arm]["base"]
    base_text = run_bench.prompt_for(task, base_cond, seed)[0]["content"]
    block = "\n".join("- " + f for f in note_facts(task, base_cond))
    if base_text.count(block) != 1:
        raise AssertionError(f"note block not found exactly once: {task['tid']}/{arm}/{seed}")
    extra = inserted_text(ARMS[arm]["kind"])
    insertion = "\n\n" + extra
    text = base_text.replace(block, block + insertion, 1)
    # integrity: removing the inserted paragraph reproduces the base prompt byte-for-byte
    if text.replace(insertion, "", 1) != base_text:
        raise AssertionError(f"insertion is not removable: {task['tid']}/{arm}/{seed}")
    return {
        "tid": task["tid"], "family": task["family"], "arm": arm, "base_cond": base_cond,
        "seed": seed, "kind": ARMS[arm]["kind"], "inserted": extra,
        "base_prompt_sha256": sha256_text(base_text),
        "prompt_sha256": sha256_text(text), "prompt": text,
    }


def cell_order() -> list[tuple[dict, str, int]]:
    return [(t, a, s) for t in TASKS for a in ARM_ORDER for s in SEEDS]


def prereg_gate(api_call: bool, ack: bool) -> dict:
    if not PREREG.exists() or not FREEZE.exists():
        raise SystemExit("PREREG.md / results/freeze.json missing: freeze before any API call")
    frozen = json.loads(FREEZE.read_text())
    cur = sha256_file(PREREG)
    if frozen.get("prereg_sha256") != cur:
        raise SystemExit("PREREG.md hash does not match the frozen fingerprint")
    if not CONTROLS.exists() or sha256_file(CONTROLS) != frozen.get("controls_snapshot_sha256"):
        raise SystemExit("frozen control snapshot missing or changed")
    if api_call and not ack:
        raise SystemExit("refusing API calls without --ack-prereg (PREREG must be frozen)")
    return frozen


def done_keys() -> set[tuple[str, str, int]]:
    out: set[tuple[str, str, int]] = set()
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                out.add((r["tid"], r["arm"], int(r["seed"])))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return out


def spent_so_far() -> float:
    total = 0.0
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                total += float(json.loads(line).get("cost_cny") or 0.0)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return total


def load_controls() -> list[dict]:
    rows = []
    for line in CONTROLS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_one(env: dict, task: dict, arm: str, seed: int, model: str) -> dict:
    spec = make_prompt(task, arm, seed)
    messages = [{"role": "user", "content": spec["prompt"]}]
    t0 = time.time()
    try:
        resp = chat(env, messages, model, TEMPERATURE, MAX_TOKENS)
    except Exception as exc:  # noqa: BLE001 - recorded, not hidden
        return {
            "tid": task["tid"], "family": task["family"], "arm": arm,
            "base_cond": spec["base_cond"], "seed": seed, "temperature": TEMPERATURE,
            "pass": False, "error": f"api: {type(exc).__name__}: {exc}"[:300],
            "tokens": {}, "cost_cny": 0.0, "latency_s": round(time.time() - t0, 2),
            "code_len": 0, "prompt_sha256": spec["prompt_sha256"],
            "base_prompt_sha256": spec["base_prompt_sha256"],
            "inserted_kind": spec["kind"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    raw = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    code = run_bench.parse_code(parse_json(raw), raw)
    ok, out = run_bench.run_tests(code, task["tests"]) if code.strip() else (False, "no code")
    usage = resp.get("usage") or {}
    return {
        "tid": task["tid"], "family": task["family"], "arm": arm,
        "base_cond": spec["base_cond"], "seed": seed, "temperature": TEMPERATURE,
        "pass": bool(ok), "code_len": len(code), "output": (out or "")[-400:],
        "model": model,
        "tokens": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
            "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
        },
        "cost_cny": usage_cost(usage), "latency_s": round(time.time() - t0, 2),
        "prompt_sha256": spec["prompt_sha256"],
        "base_prompt_sha256": spec["base_prompt_sha256"],
        "inserted_kind": spec["kind"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# ---------------------------------------------------------------------------
# dry-run / ping / run
# ---------------------------------------------------------------------------
def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def do_dry_run() -> int:
    frozen = prereg_gate(api_call=False, ack=False)
    prompts = []
    errors: list[str] = []
    # prompt integrity checks
    base_texts = {}
    for task, arm, seed in cell_order():
        spec = make_prompt(task, arm, seed)
        prompts.append({"tid": spec["tid"], "arm": arm, "seed": seed,
                        "base_cond": spec["base_cond"], "kind": spec["kind"],
                        "prompt_sha256": spec["prompt_sha256"], "prompt": spec["prompt"]})
        text = spec["prompt"]
        base = run_bench.prompt_for(task, spec["base_cond"], seed)[0]["content"]
        base_texts[(task["tid"], arm, seed)] = base
        if text.count(spec["inserted"]) != 1:
            errors.append(f"insertion count != 1: {task['tid']}/{arm}/{seed}")
        if text.replace("\n\n" + spec["inserted"], "", 1) != base:
            errors.append(f"diff-only check failed: {task['tid']}/{arm}/{seed}")
        if not text.startswith(base[: base.index("\n\n")]):
            errors.append(f"prompt prefix changed: {task['tid']}/{arm}/{seed}")
    # cross-arm: p2/p1/p2f/p1f vs their base; w2f vs c2f; headers unchanged by construction
    for task in TASKS:
        for seed in SEEDS:
            for arm in ("p2", "p1", "p2f", "p1f"):
                a = base_texts[(task["tid"], arm, seed)]
                b = run_bench.prompt_for(task, ARMS[arm]["base"], seed)[0]["content"]
                if a != b:
                    errors.append(f"base prompt changed: {task['tid']}/{arm}/{seed}")
            # note body appears identically in arm and base (already implied by diff-only)
    # frozen controls integrity
    controls = load_controls()
    if len(controls) != len(CONTROL_CONDS) * len(TASKS) * 2:
        errors.append(f"control rows {len(controls)} != {len(CONTROL_CONDS) * len(TASKS) * 2}")
    ctrl_map = {(r["tid"], r["cond"], int(r["seed"])) for r in controls}
    for task in TASKS:
        for cond in CONTROL_CONDS:
            for seed in SEEDS:
                if (task["tid"], cond, seed) not in ctrl_map:
                    errors.append(f"missing control cell: {task['tid']}/{cond}/{seed}")
    if sha256_file(CONTROLS) != frozen["controls_snapshot_sha256"]:
        errors.append("control snapshot hash mismatch")
    # grading sanity: empty code must fail every task (uses the real hidden grader)
    empty_fail = 0
    for task in TASKS:
        ok, _ = run_bench.run_tests("", task["tests"])
        if ok:
            errors.append(f"grading sanity failed (empty code passes): {task['tid']}")
        else:
            empty_fail += 1
    write_jsonl(PROMPTS, prompts)
    report = {
        "mode": "dry-run",
        "frozen": frozen,
        "n_prompts": len(prompts),
        "expected_cells": EXPECTED_CELLS,
        "arms": ARM_ORDER,
        "seeds": list(SEEDS),
        "temperature": TEMPERATURE,
        "insertion_checks": len(prompts),
        "grading_empty_code_fails": empty_fail,
        "n_free_text_prompt_errors": len(errors),
        "errors": errors[:50],
    }
    DRY_RUN.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"}, indent=1))
    if errors:
        print(f"DRY-RUN FAILED: {len(errors)} errors", file=sys.stderr)
        for e in errors[:20]:
            print("  -", e, file=sys.stderr)
        return 1
    print(f"DRY-RUN OK: {len(prompts)} prompts, diff-only checks {len(prompts)}/{len(prompts)}, "
          f"grading sanity {empty_fail}/{len(TASKS)}")
    return 0


def do_ping(env: dict, model: str) -> int:
    frozen = prereg_gate(api_call=True, ack=True)
    try:
        resp = chat(env, [{"role": "user",
                           "content": 'Reply with exactly this JSON: {"ok": true}'}],
                    model, 0.0, 16)
    except Exception as exc:  # noqa: BLE001
        print(f"PING FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    usage = resp.get("usage") or {}
    out = {"mode": "ping", "model": model, "ok": True,
           "usage": usage, "cost_cny": usage_cost(usage),
           "prereg_sha256": frozen["prereg_sha256"],
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "note": "connectivity check only; not one of the 540 cells"}
    (RESULTS / "ping.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"PING OK model={model} cost=¥{out['cost_cny']:.6f}")
    return 0


def do_run(env: dict, model: str, workers: int) -> int:
    frozen = prereg_gate(api_call=True, ack=True)
    done = done_keys()
    spent = spent_so_far()
    todo = [c for c in cell_order() if (c[0]["tid"], c[1], c[2]) not in done]
    print(f"[run] cells={EXPECTED_CELLS} done={len(done)} todo={len(todo)} "
          f"spent=¥{spent:.4f}", file=sys.stderr)
    if not todo:
        print("[run] nothing to do", file=sys.stderr)
        return 0
    chunk = max(1, workers * 2)
    with ROWS.open("a", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for start in range(0, len(todo), chunk):
                batch = todo[start:start + chunk]
                futs = [ex.submit(run_one, env, t, a, s, model) for t, a, s in batch]
                for fut in futs:
                    row = fut.result()
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
                    spent += row.get("cost_cny") or 0.0
                print(f"[run] {min(start + chunk, len(todo))}/{len(todo)} "
                      f"spent=¥{spent:.4f}", file=sys.stderr)
                if spent >= COST_STOP_CNY:
                    print(f"[run] STOP at ¥{spent:.4f} >= ¥{COST_STOP_CNY} "
                          f"(hard cap ¥{COST_CAP_CNY})", file=sys.stderr)
                    break
    rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    per_arm = {a: 0.0 for a in ARM_ORDER}
    for r in rows:
        per_arm[r["arm"]] = round(per_arm.get(r["arm"], 0.0) + (r.get("cost_cny") or 0.0), 6)
    cost_log = {
        "model": model, "cells_written": len(rows), "expected_cells": EXPECTED_CELLS,
        "cost_cny_total": round(sum(per_arm.values()), 6),
        "cost_cny_per_arm": per_arm, "cost_cap_cny": COST_CAP_CNY,
        "cost_stop_cny": COST_STOP_CNY, "cap_respected": sum(per_arm.values()) <= COST_CAP_CNY,
        "prereg_sha256": frozen["prereg_sha256"],
        "prereg_mtime": frozen["prereg_mtime"], "frozen_at": frozen["frozen_at"],
        "controls_snapshot_sha256": frozen["controls_snapshot_sha256"],
        "first_row_ts": rows[0]["ts"] if rows else None,
        "last_row_ts": rows[-1]["ts"] if rows else None,
    }
    COST_LOG.write_text(json.dumps(cost_log, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"[run] wrote {len(rows)} rows; cost=¥{cost_log['cost_cny_total']:.4f} "
          f"(cap ¥{COST_CAP_CNY})", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def sign_test(diffs: list[float], alternative: str) -> dict:
    """Exact paired sign test over non-tied task differences."""
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    n = pos + neg
    if n == 0:
        return {"pos": 0, "neg": 0, "n": 0, "p": 1.0, "p_one_sided": 1.0}
    def tail_ge(k: int) -> float:
        return sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    def tail_le(k: int) -> float:
        return sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    p_greater = tail_ge(pos)
    p_less = tail_le(pos)
    return {
        "pos": pos, "neg": neg, "n": n,
        "p_one_sided": p_greater if alternative == "greater" else p_less,
        "p_two_sided": min(1.0, 2 * min(p_greater, p_less)),
    }


def bootstrap_ci(vals: list[float], n: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    rng = random.Random(seed)
    m = len(vals)
    means = []
    for _ in range(n):
        s = 0.0
        for _ in range(m):
            s += vals[rng.randrange(m)]
        means.append(s / m)
    means.sort()
    return {
        "mean": statistics.fmean(vals),
        "ci95": [means[int(0.025 * n)], means[int(0.975 * n) - 1]],
        "n_boot": n, "seed": seed,
    }


def paired_contrast(task_diffs: dict[str, float], label: str, alternative: str = "two-sided") -> dict:
    vals = [task_diffs[t] for t in sorted(task_diffs)]
    boot = bootstrap_ci(vals)
    st = sign_test(vals, "greater" if alternative == "greater" else "less" if alternative == "less" else "two-sided")
    return {
        "label": label,
        "n_tasks": len(vals),
        "mean_pp": 100.0 * boot["mean"],
        "ci95_pp": [100.0 * boot["ci95"][0], 100.0 * boot["ci95"][1]],
        "bootstrap": boot,
        "sign_test": st,
        "sign_test_p_one_sided": st["p_one_sided"],
        "sign_test_p_two_sided": st["p_two_sided"],
        "improved": sum(1 for v in vals if v > 0),
        "worsened": sum(1 for v in vals if v < 0),
        "tied": sum(1 for v in vals if v == 0),
        "task_diffs": {t: task_diffs[t] for t in sorted(task_diffs)},
    }


def analyze() -> dict:
    frozen = prereg_gate(api_call=False, ack=False)
    new_rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    controls = load_controls()
    tids = [t["tid"] for t in TASKS]
    fam = {t["tid"]: t["family"] for t in TASKS}
    # maps
    new = {(r["tid"], r["arm"], int(r["seed"])): r for r in new_rows}
    ctrl = {(r["tid"], r["cond"], int(r["seed"])): r for r in controls}
    coverage = {a: sum(1 for t in tids for s in SEEDS if (t, a, s) in new) for a in ARM_ORDER}
    errors = [r for r in new_rows if r.get("error")]

    def mean_pass(source: str, key: str) -> float | None:
        """source: 'new' or 'ctrl'; key: arm or control cond."""
        vals = []
        for t in tids:
            cells = [new.get((t, key, s)) if source == "new" else ctrl.get((t, key, s))
                     for s in SEEDS]
            got = [c["pass"] for c in cells if c is not None]
            if len(got) != len(SEEDS):
                return None
            vals.append(statistics.fmean(got))
        return statistics.fmean(vals)

    def task_scores(source: str, key: str) -> dict[str, float]:
        out = {}
        for t in tids:
            vals = [(new if source == "new" else ctrl).get((t, key, s)) for s in SEEDS]
            got = [c["pass"] for c in vals if c is not None]
            if len(got) == len(SEEDS):
                out[t] = statistics.fmean(got)
        return out

    arm_rates = {}
    for a in ARM_ORDER:
        cells = [new[(t, a, s)] for t in tids for s in SEEDS if (t, a, s) in new]
        arm_rates[a] = {
            "n": len(cells), "pass": sum(1 for c in cells if c["pass"]),
            "pass_rate": (sum(1 for c in cells if c["pass"]) / len(cells)) if cells else None,
            "completion_tokens_mean": statistics.fmean(
                [(c.get("tokens") or {}).get("completion_tokens") or 0 for c in cells]
            ) if cells else None,
            "prompt_tokens_mean": statistics.fmean(
                [(c.get("tokens") or {}).get("prompt_tokens") or 0 for c in cells]
            ) if cells else None,
            "code_len_mean": statistics.fmean([c.get("code_len") or 0 for c in cells])
            if cells else None,
            "latency_s_mean": statistics.fmean([c.get("latency_s") or 0 for c in cells])
            if cells else None,
            "cost_cny": round(sum(c.get("cost_cny") or 0 for c in cells), 6),
            "by_seed": {str(s): {
                "n": sum(1 for t in tids if (t, a, s) in new),
                "pass": sum(1 for t in tids if (t, a, s) in new and new[(t, a, s)]["pass"]),
            } for s in SEEDS},
        }
    control_rates = {}
    for c in CONTROL_CONDS:
        cells = [ctrl[(t, c, s)] for t in tids for s in SEEDS if (t, c, s) in ctrl]
        control_rates[c] = {
            "n": len(cells), "pass": sum(1 for x in cells if x["pass"]),
            "pass_rate": (sum(1 for x in cells if x["pass"]) / len(cells)) if cells else None,
            "completion_tokens_mean": statistics.fmean(
                [(x.get("tokens") or 0) for x in cells]) if cells else None,
            "by_seed": {str(s): {
                "n": sum(1 for t in tids if (t, c, s) in ctrl),
                "pass": sum(1 for t in tids if (t, c, s) in ctrl and ctrl[(t, c, s)]["pass"]),
            } for s in SEEDS},
        }
    # per-task scores
    scores = {a: task_scores("new", a) for a in ARM_ORDER}
    for c in CONTROL_CONDS:
        scores[c] = task_scores("ctrl", c)
    # complete per-task coverage? (needed for decision rules)
    complete = all(len(scores[a]) == len(tids) for a in ARM_ORDER) and \
        all(len(scores[c]) == len(tids) for c in CONTROL_CONDS)
    contrasts = {}
    if complete:
        def diffs(x: str, y: str) -> dict[str, float]:
            return {t: scores[x][t] - scores[y][t] for t in tids}
        contrasts["H1_p2_minus_c2"] = paired_contrast(diffs("p2", "c2"),
                                                      "H1 primary: rule on stale note (p2 - c2)",
                                                      alternative="greater")
        contrasts["H2_p1_minus_c1"] = paired_contrast(diffs("p1", "c1"),
                                                      "H2 harm check: rule on correct note (p1 - c1)")
        contrasts["H3_did"] = paired_contrast(
            {t: (scores["p2"][t] - scores["c2"][t]) - (scores["p2f"][t] - scores["c2f"][t])
             for t in tids},
            "H3 exploratory: (p2-c2) - (p2f-c2f)")
        contrasts["H4_p2f_minus_w2f"] = paired_contrast(
            {t: scores["p2f"][t] - scores["w2f"][t] for t in tids},
            "H4 exploratory: rule vs warning under full suite (p2f - w2f)")
        contrasts["p2f_minus_c2f"] = paired_contrast(
            {t: scores["p2f"][t] - scores["c2f"][t] for t in tids},
            "secondary: rule + full suite vs full suite (p2f - c2f)")
        if "c1f" in scores:  # c1f is not part of the frozen control snapshot
            contrasts["p1f_minus_c1f"] = paired_contrast(
                {t: scores["p1f"][t] - scores["c1f"][t] for t in tids},
                "secondary: rule on correct note + full suite vs c1f")
    decisions = {}
    if "H1_p2_minus_c2" in contrasts:
        h1 = contrasts["H1_p2_minus_c2"]
        decisions["H1"] = {
            "supported": h1["sign_test_p_one_sided"] < 0.05,
            "rule": "one-sided exact sign test p < .05 (primary)",
            "p_one_sided": h1["sign_test_p_one_sided"],
            "mean_pp": h1["mean_pp"],
            "ci95_pp": h1["ci95_pp"],
        }
    if "H2_p1_minus_c1" in contrasts:
        h2 = contrasts["H2_p1_minus_c1"]
        decisions["H2"] = {
            "non_inferior": h2["ci95_pp"][0] > -10.0,
            "rule": "lower 95% bootstrap CI bound of (p1-c1) > -0.10",
            "mean_pp": h2["mean_pp"],
            "ci95_pp": h2["ci95_pp"],
            "margin_pp": -10.0,
        }
    # per-family descriptive
    per_family = {}
    for f in sorted(set(fam.values())):
        per_family[f] = {}
        for a in ARM_ORDER:
            cells = [new[(t, a, s)] for t in tids if fam[t] == f for s in SEEDS
                     if (t, a, s) in new]
            per_family[f][a] = {
                "n": len(cells),
                "pass_rate": (sum(1 for c in cells if c["pass"]) / len(cells))
                if cells else None,
            }
        for c in CONTROL_CONDS:
            cells = [ctrl[(t, c, s)] for t in tids if fam[t] == f for s in SEEDS
                     if (t, c, s) in ctrl]
            per_family[f][c] = {
                "n": len(cells),
                "pass_rate": (sum(1 for x in cells if x["pass"]) / len(cells))
                if cells else None,
            }
    # cost / tokens
    cost_total = round(sum(r.get("cost_cny") or 0 for r in new_rows), 6)
    tokens = {}
    for a in ARM_ORDER:
        cells = [new[(t, a, s)] for t in tids for s in SEEDS if (t, a, s) in new]
        tokens[a] = {
            "prompt_tokens": sum((c.get("tokens") or {}).get("prompt_tokens") or 0 for c in cells),
            "completion_tokens": sum((c.get("tokens") or {}).get("completion_tokens") or 0 for c in cells),
            "total_tokens": sum((c.get("tokens") or {}).get("total_tokens") or 0 for c in cells),
        }
    # sanity checks
    prompts = []
    if PROMPTS.exists():
        prompts = [json.loads(l) for l in PROMPTS.read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    prompt_map = {(p["tid"], p["arm"], p["seed"]): p["prompt"] for p in prompts}
    diff_only_ok = 0
    diff_only_total = 0
    for t in tids:
        for seed in SEEDS:
            for arm in ARM_ORDER:
                p = prompt_map.get((t, arm, seed))
                if p is None:
                    continue
                extra = inserted_text(ARMS[arm]["kind"])
                task_obj = next(x for x in TASKS if x["tid"] == t)
                base = run_bench.prompt_for(task_obj, ARMS[arm]["base"], seed)[0]["content"]
                diff_only_total += 1
                if p.replace("\n\n" + extra, "", 1) == base:
                    diff_only_ok += 1
    key_seen = False
    try:
        env = load_env()
        key = env.get("DEEPSEEK_API_KEY", "")
        if key:
            for fname in (ROWS, PROMPTS, COST_LOG):
                if fname.exists() and key in fname.read_text(encoding="utf-8", errors="ignore"):
                    key_seen = True
    except SystemExit:
        pass
    first_ts = new_rows[0]["ts"] if new_rows else None
    frozen_before_first = None
    if first_ts:
        try:
            first_epoch = time.mktime(time.strptime(first_ts[:19], "%Y-%m-%dT%H:%M:%S"))
            frozen_before_first = PREREG.stat().st_mtime <= first_epoch
        except ValueError:
            pass
    sanity = {
        "expected_cells": EXPECTED_CELLS,
        "cells_written": len(new_rows),
        "coverage_by_arm": coverage,
        "complete": len(new_rows) == EXPECTED_CELLS
        and all(coverage[a] == len(tids) * len(SEEDS) for a in ARM_ORDER),
        "api_error_rows": len(errors),
        "prompt_diff_only_checks": [diff_only_ok, diff_only_total],
        "prompt_diff_only_ok": diff_only_ok == diff_only_total and diff_only_total == EXPECTED_CELLS,
        "prompt_count": len(prompts),
        "controls_rows": len(controls),
        "controls_snapshot_sha256": sha256_file(CONTROLS),
        "prereg_sha256": sha256_file(PREREG),
        "prereg_sha256_matches_freeze": sha256_file(PREREG) == frozen["prereg_sha256"],
        "prereg_mtime": frozen["prereg_mtime"],
        "frozen_at": frozen["frozen_at"],
        "first_row_ts": first_ts,
        "last_row_ts": new_rows[-1]["ts"] if new_rows else None,
        "prereg_frozen_before_first_call": frozen_before_first,
        "cost_cny_total": cost_total,
        "cost_cap_cny": COST_CAP_CNY,
        "cost_stop_cny": COST_STOP_CNY,
        "cost_cap_respected": cost_total <= COST_CAP_CNY,
        "api_key_in_outputs": key_seen,
        "grading": "run_bench.run_tests hidden pytest; pass=returncode 0",
    }
    summary = {
        "schema": "precedence/1",
        "design": "5 new arms (p2,p1,p2f,w2f,p1f) x 54 tasks x 2 prompt-variant seeds; "
                  "T=0.3; controls c1/c2/c2f from frozen bench_chat batch",
        "model": new_rows[0].get("model") if new_rows else None,
        "cells_new": len(new_rows),
        "prereg_sha256": frozen["prereg_sha256"],
        "arm_rates": arm_rates,
        "control_rates": control_rates,
        "contrasts": contrasts,
        "hypothesis_decisions": decisions,
        "per_family": per_family,
        "tokens": tokens,
        "cost_cny_total": cost_total,
        "sanity": sanity,
        "analysis_plan": {
            "per_task": "mean pass over seeds 0/1",
            "H1": "one-sided exact paired sign test p<.05; 1000x task bootstrap CI reported",
            "H2": "non-inferiority: lower 95% bootstrap CI of p1-c1 > -0.10",
            "H3": "exploratory DiD (p2-c2)-(p2f-c2f)",
            "H4": "exploratory p2f-w2f (rule vs warning, full suite)",
            "bootstrap": f"{BOOT_N} resamples over tasks, seed {BOOT_SEED}",
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    # task table
    cols = ["tid", "family"] + [f"score_{a}" for a in ARM_ORDER] + \
           [f"score_{c}" for c in CONTROL_CONDS] + \
           ["diff_H1_p2_c2", "diff_H2_p1_c1", "diff_H3_did", "diff_H4_p2f_w2f"]
    with TASK_TABLE.open("w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for t in tids:
            row = {"tid": t, "family": fam[t]}
            for a in ARM_ORDER:
                row[f"score_{a}"] = scores[a].get(t)
            for c in CONTROL_CONDS:
                row[f"score_{c}"] = scores[c].get(t)
            row["diff_H1_p2_c2"] = (scores["p2"][t] - scores["c2"][t]) if complete else ""
            row["diff_H2_p1_c1"] = (scores["p1"][t] - scores["c1"][t]) if complete else ""
            row["diff_H3_did"] = ((scores["p2"][t] - scores["c2"][t])
                                  - (scores["p2f"][t] - scores["c2f"][t])) if complete else ""
            row["diff_H4_p2f_w2f"] = (scores["p2f"][t] - scores["w2f"][t]) if complete else ""
            fh.write("\t".join("" if row.get(c) is None else str(row.get(c))
                               for c in cols) + "\n")
    # console
    print("== pass rates (new arms, n=108; controls from frozen batch) ==")
    for a in ARM_ORDER:
        r = arm_rates[a]
        print(f"  {a:4s} {r['pass']}/{r['n']} = {100*r['pass_rate']:.1f}%")
    for c in CONTROL_CONDS:
        r = control_rates[c]
        print(f"  {c:4s} {r['pass']}/{r['n']} = {100*r['pass_rate']:.1f}% (control)")
    for name, c in contrasts.items():
        print(f"  {name}: {c['mean_pp']:+.2f} pp "
              f"[{c['ci95_pp'][0]:+.2f},{c['ci95_pp'][1]:+.2f}] "
              f"sign p1={c['sign_test_p_one_sided']:.4f} p2={c['sign_test_p_two_sided']:.4f} "
              f"improved/worsened/tied={c['improved']}/{c['worsened']}/{c['tied']}")
    print(f"  decisions: {json.dumps(decisions)}")
    print(f"  cells={len(new_rows)}/{EXPECTED_CELLS} complete={sanity['complete']} "
          f"cost=¥{cost_total:.4f} cap_ok={sanity['cost_cap_respected']} "
          f"diff_only_ok={sanity['prompt_diff_only_ok']} key_in_outputs={key_seen}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="source-of-truth precedence experiment")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ack-prereg", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default="")
    a = ap.parse_args(argv)
    if not any((a.dry_run, a.ping, a.run, a.analyze, a.all)):
        ap.print_help()
        return 1
    if a.dry_run:
        return do_dry_run()
    if a.analyze and not (a.ping or a.run or a.all):
        analyze()
        return 0
    env = load_env()
    model = a.model or env["DEEPSEEK_MODEL"]
    if a.ping or a.all:
        rc = do_ping(env, model)
        if rc != 0:
            return rc
    if a.run or a.all:
        rc = do_run(env, model, a.workers)
        if rc != 0:
            return rc
    if a.analyze or a.all:
        analyze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
