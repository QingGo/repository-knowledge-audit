#!/usr/bin/env python3
"""Targeted R7 (git provenance) recheck used for the non-ASCII/quotepath bug.

Runs:

  * the 5 read-only local repos with the R7-only natural config
    (`fixtures/configs/natural_r7git_<repo>.json`), and
  * the two R5 R7 bug-probe fixtures built by mutate.py
    (`fixtures/repos/R7R-wechat-NC-probe`, `R7R-wechat-POS-uncommitted-probe`).

Expected after the quotepath fix:
  - R5 natural: 0 findings (its 6 non-ASCII docs are tracked and clean);
  - bug-probe NC: no provenance_gap finding on docs/<private KB text removed>.md;
  - bug-probe POS (uncommitted edit to the same non-ASCII doc): 1 confirmed finding.
Before the fix the NC report shows 6 false provenance_gap findings for wechat and the
uncommitted-edit probe is missed.

Usage: python3 r7_recheck.py --tag before|after   (writes results/r7_recheck_<tag>.json)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parent.parent
KBLINT = KB / "kblint"
OUT = HERE / "results"
NOW = "2026-11-05"
REPOS = {
    "R2": "/HOME/code/R2",
    "R3": "/HOME/code/R3",
    "R5": "/HOME/code/R5",
    "R4": "/HOME/code/R4",
    "R1": "/HOME/code/R1",
}


def scan(config_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.iterdir():
        if p.is_file():
            p.unlink()
    subprocess.run([sys.executable, "-m", "kblint", "scan", "--config", str(config_path),
                    "--out", str(out_dir), "--now", NOW, "--quiet"],
                   cwd=str(KBLINT), capture_output=True, text=True)
    fs = []
    if (out_dir / "findings.jsonl").exists():
        fs = [json.loads(l) for l in (out_dir / "findings.jsonl").read_text().splitlines()
              if l.strip()]
    return fs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"tag": args.tag, "kblint_version": _version(),
           "rule_hashes": _rule_hashes(), "repos": {}, "probes": {}}
    for repo in REPOS:
        cfg = HERE / "fixtures/configs" / f"natural_r7git_{repo}.json"
        fs = scan(cfg, OUT / "scans" / f"r7recheck_{args.tag}_{repo}")
        out["repos"][repo] = {
            "n_findings": len(fs),
            "by_rule": dict(Counter(f["rule"] for f in fs)),
            "findings": [{"rule": f["rule"], "doc": f.get("doc"),
                          "disposition": f.get("disposition"),
                          "subject": f.get("subject")} for f in fs]}
    # wechat bug probes
    for cid in ("R7R-wechat-NC-probe", "R7R-wechat-POS-uncommitted-probe"):
        cfg = HERE / "fixtures/configs" / f"{cid}.json"
        fs = scan(cfg, OUT / "scans" / f"r7recheck_{args.tag}_{cid}")
        target = [f for f in fs if f.get("doc") == "docs/<private KB text removed>.md"]
        out["probes"][cid] = {
            "n_findings_total": len(fs), "n_findings_target_doc": len(target),
            "target_findings": [{"rule": f["rule"], "disposition": f.get("disposition"),
                                 "subject": f.get("subject")} for f in target]}
    out["wechat_expected"] = {
        "natural_findings": 0,
        "probe_NC_target_findings": 0,
        "probe_POS_uncommitted_target_findings": 1,
    }
    out["wechat_pass"] = (
        out["repos"]["R5"]["n_findings"] == 0
        and out["probes"]["R7R-wechat-NC-probe"]["n_findings_target_doc"] == 0
        and out["probes"]["R7R-wechat-POS-uncommitted-probe"]["n_findings_target_doc"] == 1)
    path = OUT / f"r7_recheck_{args.tag}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("tag", "wechat_pass", "wechat_expected")}, indent=1))
    print("[wrote]", path)
    return 0


def _version():
    text = (KBLINT / "kblint/__init__.py").read_text(encoding="utf-8")
    import re
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "unknown"


def _rule_hashes():
    import hashlib
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            for p in sorted((KBLINT / "kblint/rules").glob("r*.py"))}


if __name__ == "__main__":
    sys.exit(main())
