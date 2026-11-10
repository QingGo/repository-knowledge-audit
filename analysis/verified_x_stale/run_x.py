#!/usr/bin/env python3
"""2x2 experiment: verified label x correct/stale note (chat model, 54 tasks).

Pre-registration: `PREREG.md` in this directory (frozen before any API call).
The runner reuses, without editing, the benchmark prompt builder and hidden-test
grader:

  kb-health/outcome_bench/run_bench.py     prompt_for(), run_tests(), parse_code()
  kb-health/outcome_bench/conventions.py   TASKS (54 tasks, 7 families)
  kb-health/probe_screen/run_probes.py     load_env(), chat(), parse_json(), usage_cost()

Arms (header is the only manipulation; note body is `TASKS[i]["useful"]` vs
`TASKS[i]["stale"]`):
  c1    correct note + neutral header
  c1ver correct note + verified header
  c2    stale note   + neutral header
  c2ver stale note   + verified header

Cells: 54 tasks x 4 arms x 2 seeds (temperature 0.2 / 0.3) = 432 completions.
Cost cap: 1.5 CNY (see PREREG.md §5). Rows are written as they arrive and the
run is resume-safe by (tid, arm, seed).

Usage (from the kb-health repo root):
  python3 analysis/verified_x_stale/run_x.py --dry-run
  python3 analysis/verified_x_stale/run_x.py --ping        --ack-prereg
  python3 analysis/verified_x_stale/run_x.py --run         --ack-prereg
  python3 analysis/verified_x_stale/run_x.py --analyze
  python3 analysis/verified_x_stale/run_x.py --all         --ack-prereg

Writes only under analysis/verified_x_stale/. The API key is read via load_env
and never printed or written to any output file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
KB_HEALTH = HERE.parents[1]  # analysis/verified_x_stale -> kb-health
OUTCOME = KB_HEALTH / "outcome_bench"
PROBE = KB_HEALTH / "probe_screen"
for p in (str(OUTCOME), str(PROBE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_bench  # noqa: E402  (prompt_for/run_tests/parse_code; never edited)
from run_probes import load_env, chat, parse_json, usage_cost  # noqa: E402
from conventions import TASKS  # noqa: E402

RESULTS = HERE / "results"
ROWS = RESULTS / "bench_x.jsonl"
PROMPTS = RESULTS / "prompts.jsonl"
COST_LOG = RESULTS / "cost_log.json"
SUMMARY = RESULTS / "summary.json"
TASK_TABLE = RESULTS / "task_table.tsv"
PREREG = HERE / "PREREG.md"

NEUTRAL_HEADER = "Project knowledge note:\n"
VERIFIED_HEADER = ("Project knowledge note (verified conventions from the current "
                   "repo):\n")
ARMS = {
    "c1":    {"truth": "correct", "header_kind": "neutral",  "header": NEUTRAL_HEADER},
    "c1ver": {"truth": "correct", "header_kind": "verified", "header": VERIFIED_HEADER},
    "c2":    {"truth": "stale",   "header_kind": "neutral",  "header": NEUTRAL_HEADER},
    "c2ver": {"truth": "stale",   "header_kind": "verified", "header": VERIFIED_HEADER},
}
ARM_ORDER = ["c1", "c1ver", "c2", "c2ver"]
SEED_TEMPERATURES = {0: 0.2, 1: 0.3}
MAX_TOKENS = 2400
COST_CAP_CNY = 1.5
COST_STOP_CNY = 1.45
BOOTSTRAP_N = 10000
FLIP_N = 100000
BOOTSTRAP_SEED = 20261109

_HEAD_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_results() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)


def prereg_gate(ack: bool, api_call: bool) -> str:
    if not PREREG.exists():
        raise SystemExit("PREREG.md missing: pre-register before any API call")
    sha = sha256_file(PREREG)
    if api_call and not ack:
        raise SystemExit("refusing to make API calls without --ack-prereg "
                         "(PREREG.md must be frozen before calls)")
    return sha


def make_prompt(task: dict, arm: str, seed: int) -> list[dict]:
    """Build the benchmark prompt with only the note header changed.

    Uses run_bench.prompt_for unchanged; the module-level `HEAD` entry for the
    reused condition ("c1" for correct, "c2" for stale) is swapped per arm under
    a lock and restored afterwards, so the four arms differ only in the header
    string.
    """
    cond = "c1" if ARMS[arm]["truth"] == "correct" else "c2"
    header = ARMS[arm]["header"]
    with _HEAD_LOCK:
        old = run_bench.HEAD.get(cond)
        run_bench.HEAD[cond] = header
        try:
            messages = run_bench.prompt_for(task, cond, seed)
        finally:
            if old is None:
                run_bench.HEAD.pop(cond, None)
            else:
                run_bench.HEAD[cond] = old
    return messages


def cell_order() -> list[tuple[dict, str, int]]:
    """Deterministic task -> arm -> seed order (balanced coverage if capped)."""
    return [(task, arm, seed) for task in TASKS for arm in ARM_ORDER
            for seed in (0, 1)]


def done_keys() -> set[tuple[str, str, int]]:
    done: set[tuple[str, str, int]] = set()
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                done.add((r["tid"], r["arm"], int(r["seed"])))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return done


def spent_so_far() -> float:
    spent = 0.0
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                spent += float(json.loads(line).get("cost_cny") or 0.0)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return spent


def run_one(env: dict, task: dict, arm: str, seed: int, model: str) -> dict:
    temperature = SEED_TEMPERATURES[seed]
    messages = make_prompt(task, arm, seed)
    prompt_text = messages[-1]["content"]
    t0 = time.time()
    try:
        resp = chat(env, messages, model, temperature, MAX_TOKENS)
    except Exception as exc:  # noqa: BLE001 - recorded, not hidden
        return {
            "tid": task["tid"], "family": task["family"], "arm": arm,
            "note_truth": ARMS[arm]["truth"],
            "header_kind": ARMS[arm]["header_kind"], "header": ARMS[arm]["header"],
            "seed": seed, "temperature": temperature, "pass": False,
            "error": f"api: {type(exc).__name__}: {exc}"[:300],
            "tokens": {}, "cost_cny": 0.0,
            "latency_s": round(time.time() - t0, 2), "code_len": 0,
            "prompt_sha256": sha256_text(prompt_text),
            "prompt_chars": len(prompt_text),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    raw = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    code = run_bench.parse_code(parse_json(raw), raw)
    if code.strip():
        ok, out = run_bench.run_tests(code, task["tests"])
    else:
        ok, out = False, "no code"
    usage = resp.get("usage") or {}
    tokens = {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
        "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    return {
        "tid": task["tid"], "family": task["family"], "arm": arm,
        "note_truth": ARMS[arm]["truth"],
        "header_kind": ARMS[arm]["header_kind"], "header": ARMS[arm]["header"],
        "seed": seed, "temperature": temperature, "pass": bool(ok),
        "code_len": len(code), "output": (out or "")[-400:],
        "model": model, "tokens": tokens, "cost_cny": usage_cost(usage),
        "latency_s": round(time.time() - t0, 2),
        "prompt_sha256": sha256_text(prompt_text),
        "prompt_chars": len(prompt_text),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# ---------------------------------------------------------------------------
# modes: dry-run / ping / run
# ---------------------------------------------------------------------------
def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def do_dry_run() -> int:
    ensure_results()
    prereg_gate(ack=False, api_call=False)
    prompts = []
    errors = []
    for task, arm, seed in cell_order():
        msgs = make_prompt(task, arm, seed)
        text = msgs[-1]["content"]
        prompts.append({"tid": task["tid"], "arm": arm, "seed": seed,
                        "prompt_sha256": sha256_text(text), "prompt": text})
        header = ARMS[arm]["header"].strip()
        if text.count(header) != 1:
            errors.append(f"{task['tid']}/{arm}/{seed}: header count "
                          f"{text.count(header)} != 1")
    # factorial sanity: c1 vs c1ver and c2 vs c2ver differ only in the header line
    by_cell = {(p["tid"], p["arm"], p["seed"]): p["prompt"] for p in prompts}
    header_pairs = [("c1", "c1ver", NEUTRAL_HEADER, VERIFIED_HEADER),
                    ("c2", "c2ver", NEUTRAL_HEADER, VERIFIED_HEADER)]
    header_only_checks = 0
    for tid in [t["tid"] for t in TASKS]:
        for seed in (0, 1):
            for a, b, ha, hb in header_pairs:
                pa = by_cell[(tid, a, seed)].replace(ha.strip(), "<HEADER>")
                pb = by_cell[(tid, b, seed)].replace(hb.strip(), "<HEADER>")
                header_only_checks += 1
                if pa != pb:
                    errors.append(f"header-only check failed: {tid}/{seed}/{a}-{b}")
            # headers must be identical across truth arms
            for header, arms in ((NEUTRAL_HEADER, ("c1", "c2")),
                                 (VERIFIED_HEADER, ("c1ver", "c2ver"))):
                ok = all(header.strip() in by_cell[(tid, arm, seed)] for arm in arms)
                if not ok:
                    errors.append(f"cross-truth header check failed: {tid}/{seed}/{arms}")
    # note bodies: exact bullet lines from conventions.py, nothing extra
    body_checks = 0
    for task in TASKS:
        for arm in ARM_ORDER:
            facts = task["useful"] if ARMS[arm]["truth"] == "correct" else task["stale"]
            expected = "- " + "\n- ".join(facts)
            for seed in (0, 1):
                text = by_cell[(task["tid"], arm, seed)]
                body_checks += 1
                if expected not in text:
                    errors.append(f"note body missing/mangled: {task['tid']}/{arm}/{seed}")
    # grading sanity: empty code fails the hidden tests for every task
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
        "n_prompts": len(prompts),
        "n_tasks": len(TASKS),
        "n_arms": len(ARM_ORDER),
        "n_seeds": len(SEED_TEMPERATURES),
        "expected_cells": len(TASKS) * len(ARM_ORDER) * len(SEED_TEMPERATURES),
        "header_only_checks": header_only_checks,
        "body_checks": body_checks,
        "grading_empty_code_fails": empty_fail,
        "errors": errors,
        "prereg_sha256": sha256_file(PREREG),
    }
    (RESULTS / "dry_run.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"}, indent=1))
    if errors:
        print(f"DRY-RUN FAILED: {len(errors)} errors", file=sys.stderr)
        for e in errors[:20]:
            print("  -", e, file=sys.stderr)
        return 1
    print(f"DRY-RUN OK: {len(prompts)} prompts, {header_only_checks} header-only checks, "
          f"{body_checks} body checks, grading sanity {empty_fail}/{len(TASKS)}")
    return 0


def do_ping(env: dict, model: str) -> int:
    ensure_results()
    prereg_sha = prereg_gate(ack=True, api_call=True)
    t0 = time.time()
    try:
        resp = chat(env, [{"role": "user",
                           "content": 'Reply with exactly this JSON: {"ok": true}'}],
                    model, 0.2, 16)
    except Exception as exc:  # noqa: BLE001
        print(f"PING FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    usage = resp.get("usage") or {}
    out = {
        "mode": "ping",
        "model": model,
        "ok": True,
        "latency_s": round(time.time() - t0, 2),
        "usage": usage,
        "cost_cny": usage_cost(usage),
        "prereg_sha256": prereg_sha,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "connectivity check only; not part of the 432 cells",
    }
    (RESULTS / "ping.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PING OK model={model} latency={out['latency_s']}s "
          f"cost=¥{out['cost_cny']:.6f}")
    return 0


def do_run(env: dict, model: str, workers: int) -> int:
    ensure_results()
    prereg_sha = prereg_gate(ack=True, api_call=True)
    done = done_keys()
    spent = spent_so_far()
    todo = [c for c in cell_order() if (c[0]["tid"], c[1], c[2]) not in done]
    print(f"[run] tasks={len(TASKS)} cells={len(cell_order())} done={len(done)} "
          f"todo={len(todo)} spent=¥{spent:.4f}", file=sys.stderr)
    if not todo:
        print("[run] nothing to do (all cells present)", file=sys.stderr)
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
                    print(f"[run] COST STOP at ¥{spent:.4f} >= ¥{COST_STOP_CNY} "
                          f"(hard cap ¥{COST_CAP_CNY})", file=sys.stderr)
                    break
    # cost log
    rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    per_arm: dict[str, float] = {a: 0.0 for a in ARM_ORDER}
    n_calls = 0
    for r in rows:
        per_arm[r["arm"]] = round(per_arm.get(r["arm"], 0.0)
                                  + (r.get("cost_cny") or 0.0), 6)
        n_calls += 1
    cost_log = {
        "model": model,
        "cells_written": n_calls,
        "expected_cells": len(TASKS) * len(ARM_ORDER) * len(SEED_TEMPERATURES),
        "cost_cny_total": round(sum(per_arm.values()), 6),
        "cost_cny_per_arm": per_arm,
        "cost_cap_cny": COST_CAP_CNY,
        "cap_respected": sum(per_arm.values()) <= COST_CAP_CNY,
        "prereg_sha256": prereg_sha,
        "prereg_mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                      time.localtime(PREREG.stat().st_mtime)),
        "first_row_ts": rows[0]["ts"] if rows else None,
        "last_row_ts": rows[-1]["ts"] if rows else None,
    }
    COST_LOG.write_text(json.dumps(cost_log, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"[run] wrote {n_calls} rows; cost=¥{cost_log['cost_cny_total']:.4f} "
          f"(cap ¥{COST_CAP_CNY})", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# analysis (pre-registered plan)
# ---------------------------------------------------------------------------
def load_rows() -> list[dict]:
    if not ROWS.exists():
        raise SystemExit(f"no results: {ROWS}")
    rows = []
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def boot_ci(vals: list[float], n: int = BOOTSTRAP_N,
            seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    rng = random.Random(seed)
    m = len(vals)
    means = []
    for _ in range(n):
        s = 0.0
        for _ in range(m):
            s += vals[rng.randrange(m)]
        means.append(s / m)
    means.sort()
    return (statistics.fmean(vals),
            means[int(0.025 * n)], means[int(0.975 * n) - 1])


def signflip_p(vals: list[float], n: int = FLIP_N,
               seed: int = BOOTSTRAP_SEED) -> float:
    obs = abs(statistics.fmean(vals))
    if obs == 0:
        return 1.0
    rng = random.Random(seed + 1)
    hits = 0
    m = len(vals)
    for _ in range(n):
        s = 0.0
        for v in vals:
            if rng.random() < 0.5:
                s += v
            else:
                s -= v
        if abs(s / m) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (n + 1)


def paired_summary(task_diffs: dict[str, float], label: str) -> dict:
    vals = [task_diffs[t] for t in sorted(task_diffs)]
    point, lo, hi = boot_ci(vals)
    improved = sum(1 for v in vals if v > 0)
    worsened = sum(1 for v in vals if v < 0)
    tied = sum(1 for v in vals if v == 0)
    return {
        "label": label,
        "n_tasks": len(vals),
        "mean_pp": 100.0 * point,
        "ci95_pp": [100.0 * lo, 100.0 * hi],
        "ci_excludes_zero": bool(lo > 0 or hi < 0),
        "signflip_p_two_sided": signflip_p(vals),
        "improved": improved, "worsened": worsened, "tied": tied,
        "task_diffs": {t: task_diffs[t] for t in sorted(task_diffs)},
    }


def analyze() -> dict:
    prereg_sha = sha256_file(PREREG)
    rows = load_rows()
    by_cell: dict[tuple[str, str, int], dict] = {}
    for r in rows:
        by_cell[(r["tid"], r["arm"], int(r["seed"]))] = r
    tids = [t["tid"] for t in TASKS]
    fam = {t["tid"]: t["family"] for t in TASKS}
    arms = ARM_ORDER
    expected_cells = len(tids) * len(arms) * 2
    coverage = {a: sum(1 for t in tids for s in (0, 1) if (t, a, s) in by_cell)
                for a in arms}
    errors = [r for r in rows if r.get("error")]
    # arm rates over available cells
    arm_rate = {}
    for a in arms:
        cells = [by_cell[(t, a, s)] for t in tids for s in (0, 1)
                 if (t, a, s) in by_cell]
        arm_rate[a] = {
            "n": len(cells),
            "pass": sum(1 for c in cells if c["pass"]),
            "pass_rate": (sum(1 for c in cells if c["pass"]) / len(cells))
            if cells else None,
            "by_seed": {str(s): {
                "n": sum(1 for t in tids if (t, a, s) in by_cell),
                "pass_rate": (sum(1 for t in tids if (t, a, s) in by_cell
                                  and by_cell[(t, a, s)]["pass"])
                              / max(1, sum(1 for t in tids
                                           if (t, a, s) in by_cell)))
                } for s in (0, 1)},
            "completion_tokens_mean": statistics.fmean(
                [c["tokens"].get("completion_tokens") or 0 for c in cells])
            if cells else None,
            "latency_s_mean": statistics.fmean([c.get("latency_s") or 0
                                                for c in cells]) if cells else None,
            "code_len_mean": statistics.fmean([c.get("code_len") or 0
                                               for c in cells]) if cells else None,
            "cost_cny": round(sum(c.get("cost_cny") or 0 for c in cells), 6),
        }
    # paired task-level: mean over available seeds
    def task_mean(tid: str, arm: str) -> float | None:
        vals = [by_cell[(tid, arm, s)]["pass"] for s in (0, 1)
                if (tid, arm, s) in by_cell]
        return statistics.fmean(vals) if vals else None

    h1: dict[str, float] = {}
    h2: dict[str, float] = {}
    h3: dict[str, float] = {}
    for t in tids:
        a = task_mean(t, "c1")
        av = task_mean(t, "c1ver")
        b = task_mean(t, "c2")
        bv = task_mean(t, "c2ver")
        if None not in (a, av):
            h1[t] = av - a
        if None not in (b, bv):
            h2[t] = bv - b
        if None not in (a, av, b, bv):
            h3[t] = (av - a) - (bv - b)
    contrasts = {}
    if h1:
        contrasts["H1_c1ver_minus_c1"] = paired_summary(h1, "H1: verified minus neutral (correct note)")
    if h2:
        contrasts["H2_c2ver_minus_c2"] = paired_summary(h2, "H2: verified minus neutral (stale note)")
    if h3:
        contrasts["H3_difference_in_differences"] = paired_summary(
            h3, "H3: (c1ver-c1) - (c2ver-c2)")
    # hypotheses verdicts (pre-registered decision rules)
    verdicts = {}
    if "H1_c1ver_minus_c1" in contrasts:
        c = contrasts["H1_c1ver_minus_c1"]
        verdicts["H1"] = {"supported": c["ci95_pp"][0] > 0,
                          "rule": "95% CI entirely above 0"}
    if "H2_c2ver_minus_c2" in contrasts:
        c = contrasts["H2_c2ver_minus_c2"]
        verdicts["H2"] = {"supported": c["ci95_pp"][1] < 0,
                          "rule": "95% CI entirely below 0"}
    if "H3_difference_in_differences" in contrasts:
        c = contrasts["H3_difference_in_differences"]
        verdicts["H3"] = {"supported": c["ci_excludes_zero"],
                          "rule": "95% CI excludes 0 (direction reported literally)"}
    # 2x2 table
    table_2x2 = {}
    for truth, arm_neutral, arm_verified in (("correct", "c1", "c1ver"),
                                             ("stale", "c2", "c2ver")):
        table_2x2[truth] = {
            "neutral": {"arm": arm_neutral, **arm_rate[arm_neutral]},
            "verified": {"arm": arm_verified, **arm_rate[arm_verified]},
        }
    # per family
    fam_table = {}
    for f in sorted(set(fam.values())):
        fam_table[f] = {}
        for a in arms:
            cells = [by_cell[(t, a, s)] for t in tids if fam[t] == f
                     for s in (0, 1) if (t, a, s) in by_cell]
            fam_table[f][a] = {
                "n": len(cells),
                "pass_rate": (sum(1 for c in cells if c["pass"]) / len(cells))
                if cells else None}
    # per-task table (written as TSV)
    task_rows = []
    for t in tids:
        row = {"tid": t, "family": fam[t],
               **{f"pass_{a}": task_mean(t, a) for a in arms}}
        for key, d in (("diff_H1_c1ver_minus_c1", h1),
                       ("diff_H2_c2ver_minus_c2", h2),
                       ("diff_H3_did", h3)):
            row[key] = d.get(t)
        task_rows.append(row)
    # cost / tokens
    cost_total = round(sum(r.get("cost_cny") or 0 for r in rows), 6)
    tokens = {}
    for a in arms:
        cells = [by_cell[(t, a, s)] for t in tids for s in (0, 1)
                 if (t, a, s) in by_cell]
        tokens[a] = {
            "prompt_tokens": sum((c["tokens"].get("prompt_tokens") or 0)
                                 for c in cells),
            "completion_tokens": sum((c["tokens"].get("completion_tokens") or 0)
                                     for c in cells),
            "total_tokens": sum((c["tokens"].get("total_tokens") or 0)
                                for c in cells),
            "cache_hit_tokens": sum((c["tokens"].get("prompt_cache_hit_tokens") or 0)
                                    for c in cells),
        }
    # sanity checks (pre-registered §7; all recomputed from artifacts)
    prompts = []
    if PROMPTS.exists():
        prompts = [json.loads(l) for l in PROMPTS.read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    prompt_by = {(p["tid"], p["arm"], p["seed"]): p["prompt"] for p in prompts}
    header_ok = 0
    header_total = 0
    for t in tids:
        for s in (0, 1):
            for a, b, ha, hb in (("c1", "c1ver", NEUTRAL_HEADER, VERIFIED_HEADER),
                                 ("c2", "c2ver", NEUTRAL_HEADER, VERIFIED_HEADER)):
                pa = prompt_by.get((t, a, s), "").replace(ha.strip(), "<HEADER>")
                pb = prompt_by.get((t, b, s), "").replace(hb.strip(), "<HEADER>")
                header_total += 1
                header_ok += 1 if pa == pb else 0
    key_seen = False
    try:
        env = load_env()
        key = env.get("DEEPSEEK_API_KEY", "")
        if key:
            for fname in (ROWS, PROMPTS, COST_LOG):
                if fname.exists() and key in fname.read_text(encoding="utf-8",
                                                            errors="ignore"):
                    key_seen = True
    except SystemExit:
        pass
    sanity = {
        "expected_cells": expected_cells,
        "cells_written": len(rows),
        "coverage_by_arm": coverage,
        "complete": len(rows) == expected_cells
        and all(coverage[a] == len(tids) * 2 for a in arms),
        "prompt_header_only_checks": [header_ok, header_total],
        "prompt_header_only_ok": header_ok == header_total,
        "api_error_rows": len(errors),
        "cost_cny_total": cost_total,
        "cost_cap_cny": COST_CAP_CNY,
        "cost_cap_respected": cost_total <= COST_CAP_CNY,
        "prereg_sha256": prereg_sha,
        "prereg_mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                      time.localtime(PREREG.stat().st_mtime)),
        "first_row_ts": rows[0]["ts"] if rows else None,
        "last_row_ts": rows[-1]["ts"] if rows else None,
        "prereg_frozen_before_first_call": None,  # filled below
        "api_key_in_outputs": key_seen,
        "grading": "run_bench.run_tests hidden pytest; pass=returncode 0",
    }
    # simpler/robust prereg-before-call check using wall-clock epoch strings
    if rows:
        try:
            first_epoch = time.mktime(time.strptime(rows[0]["ts"][:19],
                                                    "%Y-%m-%dT%H:%M:%S"))
            sanity["prereg_frozen_before_first_call"] = \
                PREREG.stat().st_mtime <= first_epoch + 1
        except ValueError:
            pass
    summary = {
        "schema": "verified-x-stale/1",
        "design": "2x2: note truth (correct/stale) x header (neutral/verified), "
                  "54 tasks, seeds {0: T=0.2, 1: T=0.3}, one completion/cell",
        "model": rows[0].get("model") if rows else None,
        "cells": len(rows),
        "prereg_sha256": prereg_sha,
        "arm_rates": arm_rate,
        "table_2x2": table_2x2,
        "contrasts": contrasts,
        "hypothesis_verdicts": verdicts,
        "per_family": fam_table,
        "tokens": tokens,
        "cost_cny_total": cost_total,
        "sanity": sanity,
        "analysis_plan": {
            "metric": "task-level pass rate (mean over 2 seeds); paired over 54 tasks",
            "bootstrap": f"task bootstrap {BOOTSTRAP_N} resamples, seed {BOOTSTRAP_SEED}",
            "signflip": f"two-sided paired sign-flip {FLIP_N} draws, seed {BOOTSTRAP_SEED + 1}",
            "decision_rule": "CI-based (H1 lower>0; H2 upper<0; H3 CI excludes 0)",
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    # task table TSV
    cols = ["tid", "family"] + [f"pass_{a}" for a in arms] + \
           ["diff_H1_c1ver_minus_c1", "diff_H2_c2ver_minus_c2", "diff_H3_did"]
    with TASK_TABLE.open("w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for row in task_rows:
            fh.write("\t".join("" if row.get(c) is None else str(row.get(c))
                               for c in cols) + "\n")
    # console headline
    print("== 2x2 pass rates (n cells) ==")
    for truth, d in table_2x2.items():
        print(f"  {truth:7s} neutral={d['neutral']['pass_rate']:.3f} "
              f"({d['neutral']['pass']}/{d['neutral']['n']})  "
              f"verified={d['verified']['pass_rate']:.3f} "
              f"({d['verified']['pass']}/{d['verified']['n']})")
    for name, c in contrasts.items():
        print(f"  {name}: {c['mean_pp']:+.2f} pp "
              f"[{c['ci95_pp'][0]:+.2f},{c['ci95_pp'][1]:+.2f}] "
              f"p={c['signflip_p_two_sided']:.4f} "
              f"improved/worsened/tied={c['improved']}/{c['worsened']}/{c['tied']}")
    print(f"  verdicts: {json.dumps(verdicts)}")
    print(f"  cells={len(rows)}/{expected_cells} cost=¥{cost_total:.4f} "
          f"cap_ok={sanity['cost_cap_respected']} "
          f"header_only_ok={sanity['prompt_header_only_ok']} "
          f"key_in_outputs={sanity['api_key_in_outputs']}")
    return summary


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="2x2 verified-label x truth experiment")
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
    rc = 0
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
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
