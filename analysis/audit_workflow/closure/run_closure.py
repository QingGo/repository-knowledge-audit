#!/usr/bin/env python3
"""Closure of the R2 audit-repair loop: 4 → 3 → 0 (task-81).

Runs on read-only `git archive` copies of /HOME/code/R2:

  parent   = 2bc2feba97ca5ca1e920bab57413b99779402e0a  (stale KB; R9 = 4)
  fix      = 29a0bc7e06aefb615eb5c07a46f56480a9bef0af  (human fix commit; R9 = 3)
  repaired = fix tree + a minimal KB-only edit of AGENTS.md that repoints the three
             stale `docs/*.md` references to the real in-repo artifact (README.md),
             preserving the claims (no deletion, no repo change)

For each state it runs the committed workflow config with kblint v0.2.1 and saves the
JSON/Markdown/SARIF reports under closure/raw/<state>/ plus a meta.json (command,
exit code, wall time, parsed counts, finding ids, output hashes, determinism check).

Usage: python3 closure/run_closure.py [--scratch /tmp/kb-audit-closure]
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.dirname(HERE)
KBLINT = os.path.abspath(os.path.join(WORKFLOW, "..", "..", "kblint"))
CONFIG = os.path.join(WORKFLOW, "configs", "R2.kblint.json")
RAW = os.path.join(HERE, "raw")
BEFORE_AFTER = os.path.join(HERE, "before_after")
REPO = "/HOME/code/R2"
PARENT = "2bc2feba97ca5ca1e920bab57413b99779402e0a"
FIX = "29a0bc7e06aefb615eb5c07a46f56480a9bef0af"
KB = "AGENTS.md"
NOW = "2026-11-05"
FAIL_ON = "medium"
OUTPUT_FILES = ("findings.jsonl", "audit_queue.jsonl", "summary.md", "report.sarif")
COUNTS_RE = {
    "docs": re.compile(r"docs scanned: (\d+)"),
    "claims": re.compile(r"claims extracted: (\d+)"),
    "findings": re.compile(r"findings: \*\*(\d+)\*\*"),
    "queue": re.compile(r"audit queue \(not defects\): \*\*(\d+)\*\*"),
}

# The minimal KB-only repair: replace three stale in-repo paths with the real
# in-repo documentation artifact (README.md sections hold the architecture and
# implementation/decision records; the repository has never contained a
# standalone paper). The claim text is preserved; only the target is corrected.
OLD_BLOCK = """- <private KB text removed>: `weights/` (46 safetensors, ~150GB); <private KB text removed>: `docs/paper.md`
- <private KB text removed>: `hot_experts.json`; <private KB text removed>: `docs/arch_design.md`
- <private KB text removed>: `docs/implementation_notes.md`"""
NEW_BLOCK = """- <private KB text removed>: `weights/` (46 safetensors, ~150GB); <private KB text removed>: `README.md`（<private KB text removed>/<private KB text removed>；<private KB text removed>）
- <private KB text removed>: `hot_experts.json`; <private KB text removed>: `README.md`（<private KB text removed>）
- <private KB text removed>: `README.md`（<private KB text removed> / <private KB text removed> / <private KB text removed>）"""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, check=True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit("git %s failed: %s" % (" ".join(args), proc.stderr[-2000:]))
    return proc


def extract(commit: str, dest: str) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    proc = subprocess.Popen(["git", "-C", REPO, "archive", commit], stdout=subprocess.PIPE)
    tar = subprocess.run(["tar", "-x", "-C", dest], stdin=proc.stdout, capture_output=True, text=True)
    proc.stdout.close()
    if proc.wait() != 0 or tar.returncode != 0:
        raise SystemExit("archive extract failed for " + commit)


def scan(state: str, tree: str) -> dict:
    out_dir = os.path.join(RAW, state)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    cmd = [sys.executable, "-m", "kblint", "scan", "--repo", tree, "--config", CONFIG,
           "--out", out_dir, "--format", "json,md,sarif",
           "--fail-on", FAIL_ON, "--now", NOW]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=KBLINT, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    if proc.returncode not in (0, 1):
        raise SystemExit("kblint failed for %s rc=%s\n%s" % (state, proc.returncode, proc.stderr[-3000:]))
    open(os.path.join(out_dir, "stdout.txt"), "w", encoding="utf-8").write(proc.stdout)
    open(os.path.join(out_dir, "stderr.txt"), "w", encoding="utf-8").write(proc.stderr)
    summary = open(os.path.join(out_dir, "summary.md"), encoding="utf-8").read()
    counts = {k: int(rx.search(summary).group(1)) for k, rx in COUNTS_RE.items() if rx.search(summary)}
    findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.jsonl"),
                                           encoding="utf-8") if l.strip()]
    queue = [json.loads(l) for l in open(os.path.join(out_dir, "audit_queue.jsonl"),
                                        encoding="utf-8") if l.strip()]

    # determinism: rerun into scratch, compare outputs
    verify = out_dir + ".verify"
    shutil.rmtree(verify, ignore_errors=True)
    vcmd = [sys.executable, "-m", "kblint", "scan", "--repo", tree, "--config", CONFIG,
            "--out", verify, "--format", "json,md,sarif", "--fail-on", FAIL_ON, "--now", NOW]
    vproc = subprocess.run(vcmd, cwd=KBLINT, capture_output=True, text=True)
    hashes = {n: sha256_file(os.path.join(out_dir, n)) for n in OUTPUT_FILES}
    vhashes = {n: sha256_file(os.path.join(verify, n)) for n in OUTPUT_FILES}
    deterministic = hashes == vhashes and vproc.returncode == proc.returncode
    shutil.rmtree(verify, ignore_errors=True)

    meta = {
        "state": state,
        "tree": tree,
        "config": CONFIG,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "runtime_s": round(elapsed, 4),
        "counts": counts,
        "findings_total": len(findings),
        "findings_by_rule": {r: sum(1 for f in findings if f.get("rule") == r)
                             for r in sorted({f.get("rule") for f in findings})},
        "r9_findings": [f for f in findings if f.get("rule") == "R9"],
        "r9_count": sum(1 for f in findings if f.get("rule") == "R9"),
        "audit_queue_rows": len(queue),
        "output_sha256": hashes,
        "deterministic_rerun_byte_identical": deterministic,
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default="/tmp/kb-audit-closure")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(BEFORE_AFTER, exist_ok=True)

    status_before = git("status", "--porcelain").stdout
    states = {}

    parent_tree = os.path.join(args.scratch, "parent")
    fix_tree = os.path.join(args.scratch, "fix")
    repaired_tree = os.path.join(args.scratch, "repaired")
    shutil.rmtree(args.scratch, ignore_errors=True)
    extract(PARENT, parent_tree)
    extract(FIX, fix_tree)
    shutil.copytree(fix_tree, repaired_tree)
    kb_path = os.path.join(repaired_tree, KB)
    original = open(kb_path, encoding="utf-8").read()
    if OLD_BLOCK not in original:
        raise SystemExit("repair anchor block not found in fix-commit " + KB)
    repaired = original.replace(OLD_BLOCK, NEW_BLOCK, 1)
    open(kb_path, "w", encoding="utf-8").write(repaired)

    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True), repaired.splitlines(keepends=True),
        fromfile="a/" + KB, tofile="b/" + KB, n=3))
    with open(os.path.join(HERE, "KB_REPAIR.diff"), "w", encoding="utf-8") as f:
        f.writelines(diff)

    for state, tree in (("parent", parent_tree), ("fix", fix_tree), ("repaired", repaired_tree)):
        states[state] = scan(state, tree)
    assert git("status", "--porcelain").stdout == status_before, "source repo changed!"

    # compact before/after table
    rows = []
    for state in ("parent", "fix", "repaired"):
        m = states[state]
        rows.append({
            "state": state,
            "claims": m["counts"].get("claims"),
            "queue": m["counts"].get("queue"),
            "r9": m["r9_count"],
            "exit": m["exit_code"],
            "runtime_s": m["runtime_s"],
            "deterministic": m["deterministic_rerun_byte_identical"],
        })
    summary = {
        "task": "task-81 R2 closure 4 → 3 → 0",
        "kblint_version": "0.2.1",
        "repo": REPO,
        "commits": {"parent": PARENT, "fix": FIX},
        "kb_file": KB,
        "repair": {"seed_tree": "fix", "edited": [KB],
                   "changed_lines": sum(1 for l in diff if (l.startswith("+") or l.startswith("-"))
                                        and not l.startswith(("+++", "---"))),
                   "diff_file": "KB_REPAIR.diff",
                   "target": "README.md (real in-repo documentation artifact)"},
        "states": states,
        "table": rows,
        "source_repo_unchanged": True,
    }
    with open(os.path.join(BEFORE_AFTER, "closure_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
        f.write("\n")

    md = ["# R2 closure: 4 → 3 → 0 (kblint v0.2.1)\n",
          "| state | claims | audit queue | R9 findings | exit | runtime | rerun byte-identical |",
          "|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s | %.3f s | %s |" % (
            r["state"], r["claims"], r["queue"], r["r9"], r["exit"], r["runtime_s"],
            r["deterministic"]))
    with open(os.path.join(BEFORE_AFTER, "closure_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print("\n".join(md))
    print("\nR9 by state:")
    for r in ("parent", "fix", "repaired"):
        print(" %-9s R9=%d" % (r, states[r]["r9_count"]), [
            (f.get("locator"), f.get("subject")) for f in states[r]["r9_findings"]])
    print("\nKB_REPAIR.diff:", os.path.join(HERE, "KB_REPAIR.diff"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
