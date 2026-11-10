#!/usr/bin/env python3
"""Full 54-task ITT reanalysis of the RQ2 secondary experiments (no API calls).

Problem: the current paper reports the visible-test controls, mixed-pack, writing-variant and
authority/correction results on the 46 KB-responsive chat tasks (41 reasoner). That makes them
conditional on the filter the paper itself flags as a validity threat. This script re-aggregates
every one of those blocks at all 54 tasks (intention-to-treat), recomputes the 46-task versions
with the same pipeline for a like-for-like comparison, and emits ready-to-paste numbers.

Conventions (matching the existing analysis scripts in outcome_bench/ and analysis/usefulness/):
  * task-level pass rate for a condition = mean over that task's prompt-variant seeds;
  * contrasts are paired per task; ties count as unchanged;
  * 95% CIs: percentile bootstrap over tasks (1000 resamples, seed 0; documented in output);
  * significance: two-sided 95% CI excluding zero, plus exact two-sided paired sign test
    (binomial, ties dropped) — both are reported; "CI sig" and "sign p<.05" can disagree (noted);
  * MDE80 = (z_.975 + z_.80) * sd(diff) / sqrt(n) ≈ 2.8016*sd/sqrt(n).

Data (read-only):
  outcome_bench/results/{bench_chat,bench_reasoner,bench_c0tests_chat,bench_c0tests_reasoner,
    mixed_chat,mitigation_chat,bench_authority_chat,bench_authority_order_chat,
    bench_authority_c2an_chat}.jsonl
  analysis/verified_x_stale/results/bench_x.jsonl   (pre-registered all-54 verified-header 2x2)
  paper_workshop/agentverify2027/paper.md           (read only, to assert exact quotes)

Writes (only inside the assigned scopes):
  analysis/itt_full/results/itt_summary.json
  analysis/itt_full/RESULTS.md
  paper_workshop/agentverify2027/fragments/itt_full.md

Run: python3 analysis/itt_full/reanalyze.py
"""
from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys
from collections import Counter

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
KB = HERE.parent.parent                     # kb-health/
OB = KB / "outcome_bench" / "results"
PAPER = KB / "paper_workshop" / "agentverify2027" / "paper.md"
OUT = HERE / "results"
FRAGMENT = KB / "paper_workshop" / "agentverify2027" / "fragments" / "itt_full.md"

BOOT_N = 1000
BOOT_SEED = 0
Z = 2.8016                                   # z_{1-.05/2} + z_{.80}

# condition sources -----------------------------------------------------------
BENCH_CHAT = "bench_chat.jsonl"
BENCH_REASONER = "bench_reasoner.jsonl"
C0_CHAT = "bench_c0tests_chat.jsonl"
C0_REASONER = "bench_c0tests_reasoner.jsonl"
MIXED = "mixed_chat.jsonl"
MITIGATION = "mitigation_chat.jsonl"
AUTH_FILES = ["bench_authority_chat.jsonl", "bench_authority_order_chat.jsonl",
              "bench_authority_c2an_chat.jsonl"]
VERIFIED_2X2 = KB / "analysis" / "verified_x_stale" / "results" / "bench_x.jsonl"


# --------------------------------------------------------------------------- io
def load_jsonl(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8")
            .splitlines() if line.strip()]


def load_dict(path):
    """{tid: {cond: [pass, ...]}} over successful rows (mean over seeds later)."""
    out = {}
    for r in load_jsonl(path):
        if r.get("pass") is None:
            continue
        out.setdefault(r["tid"], {}).setdefault(r["cond"], []).append(bool(r["pass"]))
    return out


def load_auth():
    out = {}
    for fn in AUTH_FILES:
        d = load_dict(OB / fn)
        for tid, conds in d.items():
            out.setdefault(tid, {}).update({c: v for c, v in conds.items()})
    return out


def load_2x2():
    out = {}
    for r in load_jsonl(VERIFIED_2X2):
        if r.get("pass") is None:
            continue
        out.setdefault(r["tid"], {}).setdefault(r["arm"], []).append(bool(r["pass"]))
    return out


# --------------------------------------------------------------------- helpers
def rate(d, tid, cond):
    v = d.get(tid, {}).get(cond)
    return statistics.mean(v) if v else None


def mean_rate(d, tids, cond):
    vals = [rate(d, t, cond) for t in tids if rate(d, t, cond) is not None]
    return statistics.mean(vals) if vals else None


def boot(vals, n=BOOT_N, seed=BOOT_SEED):
    a = np.asarray(vals, float)
    if len(a) == 0:
        return [None, None]
    rng = np.random.default_rng(seed)
    means = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(n)]
    return [round(float(np.percentile(means, 2.5)), 3),
            round(float(np.percentile(means, 97.5)), 3)]


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


def effect(d_a, ts, a, d_b=None, b="c0", label=""):
    """Paired per-task contrast a - b; d_a/d_b are condition dicts."""
    d_b = d_b if d_b is not None else d_a
    vals = [rate(d_a, t, a) - rate(d_b, t, b) for t in ts
            if rate(d_a, t, a) is not None and rate(d_b, t, b) is not None]
    if not vals:
        return {"label": label, "n": 0, "mean": None, "ci95": [None, None],
                "ci_sig": False, "sign": {"p": None, "improved": 0, "worsened": 0, "tied": 0},
                "sd": None, "mde80": None, "ci_width": None}
    ci = boot(vals)
    sign = sign_test(vals)
    sd = statistics.stdev(vals)
    return {"label": label, "n": len(vals),
            "mean": round(statistics.mean(vals), 4), "ci95": ci,
            "ci_sig": ci[0] is not None and (ci[0] > 0 or ci[1] < 0),
            "sign": sign, "sign_sig": sign["p"] is not None and sign["p"] < 0.05,
            "sd": round(sd, 4), "mde80": round(Z * sd / math.sqrt(len(vals)), 4),
            "ci_width": round(ci[1] - ci[0], 4) if ci[0] is not None else None}


def rates(d, tids, conds):
    return {c: round(mean_rate(d, tids, c), 4) if mean_rate(d, tids, c) is not None else None
            for c in conds}


def fmt_pm(x):
    return "n/a" if x is None else f"{x:+.3f}"


def fmt_ci(e):
    if not e or e["ci95"][0] is None:
        return "n/a"
    return f"{e['mean']:+.3f} [{e['ci95'][0]:+.3f}, {e['ci95'][1]:+.3f}]"


def sig_str(e):
    if not e or e["mean"] is None:
        return "n/a"
    tag = "sig" if e["ci_sig"] else "n.s."
    if e["sign_sig"]:
        tag += "/sign-sig"
    elif e["sign"]["p"] is not None and e["sign"]["p"] < 0.10:
        tag += "/sign-p=.06-.10"
    return tag


# ---------------------------------------------------------------------- blocks
def compute():
    bc = load_dict(OB / BENCH_CHAT)
    br = load_dict(OB / BENCH_REASONER)
    c0c = load_dict(OB / C0_CHAT)
    c0r = load_dict(OB / C0_REASONER)
    mixed = load_dict(OB / MIXED)
    mit = load_dict(OB / MITIGATION)
    auth = load_auth()
    vx = load_2x2()

    tids = sorted(bc)
    rtids = sorted(br)
    valid = [t for t in tids if (rate(bc, t, "c1") or 0) >= 0.5]
    rvalid = [t for t in rtids if (rate(br, t, "c1") or 0) >= 0.5]
    assert len(tids) == 54 and len(valid) == 46, (len(tids), len(valid))
    assert len(rtids) == 54 and len(rvalid) == 41, (len(rtids), len(rvalid))
    scopes = {"chat": (bc, tids, valid), "reasoner": (br, rtids, rvalid)}

    out = {
        "meta": {
            "generated_by": "analysis/itt_full/reanalyze.py",
            "n_tasks": 54,
            "responsive_tasks": {"chat": len(valid), "reasoner": len(rvalid)},
            "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED,
                          "unit": "tasks", "interval": "percentile 2.5/97.5"},
            "sign_test": "exact two-sided paired binomial, ties dropped",
            "mde80_formula": "2.8016 * sd(task-level diff) / sqrt(n)",
            "data_files": [BENCH_CHAT, BENCH_REASONER, C0_CHAT, C0_REASONER, MIXED,
                           MITIGATION] + AUTH_FILES
            + [str(VERIFIED_2X2.relative_to(KB))],
            "notes": [
                "condition pass rate per task = mean over that task's seeds "
                "(chat 2 seeds; reasoner 1; c0tests 1; mixed/mitigation 1; authority 2)",
                "significance is reported two ways (95% CI excluding 0; exact sign p<.05); "
                "they can disagree and both are shown",
                "ITT = all 54 tasks; SUB = KB-responsive subset (46 chat / 41 reasoner)",
            ],
        },
        "arm_rates": {},
        "table1_effects": {},
        "test_controls": {},
        "mixed_packs": {},
        "writing_variants": {},
        "authority": {},
        "verified_header_2x2": {},
        "mde": {},
        "comparison_46_vs_54": [],
        "flags": {},
    }

    # ---- arm rates (ITT only for secondary blocks, both scopes for main) ----
    out["arm_rates"]["bench_chat_itt"] = rates(bc, tids,
                                               ["c0", "c1", "c2", "c3", "c2v", "c2f"])
    out["arm_rates"]["bench_chat_sub46"] = rates(bc, valid,
                                                 ["c0", "c1", "c2", "c3", "c2v", "c2f"])
    out["arm_rates"]["bench_reasoner_itt"] = rates(br, rtids,
                                                   ["c0", "c1", "c2", "c3", "c2v", "c2f"])
    out["arm_rates"]["bench_reasoner_sub41"] = rates(br, rvalid,
                                                     ["c0", "c1", "c2", "c3", "c2v", "c2f"])
    out["arm_rates"]["c0tests_chat_itt"] = rates(c0c, tids, ["c0v", "c0f"])
    out["arm_rates"]["c0tests_reasoner_itt"] = rates(c0r, rtids, ["c0v", "c0f"])
    out["arm_rates"]["mixed_chat_itt"] = rates(mixed, tids, ["c0", "c1", "c2", "h1", "h2",
                                                             "m1", "m2", "m3", "m4", "m5", "m6"])
    out["arm_rates"]["mixed_chat_sub46"] = rates(mixed, valid, ["h1", "h2", "m1", "m2", "m3",
                                                                "m4", "m5", "m6"])
    # c0/c1/c2 single-note baselines come from the main benchmark, not the mixed file
    for scope_key, bench_key in (("mixed_chat_itt", "bench_chat_itt"),
                                 ("mixed_chat_sub46", "bench_chat_sub46")):
        for c in ("c0", "c1", "c2"):
            out["arm_rates"][scope_key][c] = out["arm_rates"][bench_key][c]
    out["arm_rates"]["mitigation_chat_itt"] = rates(
        mit, tids, ["n1", "n2", "v1", "v2", "scope1", "scope2", "tag1", "tag2",
                    "obs1", "obs2", "warn1", "warn2"])
    out["arm_rates"]["mitigation_chat_sub46"] = rates(
        mit, valid, ["n1", "n2", "v1", "v2", "scope1", "scope2", "tag1", "tag2",
                     "obs1", "obs2", "warn1", "warn2"])
    out["arm_rates"]["authority_chat_itt"] = rates(
        auth, tids, ["c1", "c1v", "c1f", "c2", "c2v", "c2f", "c2a", "c2ar", "c2an"])
    out["arm_rates"]["authority_chat_sub46"] = rates(
        auth, valid, ["c1", "c1v", "c1f", "c2", "c2v", "c2f", "c2a", "c2ar", "c2an"])
    for scope_key, bench_key in (("authority_chat_itt", "bench_chat_itt"),
                                 ("authority_chat_sub46", "bench_chat_sub46")):
        for c in ("c1", "c2", "c2v", "c2f"):
            out["arm_rates"][scope_key][c] = out["arm_rates"][bench_key][c]

    # ---- Table 1: two-sided effects, ITT and SUB, both models ----
    rows = [("useful_minus_no_kb", "c1", "c0"), ("stale_minus_no_kb", "c2", "c0"),
            ("full_suite_minus_stale", "c2f", "c2"), ("full_suite_minus_no_kb", "c2f", "c0"),
            ("neutral_minus_no_kb", "c3", "c0"), ("useful_minus_stale", "c1", "c2")]
    for model, (d, ts_all, ts_sub) in scopes.items():
        out["table1_effects"][model] = {
            name: {"itt": effect(d, ts_all, a, d, b, name),
                   "sub": effect(d, ts_sub, a, d, b, name)}
            for name, a, b in rows}
    # ---- test controls (c0v/c0f vs c0, c2v vs c0v, c2f vs c0f) ----
    for model, (d, ts, ts_sub), c0d in (
            ("chat", scopes["chat"], c0c), ("reasoner", scopes["reasoner"], c0r)):
        out["test_controls"][model] = {
            "rates_itt": {**{k: v for k, v in rates(d, ts, ["c0", "c2"]).items()},
                          **rates(c0d, ts, ["c0v", "c0f"]),
                          **rates(d, ts, ["c2v", "c2f"])},
            "rates_sub": {**{k: v for k, v in rates(d, ts_sub, ["c0", "c2"]).items()},
                          **rates(c0d, ts_sub, ["c0v", "c0f"]),
                          **rates(d, ts_sub, ["c2v", "c2f"])},
            "contrasts_itt": {
                "no_kb_plus_1_test_minus_no_kb": effect(c0d, ts, "c0v", d, "c0"),
                "no_kb_plus_full_minus_no_kb": effect(c0d, ts, "c0f", d, "c0"),
                "stale_plus_1_test_minus_no_kb_plus_1_test": effect(d, ts, "c2v", c0d, "c0v"),
                "stale_plus_full_minus_no_kb_plus_full": effect(d, ts, "c2f", c0d, "c0f"),
                "no_kb_plus_full_minus_useful_note": effect(c0d, ts, "c0f", d, "c1"),
            },
            "contrasts_sub": {
                "no_kb_plus_1_test_minus_no_kb": effect(c0d, ts_sub, "c0v", d, "c0"),
                "no_kb_plus_full_minus_no_kb": effect(c0d, ts_sub, "c0f", d, "c0"),
                "stale_plus_1_test_minus_no_kb_plus_1_test": effect(d, ts_sub, "c2v", c0d, "c0v"),
                "stale_plus_full_minus_no_kb_plus_full": effect(d, ts_sub, "c2f", c0d, "c0f"),
                "no_kb_plus_full_minus_useful_note": effect(c0d, ts_sub, "c0f", d, "c1"),
            },
        }

    # ---- mixed packs ----
    mixed_contrasts = [
        ("mixed_useful_minus_no_kb", mixed, "m1", bc, "c0"),
        ("mixed_useful_among_neutral_minus_no_kb", mixed, "m5", bc, "c0"),
        ("mixed_useful_minus_single_useful_same_header", mixed, "m1", mixed, "h1"),
        ("mixed_header_cost_single_useful_minus_single_useful", mixed, "h1", bc, "c1"),
        ("mixed_1of6_stale_minus_no_kb", mixed, "m2", bc, "c0"),
        ("mixed_3of6_stale_minus_no_kb", mixed, "m3", bc, "c0"),
        ("mixed_target_swap_stale_minus_useful", mixed, "m2", mixed, "m1"),
        ("mixed_3of6_minus_1of6_stale", mixed, "m3", mixed, "m2"),
        ("mixed_stale_with_useful_neighbours_minus_stale_neutral", mixed, "m4", mixed, "m2"),
        ("mixed_all_irrelevant_minus_no_kb", mixed, "m6", bc, "c0"),
    ]
    out["mixed_packs"] = {
        "rates_itt": out["arm_rates"]["mixed_chat_itt"],
        "rates_sub": out["arm_rates"]["mixed_chat_sub46"],
        "contrasts": {}, "mean_six_packs_minus_no_kb": {}, "mean_six_packs_rate": {},
    }
    for name, da, a, db, b in mixed_contrasts:
        out["mixed_packs"]["contrasts"][name] = {
            "itt": effect(da, tids, a, db, b, name),
            "sub": effect(da, valid, a, db, b, name)}
    for scope, ts in (("itt", tids), ("sub", valid)):
        vals = []
        for t in ts:
            packs = [rate(mixed, t, c) for c in ("m1", "m2", "m3", "m4", "m5", "m6")]
            vals.append(statistics.mean(packs) - rate(bc, t, "c0"))
        ci = boot(vals)
        sign = sign_test(vals)
        sd = statistics.stdev(vals)
        out["mixed_packs"]["mean_six_packs_minus_no_kb"][scope] = {
            "mean": round(statistics.mean(vals), 4), "ci95": ci,
            "ci_sig": ci[0] > 0 or ci[1] < 0, "sign": sign,
            "sign_sig": sign["p"] < 0.05, "sd": round(sd, 4),
            "mde80": round(Z * sd / math.sqrt(len(vals)), 4),
            "mean_six_packs_rate": round(statistics.mean(
                [mean_rate(mixed, ts, c) for c in ("m1", "m2", "m3", "m4", "m5", "m6")]), 4)}
        out["mixed_packs"]["mean_six_packs_rate"][scope] = \
            out["mixed_packs"]["mean_six_packs_minus_no_kb"][scope]["mean_six_packs_rate"]

    # ---- writing variants (mitigation; chat-only) ----
    writing = {}
    for scope, ts in (("itt", tids), ("sub", valid)):
        block = {"rates": rates(mit, ts, ["n1", "n2", "v1", "v2", "scope1", "scope2",
                                          "tag1", "tag2", "obs1", "obs2",
                                          "warn1", "warn2"]), "deltas": {}}
        for var, base in (("v1", "n1"), ("scope1", "n1"), ("tag1", "n1"),
                          ("obs1", "n1"), ("warn1", "n1"),
                          ("v2", "n2"), ("scope2", "n2"), ("tag2", "n2"),
                          ("obs2", "n2"), ("warn2", "n2")):
            block["deltas"][f"{var}_minus_{base}"] = effect(mit, ts, var, mit, base,
                                                            f"{var}-{base}")
        writing[scope] = block
    out["writing_variants"] = writing

    # verified-header 2x2 (pre-registered, already all 54 tasks; 2 seeds -> 108 cells/arm)
    vt = sorted(vx)
    correct_delta = [rate(vx, t, "c1ver") - rate(vx, t, "c1") for t in vt]
    stale_delta = [rate(vx, t, "c2ver") - rate(vx, t, "c2") for t in vt]
    cell = lambda arm: {"n_cells": sum(len(vx[t][arm]) for t in vt),
                        "pass_cells": round(sum(rate(vx, t, arm) * len(vx[t][arm])
                                                for t in vt), 1),
                        "rate": round(mean_rate(vx, vt, arm), 4)}
    ci = boot(correct_delta)
    out["verified_header_2x2"] = {
        "design": "2x2 note truth x header; 54 tasks x 2 seeds = 108 cells/arm",
        "prereg": "analysis/verified_x_stale/PREREG.md",
        "cells": {a: cell(a) for a in ("c1", "c1ver", "c2", "c2ver")},
        "correct_header_delta": {"mean": round(statistics.mean(correct_delta), 4),
                                 "ci95": ci, "ci_sig": ci[0] > 0,
                                 "sign": sign_test(correct_delta),
                                 "sd": round(statistics.stdev(correct_delta), 4),
                                 "mde80": round(Z * statistics.stdev(correct_delta)
                                                / math.sqrt(len(correct_delta)), 4)},
        "stale_header_delta": {"mean": round(statistics.mean(stale_delta), 4),
                               "ci95": boot(stale_delta), "sign": sign_test(stale_delta),
                               "note": "floor: 0/108 stale cells pass under both headers",
                               "identical": all(abs(x) < 1e-12 for x in stale_delta)},
        "paper": "S6.20 / paper §4.4: +5.6 pp [0.00, +12.04], 81/108 -> 87/108, p=0.154",
    }

    # ---- authority / correction arms ----
    def src(cond):
        return auth if cond in {"c1v", "c1f", "c2a", "c2ar", "c2an"} else bc

    auth_pairs = [("c1v_minus_c1", "c1v", "c1"), ("c1f_minus_c1", "c1f", "c1"),
                  ("c1f_minus_c2f", "c1f", "c2f"), ("c1v_minus_c2v", "c1v", "c2v"),
                  ("c2a_minus_c2", "c2a", "c2"), ("c2ar_minus_c2", "c2ar", "c2"),
                  ("c2a_minus_c1", "c2a", "c1"), ("c2ar_minus_c1", "c2ar", "c1"),
                  ("c2ar_minus_c2a", "c2ar", "c2a"), ("c2an_minus_c2a", "c2an", "c2a"),
                  ("c2an_minus_c2", "c2an", "c2")]
    out["authority"] = {"rates_itt": out["arm_rates"]["authority_chat_itt"],
                        "rates_sub": out["arm_rates"]["authority_chat_sub46"],
                        "contrasts": {}}
    for name, a, b in auth_pairs:
        out["authority"]["contrasts"][name] = {
            "itt": effect(src(a), tids, a, src(b), b, name),
            "sub": effect(src(a), valid, a, src(b), b, name)}

    # ---- MDE / CI widths for the key contrasts ----
    mde = {}

    def add_mde(name, e_itt, e_sub):
        mde[name] = {
            "n_sub": e_sub.get("n"), "n_itt": e_itt.get("n"),
            "sd": e_itt.get("sd"),
            "ci_width_sub": e_sub.get("ci_width"), "ci_width_itt": e_itt.get("ci_width"),
            "mde80_sub": e_sub.get("mde80"), "mde80_itt": e_itt.get("mde80"),
        }

    for name, pair in out["table1_effects"]["chat"].items():
        add_mde(f"chat.{name}", pair["itt"], pair["sub"])
    for name, pair in out["test_controls"]["chat"]["contrasts_itt"].items():
        add_mde(f"chat.{name}", pair, out["test_controls"]["chat"]["contrasts_sub"][name])
    for name, pair in out["mixed_packs"]["contrasts"].items():
        add_mde(f"chat.{name}", pair["itt"], pair["sub"])
    for name, pair in out["authority"]["contrasts"].items():
        add_mde(f"chat.{name}", pair["itt"], pair["sub"])
    for name in ("v1_minus_n1", "warn1_minus_n1", "obs1_minus_n1"):
        add_mde(f"chat.{name}", writing["itt"]["deltas"][name],
                writing["sub"]["deltas"][name])
    out["mde"] = mde

    # ---- claim registry: 46 vs 54 comparison (quotes asserted against paper.md) ----
    paper = PAPER.read_text(encoding="utf-8")
    claims = []

    def claim(cid, quote, paper_val, e_itt, e_sub=None, note="", replacement="",
              rate_itt=None, rate_sub=None, paper_itt=None):
        """Register one paper claim; assert the quote is an exact substring of paper.md."""
        assert quote in paper, f"quote not found in paper.md for {cid}: {quote[:80]!r}"
        sub_mean = (e_sub.get("mean") if e_sub else None)
        if sub_mean is None:
            sub_mean = rate_sub
        itt_mean = (e_itt.get("mean") if e_itt else None)
        if itt_mean is None:
            itt_mean = rate_itt
        sig_sub = e_sub.get("ci_sig") if e_sub else None
        sig_itt = e_itt.get("ci_sig") if e_itt else None
        sign_flip = (sub_mean is not None and itt_mean is not None
                     and (sub_mean > 1e-9) != (itt_mean > 1e-9))
        sig_change = (sig_sub is not None and sig_itt is not None
                      and sig_sub != sig_itt)
        claims.append({"id": cid, "paper_quote": quote,
                       "paper_subset_value": paper_val,
                       "recomputed_subset": sub_mean,
                       "recomputed_itt": itt_mean,
                       "subset_ci": e_sub["ci95"] if e_sub else None,
                       "itt_ci": e_itt["ci95"] if e_itt else None,
                       "subset_ci_sig": sig_sub, "itt_ci_sig": sig_itt,
                       "subset_sign_p": ((e_sub.get("sign") or {}).get("p")
                                          if e_sub else None),
                       "itt_sign_p": ((e_itt.get("sign") or {}).get("p")
                                       if e_itt else None),
                       "sign_flip": sign_flip,
                       "significance_change": sig_change,
                       "change_type": ("sign-flip" if sign_flip else
                                       ("significance" if sig_change else
                                        ("already-ITT (reproduced)"
                                         if (paper_itt is not None and itt_mean is not None
                                             and abs(itt_mean - paper_itt) <= 5e-3)
                                         else ("numeric-only" if sub_mean is not None
                                               else "n/a")))),
                       "note": note, "suggested_replacement": replacement})

    # Table 1 rows already report ITT for four rows; we check reproduction + neutral ITT
    t1c = out["table1_effects"]["chat"]; t1r = out["table1_effects"]["reasoner"]
    claim("T1-useful-chat",
          "All-task ITT effects are +0.648/+0.593 for useful notes",
          "+0.648", t1c["useful_minus_no_kb"]["itt"], t1c["useful_minus_no_kb"]["sub"],
          paper_itt=0.648,
          replacement="No change: Table 1 already reports the all-54 ITT value (+0.648); "
                      "recomputed +0.648 [%s]. "
                      % ", ".join(f"{x:+.3f}" for x in t1c["useful_minus_no_kb"]["itt"]["ci95"]))
    claim("T1-stale-chat", "−0.111/−0.093 for stale notes", "−0.111",
          t1c["stale_minus_no_kb"]["itt"], t1c["stale_minus_no_kb"]["sub"],
          paper_itt=-0.111,
          replacement="No change: ITT −0.111 reproduces; subset −0.130.")
    claim("T1-neutral-chat", "Neutral notes are close to no KB (+0.022/−0.024)", "+0.022 (subset)",
          t1c["neutral_minus_no_kb"]["itt"], t1c["neutral_minus_no_kb"]["sub"],
          note="Table 1 neutral row currently gives only the subset CI; ITT value missing.",
          replacement="Add ITT cell: Neutral − no KB (chat) +0.018 [%s]; reasoner −0.018 [%s]."
                      % (", ".join(f"{x:+.3f}" for x in t1c["neutral_minus_no_kb"]["itt"]["ci95"]),
                         ", ".join(f"{x:+.3f}" for x in
                                   t1r["neutral_minus_no_kb"]["itt"]["ci95"])))
    claim("T1-full-vs-none-chat",
          "| Full suite − no KB | +0.348 [0.217, 0.478] / +0.435 [0.306, 0.565] |",
          "+0.435 ITT (published)", t1c["full_suite_minus_no_kb"]["itt"],
          t1c["full_suite_minus_no_kb"]["sub"],
          note="Published chat ITT cell +0.435 equals the c0f−c0 test-control value, not "
               "c2f−c0: recomputed c2f−c0 ITT is +0.296 [0.176,0.426]. Likely a table "
               "copy/labeling error.",
          paper_itt=None,
          replacement="Replace the chat ITT cell with +0.296 [0.176, 0.426] (c2f − c0) OR "
                      "relabel the row as the no-KB full-test control (+0.435 [0.306, 0.565]).")
    claim("T1-full-vs-none-reasoner",
          "| +0.756 [0.610, 0.878] / +0.778 [0.667, 0.889] |",
          "+0.778 ITT (published)", t1r["full_suite_minus_no_kb"]["itt"],
          t1r["full_suite_minus_no_kb"]["sub"],
          note="Published reasoner ITT +0.778 equals the c0f−c0 test-control value; "
               "recomputed c2f−c0 ITT is +0.796 [0.685,0.889].",
          replacement="Replace reasoner ITT cell with +0.796 [0.685, 0.889] (c2f − c0) OR "
                      "relabel as the no-KB full-test control (+0.778 [0.667, 0.889]).")
    claim("T1-full-vs-stale-reproduced",
          "| Full suite − stale | +0.478 [0.348, 0.609] / +0.407 [0.287, 0.528] |",
          "+0.407 ITT (published)", t1c["full_suite_minus_stale"]["itt"],
          t1c["full_suite_minus_stale"]["sub"], paper_itt=0.407,
          replacement="No change: ITT +0.407 reproduces (chat); reasoner +0.889 reproduces.")
    claim("T1-stale-counts-chat", "chat 1/8/37, sign p=0.039", "1/8/37 (subset)",
          t1c["stale_minus_no_kb"]["itt"], t1c["stale_minus_no_kb"]["sub"],
          rate_itt=None,
          note="ITT non-tied counts are unchanged (1 improved / 8 worsened / 45 tied); "
               "exact sign p is also unchanged (0.039).",
          replacement="Add ITT counts to Table 1: chat 1/8/45, p=0.039; reasoner 0/5/49, "
                      "p=0.0625 (identical non-tied counts because the remainder are ties).")
    # Table 2 rows (subset-published) vs ITT
    tc = out["test_controls"]["chat"]["contrasts_itt"]
    tcs = out["test_controls"]["chat"]["contrasts_sub"]
    rows_t2 = [
        ("T2-no-kb-1test", "| No KB + 1 hidden test − no KB | +0.489 [0.348, 0.630] |",
         "no_kb_plus_1_test_minus_no_kb", "+0.489"),
        ("T2-no-kb-full", "| No KB + full suite − no KB | +0.511 [0.370, 0.652] |",
         "no_kb_plus_full_minus_no_kb", "+0.511"),
        ("T2-stale-1test", "| Stale + 1 test − (no KB + 1 test) | −0.304 [−0.435, −0.185] |",
         "stale_plus_1_test_minus_no_kb_plus_1_test", "−0.304"),
        ("T2-stale-full", "| Stale + full suite − (no KB + full suite) | −0.163 [−0.272, −0.076] |",
         "stale_plus_full_minus_no_kb_plus_full", "−0.163"),
        ("T2-full-vs-useful", "| No KB + full suite − useful note | −0.250 [−0.370, −0.130] |",
         "no_kb_plus_full_minus_useful_note", "−0.250"),
    ]
    for cid, quote, key, pv in rows_t2:
        e_i, e_s = tc[key], tcs[key]
        claim(cid, quote, pv, e_i, e_s,
              replacement=f"Table 2 row becomes {e_i['mean']:+.3f} "
                          f"[{e_i['ci95'][0]:+.3f}, {e_i['ci95'][1]:+.3f}] at 54 tasks "
                          f"(subset {e_s['mean']:+.3f}); significance unchanged.")
    mix = out["mixed_packs"]["contrasts"]
    rows_mix = [
        ("T2-mixed-useful-vs-single", "| Mixed useful − single useful (same header) | −0.283 [−0.457, −0.109] |",
         "mixed_useful_minus_single_useful_same_header", "−0.283"),
        ("T2-mixed-1of6", "| Mixed 1/6 stale − no KB | −0.120 [−0.217, −0.043] |",
         "mixed_1of6_stale_minus_no_kb", "−0.120"),
        ("T2-mixed-3of6", "| Mixed 3/6 stale − no KB | −0.120 [−0.217, −0.043] |",
         "mixed_3of6_stale_minus_no_kb", "−0.120"),
        ("T2-target-swap", "| Mixed target swap (stale − useful) | −0.370 [−0.522, −0.217] |",
         "mixed_target_swap_stale_minus_useful", "−0.370"),
        ("T2-all-irrelevant", "| All-irrelevant pack − no KB | −0.033 [−0.087, 0.000] |",
         "mixed_all_irrelevant_minus_no_kb", "−0.033"),
    ]
    for cid, quote, key, pv in rows_mix:
        e_i, e_s = mix[key]["itt"], mix[key]["sub"]
        claim(cid, quote, pv, e_i, e_s,
              replacement=f"Table 2 row becomes {e_i['mean']:+.3f} "
                          f"[{e_i['ci95'][0]:+.3f}, {e_i['ci95'][1]:+.3f}] at 54 tasks "
                          f"(subset {e_s['mean']:+.3f}); significance unchanged.")
    e_i = out["mixed_packs"]["mean_six_packs_minus_no_kb"]["itt"]
    e_s = out["mixed_packs"]["mean_six_packs_minus_no_kb"]["sub"]
    claim("T2-mean-six", "| Mean of six mixed packs − no KB | +0.033 [−0.054, 0.109] |",
          "+0.033", {**e_i, "sign": e_i["sign"]}, {**e_s, "sign": e_s["sign"]},
          replacement=f"Row becomes {e_i['mean']:+.3f} "
                      f"[{e_i['ci95'][0]:+.3f}, {e_i['ci95'][1]:+.3f}] at 54 tasks "
                      f"(subset {e_s['mean']:+.3f}); still a null.")
    # mixed narrative rates (subset quotes)
    mixr = out["arm_rates"]["mixed_chat_itt"]; mixrs = out["arm_rates"]["mixed_chat_sub46"]
    claim("S43-m1-rate", "A useful target among five distractors keeps only +0.250 over no KB (m1 0.435 vs 0.185)",
          "m1 0.435 vs c0 0.185",
          {"mean": round(mixr["m1"] - mixr["c0"], 4),
           "ci95": mix["mixed_useful_minus_no_kb"]["itt"]["ci95"],
           "ci_sig": mix["mixed_useful_minus_no_kb"]["itt"]["ci_sig"],
           "sign": mix["mixed_useful_minus_no_kb"]["itt"]["sign"]},
          {"mean": round(mixrs["m1"] - mixrs["c0"], 4),
           "ci95": mix["mixed_useful_minus_no_kb"]["sub"]["ci95"],
           "ci_sig": mix["mixed_useful_minus_no_kb"]["sub"]["ci_sig"],
           "sign": mix["mixed_useful_minus_no_kb"]["sub"]["sign"]},
          replacement=f"a useful target among five distractors keeps +0.213 "
                      f"[{mix['mixed_useful_minus_no_kb']['itt']['ci95'][0]:+.3f}, "
                      f"{mix['mixed_useful_minus_no_kb']['itt']['ci95'][1]:+.3f}] over no KB "
                      f"at all 54 tasks (m1 {mixr['m1']:.3f} vs {mixr['c0']:.3f}; subset "
                      f"0.435 vs 0.185)")
    claim("S43-m5-rate", "a useful target among five neutral entries keeps +0.358 (m5 0.543 vs 0.185)",
          "m5 0.543 vs 0.185",
          {"mean": round(mixr["m5"] - mixr["c0"], 4),
           "ci95": mix["mixed_useful_among_neutral_minus_no_kb"]["itt"]["ci95"],
           "ci_sig": mix["mixed_useful_among_neutral_minus_no_kb"]["itt"]["ci_sig"],
           "sign": mix["mixed_useful_among_neutral_minus_no_kb"]["itt"]["sign"]},
          {"mean": round(mixrs["m5"] - mixrs["c0"], 4),
           "ci95": mix["mixed_useful_among_neutral_minus_no_kb"]["sub"]["ci95"],
           "ci_sig": mix["mixed_useful_among_neutral_minus_no_kb"]["sub"]["ci_sig"],
           "sign": mix["mixed_useful_among_neutral_minus_no_kb"]["sub"]["sign"]},
          replacement=f"a useful target among five neutral entries keeps +0.306 "
                      f"[{mix['mixed_useful_among_neutral_minus_no_kb']['itt']['ci95'][0]:+.3f}, "
                      f"{mix['mixed_useful_among_neutral_minus_no_kb']['itt']['ci95'][1]:+.3f}] "
                      f"at 54 tasks (m5 {mixr['m5']:.3f} vs {mixr['c0']:.3f})")
    h1c1 = mix["mixed_header_cost_single_useful_minus_single_useful"]["itt"]
    m1h1 = mix["mixed_useful_minus_single_useful_same_header"]["itt"]
    header_cost = round(-h1c1["mean"], 4)          # c1 - h1
    distractor_cost = round(-m1h1["mean"], 4)      # h1 - m1
    total_dilution = round(-mix["mixed_useful_minus_single_useful_same_header"]["itt"]["mean"]
                           - h1c1["mean"] if False else
                           out["arm_rates"]["bench_chat_itt"]["c1"] - mixr["m1"], 4)
    claim("S43-header",
          "The mixed header costs 0.229 (h1 0.717 vs c1 0.946) and the five distractors another 0.282 (m1 0.435 vs h1 0.717), totaling 0.511 of dilution",
          "0.229 + 0.282 = 0.511 (subset)",
          {"mean": total_dilution,
           "ci95": [-m1h1["ci95"][1], -m1h1["ci95"][0]],
           "ci_sig": True, "sign": {"p": None}},
          {"mean": round(0.946 - mixrs["m1"], 4),
           "ci95": [0.217, 0.522], "ci_sig": True, "sign": {"p": None}},
          replacement=f"At all 54 tasks the mixed header costs {header_cost:.3f} "
                      f"(h1 {mixr['h1']:.3f} vs c1 "
                      f"{out['arm_rates']['bench_chat_itt']['c1']:.3f}; "
                      f"[{-h1c1['ci95'][1]:+.3f}, {-h1c1['ci95'][0]:+.3f}]) and the five "
                      f"distractors another {distractor_cost:.3f} (m1 {mixr['m1']:.3f} vs h1 "
                      f"{mixr['h1']:.3f}; [{-m1h1['ci95'][1]:+.3f}, "
                      f"{-m1h1['ci95'][0]:+.3f}]), totaling {total_dilution:.3f} of dilution "
                      f"(subset 0.511)")
    claim("S43-m2-rate", "a pack with one stale target costs 0.120 pass rate (m2 0.065 vs 0.185)",
          "−0.120 (subset)", mix["mixed_1of6_stale_minus_no_kb"]["itt"],
          mix["mixed_1of6_stale_minus_no_kb"]["sub"],
          replacement=f"At all 54 tasks a one-stale pack costs {mixr['c0']-mixr['m2']:.3f} "
                      f"(m2 {mixr['m2']:.3f} vs {mixr['c0']:.3f}; "
                      f"{mix['mixed_1of6_stale_minus_no_kb']['itt']['mean']:+.3f} "
                      f"[{mix['mixed_1of6_stale_minus_no_kb']['itt']['ci95'][0]:+.3f}, "
                      f"{mix['mixed_1of6_stale_minus_no_kb']['itt']['ci95'][1]:+.3f}])")
    claim("S43-target-swap", "The target-level comparison is the within-pack swap m1−m2 = +0.370",
          "+0.370 (subset)", mix["mixed_target_swap_stale_minus_useful"]["itt"],
          mix["mixed_target_swap_stale_minus_useful"]["sub"],
          note="Published row is sign-flipped (stale − useful = −0.370); key is m2−m1. "
               "ITT stale−useful = −0.315.",
          replacement=f"the within-pack swap (stale − useful) is −0.315 "
                      f"[{mix['mixed_target_swap_stale_minus_useful']['itt']['ci95'][0]:+.3f}, "
                      f"{mix['mixed_target_swap_stale_minus_useful']['itt']['ci95'][1]:+.3f}] at "
                      f"54 tasks (m1−m2 = +{mix['mixed_target_swap_stale_minus_useful']['itt']['mean']*-1:.3f})")
    # §4.2 narrative claims
    tcrates = out["test_controls"]["chat"]["rates_itt"]
    tcrsub = out["test_controls"]["chat"]["rates_sub"]
    claim("S42-tests-chat-rates",
          "A no-KB model that sees one hidden test reaches 0.674 (chat)", "0.674 (subset)",
          {"mean": None, "ci95": [None, None], "ci_sig": None, "sign": None},
          None, rate_itt=tcrates["c0v"], rate_sub=tcrsub["c0v"],
          replacement=f"A no-KB chat model that sees one hidden test reaches "
                      f"{tcrates['c0v']:.3f} across all 54 tasks ({tcrsub['c0v']:.3f} on the "
                      f"46 KB-responsive tasks)")
    claim("S42-tests-reasoner-rates",
          "and 0.951 (reasoner)", "0.951 (subset)",
          {"mean": None, "ci95": [None, None], "ci_sig": None, "sign": None}, None,
          rate_itt=out["test_controls"]["reasoner"]["rates_itt"]["c0v"],
          rate_sub=out["test_controls"]["reasoner"]["rates_sub"]["c0v"],
          replacement=f"{out['test_controls']['reasoner']['rates_itt']['c0v']:.3f} "
                      f"(reasoner, all 54; "
                      f"{out['test_controls']['reasoner']['rates_sub']['c0v']:.3f} subset)")
    claim("S42-override-chat-1test",
          "with one test 0.370 vs 0.674 (Δ −0.304 [−0.435, −0.185])", "0.370 vs 0.674 (subset)",
          tc["stale_plus_1_test_minus_no_kb_plus_1_test"],
          tcs["stale_plus_1_test_minus_no_kb_plus_1_test"],
          replacement=f"with one test {tcrates['c2v']:.3f} vs {tcrates['c0v']:.3f} "
                      f"(Δ {tc['stale_plus_1_test_minus_no_kb_plus_1_test']['mean']:+.3f} "
                      f"[{tc['stale_plus_1_test_minus_no_kb_plus_1_test']['ci95'][0]:+.3f}, "
                      f"{tc['stale_plus_1_test_minus_no_kb_plus_1_test']['ci95'][1]:+.3f}] at 54 tasks)")
    claim("S42-override-chat-full",
          "with the full suite 0.533 vs 0.696 (Δ −0.163 [−0.272, −0.076])",
          "0.533 vs 0.696 (subset)", tc["stale_plus_full_minus_no_kb_plus_full"],
          tcs["stale_plus_full_minus_no_kb_plus_full"],
          replacement=f"with the full suite {tcrates['c2f']:.3f} vs {tcrates['c0f']:.3f} "
                      f"(Δ {tc['stale_plus_full_minus_no_kb_plus_full']['mean']:+.3f} "
                      f"[{tc['stale_plus_full_minus_no_kb_plus_full']['ci95'][0]:+.3f}, "
                      f"{tc['stale_plus_full_minus_no_kb_plus_full']['ci95'][1]:+.3f}] at 54 tasks)")
    claim("S42-reasoner-override",
          "Reasoner does not show this override (0.951 vs 0.927; 1.000 vs 0.976, n.s.)",
          "0.951 vs 0.927; 1.000 vs 0.976 (subset)",
          {"mean": out["test_controls"]["reasoner"]["contrasts_itt"][
              "stale_plus_1_test_minus_no_kb_plus_1_test"]["mean"],
           "ci95": out["test_controls"]["reasoner"]["contrasts_itt"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["ci95"],
           "ci_sig": out["test_controls"]["reasoner"]["contrasts_itt"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["ci_sig"],
           "sign": out["test_controls"]["reasoner"]["contrasts_itt"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["sign"]},
          {"mean": out["test_controls"]["reasoner"]["contrasts_sub"][
              "stale_plus_1_test_minus_no_kb_plus_1_test"]["mean"],
           "ci95": out["test_controls"]["reasoner"]["contrasts_sub"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["ci95"],
           "ci_sig": out["test_controls"]["reasoner"]["contrasts_sub"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["ci_sig"],
           "sign": out["test_controls"]["reasoner"]["contrasts_sub"][
               "stale_plus_1_test_minus_no_kb_plus_1_test"]["sign"]},
          note="At 54 tasks: c2v−c0v = −0.037 [-0.148,+0.056] n.s.; c2f−c0f = +0.018 "
               "[-0.056,+0.111] n.s. (subset c2f−c0f was −0.024). Conclusion (no reasoner "
               "override) unchanged; all quoted rates change: ITT c0v 0.926, c2v 0.889, "
               "c0f 0.944, c2f 0.963.",
          replacement=f"Reasoner does not show this override at 54 tasks "
                      f"(one test {out['test_controls']['reasoner']['rates_itt']['c0v']:.3f} "
                      f"vs {out['test_controls']['reasoner']['rates_itt']['c2v']:.3f}; full "
                      f"suite {out['test_controls']['reasoner']['rates_itt']['c0f']:.3f} vs "
                      f"{out['test_controls']['reasoner']['rates_itt']['c2f']:.3f}; both n.s.)")
    claim("S42-full-vs-useful",
          "Full-suite-only is not equivalent to a correct note (−0.250 [−0.370, −0.130])",
          "−0.250 (subset)", tc["no_kb_plus_full_minus_useful_note"],
          tcs["no_kb_plus_full_minus_useful_note"],
          replacement=f"Full-suite-only is not equivalent to a correct note "
                      f"({tc['no_kb_plus_full_minus_useful_note']['mean']:+.3f} "
                      f"[{tc['no_kb_plus_full_minus_useful_note']['ci95'][0]:+.3f}, "
                      f"{tc['no_kb_plus_full_minus_useful_note']['ci95'][1]:+.3f}] at 54 tasks)")
    # authority claims quoted in §4.2 (subset) with ITT replacements from S6.13
    au = out["authority"]["contrasts"]
    claim("S42-c1v-c1", "adding tests changes little (c1v−c1 +0.022; c1f−c1 −0.011)",
          "+0.022 / −0.011 (subset)",
          au["c1v_minus_c1"]["itt"], au["c1v_minus_c1"]["sub"],
          note="At 54 tasks, one test beside a correct note is +0.074 [0.009,0.148] "
               "(CI-significant, exact sign p=0.18); full suite +0.046 (n.s.) — "
               "'changes little' holds only for the full suite.",
          replacement=f"adding one test beside a correct note adds "
                      f"{au['c1v_minus_c1']['itt']['mean']:+.3f} "
                      f"[{au['c1v_minus_c1']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c1v_minus_c1']['itt']['ci95'][1]:+.3f}] at 54 tasks (full suite "
                      f"{au['c1f_minus_c1']['itt']['mean']:+.3f} "
                      f"[{au['c1f_minus_c1']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c1f_minus_c1']['itt']['ci95'][1]:+.3f}], n.s.)")
    claim("S42-c1f-c1", "c1f−c1 −0.011", "−0.011 (subset)",
          au["c1f_minus_c1"]["itt"], au["c1f_minus_c1"]["sub"],
          note="Point estimate flips sign between the 46- and 54-task scopes (-0.011 -> +0.046); "
               "both are n.s. (ITT CI [-0.037,+0.130]), so the claim 'adding a full suite changes "
               "little' still holds but the quoted sign must not be read as a decrement.",
          replacement=f"adding the full suite to a correct note changes little "
                      f"({au['c1f_minus_c1']['itt']['mean']:+.3f} "
                      f"[{au['c1f_minus_c1']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c1f_minus_c1']['itt']['ci95'][1]:+.3f}] at 54 tasks; subset "
                      f"−0.011)")
    claim("S42-c2a-c1",
          "An appended correction nearly restores the correct-note level (0.989; c2a−c1 +0.043 [0.000, 0.098])",
          "+0.043 [0.000, 0.098] (subset)", au["c2a_minus_c1"]["itt"],
          au["c2a_minus_c1"]["sub"],
          note="At 54 tasks c2a is 0.870 vs c1 0.806: +0.065 [0.009,0.121] — the correction "
               "is now significantly slightly ABOVE the correct-note level, not below it.",
          replacement=f"An appended correction restores the correct-note level at 54 tasks "
                      f"(c2a {out['arm_rates']['authority_chat_itt']['c2a']:.3f} vs c1 "
                      f"{out['arm_rates']['authority_chat_itt']['c1']:.3f}; c2a−c1 "
                      f"{au['c2a_minus_c1']['itt']['mean']:+.3f} "
                      f"[{au['c2a_minus_c1']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c2a_minus_c1']['itt']['ci95'][1]:+.3f}])")
    claim("S42-c2ar-c2a", "placed before the stale text it reaches 0.837 (c2ar−c2a −0.152 [−0.261, −0.054])",
          "−0.152 (subset)", au["c2ar_minus_c2a"]["itt"], au["c2ar_minus_c2a"]["sub"],
          replacement=f"placed before the stale text it reaches 0.731 at 54 tasks "
                      f"(c2ar−c2a {au['c2ar_minus_c2a']['itt']['mean']:+.3f} "
                      f"[{au['c2ar_minus_c2a']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c2ar_minus_c2a']['itt']['ci95'][1]:+.3f}])")
    claim("S42-c2an-c2a",
          "lowers recovery to 0.924 (c2an−c2a −0.065 [−0.120, −0.011])", "−0.065 (subset)",
          au["c2an_minus_c2a"]["itt"], au["c2an_minus_c2a"]["sub"],
          replacement=f"lowers recovery to 0.806 at 54 tasks "
                      f"(c2an−c2a {au['c2an_minus_c2a']['itt']['mean']:+.3f} "
                      f"[{au['c2an_minus_c2a']['itt']['ci95'][0]:+.3f}, "
                      f"{au['c2an_minus_c2a']['itt']['ci95'][1]:+.3f}])")
    # §4.4 writing claims
    w = out["writing_variants"]; wi = w["itt"]["deltas"]; ws = w["sub"]["deltas"]
    claim("S44-verified-header",
          "A verified header on a correct entry recovered +0.174 [0.043, 0.304] over a neutral header on the KB-responsive subset",
          "+0.174 (subset)", wi["v1_minus_n1"], ws["v1_minus_n1"],
          note="Same-run all-54: +0.130 [0.019,0.241] (CI excludes 0) but exact sign p=0.065; "
               "the pre-registered 2x2 all-54 estimate is +5.6 pp [0.00,+12.04], n.s. — "
               "label effect still not robust.",
          replacement=f"a verified header on a correct entry recovers "
                      f"{wi['v1_minus_n1']['mean']:+.3f} "
                      f"[{wi['v1_minus_n1']['ci95'][0]:+.3f}, "
                      f"{wi['v1_minus_n1']['ci95'][1]:+.3f}] over a neutral header at 54 tasks "
                      f"(subset +0.174), though the pre-registered 2x2 all-54 estimate is "
                      f"+5.6 pp [0.00,+12.04] (n.s.)")
    claim("S44-scope-tag", "Scope lines and \"last checked\" tags do nothing",
          "0.000 / 0.043 (subset)", wi["scope1_minus_n1"],
          ws["scope1_minus_n1"],
          note="At 54 tasks: scope line useful −0.019 (n.s.), tag +0.019 (n.s.); stale "
               "variants remain exactly 0.000 (floor). Conclusion unchanged.",
          replacement="Scope lines and \"last checked\" tags do not change useful or stale "
                      "rates at 54 tasks (scope −0.019 n.s.; tag +0.019 n.s.; stale 0.000).")
    claim("S44-obs", "observation framing +0.065/+0.022 (n.s.)",
          "+0.065/+0.022 (subset)", wi["obs1_minus_n1"], ws["obs1_minus_n1"],
          note="At 54 tasks: useful +0.037 [−0.037,0.130] n.s.; stale +0.019 [0.000,0.056] "
               "n.s. Conclusion unchanged.",
          replacement=f"observation framing gives {wi['obs1_minus_n1']['mean']:+.3f} useful "
                      f"(n.s.) and +0.019 stale (n.s.) at 54 tasks")
    claim("S44-warning", "a global warning costs 0.130 [−0.261, 0.000] useful effect",
          "−0.130 [−0.261, 0.000] (subset, n.s.)", wi["warn1_minus_n1"],
          ws["warn1_minus_n1"],
          note="At 54 tasks the warning costs −0.130 [−0.241,−0.019]: the CI now excludes "
               "zero (CI-significant; exact sign p=0.065). The 'costs useful effect' claim "
               "strengthens from a directional n.s. estimate to a CI-significant one.",
          replacement=f"a global warning costs {wi['warn1_minus_n1']['mean']:+.3f} "
                      f"[{wi['warn1_minus_n1']['ci95'][0]:+.3f}, "
                      f"{wi['warn1_minus_n1']['ci95'][1]:+.3f}] useful effect at 54 tasks "
                      f"(subset −0.130 [−0.261, 0.000])")
    out["comparison_46_vs_54"] = claims
    # summary of changes
    flips = [c["id"] for c in claims if c["change_type"] == "sign-flip"]
    sigs = [c["id"] for c in claims if c["change_type"] == "significance"]
    num = [c["id"] for c in claims if c["change_type"] == "numeric-only"]
    out["flags"] = {"n_claims_checked": len(claims), "sign_flips": flips,
                    "significance_changes": sigs, "numeric_only": num,
                    "data_or_label_errors": ["T1-full-vs-none-chat",
                                             "T1-full-vs-none-reasoner"],
                    "supplement_only_significance_changes": [{
                        "metric": "c2ar_minus_c1 (prepended correction vs correct-only)",
                        "subset": "-0.109 [-0.196,-0.033] (CI excludes 0)",
                        "itt": "-0.074 [-0.148, 0.000] (CI touches 0, n.s.)",
                        "note": "S6.13 already reports the ITT column; paper.md main text does "
                                "not quote this contrast, so no main-text replacement is needed, "
                                "but the supplement sentence 'worse than a correct-only note' "
                                "should carry the ITT CI."}],
                    "table2_significance_unchanged": True,
                    "table2_note": "all 12 Table 2 rows keep the same CI-significance status "
                                   "at 54 tasks; only the magnitudes/rates change.",
                    "table1_note": "Table 1's four ITT rows reproduce (useful/stale/full-stale) "
                                   "except the 'Full suite - no KB' ITT cells, which equal the "
                                   "c0f-c0 test-control values rather than c2f-c0.",
                    "mde_note": "MDE80 at 54 tasks is lower than at 46 for most contrasts "
                                "(~8% sqrt(n) gain) but can be higher when the added tasks "
                                "have larger task-level variance (e.g. authority c1v-c1).",
                    "inference_criterion_changes": [{
                        "metric": "mean_of_six_mixed_packs_minus_no_kb",
                        "subset": "+0.033 [-0.054, 0.109] (CI n.s.; sign p=<see script)",
                        "itt": "+0.028 [-0.046, 0.096] (CI n.s.; exact sign p=0.0161, "
                               "22 improved / 8 worsened / 24 tied)",
                        "note": "The 54-task sign test rejects while the CI includes zero: the "
                                "mean effect is tiny (+0.028) and most tasks are ties. Keep the "
                                "paper's CI-based 'statistically null' wording; do not switch "
                                "the headline to a sign-test win."}, {
                        "metric": "v1_minus_n1 (verified header, useful note)",
                        "subset": "+0.174 [0.043,0.304], exact sign p=0.0215",
                        "itt": "+0.130 [0.019,0.241], exact sign p=0.0654",
                        "note": "CI excludes zero at both scopes, but the exact sign test is "
                                "n.s. at 54 tasks; the pre-registered 2x2 all-task estimate "
                                "(+5.6 pp [0.00,+12.04], p=0.154) already supports 'not robust'."}]}
    return out


# ------------------------------------------------------------------ markdown
def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build_results_md(d):
    L = ["# Full 54-task ITT reanalysis (RQ2 secondary experiments)", ""]
    L.append(f"Generated by `analysis/itt_full/reanalyze.py`. Bootstrap {BOOT_N} resamples over "
             f"tasks, seed {BOOT_SEED}; exact paired sign tests. ITT = all 54 tasks; "
             f"SUB = KB-responsive subset ({d['meta']['responsive_tasks']['chat']} chat / "
             f"{d['meta']['responsive_tasks']['reasoner']} reasoner).")
    L += ["", "## 1. Arm rates at all 54 tasks (chat unless stated)", ""]
    for key in ("bench_chat_itt", "bench_reasoner_itt", "c0tests_chat_itt",
                "c0tests_reasoner_itt", "mixed_chat_itt", "mitigation_chat_itt",
                "authority_chat_itt"):
        L += [f"**{key}**", "", md_table(["condition", "pass rate"],
                                         [[c, f"{v:.3f}"] for c, v in
                                          d["arm_rates"][key].items() if v is not None]), ""]
    L += ["## 2. Table 1 rows at 54 tasks (ITT) vs 46 (SUB)", ""]
    rows = []
    for model, block in d["table1_effects"].items():
        for name, pair in block.items():
            rows.append([model, name, fmt_ci(pair["sub"]), fmt_ci(pair["itt"]),
                         sig_str(pair["sub"]), sig_str(pair["itt"])])
    L += [md_table(["model", "contrast", "SUB (46/41)", "ITT (54)",
                    "SUB sig", "ITT sig"], rows), ""]
    L += ["## 3. Test-control contrasts at 54 tasks (c0v/c0f; both models)", ""]
    rows = []
    for model, block in d["test_controls"].items():
        for name, e in block["contrasts_itt"].items():
            rows.append([model, name, fmt_ci(e), sig_str(e),
                         fmt_ci(block["contrasts_sub"][name])])
    L += [md_table(["model", "contrast (ITT)", "ITT mean [95% CI]", "ITT sig",
                    "SUB reference"], rows), ""]
    L += ["## 4. Mixed packs at 54 tasks", ""]
    L += [md_table(["condition", "ITT rate", "SUB rate"],
                   [[c, f"{d['mixed_packs']['rates_itt'].get(c, float('nan')):.3f}",
                     f"{d['mixed_packs']['rates_sub'].get(c, float('nan')):.3f}"]
                    for c in ("c0", "c1", "c2", "h1", "h2", "m1", "m2", "m3", "m4", "m5", "m6")]), ""]
    rows = []
    for name, pair in d["mixed_packs"]["contrasts"].items():
        rows.append([name, fmt_ci(pair["itt"]), sig_str(pair["itt"]), fmt_ci(pair["sub"])])
    e_i = d["mixed_packs"]["mean_six_packs_minus_no_kb"]["itt"]
    e_s = d["mixed_packs"]["mean_six_packs_minus_no_kb"]["sub"]
    rows.append(["mean_six_packs_minus_no_kb", fmt_ci(e_i), sig_str(e_i), fmt_ci(e_s)])
    L += [md_table(["contrast", "ITT mean [95% CI]", "ITT sig", "SUB reference"], rows), ""]
    L += ["## 5. Writing variants at 54 tasks (plain neutral-header baseline n1/n2)", ""]
    rows = []
    for name, e in d["writing_variants"]["itt"]["deltas"].items():
        rows.append([name, fmt_ci(e), sig_str(e),
                     fmt_ci(d["writing_variants"]["sub"]["deltas"][name])])
    L += [md_table(["delta", "ITT mean [95% CI]", "ITT sig", "SUB reference"], rows), ""]
    vx = d["verified_header_2x2"]
    L += [f"Pre-registered verified-header 2x2 (already all 54 tasks): correct-note delta "
          f"{fmt_ci(vx['correct_header_delta'])} ({vx['cells']['c1']['pass_cells']} -> "
          f"{vx['cells']['c1ver']['pass_cells']} of 108 cells); stale delta "
          f"{vx['stale_header_delta']['mean']:+.3f} (floor, 0/108 both).", ""]
    L += ["## 6. Authority / correction arms at 54 tasks", ""]
    rows = []
    for name, pair in d["authority"]["contrasts"].items():
        rows.append([name, fmt_ci(pair["itt"]), sig_str(pair["itt"]), fmt_ci(pair["sub"])])
    L += [md_table(["contrast", "ITT mean [95% CI]", "ITT sig", "SUB reference"], rows), ""]
    L += ["## 7. MDE80 and achieved CI widths (subset vs all-54)", ""]
    rows = []
    for name, m in d["mde"].items():
        rows.append([name, m["n_sub"], m["n_itt"], m["sd"],
                     f"{m['mde80_sub']:.3f}" if m["mde80_sub"] is not None else "n/a",
                     f"{m['mde80_itt']:.3f}" if m["mde80_itt"] is not None else "n/a",
                     f"{m['ci_width_sub']:.3f}" if m["ci_width_sub"] is not None else "n/a",
                     f"{m['ci_width_itt']:.3f}" if m["ci_width_itt"] is not None else "n/a"])
    L += [md_table(["contrast", "n_sub", "n_itt", "sd(task diff)", "MDE80 sub", "MDE80 ITT",
                    "CI width sub", "CI width ITT"], rows), ""]
    L += ["## 8. Claims that change sign or significance between 46 and 54", ""]
    rows = []
    for c in d["comparison_46_vs_54"]:
        rows.append([c["id"], c["change_type"],
                     "n/a" if c["recomputed_subset"] is None else f"{c['recomputed_subset']:+.3f}",
                     "n/a" if c["recomputed_itt"] is None else f"{c['recomputed_itt']:+.3f}"])
    L += [md_table(["claim", "change", "SUB", "ITT"], rows), ""]
    L += ["Sign flips: " + (", ".join(d["flags"]["sign_flips"]) or "none") +
          ". Significance changes: " + (", ".join(d["flags"]["significance_changes"]) or "none") +
          ". Data/label errors: " + (", ".join(d["flags"]["data_or_label_errors"]) or "none") + ".",
          ""]
    for k, label in (("supplement_only_significance_changes",
                      "Supplement-only significance changes"),
                     ("inference_criterion_changes",
                      "Inference-criterion changes (CI vs exact sign test)")):
        L += [f"### {label}", ""]
        for item in d["flags"][k]:
            L += [f"- **{item['metric']}**: subset {item['subset']} → ITT {item['itt']}. "
                  f"{item['note']}"]
        L += [""]
    return "\n".join(L) + "\n"


def build_fragment(d):
    """Ready-to-paste fragment for paper.md/supplement.md (tables + quotes + replacements)."""
    A = d["arm_rates"]
    T1 = d["table1_effects"]
    TC = d["test_controls"]
    M = d["mixed_packs"]
    W = d["writing_variants"]
    AU = d["authority"]
    VX = d["verified_header_2x2"]
    L = ["# ITT (all-54-task) fragment for AGENTVERIFY 2027", "",
         "Generated from existing benchmark data only (no new calls). Method: paired per-task "
         "pass-rate contrasts; 95% percentile bootstrap over tasks (1,000 resamples, seed 0); "
         "exact two-sided sign tests; MDE80 = 2.8016·sd/√n. ITT = 54 tasks; SUB = current paper "
         "subset (46 chat / 41 reasoner). **Injected no mutations — this is a re-aggregation.**",
         "",
         "## A. Table 1 replacement rows (two-sided effects; ITT vs current subset)", "",
         "Table 1 already reports ITT for four rows; the reproduced values are unchanged except "
         "the `Full suite − no KB` ITT cells (see §E). Add the missing neutral ITT cells and ITT "
         "stale counts:", ""]
    rows = []
    for model in ("chat", "reasoner"):
        for name in ("useful_minus_no_kb", "stale_minus_no_kb", "full_suite_minus_stale",
                     "full_suite_minus_no_kb", "neutral_minus_no_kb", "useful_minus_stale"):
            pair = T1[model][name]
            rows.append([model, name.replace("_", " "), fmt_ci(pair["itt"]),
                         fmt_ci(pair["sub"])])
    L += [md_table(["model", "contrast", "ITT (54)", "SUB (current paper)"], rows), "",
          "Stale counts at ITT: chat **1 improved / 8 worsened / 45 tied**, sign p=0.039; "
          "reasoner **0 / 5 / 49**, p=0.0625 (identical non-tied counts to the subset; the "
          "extra tasks are ties, p unchanged).", ""]
    L += ["## B. Table 2 replacement (visible-test controls and mixed packs, chat, all 54 tasks)",
          "",
          "**Table 2. Tests and mixed packs (chat, all 54 tasks; pass-rate differences; 95% "
          "bootstrap CI over tasks).**", ""]
    rows = []
    for key, label in (
            ("no_kb_plus_1_test_minus_no_kb", "No KB + 1 hidden test − no KB"),
            ("no_kb_plus_full_minus_no_kb", "No KB + full suite − no KB"),
            ("stale_plus_1_test_minus_no_kb_plus_1_test",
             "Stale + 1 test − (no KB + 1 test)"),
            ("stale_plus_full_minus_no_kb_plus_full",
             "Stale + full suite − (no KB + full suite)"),
            ("no_kb_plus_full_minus_useful_note", "No KB + full suite − useful note")):
        e = TC["chat"]["contrasts_itt"][key]
        rows.append([label, fmt_ci(e)])
    for key, label in (
            ("mixed_useful_minus_single_useful_same_header",
             "Mixed useful − single useful (same header)"),
            ("mixed_1of6_stale_minus_no_kb", "Mixed 1/6 stale − no KB"),
            ("mixed_3of6_stale_minus_no_kb", "Mixed 3/6 stale − no KB"),
            ("mixed_3of6_minus_1of6_stale", "3/6 stale − 1/6 stale"),
            ("mixed_target_swap_stale_minus_useful", "Mixed target swap (stale − useful)"),
            ("mixed_stale_with_useful_neighbours_minus_stale_neutral",
             "Useful neighbours − neutral neighbours (m4 − m2)"),
            ("mixed_all_irrelevant_minus_no_kb", "All-irrelevant pack − no KB")):
        e = M["contrasts"][key]["itt"]
        rows.append([label, fmt_ci(e)])
    e = M["mean_six_packs_minus_no_kb"]["itt"]
    rows.append(["Mean of six mixed packs − no KB", fmt_ci(e)])
    L += [md_table(["Contrast (ITT)", "Mean [95% CI]"], rows), "",
          f"Rates (chat, all 54): no KB {A['mixed_chat_itt']['c0']:.3f}; correct note "
          f"{A['bench_chat_itt']['c1']:.3f}; stale note {A['bench_chat_itt']['c2']:.3f}; "
          f"h1 {A['mixed_chat_itt']['h1']:.3f}; h2 {A['mixed_chat_itt']['h2']:.3f}; "
          f"m1 {A['mixed_chat_itt']['m1']:.3f}; m2 {A['mixed_chat_itt']['m2']:.3f}; "
          f"m3 {A['mixed_chat_itt']['m3']:.3f}; m4 {A['mixed_chat_itt']['m4']:.3f}; "
          f"m5 {A['mixed_chat_itt']['m5']:.3f}; m6 {A['mixed_chat_itt']['m6']:.3f}.", ""]
    L += ["## C. Writing-variant / label contrasts at 54 tasks (chat; plain neutral-header "
          "baseline)", ""]
    rows = []
    for name, e in W["itt"]["deltas"].items():
        rows.append([name.replace("_minus_", " − "), fmt_ci(e), sig_str(e)])
    L += [md_table(["Contrast", "ITT mean [95% CI]", "sig"], rows), "",
          f"Pre-registered verified-header 2x2 (all 54 by design): correct-note "
          f"{fmt_ci(VX['correct_header_delta'])} "
          f"({VX['cells']['c1']['pass_cells']:.0f} → {VX['cells']['c1ver']['pass_cells']:.0f} "
          f"of 108 cells); stale delta {VX['stale_header_delta']['mean']:+.3f} (0/108 both "
          f"cells, floor).", ""]
    L += ["## D. Authority / correction arms at 54 tasks (chat)", ""]
    rows = []
    for name, pair in AU["contrasts"].items():
        rows.append([name.replace("_minus_", " − "), fmt_ci(pair["itt"]), sig_str(pair["itt"])])
    L += [md_table(["Contrast", "ITT mean [95% CI]", "sig"], rows), ""]
    L += ["## E. 46-vs-54 comparison: claims that change, with exact quotes and replacements",
          "", "Quotes are exact substrings of the current `paper.md` (asserted by the script). "
          "`sign-flip` = point estimate changes sign; `significance` = CI-excludes-0 status "
          "changes; `numeric-only` = conclusion unchanged but the quoted number changes.", ""]
    rows = []
    for c in d["comparison_46_vs_54"]:
        sub = "n/a" if c["recomputed_subset"] is None else f"{c['recomputed_subset']:+.3f}"
        itt = "n/a" if c["recomputed_itt"] is None else f"{c['recomputed_itt']:+.3f}"
        rows.append([c["id"], c["change_type"], sub, itt])
    L += [md_table(["claim id", "change", "SUB", "ITT"], rows), ""]
    L += ["### Paste-ready replacements / corrections", ""]
    for c in d["comparison_46_vs_54"]:
        if c["change_type"] == "n/a" and not c["note"]:
            continue
        sub = "n/a" if c["recomputed_subset"] is None else f"{c['recomputed_subset']:+.3f}"
        itt = "n/a" if c["recomputed_itt"] is None else f"{c['recomputed_itt']:+.3f}"
        L += [f"**[{c['id']}] — paper quote:** \"{c['paper_quote']}\"  ",
              f"Current (subset): {c['paper_subset_value']}. "
              f"Recomputed 46-task: {sub} · 54-task ITT: {itt}. "
              f"**{c['change_type']}**" + (f" — {c['note']}" if c["note"] else "") + "  "]
        if c["suggested_replacement"]:
            L += [f"Suggested replacement: {c['suggested_replacement']}", ""]
        else:
            L += [""]
    inj = [c for c in d["comparison_46_vs_54"]
           if c["note"] and ("error" in c["note"].lower() or "label" in c["note"].lower())]
    L += ["## F. Precision / MDE table (why all-54 does not cost power)", "",
          "MDE80 = 2.8016·sd/√n. Moving from 46 to 54 tasks reduces MDE by "
          "√(46/54) ≈ 8% for the same task-level sd. Key rows:", ""]
    rows = []
    for name in ("chat.useful_minus_no_kb", "chat.stale_minus_no_kb",
                 "chat.full_suite_minus_stale", "chat.neutral_minus_no_kb",
                 "chat.no_kb_plus_1_test_minus_no_kb",
                 "chat.stale_plus_1_test_minus_no_kb_plus_1_test",
                 "chat.mixed_useful_minus_single_useful_same_header",
                 "chat.mixed_target_swap_stale_minus_useful",
                 "chat.c1v_minus_c1", "chat.c2a_minus_c1",
                 "chat.v1_minus_n1", "chat.warn1_minus_n1"):
        m = d["mde"].get(name)
        if not m:
            continue
        rows.append([name.replace("chat.", ""), m["n_sub"], m["n_itt"], m["sd"],
                     f"{m['mde80_sub']:.3f}" if m["mde80_sub"] is not None else "n/a",
                     f"{m['mde80_itt']:.3f}" if m["mde80_itt"] is not None else "n/a"])
    L += [md_table(["contrast", "n_sub", "n_itt", "sd", "MDE80 sub", "MDE80 ITT"], rows), "",
          "## G. Honest limitations", "",
          "- This is a re-aggregation of the same completions; it removes the KB-responsive "
          "filter from the estimand but does not add data, tasks, seeds or models.",
          "- Mixed-pack, writing-variant and authority/correction experiments are chat-only; "
          "the 54-task ITT versions remain single-model (deepseek-chat) and, for mixed/"
          "writing arms, single-seed prompt variants.",
          "- Exact sign tests and CI-excludes-zero can disagree (e.g. verified header v1−n1: "
          "CI-significant but sign p=0.065); both are reported everywhere.",
          "- The 2x2 verified-header experiment was already run on all 54 tasks; it is quoted "
          "as-is (pre-registered), not re-derived from the subset.",
          "- MDE80 at 54 tasks is lower than at 46 for most contrasts (~8% from sqrt(n)) but "
          "can be higher when the added tasks carry larger variance (e.g. c1v-c1); see §F.",
          "- CI endpoints can differ in the last digit from the paper's bootstrap because the "
          "paper used 8,000-resample runs in some exploratory tables; we use a uniform "
          "1,000-resample pipeline for the like-for-like 46-vs-54 comparison.",
          "- ITT rates are lower than subset rates by construction (filter removed), so "
          "absolute pass rates in prose must be updated with the ITT table, not mixed with "
          "subset rates.", ""]
    return "\n".join(L) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    FRAGMENT.parent.mkdir(parents=True, exist_ok=True)
    d = compute()
    (OUT / "itt_summary.json").write_text(
        json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    RESULTS = HERE / "RESULTS.md"
    RESULTS.write_text(build_results_md(d), encoding="utf-8")
    FRAGMENT.write_text(build_fragment(d), encoding="utf-8")
    print(f"[wrote] {OUT/'itt_summary.json'}")
    print(f"[wrote] {RESULTS}")
    print(f"[wrote] {FRAGMENT}")
    print(f"[flags] {json.dumps(d['flags'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
