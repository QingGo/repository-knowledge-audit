#!/usr/bin/env python3
"""Round-16 zero-cost robustness analyses: flip rate, adoption feasibility, family LOO.

No API calls. Reads only already-stored graded-completion JSONL and writes one results JSON
under this directory.  The authoritative stores are the frozen outcome_bench results:

  outcome_bench/results/bench_chat.jsonl            54 tasks x 6 conditions x 2 seeds (chat)
  outcome_bench/results/bench_reasoner.jsonl        54 tasks x 6 conditions x 1 seed (reasoner)
  outcome_bench/results/bench_c0tests_chat.jsonl    c0v/c0f (chat)
  outcome_bench/results/bench_c0tests_reasoner.jsonl c0v/c0f (reasoner)
  outcome_bench/results/bench_authority_chat.jsonl  c1v/c1f/c2a (chat)
  analysis/model_family_mimo/results/mimo_chat.jsonl MiMo replication, 54 x 5 conds x 1 seed

Each stored row = {tid, family, cond, seed, pass, code_len, output (tail-400 chars of the
pytest log), model, tokens, cost_cny, latency_s}.  It does NOT contain the completion code
(only its length), which is why the adoption-classification stretch item is INFEASIBLE.

Run: python3 analysis/flip_family_loo/run.py
Writes: analysis/flip_family_loo/results.json
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import statistics
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
KB = HERE.parent.parent
OB = KB / "outcome_bench" / "results"
MIMO = KB / "analysis" / "model_family_mimo" / "results" / "mimo_chat.jsonl"
OUT = HERE / "results.json"

Z95 = 1.959963984540054
Z_MDE = 2.801585218112968                     # z_{.975} + z_{.80}
FAMILIES = ["ce_grad", "masked_mean", "masked_softmax", "quantize", "shift_ce",
            "stable_softmax", "topk"]


# --------------------------------------------------------------------------- load
def load_jsonl(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8")
            .splitlines() if line.strip()]


def load_graded(path):
    rows = load_jsonl(path)
    return [r for r in rows if r.get("pass") is not None]


def task_map(rows):
    """{tid: {cond: {seed: pass}}} plus {tid: family}."""
    tm, fam = {}, {}
    for r in rows:
        fam[r["tid"]] = r["family"]
        tm.setdefault(r["tid"], {}).setdefault(r["cond"], {})[r["seed"]] = bool(r["pass"])
    return tm, fam


def merge(base, extra):
    out = {t: {c: dict(seeds) for c, seeds in conds.items()} for t, conds in base.items()}
    for t, conds in extra.items():
        out.setdefault(t, {})
        for c, seeds in conds.items():
            out[t].setdefault(c, {}).update(seeds)
    return out


# ------------------------------------------------------------------------ stats
def rate(tm, tid, cond):
    seeds = (tm.get(tid, {}).get(cond) or {})
    return statistics.mean(seeds.values()) if seeds else None


def rate_over(tm, tids, cond):
    vals = [rate(tm, t, cond) for t in tids if rate(tm, t, cond) is not None]
    return statistics.mean(vals) if vals else None


def wilson(k, n, z=Z95):
    """Wilson score 95% CI for k successes out of n (percent)."""
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * (center - half), 1), round(100 * (center + half), 1)]


def boot_mean(vals, n=10000, seed=0):
    a = np.asarray(vals, float)
    rng = np.random.default_rng(seed)
    means = np.array([a[rng.integers(0, len(a), len(a))].mean() for _ in range(n)])
    return [round(float(np.percentile(means, 2.5)), 3),
            round(float(np.percentile(means, 97.5)), 3)]


def boot_mean_family(vals_by_task, fam, n=10000, seed=0):
    """7-family cluster bootstrap: resample families with replacement."""
    fams = sorted(set(fam[t] for t in vals_by_task))
    by_fam = {f: [vals_by_task[t] for t in vals_by_task if fam[t] == f] for f in fams}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = rng.integers(0, len(fams), len(fams))
        pooled = [v for i in pick for v in by_fam[fams[i]]]
        out.append(float(np.mean(pooled)))
    return [round(float(np.percentile(out, 2.5)), 3),
            round(float(np.percentile(out, 97.5)), 3)]


def sign_test(vals):
    pos = sum(1 for v in vals if v > 1e-9)
    neg = sum(1 for v in vals if v < -1e-9)
    n = pos + neg
    if n == 0:
        return {"p": 1.0, "improved": 0, "worsened": 0, "tied": len(vals)}
    k = min(pos, neg)
    p = 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"p": round(min(1.0, p), 4), "improved": pos, "worsened": neg,
            "tied": len(vals) - n}


def mde80(vals):
    return round(Z_MDE * statistics.stdev(vals) / math.sqrt(len(vals)), 4)


def subset(tm, cond_min=0.5, ref_cond="c1"):
    """KB-responsive subset used by the paper (correct-note pass rate >= 0.5)."""
    return [t for t in sorted(tm)
            if rate(tm, t, ref_cond) is not None and rate(tm, t, ref_cond) >= cond_min]


# ------------------------------------------------------------------ analyses
def flip_block(tm, model, seeds_label=""):
    cells = []
    for tid in sorted(tm):
        c0 = tm[tid].get("c0") or {}
        c2 = tm[tid].get("c2") or {}
        c1 = tm[tid].get("c1") or {}
        for seed in sorted(set(c0) & set(c2)):
            cells.append({"task_id": tid, "seed": seed, "family": FAM[tid],
                          "c0": bool(c0[seed]), "c2": bool(c2[seed]),
                          "c1": bool(c1[seed]) if seed in c1 else None})
    base = [c for c in cells if c["c0"]]
    flip = sum(1 for c in base if not c["c2"])
    # reverse useful flip: c0 fails, c1 passes (same seed)
    fail_cells = [c for c in cells if not c["c0"] and c["c1"] is not None]
    rev = sum(1 for c in fail_cells if c["c1"])
    tasks_with_prior = [t for t in sorted(tm)
                        if rate(tm, t, "c0") is not None and rate(tm, t, "c0") > 0]
    task_worse = [t for t in tasks_with_prior
                  if rate(tm, t, "c2") is not None and rate(tm, t, "c2") < rate(tm, t, "c0")]
    task_better = [t for t in tasks_with_prior
                   if rate(tm, t, "c2") is not None and rate(tm, t, "c2") > rate(tm, t, "c0")]
    block = {
        "model": model, "seeds": seeds_label,
        "n_paired_cells": len(cells),
        "c0_pass_cells": {"n": len(base), "of": len(cells),
                          "rate": round(len(base) / len(cells), 3)},
        "stale_flip_cells": {"flipped_to_fail_under_c2": flip, "denominator": len(base),
                             "percent": round(100 * flip / len(base), 1) if base else None,
                             "wilson95_pct": wilson(flip, len(base))},
        "reverse_useful_flip_cells": {
            "c0_fail_cells": len(fail_cells), "passed_under_c1": rev,
            "percent": round(100 * rev / len(fail_cells), 1) if fail_cells else None,
            "wilson95_pct": wilson(rev, len(fail_cells))},
        "task_level_prior": {
            "tasks_with_c0_any_pass": len(tasks_with_prior),
            "stale_rate_below_c0": len(task_worse),
            "stale_rate_above_c0": len(task_better),
            "tied": len(tasks_with_prior) - len(task_worse) - len(task_better)},
        "claim_check_at_least_12_of_17": {
            "supports": (model == "chat" and len(base) == 17 and flip >= 12),
            "observed": f"{flip}/{len(base)}" if model == "chat" else
                        f"n/a (chat claim; {model} has {flip}/{len(base)})",
            "note": "the '12 of 17' claim is about chat baseline-pass cells; chat = "
                    "54 tasks x 2 seed-paraphrase cells, 17 c0-pass cells"},
    }
    if model == "chat":
        block["per_seed"] = {}
        for seed in sorted({c["seed"] for c in cells}):
            cs = [c for c in cells if c["seed"] == seed]
            b = [c for c in cs if c["c0"]]
            f = sum(1 for c in b if not c["c2"])
            fc = [c for c in cs if not c["c0"]]
            rv = sum(1 for c in fc if c["c1"])
            block["per_seed"][str(seed)] = {
                "c0_pass": len(b), "stale_flips": f,
                "stale_flip_pct": round(100 * f / len(b), 1) if b else None,
                "c0_fail": len(fc), "useful_flips": rv,
                "useful_flip_pct": round(100 * rv / len(fc), 1) if fc else None}
    return block


def contrast_vals(tm, tids, a, b):
    out = {}
    for t in tids:
        va, vb = rate(tm, t, a), rate(tm, t, b)
        if va is not None and vb is not None:
            out[t] = va - vb
    return out


def loo_block(tm, tids, contrasts, fam):
    """Leave-one-family-out point estimates + task bootstrap CI on the remaining tasks."""
    out = {}
    for name, (a, b) in contrasts.items():
        vals = contrast_vals(tm, tids, a, b)
        full = {"estimate": round(statistics.mean(vals.values()), 4),
                "n_tasks": len(vals),
                "ci95_task_boot": boot_mean(list(vals.values()), n=10000),
                "sign_test": sign_test(list(vals.values())),
                "mde80": mde80(list(vals.values())),
                "family_cluster_boot_ci95": boot_mean_family(vals, fam)}
        folds = {}
        for f in FAMILIES:
            keep = [t for t in vals if fam[t] != f]
            v = [vals[t] for t in keep]
            folds[f] = {"estimate_excluding": round(statistics.mean(v), 4),
                        "n_tasks": len(keep),
                        "ci95_task_boot": boot_mean(v, n=2000),
                        "ci_excludes_zero": (boot_mean(v, n=2000)[0] > 0 or
                                             boot_mean(v, n=2000)[1] < 0)}
        est = [x["estimate_excluding"] for x in folds.values()]
        all_sig = all(x["ci_excludes_zero"] for x in folds.values())
        same_sign = all((x > 0) == (full["estimate"] > 0) for x in est)
        out[name] = {"contrast": [a, b], "full": full, "loo": folds,
                     "loo_estimate_min": min(est), "loo_estimate_max": max(est),
                     "loo_range": round(max(est) - min(est), 4),
                     "sign_stable_across_loo": same_sign,
                     "all_loo_ci_exclude_zero": all_sig}
    return out


def reproduction(tm_chat, tm_reason, tm_mimo, tids_chat, tids_reason, tids_mimo):
    def eff(tm, tids, a, b):
        vals = [rate(tm, t, a) - rate(tm, t, b) for t in tids
                if rate(tm, t, a) is not None and rate(tm, t, b) is not None]
        return {"estimate": round(statistics.mean(vals), 4), "n": len(vals),
                "ci95": boot_mean(vals, n=1000), "sign": sign_test(vals),
                "mde80": mde80(vals)}

    return {
        "paper_S2_table1": {
            "chat_useful_c1_minus_c0": {"recomputed": eff(tm_chat, tids_chat, "c1", "c0"),
                                        "paper": "+0.648 [+0.519, +0.769]"},
            "chat_stale_c2_minus_c0": {"recomputed": eff(tm_chat, tids_chat, "c2", "c0"),
                                       "paper": "-0.111 [-0.194, -0.037]"},
            "chat_fullstale_c2f_minus_c2": {"recomputed": eff(tm_chat, tids_chat, "c2f", "c2"),
                                            "paper": "+0.407 [+0.287, +0.528]"},
            "reasoner_useful_c1_minus_c0": {"recomputed": eff(tm_reason, tids_reason, "c1", "c0"),
                                            "paper": "+0.593 [+0.463, +0.722]"},
            "reasoner_stale_c2_minus_c0": {"recomputed": eff(tm_reason, tids_reason, "c2", "c0"),
                                           "paper": "-0.093 [-0.185, -0.019]"},
            "reasoner_fullstale_c2f_minus_c2": {
                "recomputed": eff(tm_reason, tids_reason, "c2f", "c2"),
                "paper": "+0.889 [+0.796, +0.963]"}},
        "paper_S6_25_mimo": {
            "c1_minus_c0": {"recomputed": eff(tm_mimo, tids_mimo, "c1", "c0"),
                            "paper": "+48.15 pp [+35.19, +61.11]"},
            "c2_minus_c0": {"recomputed": eff(tm_mimo, tids_mimo, "c2", "c0"),
                            "paper": "-14.81 pp [-25.93, -3.70]"},
            "c0f_minus_c0": {"recomputed": eff(tm_mimo, tids_mimo, "c0f", "c0"),
                             "paper": "+42.59 pp [+27.78, +57.41]"},
            "c2f_minus_c2": {"recomputed": eff(tm_mimo, tids_mimo, "c2f", "c2"),
                             "paper": "+20.37 pp [+9.26, +31.48]"},
            "c2f_minus_c0f": {"recomputed": eff(tm_mimo, tids_mimo, "c2f", "c0f"),
                              "paper": "-37.04 pp [-51.85, -24.07]"}},
        "chat_c2f_minus_c0f": eff(tm_chat, tids_chat, "c2f", "c0f"),
        "chat_c1f_minus_c2f": eff(tm_chat, tids_chat, "c1f", "c2f"),
    }


def adoption_block():
    """Adoption classification feasibility check (stretch item)."""
    bench_row_keys = set()
    for fn in ("bench_chat.jsonl", "bench_reasoner.jsonl"):
        rows = load_jsonl(OB / fn)
        bench_row_keys |= set(rows[0].keys())
    conventions = (KB / "outcome_bench" / "conventions.py").read_text(encoding="utf-8")
    has_stale_tests = ("stale_tests" in conventions or "def test_stale" in conventions
                       or "stale_spec" in conventions)
    return {
        "status": "INFEASIBLE",
        "missing": [
            "raw c2 completion code: the stored benchmark rows contain tid/family/cond/seed/"
            "pass/code_len/output(tail-400 chars of the pytest log)/tokens/cost/latency, "
            "but not the generated code. run_bench.py::one() parses code, grades it, and "
            "discards it; the frozen artifact bundle (paper_workshop/agentverify2027/"
            "artifact/code/outcome_bench/results) has the same graded-row schema.",
            "an executable stale-convention test/implementation: outcome_bench/conventions.py "
            "defines the 54 tasks with intended hidden pytest tests and natural-language "
            "'stale' bullet lists, but no stale-spec tests; grade_one.py grades a supplied "
            "completion only against the intended hidden tests.",
        ],
        "stored_row_keys": sorted(bench_row_keys),
        "conventions_has_executable_stale_tests": has_stale_tests,
        "why_not_approximable": "Classification (followed stale / followed intended / neither) "
                                "requires the completion code or a programmatic decision "
                                "procedure; the pytest tail can only show failure text, not "
                                "which convention the code implemented, and no stale-spec "
                                "assertions exist. Re-collecting completions with code logging "
                                "or re-running the API is out of scope (no API calls).",
        "would_be_needed": "store the raw completion text for c2 (and c0/c1 for comparison) + "
                           "write per-task stale-convention pytest assertions, then re-grade "
                           "offline (grade_one.py-style) into three classes.",
    }


# --------------------------------------------------------------------------- main
def main():
    chat = load_graded(OB / "bench_chat.jsonl")
    reason = load_graded(OB / "bench_reasoner.jsonl")
    chat_c0 = load_graded(OB / "bench_c0tests_chat.jsonl")
    reason_c0 = load_graded(OB / "bench_c0tests_reasoner.jsonl")
    authority = load_graded(OB / "bench_authority_chat.jsonl")
    mimo = load_graded(MIMO)

    tm_chat, fam_chat = task_map(chat)
    tm_reason, fam_reason = task_map(reason)
    tm_chat = merge(tm_chat, task_map(chat_c0)[0])
    tm_chat = merge(tm_chat, task_map(authority)[0])
    tm_reason = merge(tm_reason, task_map(reason_c0)[0])
    tm_mimo, fam_mimo = task_map(mimo)

    global FAM
    FAM = fam_chat
    assert len(tm_chat) == 54 and len(tm_reason) == 54 and len(tm_mimo) == 54, \
        (len(tm_chat), len(tm_reason), len(tm_mimo))
    assert sorted(set(fam_chat.values())) == FAMILIES, sorted(set(fam_chat.values()))
    assert fam_chat == fam_reason == fam_mimo

    tids_chat = sorted(tm_chat)
    tids_reason = sorted(tm_reason)
    tids_mimo = sorted(tm_mimo)

    # per-task/per-cell outcome tables (schema: model, condition, task_id, family, pass, seed)
    cells = []
    for model, tm in (("deepseek-chat", tm_chat), ("deepseek-reasoner", tm_reason),
                      ("mimo-v2.6-flash", tm_mimo)):
        for tid in sorted(tm):
            for cond in sorted(tm[tid]):
                for seed in sorted(tm[tid][cond]):
                    cells.append({"model": model, "condition": cond, "task_id": tid,
                                  "family": tm[tid][cond].get("__fam__", fam_chat[tid]),
                                  "pass": bool(tm[tid][cond][seed]), "seed": seed})

    contrasts_chat = {
        "useful_minus_no_kb": ("c1", "c0"),
        "stale_minus_no_kb": ("c2", "c0"),
        "c2f_minus_c0f": ("c2f", "c0f"),
        "c1f_minus_c2f": ("c1f", "c2f"),
    }
    result = {
        "schema": "flip-family-loo/1",
        "generated_by": "analysis/flip_family_loo/run.py",
        "no_api_calls": True,
        "data_sources": {
            "chat": str((OB / "bench_chat.jsonl").relative_to(KB)),
            "reasoner": str((OB / "bench_reasoner.jsonl").relative_to(KB)),
            "chat_c0tests": str((OB / "bench_c0tests_chat.jsonl").relative_to(KB)),
            "reasoner_c0tests": str((OB / "bench_c0tests_reasoner.jsonl").relative_to(KB)),
            "chat_authority": str((OB / "bench_authority_chat.jsonl").relative_to(KB)),
            "mimo": str(MIMO.relative_to(KB)),
            "note": "chat: 54 tasks x 2 prompt-variant seeds; reasoner/MiMo: 1 seed. "
                    "pass in the stored row is the hidden-test verdict; code itself is not "
                    "stored (see adoption_classification).",
        },
        "store_checks": {
            "sha256_bench_chat_16": hashlib.sha256(
                (OB / "bench_chat.jsonl").read_bytes()).hexdigest()[:16],
            "sha256_bench_reasoner_16": hashlib.sha256(
                (OB / "bench_reasoner.jsonl").read_bytes()).hexdigest()[:16],
            "sha256_mimo_chat_16": hashlib.sha256(MIMO.read_bytes()).hexdigest()[:16],
            "row_counts": {"bench_chat": len(chat), "bench_reasoner": len(reason),
                           "bench_c0tests_chat": len(chat_c0),
                           "bench_c0tests_reasoner": len(reason_c0),
                           "bench_authority_chat": len(authority), "mimo_chat": len(mimo)},
            "artifact_copy_of_bench_chat": "paper_workshop/agentverify2027/artifact/code/"
                                           "outcome_bench/results/bench_chat.jsonl (graded rows, "
                                           "same schema; no code text)",
        },
        "cells": cells,
        "flip_rate": {
            "method": "cell = one (task, prompt-variant seed) pair; c0-pass cells that fail "
                      "under c2 = stale flip. Wilson 95% CI. Reverse useful flip = c0-fail "
                      "cells that pass under c1 (same seed).",
            "deepseek-chat": flip_block(tm_chat, "chat", "2 seed-paraphrases pooled"),
            "deepseek-reasoner": flip_block(tm_reason, "reasoner", "1 seed"),
            "mimo-v2.6-flash": flip_block(tm_mimo, "mimo", "1 seed; secondary replication"),
        },
        "adoption_classification": adoption_block(),
        "family_loo": {
            "scope": "chat, all 54 tasks (ITT); per-task mean over 2 seeds; "
                     "leave-one-family-out recomputes the paired mean excluding each family; "
                     "CIs are task bootstrap on remaining tasks (2,000 resamples, seed 0)",
            "families": FAMILIES,
            "n_tasks_per_family": {f: sum(1 for t in tids_chat if fam_chat[t] == f)
                                   for f in FAMILIES},
            "contrasts": loo_block(tm_chat, tids_chat, contrasts_chat, fam_chat),
        },
        "cluster_bootstrap_7_family": {
            "method": "resample the 7 families with replacement (10,000 reps, seed 0), "
                      "pooling task-level contrasts; chat-only contrasts as above",
            "contrasts": {},
        },
        "reproduction_checks": reproduction(tm_chat, tm_reason, tm_mimo,
                                            tids_chat, tids_reason, tids_mimo),
        "caveats": [
            "Seed pooling: chat cells are two prompt-paraphrase variants, not independent "
            "samples; reasoner and MiMo have one seed.",
            "Flip cells are not independent across a task (both seeds share the task family).",
            "The MiMo replication is a different run; cross-family magnitudes are descriptive.",
            "No raw completion code is stored, so adoption classification is INFEASIBLE "
            "(exact missing pieces in adoption_classification).",
            "All numbers are recomputed from the frozen graded JSONL; no new model calls.",
        ],
    }
    # family-cluster bootstrap for all four chat contrasts
    for name, (a, b) in contrasts_chat.items():
        vals = contrast_vals(tm_chat, tids_chat, a, b)
        result["cluster_bootstrap_7_family"]["contrasts"][name] = {
            "estimate": round(statistics.mean(vals.values()), 4),
            "ci95_family_cluster": boot_mean_family(vals, fam_chat),
            "ci95_task_boot": boot_mean(list(vals.values()), n=10000),
        }

    # reproduce the existing S2 7-family cluster bootstrap on the KB-responsive subset
    sub_chat = subset(tm_chat)
    sub_reason = subset(tm_reason)
    repro_fam = {}
    for model, tm, tids in (("chat", tm_chat, sub_chat),
                            ("reasoner", tm_reason, sub_reason)):
        vals = contrast_vals(tm, tids, "c2", "c0")
        repro_fam[f"{model}_stale_subset"] = {
            "n_tasks": len(vals),
            "estimate": round(statistics.mean(vals.values()), 4),
            "ci95_family_cluster_10k": boot_mean_family(vals, fam_chat),
            "published_S2": "chat [-0.23, -0.04]; reasoner [-0.24, -0.04]" if model == "chat"
                            else "reasoner [-0.24, -0.04]",
        }
        vals_u = contrast_vals(tm, tids, "c1", "c0")
        repro_fam[f"{model}_useful_subset"] = {
            "n_tasks": len(vals_u),
            "estimate": round(statistics.mean(vals_u.values()), 4),
            "ci95_family_cluster_10k": boot_mean_family(vals_u, fam_chat),
        }
    result["existing_S2_family_cluster_reproduction"] = repro_fam

    # c2f-c0f sensitivity: c0f exists for one seed only, so offer the seed-0 paired variant
    v0 = {}
    for t in tids_chat:
        a = tm_chat[t].get("c2f") or {}
        b = tm_chat[t].get("c0f") or {}
        if 0 in a and 0 in b:
            v0[t] = float(a[0]) - float(b[0])
    result["sensitivity_c2f_minus_c0f_seed0_only"] = {
        "note": "c0f was run with one prompt-variant seed; the all-54 estimate above averages "
                "c2f over two seeds and c0f over one, so this paired seed-0 variant isolates "
                "the seed composition",
        "estimate": round(statistics.mean(v0.values()), 4),
        "n_tasks": len(v0),
        "ci95": boot_mean(list(v0.values()), n=1000),
        "sign": sign_test(list(v0.values())),
    }

    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[wrote] {OUT} ({len(cells)} cells)")
    for model in ("deepseek-chat", "deepseek-reasoner", "mimo-v2.6-flash"):
        b = result["flip_rate"][model]
        print(f"  {model}: stale flip {b['stale_flip_cells']['flipped_to_fail_under_c2']}"
              f"/{b['stale_flip_cells']['denominator']} "
              f"({b['stale_flip_cells']['percent']}%, Wilson "
              f"{b['stale_flip_cells']['wilson95_pct']}); reverse useful "
              f"{b['reverse_useful_flip_cells']['passed_under_c1']}"
              f"/{b['reverse_useful_flip_cells']['c0_fail_cells']} "
              f"({b['reverse_useful_flip_cells']['percent']}%)")
    print("  adoption:", result["adoption_classification"]["status"])
    for name, blk in result["family_loo"]["contrasts"].items():
        print(f"  LOO {name}: full {blk['full']['estimate']:+.3f}, range "
              f"[{blk['loo_estimate_min']:+.3f}, {blk['loo_estimate_max']:+.3f}], "
              f"sign stable={blk['sign_stable_across_loo']}, "
              f"all CIs exclude 0={blk['all_loo_ci_exclude_zero']}, family-cluster "
              f"{blk['full']['family_cluster_boot_ci95']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
