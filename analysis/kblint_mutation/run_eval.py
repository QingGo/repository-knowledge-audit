#!/usr/bin/env python3
"""Run the kblint mutation evaluation: scan every fixture + natural corpus, compute
TP/FP/FN/TN, precision/recall/FPR, disposition split, runtime, and natural precision.

Deterministic, offline, stdlib only. Writes only under this directory (`results/`).
Does NOT modify kb-health/kblint (read-only tool use: `python3 -m kblint scan`).

Inputs:
  fixtures/MANIFEST.json           built by mutate.py
  results/natural_verification.jsonl  manual verification of natural findings
                                   (written by hand; keyed by corpus+doc+rule+subject)
Outputs:
  results/cases.jsonl              one row per mutant scan
  results/findings_injected.jsonl  findings from mutant scans
  results/natural_findings.jsonl   natural findings + verification verdicts
  results/summary.json             all metrics
  results/RESULTS_TABLE.md         paper-ready tables

Run: python3 run_eval.py [--skip-natural] [--quick]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parent.parent                      # kb-health/
KBLINT = KB / "kblint"
OUT = HERE / "results"
NOW = "2026-11-05"
FIXTURES = HERE / "fixtures"

LOCAL_REPOS = {
    "R2": "/HOME/code/R2",
    "R3": "/HOME/code/R3",
    "R5": "/HOME/code/R5",
    "R4": "/HOME/code/R4",
    "R1": "/HOME/code/R1",
}
SAMPLE_REPO = KBLINT / "examples/sample_repo"
SAMPLE_CONFIG = KBLINT / "examples/sample.kblint.json"
NANOV41_CORPUS = KB / "corpus/R0"


def load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip()]


def write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def kblint_version():
    text = (KBLINT / "kblint/__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "unknown"


def rule_hashes():
    out = {}
    for p in sorted((KBLINT / "kblint/rules").glob("r*.py")):
        out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    out["config.py"] = hashlib.sha256(
        (KBLINT / "kblint/config.py").read_bytes()).hexdigest()[:16]
    return out


def scan(config_path: Path, out_dir: Path) -> dict:
    """Run one kblint scan; return findings/queue/summary/runtime."""
    if out_dir.exists():
        for p in out_dir.iterdir():
            p.unlink()
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "kblint", "scan", "--config", str(config_path),
         "--out", str(out_dir), "--now", NOW, "--quiet"],
        cwd=str(KBLINT), capture_output=True, text=True)
    dt = time.perf_counter() - t0
    findings = load_jsonl(out_dir / "findings.jsonl") if (out_dir / "findings.jsonl").exists() else []
    queue = load_jsonl(out_dir / "audit_queue.jsonl") if (out_dir / "audit_queue.jsonl").exists() else []
    summary = (out_dir / "summary.md").read_text(encoding="utf-8") \
        if (out_dir / "summary.md").exists() else ""
    docs = claims = None
    m = re.search(r"docs scanned: (\d+); claims extracted: (\d+)", summary)
    if m:
        docs, claims = int(m.group(1)), int(m.group(2))
    return {"exit": proc.returncode, "stderr": proc.stderr.strip()[:500],
            "runtime_s": dt, "findings": findings, "queue": queue,
            "docs": docs, "claims": claims}


def finding_matches(f, rule, doc, tokens):
    if f.get("rule") != rule:
        return False
    if doc and f.get("doc") != doc:
        return False
    if not tokens:
        return True
    # match on the finding subject only: token lists name the target reference/target text,
    # so evidence/queue context cannot accidentally make a negative control "fire".
    hay = str(f.get("subject") or "")
    return any(t in hay for t in tokens)


def run_injected(manifest):
    cases, rows, all_findings = manifest["cases"], [], []
    for i, case in enumerate(cases):
        out_dir = OUT / "scans" / case["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        res = scan(HERE / case["config_path"], out_dir)
        tokens = case.get("target_tokens") or []
        hit = [f for f in res["findings"]
               if finding_matches(f, case["rule"], case["target_doc"], tokens)]
        detected = bool(hit)
        expect = case["expect"]
        if case["mutation"] == "positive" or (
                case["mutation"] == "bug_probe" and case["expect"] == "detected"):
            outcome = "TP" if detected else "FN"
        else:
            outcome = "FP" if detected else "TN"
        disp = Counter(f.get("disposition") for f in hit)
        row = {
            "case_id": case["id"], "rule": case["rule"], "mutation": case["mutation"],
            "target_doc": case["target_doc"], "expect": expect, "detected": detected,
            "outcome": outcome, "target_tokens": tokens,
            "n_target_findings": len(hit), "target_dispositions": dict(disp),
            "n_findings_total": len(res["findings"]),
            "n_findings_by_rule": dict(Counter(f["rule"] for f in res["findings"])),
            "n_queue": len(res["queue"]), "docs": res["docs"], "claims": res["claims"],
            "runtime_s": round(res["runtime_s"], 4), "exit": res["exit"],
            "stderr": res["stderr"],
            "target_findings": [{"rule": f["rule"], "doc": f.get("doc"),
                                 "locator": f.get("locator"),
                                 "disposition": f.get("disposition"),
                                 "severity": f.get("severity"),
                                 "subject": f.get("subject")} for f in hit],
        }
        rows.append(row)
        for f in res["findings"]:
            all_findings.append({"case_id": case["id"], "rule": f["rule"],
                                 "doc": f.get("doc"), "locator": f.get("locator"),
                                 "disposition": f.get("disposition"),
                                 "severity": f.get("severity"),
                                 "subject": f.get("subject")})
        if (i + 1) % 10 == 0:
            print(f"  [injected] {i + 1}/{len(cases)} cases")
    return rows, all_findings


def metrics(rows):
    main = [r for r in rows if r["mutation"] != "bug_probe"]
    probes = [r for r in rows if r["mutation"] == "bug_probe"]
    by_rule = {}
    for rule in sorted({r["rule"] for r in main}):
        rs = [r for r in main if r["rule"] == rule]
        tp = sum(1 for r in rs if r["outcome"] == "TP")
        fn = sum(1 for r in rs if r["outcome"] == "FN")
        fp = sum(1 for r in rs if r["outcome"] == "FP")
        tn = sum(1 for r in rs if r["outcome"] == "TN")
        npos = tp + fn
        nneg = fp + tn
        disp = Counter()
        for r in rs:
            if r["outcome"] == "TP":
                disp.update(r["target_dispositions"])
        neg_claims = sum(r["claims"] or 0 for r in rs if r["mutation"] != "positive")
        by_rule[rule] = {
            "n_mutants": len(rs), "n_positive": npos, "n_controls_negatives": nneg,
            "negative_scan_claims": neg_claims,
            "fp_per_100_claims": (100.0 * fp / neg_claims) if neg_claims else None,
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": (tp / (tp + fp)) if (tp + fp) else None,
            "recall": (tp / npos) if npos else None,
            "false_positive_rate": (fp / nneg) if nneg else None,
            "tp_dispositions": dict(disp),
        }
    tp = sum(v["tp"] for v in by_rule.values())
    fn = sum(v["fn"] for v in by_rule.values())
    fp = sum(v["fp"] for v in by_rule.values())
    tn = sum(v["tn"] for v in by_rule.values())
    neg_claims_all = sum(r["claims"] or 0 for r in main if r["mutation"] != "positive")
    overall = {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "fp_per_100_claims": (100.0 * fp / neg_claims_all) if neg_claims_all else None,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "recall": (tp / (tp + fn)) if (tp + fn) else None,
        "false_positive_rate": (fp / (fp + tn)) if (fp + tn) else None,
    }
    by_mutation = {}
    for m in ("negative_control", "positive", "hard_negative"):
        rs = [r for r in main if r["mutation"] == m]
        by_mutation[m] = {"n": len(rs),
                          "outcome_counts": dict(Counter(r["outcome"] for r in rs))}
    runtimes = [r["runtime_s"] for r in main]
    return {"by_rule": by_rule, "overall": overall, "by_mutation": by_mutation,
            "runtime": {"n_scans": len(main),
                        "median_s": round(statistics.median(runtimes), 3),
                        "p90_s": round(sorted(runtimes)[int(0.9 * len(runtimes)) - 1], 3),
                        "max_s": round(max(runtimes), 3),
                        "median_docs": statistics.median(
                            [r["docs"] for r in main if r["docs"] is not None]) if main else None,
                        "median_claims": statistics.median(
                            [r["claims"] for r in main if r["claims"] is not None]) if main else None},
            "bug_probes": probes}


R9_PRIMARY_DOCS = ["AGENTS.md", "CLAUDE.md", "docs/AGENTS.md", "SKILL.md", "**/SKILL.md"]
R9_ALLOW_MISSING = [r"^(artifacts|weights|runs|outputs|dist|build|node_modules)/"]
KB_DOCS = ["AGENTS.md", "CLAUDE.md", "README.md", "README_zh.md", "README_CN.md",
           "README_EN.md", "CONTRIBUTING.md", "CHANGELOG.md", "SECURITY.md",
           "COS_REPRO.md", "docs/**/*.md", "**/AGENTS.md", "**/SKILL.md"]


def _write_cfg(name, cfg):
    CFG = FIXTURES / "configs"
    CFG.mkdir(parents=True, exist_ok=True)
    path = CFG / f"natural_{name}.json"
    path.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    return str(path)


def natural_configs():
    """Natural scan configs.

    r9-primary   : the recommended AGENTS-style reference-check scope
                   (docs/AGENTS.md/CLAUDE.md/SKILL.md) with the example config's
                   allow_missing classes; the paper-facing natural R9 sample.
    r9-extended  : broader KB docs (README/docs) with the same allow_missing list;
                   transparency sample that exposes generated-output/illustrative FPs.
    r7-git       : broad KB docs, R7 only (references/R3 off), git enabled.
    """
    out = []
    for repo, path in LOCAL_REPOS.items():
        out.append((f"{repo}:r9-primary", _write_cfg(f"r9primary_{repo}", {
            "repo": path, "docs": R9_PRIMARY_DOCS,
            "exclude": ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.venv/**"],
            "git": {"enabled": False}, "now": NOW,
            "references": {"enabled": True, "allow_missing": R9_ALLOW_MISSING}})))
        out.append((f"{repo}:r9-extended", _write_cfg(f"r9ext_{repo}", {
            "repo": path, "docs": KB_DOCS,
            "exclude": [".git/**", "node_modules/**", "dist/**", ".pytest_cache/**",
                        "build/**", ".venv/**", "site/**", "**/testdata/**"],
            "git": {"enabled": False}, "now": NOW,
            "references": {"enabled": True, "allow_missing": R9_ALLOW_MISSING}})))
        out.append((f"{repo}:r7-git", _write_cfg(f"r7git_{repo}", {
            "repo": path, "docs": KB_DOCS,
            "exclude": [".git/**", "node_modules/**", "dist/**", ".pytest_cache/**",
                        "build/**", ".venv/**", "site/**"],
            "git": {"enabled": True}, "now": NOW,
            "rules": {"R3": False, "R4": False}, "references": {"enabled": False}})))
    # shipped sample repo known-defect check (R4 enabled in the shipped config; separate)
    out.append(("sample_repo:shipped", str(SAMPLE_CONFIG)))
    # R0 corpus snapshot (no git; R9 surface)
    out.append(("R0:corpus", _write_cfg("R0_corpus", {
        "repo": str(NANOV41_CORPUS), "docs": ["**/*.md"], "exclude": [".git/**"],
        "git": {"enabled": False}, "now": NOW,
        "references": {"enabled": True, "allow_missing": R9_ALLOW_MISSING}})))
    return out


def run_natural(repeats=3):
    results, all_findings = {}, []
    for name, cfg_path in natural_configs():
        safe = name.replace(":", "_").replace("/", "_")
        out_dir = OUT / "scans" / f"natural_{safe}"
        out_dir.mkdir(parents=True, exist_ok=True)
        res = scan(Path(cfg_path), out_dir)
        times = [res["runtime_s"]]
        for rep in range(1, repeats):
            rep_dir = OUT / "scans" / f"natural_{safe}_r{rep}"
            rep_dir.mkdir(parents=True, exist_ok=True)
            times.append(scan(Path(cfg_path), rep_dir)["runtime_s"])
        by_rule = Counter(f["rule"] for f in res["findings"])
        disp = Counter(f["disposition"] for f in res["findings"])
        results[name] = {
            "docs": res["docs"], "claims": res["claims"],
            "n_findings": len(res["findings"]), "findings_by_rule": dict(by_rule),
            "dispositions": dict(disp), "n_queue": len(res["queue"]),
            "manual_review_fraction": round(
                len(res["queue"]) / res["claims"], 4) if res["claims"] else None,
            "fp_per_100_claims_unverified": round(
                100.0 * len(res["findings"]) / res["claims"], 3) if res["claims"] else None,
            "runtime_s": round(res["runtime_s"], 3), "exit": res["exit"],
            "runtime_median_s": round(statistics.median(times), 3),
            "runtime_runs_s": [round(t, 3) for t in times],
            "stderr": res["stderr"],
        }
        for f in res["findings"]:
            all_findings.append({
                "corpus": name, "rule": f["rule"], "doc": f.get("doc"),
                "locator": f.get("locator"), "disposition": f.get("disposition"),
                "severity": f.get("severity"), "subject": f.get("subject"),
                "observed": f.get("observed"), "verification": None})
        print(f"  [natural] {name}: {len(res['findings'])} findings, "
              f"{len(res['queue'])} queue, {res['runtime_s']:.2f}s")
    return results, all_findings


def apply_verification(natural_findings):
    path = OUT / "natural_verification.jsonl"
    if not path.exists():
        return {}
    rows = load_jsonl(path)
    key = {}
    for r in rows:
        key[(r["corpus"], r["rule"], r["doc"], r.get("subject") or "")] = r
    used = set()
    for f in natural_findings:
        k = (f["corpus"], f["rule"], f["doc"], f.get("subject") or "")
        v = key.get(k)
        if v:
            f["verification"] = v.get("verdict")
            f["verification_note"] = v.get("note")
            used.add(k)
    # summary per corpus
    out = defaultdict(lambda: {"verified": 0, "tp": 0, "fp": 0, "ambiguous": 0})
    for f in natural_findings:
        if f.get("verification"):
            e = out[f["corpus"]]
            e["verified"] += 1
            if f["verification"] == "TP":
                e["tp"] += 1
            elif f["verification"] == "FP":
                e["fp"] += 1
            else:
                e["ambiguous"] += 1
    for e in out.values():
        e["precision_on_verified"] = (e["tp"] / (e["tp"] + e["fp"])) if (e["tp"] + e["fp"]) else None
    return dict(out)


def verified_natural(natural, natural_findings):
    """Aggregate manual verification per scan scope and per rule, incl. FP/100 claims."""
    ver = {(f["corpus"], f["rule"], f.get("doc"), f.get("subject") or ""): f.get("verification")
           for f in natural_findings if f.get("verification")}
    scope_of = {}
    for name in natural:
        if name.endswith(":r9-primary"):
            scope_of[name] = "r9-primary"
        elif name.endswith(":r9-extended"):
            scope_of[name] = "r9-extended"
        elif name.endswith(":r7-git"):
            scope_of[name] = "r7-git"
        elif name.endswith(":corpus"):
            scope_of[name] = "corpus-snapshot"
        else:
            scope_of[name] = "shipped-fixture"

    def agg(names, rule=None):
        tp = fp = other = n = 0
        claims = 0
        for name in names:
            claims += natural[name]["claims"] or 0
            for f in natural_findings:
                if f["corpus"] != name:
                    continue
                if rule and f["rule"] != rule:
                    continue
                v = f.get("verification")
                if not v:
                    continue
                n += 1
                if v == "TP":
                    tp += 1
                elif v == "FP":
                    fp += 1
                else:
                    other += 1
        return {"n_verified": n, "tp": tp, "fp": fp, "ambiguous": other,
                "precision_on_verified": (tp / (tp + fp)) if (tp + fp) else None,
                "claims_scanned": claims,
                "fp_per_100_claims": (100.0 * fp / claims) if claims else None}

    out = {"by_scope": {}, "r9_primary": None, "r9_extended": None, "r7_git": None,
           "corpus_snapshot": None}
    for scope in ("r9-primary", "r9-extended", "r7-git", "corpus-snapshot",
                  "shipped-fixture"):
        names = [n for n in natural if scope_of[n] == scope]
        out["by_scope"][scope] = agg(names)
    out["r9_primary"] = agg([n for n in natural if scope_of[n] == "r9-primary"], rule="R9")
    out["r9_extended"] = agg([n for n in natural if scope_of[n] == "r9-extended"], rule="R9")
    out["r7_git"] = agg([n for n in natural if scope_of[n] == "r7-git"], rule="R7")
    # per-repo runtime table for the 5 read-only repos
    runtimes = {}
    for repo in LOCAL_REPOS:
        runtimes[repo] = {}
        for scope, suffix in (("r9_primary", ":r9-primary"),
                              ("r9_extended", ":r9-extended"),
                              ("r7_git", ":r7-git")):
            name = repo + suffix
            if name in natural:
                runtimes[repo][scope] = natural[name].get("runtime_median_s")
    out["runtime_5repos"] = runtimes
    return out


def known_defect_check():
    res = scan(SAMPLE_CONFIG, OUT / "scans" / "sample_repo_known")
    expected = [("R1", "docs/pins.md", "unresolved"),
                ("R2", "docs/numbers.md", "confirmed"),
                ("R3", "docs/conflict_a.md", "confirmed"),
                ("R5", "docs/negative.md", "confirmed"),
                ("R6", "docs/other_target.md", "unresolved")]
    rows = []
    for rule, doc, disp in expected:
        hit = [f for f in res["findings"] if f["rule"] == rule and f.get("doc") == doc]
        rows.append({"rule": rule, "doc": doc, "expected_disposition": disp,
                     "detected": bool(hit),
                     "dispositions": [f.get("disposition") for f in hit]})
    # R4 is enabled only in the shipped example config: reported separately (experimental)
    r4 = [f for f in res["findings"] if f["rule"] == "R4"]
    clean = ["docs/clean.md", "docs/numbers_clean.md"]
    clean_findings = [f for f in res["findings"] if f.get("doc") in clean]
    return {"n_findings": len(res["findings"]),
            "n_claims": res["claims"], "n_queue": len(res["queue"]),
            "rules_detected": sorted({f["rule"] for f in res["findings"]}),
            "known_defect_recall": sum(1 for r in rows if r["detected"]) / len(rows),
            "rows": rows,
            "r4_experimental": {"n": len(r4),
                                "note": "R4 off by default and excluded from injected eval"},
            "clean_control_docs": clean,
            "clean_control_findings": [{"rule": f["rule"], "doc": f.get("doc")}
                                       for f in clean_findings],
            "runtime_s": round(res["runtime_s"], 3)}


def md_table(summary):
    rs = summary["injected"]["by_rule"]
    lines = [
        "# kblint mutation evaluation — paper tables",
        "",
        "## Table A. Injected mutation results (controlled; one mutant = one scan)",
        "",
        "| rule | mutants (pos/neg) | TP | FN | FP | TN | recall | precision | FPR | "
        "FP / 100 claims | TP dispositions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rule, v in rs.items():
        lines.append(
            f"| {rule} | {v['n_mutants']} ({v['n_positive']}/{v['n_controls_negatives']}) | "
            f"{v['tp']} | {v['fn']} | {v['fp']} | {v['tn']} | "
            f"{_p(v['recall'])} | {_p(v['precision'])} | {_p(v['false_positive_rate'])} | "
            f"{_num(v.get('fp_per_100_claims'))} | {_disp(v['tp_dispositions'])} |")
    o = summary["injected"]["overall"]
    lines += [
        f"| **all** | {sum(v['n_mutants'] for v in rs.values())} | {o['tp']} | {o['fn']} | "
        f"{o['fp']} | {o['tn']} | {_p(o['recall'])} | {_p(o['precision'])} | "
        f"{_p(o['false_positive_rate'])} | {_num(o.get('fp_per_100_claims'))} | |",
        "",
        "Notes: (i) injected mutants are *controlled* — each breaks (positive) or preserves "
        "(hard negative/control) exactly one referenced truth; (ii) audit-queue dispositions "
        "(`revalidation_due`, `unresolved`) count as detected but are not `confirmed` defects; "
        "(iii) R4 is off by default/experimental and excluded; (iv) FP/100 claims uses the "
        "claims scanned in the control/hard-negative mutants for that rule.",
        "",
        "## Table B. Runtime (kblint CLI; deterministic, stdlib-only)",
        "",
        "| scope | scans | median | p90 | max | median docs / claims |",
        "|---|---:|---:|---:|---:|---|",
        f"| injected mutant scans | {summary['injected']['runtime']['n_scans']} | "
        f"{summary['injected']['runtime']['median_s']} s | "
        f"{summary['injected']['runtime']['p90_s']} s | "
        f"{summary['injected']['runtime']['max_s']} s | "
        f"{summary['injected']['runtime']['median_docs']} / "
        f"{summary['injected']['runtime']['median_claims']} |",
    ]
    nat = summary.get("natural") or {}
    if "corpora" in nat:
        lines += ["", "### Natural scan runtime (median of 3 runs per repo; read-only local repos)",
                  "",
                  "| repo | R9 primary scope | R9 extended scope | R7 git scope |",
                  "|---|---:|---:|---:|"]
        rt = nat.get("verified", {}).get("runtime_5repos", {})
        med = {}
        for repo, v in rt.items():
            med[repo] = v
            lines.append(f"| {repo} | {v.get('r9_primary')} s | {v.get('r9_extended')} s | "
                         f"{v.get('r7_git')} s |")
        if med:
            pcols = [med[r].get("r9_primary") for r in med if med[r].get("r9_primary")]
            ecols = [med[r].get("r9_extended") for r in med if med[r].get("r9_extended")]
            if pcols and ecols:
                import statistics as _st
                lines.append(f"| **median across repos** | {round(_st.median(pcols), 2)} s | "
                             f"{round(_st.median(ecols), 2)} s | |")
        lines += ["", "## Table C. Natural scans — manually verified precision "
                  "(natural vs injected kept separate)", "",
                  "| scope | findings | verified | TP | FP | verified precision | claims | "
                  "FP / 100 claims |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        vv = nat.get("verified", {})
        for scope, label in (("r9-primary", "R9 primary (AGENTS-style KB surface)"),
                             ("r9-extended", "R9 extended (README/docs surface)"),
                             ("r7-git", "R7 git provenance"),
                             ("corpus-snapshot", "R0 corpus snapshot (aux)"),
                             ("shipped-fixture", "shipped sample_repo (known defects)")):
            a = vv.get("by_scope", {}).get(scope)
            if not a:
                continue
            lines.append(f"| {label} | {a['n_verified']} | {a['n_verified']} | {a['tp']} | "
                         f"{a['fp']} | {_p(a['precision_on_verified'])} | "
                         f"{a['claims_scanned']} | {_num(a['fp_per_100_claims'])} |")
        lines += ["",
                  "R9 primary scope follows the recommended `references.kblint.json` deployment "
                  "(AGENTS.md / CLAUDE.md / docs/AGENTS.md / SKILL.md, allow_missing for "
                  "generated/external artifact classes). The extended scope adds README/docs and "
                  "is reported for transparency (product-documentation example paths are counted "
                  "as FPs for the KB claim surface). 'shipped-fixture' is the synthetic sample_repo "
                  "with its designed known defects; it is a sanity check, not a natural sample.",
                  ""]
        kd = nat.get("known_defect_check") or {}
        if kd:
            lines += ["## Table D. Shipped sample_repo known-defect check (sanity)", "",
                      f"- known-defect recall: {_p(kd['known_defect_recall'])} "
                      f"({sum(1 for r in kd['rows'] if r['detected'])}/{len(kd['rows'])} designed "
                      f"defects detected)",
                      f"- rules detected: {', '.join(kd['rules_detected'])}",
                      f"- R4 experimental (off by default, excluded): {kd['r4_experimental']['n']} "
                      f"finding(s)",
                      f"- clean-control docs ({', '.join(kd['clean_control_docs'])}): "
                      f"{len(kd['clean_control_findings'])} findings",
                      ""]
    lines.append("")
    return "\n".join(lines)


def _p(x):
    return "n/a" if x is None else f"{100.0 * x:.1f}%"


def _num(x):
    return "n/a" if x is None else f"{x:.2f}"


def _disp(d):
    if not d:
        return "—"
    return ", ".join(f"{k}×{v}" for k, v in sorted(d.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-natural", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    print(f"[eval] kblint version {kblint_version()}; {len(manifest['cases'])} mutants")
    rows, findings = run_injected(manifest)
    write_jsonl(OUT / "cases.jsonl", rows)
    write_jsonl(OUT / "findings_injected.jsonl", findings)
    summary = {
        "generated_by": "run_eval.py",
        "kblint": {"version": kblint_version(), "rule_hashes": rule_hashes(),
                   "now": NOW},
        "injected": metrics(rows),
        "natural": {},
    }
    if not args.skip_natural:
        natural, natural_findings = run_natural()
        verification = apply_verification(natural_findings)
        summary["natural"] = {
            "corpora": natural,
            "verification": verification,
            "verified": verified_natural(natural, natural_findings),
            "known_defect_check": known_defect_check(),
        }
        write_jsonl(OUT / "natural_findings.jsonl", natural_findings)
    # ---- compact paper-facing number block (stable keys; see REPORT.md definitions) ----
    inj = summary["injected"]
    o = inj["overall"]
    r9 = inj["by_rule"].get("R9", {})
    nat = summary.get("natural") or {}
    vv = nat.get("verified", {}) if nat else {}
    prim = (vv.get("r9_primary") or {})
    ext = (vv.get("r9_extended") or {})
    r7 = (vv.get("r7_git") or {})
    runtimes = (vv.get("runtime_5repos") or {})
    prim_rt = [v.get("r9_primary") for v in runtimes.values() if v.get("r9_primary")]
    summary["paper_numbers"] = {
        "n_mutants": sum(v["n_mutants"] for v in inj["by_rule"].values()) + 2
        if inj.get("bug_probes") else sum(v["n_mutants"] for v in inj["by_rule"].values()),
        "positives": sum(v["n_positive"] for v in inj["by_rule"].values()),
        "negatives": sum(v["n_controls_negatives"] for v in inj["by_rule"].values()),
        "negatives_incl_bug_probes": sum(v["n_controls_negatives"]
                                         for v in inj["by_rule"].values())
        + len(inj.get("bug_probes", [])),
        "bug_probe_n": len(inj.get("bug_probes", [])),
        "tp": o["tp"], "fp": o["fp"], "fn": o["fn"], "tn": o["tn"],
        "precision": o["precision"], "recall": o["recall"],
        "fpr": o["false_positive_rate"],
        "fp_per_100": o.get("fp_per_100_claims"),
        "r9_pos": r9.get("n_positive"), "r9_tp": r9.get("tp"),
        "r9_precision": r9.get("precision"), "r9_recall": r9.get("recall"),
        "r9_fpr": r9.get("false_positive_rate"),
        "r9_fp_per_100": r9.get("fp_per_100_claims"),
        "natural_tp": prim.get("tp"), "natural_fp": prim.get("fp"),
        "natural_claims": prim.get("claims_scanned"),
        "natural_precision": prim.get("precision_on_verified"),
        "natural_scope": "r9-primary (AGENTS.md/CLAUDE.md/docs/AGENTS.md/SKILL.md, "
                         "allow_missing generated/external classes)",
        "natural_extended": {"tp": ext.get("tp"), "fp": ext.get("fp"),
                             "claims": ext.get("claims_scanned"),
                             "precision": ext.get("precision_on_verified")},
        "r7_natural": {"tp": r7.get("tp"), "fp": r7.get("fp"),
                       "claims": r7.get("claims_scanned"),
                       "precision": r7.get("precision_on_verified")},
        "runtime_median_s": inj["runtime"]["median_s"],
        "runtime_5repos_r9_primary_median_s":
            round(statistics.median(prim_rt), 3) if prim_rt else None,
        "kblint_version": summary["kblint"]["version"],
        "kblint_rule_hashes": summary["kblint"]["rule_hashes"],
        "bug_probes": [{k: p.get(k) for k in ("case_id", "expect", "detected", "outcome")}
                       for p in inj.get("bug_probes", [])],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    (OUT / "RESULTS_TABLE.md").write_text(md_table(summary), encoding="utf-8")
    inj = summary["injected"]
    print("\n[headline] injected overall:", inj["overall"])
    for rule, v in inj["by_rule"].items():
        print(f"  {rule}: n={v['n_mutants']} recall={_p(v['recall'])} "
              f"precision={_p(v['precision'])} fpr={_p(v['false_positive_rate'])}")
    print(f"  runtime median {inj['runtime']['median_s']}s")
    print(f"[wrote] {OUT/'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
