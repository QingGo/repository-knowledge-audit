#!/usr/bin/env python3
"""Independent model-family replication on MiMo (Xiaomi): c0/c1/c2, 54 tasks, seed 0.

Pre-registration: `PREREG.md` in this directory (sha256 in `results/freeze.json`),
frozen before any API call. Reuses the benchmark unchanged:

  kb-health/outcome_bench/run_bench.py    prompt_for(), run_tests(), parse_code()
  kb-health/outcome_bench/conventions.py  TASKS (54 tasks)

MiMo request format copied from
/REPOS_ROOT/has-pilot/signal_bank/run_pilot.py (provider="mimo"):
OpenAI-compatible chat completions, `thinking={"type":"disabled"}`,
`max_completion_tokens`, model id `mimo-v2.6-flash`, base URL from `~/.mimo.env`
(`MIMO_BASE_URL`); the API key is read there and never printed or stored.

Core cells: 54 tasks x {c0, c1, c2} x prompt-variant seed 0 = 162 completions.
Optional stage (pre-registered, budget-gated): after the core, if spend < RMB 4,
add c0f then c2f (54 x 2 = 108) for the visible-test boundary on this family.

Usage (from kb-health/):
  python3 analysis/model_family_mimo/run_mimo.py --dry-run
  python3 analysis/model_family_mimo/run_mimo.py --validate
  python3 analysis/model_family_mimo/run_mimo.py --run
  python3 analysis/model_family_mimo/run_mimo.py --analyze

Writes only under analysis/model_family_mimo/.
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
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
KB_HEALTH = HERE.parents[1]  # analysis/model_family_mimo -> kb-health
OUTCOME = KB_HEALTH / "outcome_bench"
PROBE = KB_HEALTH / "probe_screen"
for p in (str(OUTCOME), str(PROBE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_bench  # noqa: E402  (never edited)
from conventions import TASKS  # noqa: E402

RESULTS = HERE / "results"
PREREG = HERE / "PREREG.md"
FREEZE = RESULTS / "freeze.json"
ROWS = RESULTS / "mimo_chat.jsonl"
PROMPTS = RESULTS / "mimo_prompts.jsonl"
COST_LOG = RESULTS / "cost_log.json"
SUMMARY = RESULTS / "summary.json"
TASK_TABLE = RESULTS / "task_table.tsv"
DRY_RUN = RESULTS / "dry_run.json"
VALIDATION = RESULTS / "c0v_validation.json"
ENV_PATH = pathlib.Path.home() / ".mimo.env"

MODEL = "mimo-v2.6-flash"
TEMPERATURE = 0.3
MAX_COMPLETION_TOKENS = 2400
SEED = 0
CORE_CONDS = ["c0", "c1", "c2"]
OPTIONAL_CONDS = ["c0f", "c2f"]
COST_IN_PER_M = 1.0   # CNY / M input tokens (has-pilot run_pilot.py, provider="mimo")
COST_OUT_PER_M = 2.0  # CNY / M output tokens
HARD_CAP_CNY = 10.0
STOP_CNY = 8.0
OPTIONAL_SPEND_GATE_CNY = 4.0
RETRIES = 5
BOOT_N = 1000
BOOT_SEED = 20261109
# existing DeepSeek all-54 ITT chat effects (paper's core numbers), for direction comparison
DEEPSEEK_ITT = {"useful_c1_minus_c0": 0.648, "stale_c2_minus_c0": -0.111}


# ---------------------------------------------------------------------------
# env + API (key never printed/stored)
# ---------------------------------------------------------------------------
def load_mimo_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("MIMO_API_KEY", "MIMO_BASE_URL"):
        if not env.get(k):
            raise SystemExit(f"missing {k} in {ENV_PATH}")
    return env


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mimo_cost_cny(prompt_tokens: int, completion_tokens: int) -> float:
    return round((prompt_tokens / 1e6) * COST_IN_PER_M
                 + (completion_tokens / 1e6) * COST_OUT_PER_M, 8)


def call_mimo(env: dict, messages: list[dict]) -> dict:
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "stream": False,
        "thinking": {"type": "disabled"},
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }
    url = env["MIMO_BASE_URL"].rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + env["MIMO_API_KEY"],
                 "Content-Type": "application/json"}, method="POST")
    last = None
    for attempt in range(RETRIES):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                obj = json.loads(r.read().decode())
            ch = (obj.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            usage = obj.get("usage") or {}
            return {
                "ok": True, "text": (msg.get("content") or ""),
                "finish_reason": ch.get("finish_reason"),
                "model_returned": obj.get("model"),
                "prompt_tokens": usage.get("prompt_tokens") or 0,
                "completion_tokens": usage.get("completion_tokens") or 0,
                "total_tokens": usage.get("total_tokens")
                or (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
                "usage_raw": usage,
                "latency_s": round(time.time() - t0, 3),
                "attempts": attempt + 1,
            }
        except Exception as exc:  # noqa: BLE001 - retried, then recorded
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(min(20.0, 1.2 * (2 ** attempt)))
    return {"ok": False, "error": last, "text": "", "finish_reason": None,
            "model_returned": None, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "usage_raw": {}, "latency_s": None, "attempts": RETRIES}


# ---------------------------------------------------------------------------
# prompts / cells / rows
# ---------------------------------------------------------------------------
def core_cells() -> list[tuple[dict, str]]:
    return [(t, c) for t in TASKS for c in CORE_CONDS]


def optional_cells() -> list[tuple[dict, str]]:
    return [(t, c) for t in TASKS for c in OPTIONAL_CONDS]


def cell_order() -> list[tuple[dict, str]]:
    return core_cells() + optional_cells()


def make_prompt(task: dict, cond: str) -> dict:
    text = run_bench.prompt_for(task, cond, SEED)[0]["content"]
    return {"tid": task["tid"], "family": task["family"], "cond": cond, "seed": SEED,
            "prompt_sha256": sha256_text(text), "prompt": text}


def run_one(env: dict, task: dict, cond: str) -> dict:
    spec = make_prompt(task, cond)
    t0 = time.time()
    res = call_mimo(env, [{"role": "user", "content": spec["prompt"]}])
    if not res["ok"]:
        return {
            "tid": task["tid"], "family": task["family"], "cond": cond, "seed": SEED,
            "temperature": TEMPERATURE, "pass": False,
            "error": f"api: {res.get('error')}"[:300], "code_len": 0,
            "output": "", "model": MODEL, "tokens": {}, "cost_cny": 0.0,
            "latency_s": round(time.time() - t0, 2),
            "prompt_sha256": spec["prompt_sha256"], "ts": _ts(),
        }
    raw = res["text"] or ""
    code = run_bench.parse_code(run_bench.parse_json(raw) if hasattr(run_bench, "parse_json")
                                else _parse_json(raw), raw)
    ok, out = run_bench.run_tests(code, task["tests"]) if code.strip() else (False, "no code")
    pt, ct = res["prompt_tokens"], res["completion_tokens"]
    return {
        "tid": task["tid"], "family": task["family"], "cond": cond, "seed": SEED,
        "temperature": TEMPERATURE, "pass": bool(ok), "code_len": len(code),
        "output": (out or "")[-400:], "model": MODEL,
        "model_returned": res["model_returned"], "finish_reason": res["finish_reason"],
        "tokens": {"prompt_tokens": pt, "completion_tokens": ct,
                   "total_tokens": res["total_tokens"]},
        "usage_raw": res["usage_raw"],
        "cost_cny": mimo_cost_cny(pt, ct), "latency_s": res["latency_s"],
        "attempts": res["attempts"], "prompt_sha256": spec["prompt_sha256"], "ts": _ts(),
    }


def _parse_json(text: str) -> dict:
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else {}
    except Exception:  # noqa: BLE001
        import re
        m = re.search(r"\{.*\}", text or "", flags=re.S)
        if m:
            try:
                v = json.loads(m.group(0))
                return v if isinstance(v, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def prereg_gate() -> dict:
    if not PREREG.exists() or not FREEZE.exists():
        raise SystemExit("PREREG.md / results/freeze.json missing: freeze before any API call")
    frozen = json.loads(FREEZE.read_text())
    if frozen.get("prereg_sha256") != sha256_file(PREREG):
        raise SystemExit("PREREG.md hash does not match frozen fingerprint")
    return frozen


def done_keys() -> set[tuple[str, str, int]]:
    out: set[tuple[str, str, int]] = set()
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    out.add((r["tid"], r["cond"], int(r["seed"])))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    return out


def spent_so_far() -> float:
    total = 0.0
    if ROWS.exists():
        for line in ROWS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    total += float(json.loads(line).get("cost_cny") or 0.0)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    return total


def append_rows(rows: list[dict]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with ROWS.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def write_prompts() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with PROMPTS.open("w", encoding="utf-8") as fh:
        for task, cond in cell_order():
            spec = make_prompt(task, cond)
            fh.write(json.dumps({"tid": spec["tid"], "family": spec["family"],
                                 "cond": cond, "seed": SEED,
                                 "prompt_sha256": spec["prompt_sha256"],
                                 "prompt": spec["prompt"]},
                                ensure_ascii=False) + "\n")


def _run_cells(env: dict, cells: list[tuple[dict, str]], workers: int,
               label: str) -> float:
    """Run cells (already filtered for resume), chunked, respecting the stop rule."""
    spent = spent_so_far()
    chunk = max(1, workers * 2)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for start in range(0, len(cells), chunk):
            batch = cells[start:start + chunk]
            futs = [ex.submit(run_one, env, t, c) for t, c in batch]
            rows = [f.result() for f in futs]
            append_rows(rows)
            spent += sum(r.get("cost_cny") or 0 for r in rows)
            print(f"[{label}] {min(start + chunk, len(cells))}/{len(cells)} "
                  f"spent=¥{spent:.4f}", file=sys.stderr)
            if spent >= STOP_CNY:
                print(f"[{label}] STOP at ¥{spent:.4f} >= ¥{STOP_CNY} "
                      f"(hard cap ¥{HARD_CAP_CNY})", file=sys.stderr)
                break
    return spent


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------
def do_dry_run() -> int:
    frozen = prereg_gate()
    prompts = []
    errors = []
    for task, cond in cell_order():
        spec = make_prompt(task, cond)
        expect = run_bench.prompt_for(task, cond, SEED)[0]["content"]
        if spec["prompt"] != expect:
            errors.append(f"prompt mismatch: {task['tid']}/{cond}")
        prompts.append({"tid": spec["tid"], "cond": cond, "seed": SEED,
                        "prompt_sha256": spec["prompt_sha256"], "prompt": spec["prompt"]})
    empty_fail = 0
    for task in TASKS:
        ok, _ = run_bench.run_tests("", task["tests"])
        if ok:
            errors.append(f"grading sanity failed: {task['tid']}")
        else:
            empty_fail += 1
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mimo_prompts_dry.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in prompts) + "\n")
    report = {
        "mode": "dry-run", "frozen": frozen,
        "n_core_prompts": len(core_cells()), "n_optional_prompts": len(optional_cells()),
        "n_total_prompts": len(prompts),
        "expected_core_cells": 162, "expected_optional_cells": 108,
        "model": MODEL, "endpoint": (lambda: "MIMO_BASE_URL from ~/.mimo.env")(),
        "temperature": TEMPERATURE, "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "seed": SEED, "grading_empty_code_fails": empty_fail,
        "prompt_errors": errors,
    }
    DRY_RUN.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "prompt_errors"}, indent=1))
    if errors:
        print(f"DRY-RUN FAILED: {len(errors)} errors", file=sys.stderr)
        for e in errors[:20]:
            print("  -", e, file=sys.stderr)
        return 1
    print(f"DRY-RUN OK: {len(prompts)} prompts; grading sanity {empty_fail}/{len(TASKS)}")
    return 0


def _validation_cells() -> list[tuple[dict, str]]:
    return [(TASKS[i], "c0") for i in range(5)]


def do_validate(env: dict) -> int:
    frozen = prereg_gate()
    write_prompts()
    done = done_keys()
    cells = [c for c in _validation_cells() if (c[0]["tid"], c[1], SEED) not in done]
    print(f"[validate] cells={len(cells)} (already-done skipped: {5 - len(cells)})",
          file=sys.stderr)
    if cells:
        spent = _run_cells(env, cells, workers=2, label="validate")
    else:
        spent = spent_so_far()
    rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines()
            if l.strip()] if ROWS.exists() else []
    val = [r for r in rows if (r["tid"], r["cond"]) in
           {(t["tid"], "c0") for t in TASKS[:5]}]
    api_ok = sum(1 for r in val if not r.get("error"))
    code_ok = sum(1 for r in val if r.get("code_len", 0) > 0)
    passes = sum(1 for r in val if r.get("pass"))
    out = {
        "mode": "validation", "when": _ts(), "prereg_sha256": frozen["prereg_sha256"],
        "model": MODEL, "n_calls": len(val), "api_ok": api_ok, "code_extracted": code_ok,
        "pytest_pass": passes, "spent_cny_total": round(spent, 6),
        "latencies": [r.get("latency_s") for r in val],
        "prompt_tokens": [r.get("tokens", {}).get("prompt_tokens") for r in val],
        "completion_tokens": [r.get("tokens", {}).get("completion_tokens") for r in val],
        "finish_reasons": [r.get("finish_reason") for r in val],
        "errors": [r.get("error") for r in val if r.get("error")],
        "raw_usage": [r.get("usage_raw") for r in val],
    }
    VALIDATION.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("raw_usage",)}, indent=1))
    if api_ok < len(val) or len(val) < 5:
        print("VALIDATION FAILED: API errors or missing calls; stopping (Lead will be told).",
              file=sys.stderr)
        return 2
    print(f"VALIDATION OK: {api_ok}/{len(val)} API successes, {code_ok}/{len(val)} code "
          f"extracted, {passes} pytest pass; cost so far ¥{spent:.4f}")
    return 0


def do_run(env: dict, workers: int) -> int:
    frozen = prereg_gate()
    write_prompts()
    done = done_keys()
    core_todo = [(t, c) for t, c in core_cells() if (t["tid"], c, SEED) not in done]
    spent = spent_so_far()
    print(f"[run] core done={len(core_cells()) - len(core_todo)}/{len(core_cells())} "
          f"todo={len(core_todo)} spent=¥{spent:.4f}", file=sys.stderr)
    if core_todo:
        spent = _run_cells(env, core_todo, workers, "core")
    core_done = {(r["tid"], r["cond"]) for r in
                 [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines() if l.strip()]}
    core_complete = all((t["tid"], c) in core_done for t, c in core_cells())
    opt_spent = 0.0
    optional_ran = False
    if core_complete and spent < OPTIONAL_SPEND_GATE_CNY:
        opt_todo = [(t, c) for t, c in optional_cells() if (t["tid"], c, SEED) not in done]
        print(f"[optional] spent_after_core=¥{spent:.4f} < ¥{OPTIONAL_SPEND_GATE_CNY}; "
              f"todo={len(opt_todo)}", file=sys.stderr)
        if opt_todo:
            _run_cells(env, opt_todo, workers, "optional")
        optional_ran = True
    elif not core_complete:
        print("[optional] core incomplete; optional arms not run", file=sys.stderr)
    else:
        print(f"[optional] skipped: spent ¥{spent:.4f} >= gate ¥{OPTIONAL_SPEND_GATE_CNY}",
              file=sys.stderr)
    rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines() if l.strip()]
    per_cond: dict[str, dict] = {}
    for r in rows:
        d = per_cond.setdefault(r["cond"], {"n": 0, "cost": 0.0})
        d["n"] += 1
        d["cost"] = round(d["cost"] + (r.get("cost_cny") or 0.0), 8)
    total = round(sum(v["cost"] for v in per_cond.values()), 6)
    cost_log = {
        "model": MODEL, "cells_written": len(rows),
        "expected_core": 162, "expected_optional": 108,
        "per_cond": per_cond, "cost_cny_total": total,
        "hard_cap_cny": HARD_CAP_CNY, "stop_cny": STOP_CNY,
        "cap_respected": total <= HARD_CAP_CNY,
        "optional_ran": optional_ran,
        "prereg_sha256": frozen["prereg_sha256"],
        "prereg_mtime": frozen["prereg_mtime"], "frozen_at": frozen["frozen_at"],
        "first_row_ts": rows[0]["ts"] if rows else None,
        "last_row_ts": rows[-1]["ts"] if rows else None,
    }
    COST_LOG.write_text(json.dumps(cost_log, indent=1, ensure_ascii=False) + "\n")
    print(f"[run] wrote {len(rows)} rows; cost=¥{total:.4f} "
          f"(cap ¥{HARD_CAP_CNY}); optional_ran={optional_ran}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def exact_sign_test(diffs: list[float], alternative: str) -> dict:
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    n = pos + neg
    if n == 0:
        return {"pos": 0, "neg": 0, "n": 0, "p": 1.0}
    def tail_ge(k):
        return sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    def tail_le(k):
        return sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    if alternative == "greater":
        p = tail_ge(pos)
    elif alternative == "less":
        p = tail_le(pos)
    else:
        p = min(1.0, 2 * min(tail_ge(pos), tail_le(pos)))
    return {"pos": pos, "neg": neg, "n": n, "p": p}


def bootstrap(vals: list[float]) -> dict:
    rng = random.Random(BOOT_SEED)
    m = len(vals)
    means = []
    for _ in range(BOOT_N):
        s = 0.0
        for _ in range(m):
            s += vals[rng.randrange(m)]
        means.append(s / m)
    means.sort()
    return {"mean": statistics.fmean(vals),
            "ci95": [means[int(0.025 * BOOT_N)], means[int(0.975 * BOOT_N) - 1]],
            "n_boot": BOOT_N, "seed": BOOT_SEED}


def contrast(diffs: dict[str, float], label: str, alternative: str) -> dict:
    vals = [diffs[t] for t in sorted(diffs)]
    boot = bootstrap(vals)
    sign = exact_sign_test(vals, alternative)
    return {
        "label": label, "n_tasks": len(vals),
        "mean": boot["mean"], "mean_pp": 100 * boot["mean"],
        "ci95": boot["ci95"], "ci95_pp": [100 * x for x in boot["ci95"]],
        "bootstrap": boot, "sign_test": sign, "p": sign["p"],
        "improved": sum(1 for v in vals if v > 0),
        "worsened": sum(1 for v in vals if v < 0),
        "tied": sum(1 for v in vals if v == 0),
        "task_diffs": {t: diffs[t] for t in sorted(diffs)},
    }


def analyze() -> dict:
    frozen = prereg_gate()
    rows = [json.loads(l) for l in ROWS.read_text(encoding="utf-8").splitlines() if l.strip()]
    tids = [t["tid"] for t in TASKS]
    fam = {t["tid"]: t["family"] for t in TASKS}
    by = {(r["tid"], r["cond"], int(r["seed"])): r for r in rows}
    coverage = {c: sum(1 for t in tids if (t, c, SEED) in by)
                for c in CORE_CONDS + OPTIONAL_CONDS}
    errors = [r for r in rows if r.get("error")]
    def task_pass_map(cond: str) -> dict[str, int]:
        return {t: int(by[(t, cond, SEED)]["pass"]) for t in tids
                if (t, cond, SEED) in by}
    scores = {c: task_pass_map(c) for c in CORE_CONDS + OPTIONAL_CONDS}
    core_complete = all(len(scores[c]) == len(tids) for c in CORE_CONDS)
    cond_rates = {}
    for c in CORE_CONDS + OPTIONAL_CONDS:
        v = list(scores[c].values())
        if v:
            cond_rates[c] = {"n": len(v), "pass": sum(v), "pass_rate": sum(v) / len(v)}
        else:
            cond_rates[c] = {"n": 0, "pass": 0, "pass_rate": None}
    contrasts = {}
    decisions = {}
    if core_complete:
        d1 = {t: scores["c1"][t] - scores["c0"][t] for t in tids}
        d2 = {t: scores["c2"][t] - scores["c0"][t] for t in tids}
        contrasts["H1_useful_c1_minus_c0"] = contrast(d1, "H1 useful: c1 - c0", "greater")
        contrasts["H2_stale_c2_minus_c0"] = contrast(d2, "H2 stale: c2 - c0", "less")
        c1 = contrasts["H1_useful_c1_minus_c0"]
        c2 = contrasts["H2_stale_c2_minus_c0"]
        decisions["H1"] = {"supported": c1["p"] < 0.05 and c1["mean"] > 0,
                           "rule": "one-sided exact sign test p<.05 (c1-c0>0)",
                           "p": c1["p"], "mean_pp": c1["mean_pp"],
                           "ci95_pp": c1["ci95_pp"]}
        decisions["H2"] = {"supported": c2["p"] < 0.05 and c2["mean"] < 0,
                           "rule": "one-sided exact sign test p<.05 (c2-c0<0)",
                           "p": c2["p"], "mean_pp": c2["mean_pp"],
                           "ci95_pp": c2["ci95_pp"]}
        decisions["H3"] = {
            "useful_same_direction": c1["mean"] > 0,
            "stale_same_direction": c2["mean"] < 0,
            "deepseek_itt": DEEPSEEK_ITT,
            "mimo_minus_deepseek_pp": {
                "useful": c1["mean_pp"] - 100 * DEEPSEEK_ITT["useful_c1_minus_c0"],
                "stale": c2["mean_pp"] - 100 * DEEPSEEK_ITT["stale_c2_minus_c0"]},
            "note": "direction-consistency statement, not a formal test; DeepSeek values from "
                    "existing run, not a paired control",
        }
    # optional boundary (descriptive only)
    optional = {}
    if all(len(scores[c]) == len(tids) for c in ("c0", "c2", "c0f", "c2f")):
        optional["c2f_minus_c0f"] = contrast(
            {t: scores["c2f"][t] - scores["c0f"][t] for t in tids},
            "descriptive: stale+suite vs no-KB+suite (c2f - c0f)", "two-sided")
        optional["c2f_minus_c2"] = contrast(
            {t: scores["c2f"][t] - scores["c2"][t] for t in tids},
            "descriptive: full suite effect on stale (c2f - c2)", "two-sided")
        optional["c0f_minus_c0"] = contrast(
            {t: scores["c0f"][t] - scores["c0"][t] for t in tids},
            "descriptive: full suite effect on no KB (c0f - c0)", "two-sided")
    # per-family rates
    per_family = {}
    for f in sorted(set(fam.values())):
        per_family[f] = {}
        for c in CORE_CONDS + OPTIONAL_CONDS:
            vals = [scores[c][t] for t in tids if fam[t] == f and t in scores[c]]
            per_family[f][c] = {"n": len(vals),
                                "pass_rate": (sum(vals) / len(vals)) if vals else None}
    # tokens/cost/latency
    tokens = {}
    for c in CORE_CONDS + OPTIONAL_CONDS:
        cells = [by[(t, c, SEED)] for t in tids if (t, c, SEED) in by]
        tokens[c] = {
            "n": len(cells),
            "prompt_tokens": sum((r.get("tokens") or {}).get("prompt_tokens") or 0
                                 for r in cells),
            "completion_tokens": sum((r.get("tokens") or {}).get("completion_tokens") or 0
                                     for r in cells),
            "total_tokens": sum((r.get("tokens") or {}).get("total_tokens") or 0
                                for r in cells),
            "cost_cny": round(sum(r.get("cost_cny") or 0 for r in cells), 6),
            "latency_s_mean": round(statistics.fmean([r.get("latency_s") or 0
                                                      for r in cells]), 2) if cells else None,
            "finish_reasons": _counts([r.get("finish_reason") for r in cells]),
            "model_returned": _counts([r.get("model_returned") for r in cells]),
        }
    cost_total = round(sum(r.get("cost_cny") or 0 for r in rows), 6)
    # prompt integrity (recompute prompt_for and compare to stored prompts)
    prompts = []
    if PROMPTS.exists():
        prompts = [json.loads(l) for l in PROMPTS.read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    prompt_ok = 0
    prompt_total = 0
    for task, cond in cell_order():
        text = run_bench.prompt_for(task, cond, SEED)[0]["content"]
        found = [p for p in prompts if p["tid"] == task["tid"] and p["cond"] == cond
                 and int(p["seed"]) == SEED]
        prompt_total += 1
        if found and found[0].get("prompt") == text:
            prompt_ok += 1
    # key leakage check (programmatic; key value never printed)
    key_seen = False
    try:
        env = load_mimo_env()
        key = env.get("MIMO_API_KEY", "")
        if key:
            for fname in (ROWS, PROMPTS, COST_LOG):
                if fname.exists() and key in fname.read_text(encoding="utf-8",
                                                             errors="ignore"):
                    key_seen = True
    except SystemExit:
        pass
    first_ts = rows[0]["ts"] if rows else None
    frozen_before_first = None
    if first_ts:
        try:
            first_epoch = time.mktime(time.strptime(first_ts[:19], "%Y-%m-%dT%H:%M:%S"))
            frozen_before_first = PREREG.stat().st_mtime <= first_epoch
        except ValueError:
            pass
    sanity = {
        "core_cells_expected": 162, "cells_written": len(rows),
        "coverage": coverage,
        "core_complete": len(rows) >= 162 and all(coverage[c] == 54 for c in CORE_CONDS),
        "optional_complete": all(coverage[c] == 54 for c in OPTIONAL_CONDS),
        "api_error_rows": len(errors),
        "prompt_checks": [prompt_ok, prompt_total],
        "prompt_ok": prompt_ok == prompt_total and prompt_total == len(cell_order()),
        "cost_cny_total": cost_total, "hard_cap_cny": HARD_CAP_CNY,
        "stop_cny": STOP_CNY, "cost_cap_respected": cost_total <= HARD_CAP_CNY,
        "prereg_sha256": sha256_file(PREREG),
        "prereg_sha256_matches_freeze": sha256_file(PREREG) == frozen["prereg_sha256"],
        "prereg_mtime": frozen["prereg_mtime"], "frozen_at": frozen["frozen_at"],
        "first_row_ts": first_ts, "last_row_ts": rows[-1]["ts"] if rows else None,
        "prereg_frozen_before_first_call": frozen_before_first,
        "api_key_in_outputs": key_seen,
        "grading": "run_bench.run_tests hidden pytest; pass=returncode 0",
    }
    summary = {
        "schema": "model-family-mimo/1",
        "model": MODEL,
        "design": "54 tasks x {c0,c1,c2} x seed 0 = 162 core; optional c0f,c2f = 108; "
                  "all-task ITT; one prompt seed",
        "endpoint_path": "MIMO_BASE_URL (from ~/.mimo.env) + /chat/completions",
        "temperature": TEMPERATURE, "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "cells_core": sum(1 for r in rows if r["cond"] in CORE_CONDS),
        "cells_optional": sum(1 for r in rows if r["cond"] in OPTIONAL_CONDS),
        "cond_rates": cond_rates,
        "contrasts": contrasts,
        "hypothesis_decisions": decisions,
        "optional_boundary": optional,
        "per_family": per_family,
        "tokens": tokens,
        "cost_cny_total": cost_total,
        "deepseek_itt_reference": DEEPSEEK_ITT,
        "sanity": sanity,
        "analysis_plan": {
            "ITT": "all 54 tasks; per-task pass; one seed",
            "H1": "one-sided exact sign test c1-c0>0, p<.05",
            "H2": "one-sided exact sign test c2-c0<0, p<.05",
            "H3": "direction consistency with DeepSeek (+0.648 useful, -0.111 stale); "
                  "descriptive only",
            "bootstrap": f"{BOOT_N} resamples over tasks, seed {BOOT_SEED}",
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    # task table
    cols = ["tid", "family"] + [f"pass_{c}" for c in CORE_CONDS + OPTIONAL_CONDS] + \
           ["diff_H1_c1_minus_c0", "diff_H2_c2_minus_c0"]
    with TASK_TABLE.open("w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for t in tids:
            row = {"tid": t, "family": fam[t]}
            for c in CORE_CONDS + OPTIONAL_CONDS:
                row[f"pass_{c}"] = scores[c].get(t, "")
            row["diff_H1_c1_minus_c0"] = (scores["c1"][t] - scores["c0"][t]) \
                if core_complete else ""
            row["diff_H2_c2_minus_c0"] = (scores["c2"][t] - scores["c0"][t]) \
                if core_complete else ""
            fh.write("\t".join("" if row.get(c) is None else str(row.get(c))
                               for c in cols) + "\n")
    # console
    print("== MiMo pass rates (54 tasks, seed 0) ==")
    for c in CORE_CONDS + OPTIONAL_CONDS:
        r = cond_rates[c]
        if r["n"]:
            print(f"  {c:4s} {r['pass']}/{r['n']} = {100*r['pass_rate']:.1f}%")
    for name, cc in contrasts.items():
        print(f"  {name}: {cc['mean_pp']:+.2f} pp "
              f"[{cc['ci95_pp'][0]:+.2f},{cc['ci95_pp'][1]:+.2f}] p={cc['p']:.4f} "
              f"improved/worsened/tied={cc['improved']}/{cc['worsened']}/{cc['tied']}")
    for name, cc in optional.items():
        print(f"  {name}: {cc['mean_pp']:+.2f} pp "
              f"[{cc['ci95_pp'][0]:+.2f},{cc['ci95_pp'][1]:+.2f}] p={cc['p']:.4f} "
              f"improved/worsened/tied={cc['improved']}/{cc['worsened']}/{cc['tied']}")
    print(f"  decisions: {json.dumps(decisions)}")
    print(f"  cells={len(rows)} core_complete={sanity['core_complete']} "
          f"optional_complete={sanity['optional_complete']} cost=¥{cost_total:.4f} "
          f"cap_ok={sanity['cost_cap_respected']} prompt_ok={sanity['prompt_ok']} "
          f"key_in_outputs={key_seen}")
    return summary


def _counts(values: list) -> dict:
    out: dict[str, int] = {}
    for v in values:
        k = str(v)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MiMo model-family replication (c0/c1/c2)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    if not any((a.dry_run, a.validate, a.run, a.analyze, a.all)):
        ap.print_help()
        return 1
    if a.dry_run:
        return do_dry_run()
    if a.analyze and not (a.validate or a.run or a.all):
        analyze()
        return 0
    env = load_mimo_env()
    rc = 0
    if a.validate or a.all:
        rc = do_validate(env)
        if rc != 0:
            return rc
    if a.run or a.all:
        rc = do_run(env, a.workers)
        if rc != 0:
            return rc
    if a.analyze or a.all:
        analyze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
