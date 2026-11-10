#!/usr/bin/env python3
"""End-to-end real-repository KB audit workflow (task-72, AGENTVERIFY 2027 revision).

Deterministic, no model calls, no network. For two read-only source repositories it:

  1. extracts the PARENT commit tree to a temp dir with `git archive` (never touches
     the source repo), and builds a "minimal KB repair" temp tree = parent tree with the
     one KB file replaced by the FIX commit's version (`git show <fix>:<kb>`);
  2. runs `python3 -m kblint scan` on both conditions with two committed example configs:
       - the workflow config (KB docs scope, references enabled, allow_missing for
         runtime/generated dirs), and
       - a generic references config (same docs, no allow_missing) used for the
         false-positive-by-contract adjudication;
  3. records exact commands, exit codes, wall-clock runtime, claims/queue/findings
     counts, output hashes, and a byte-identical rerun determinism check;
  4. writes machine-readable summaries under `raw/` for the figure and REPORT.md.

Writes only inside kb-health/analysis/audit_workflow/ + /tmp scratch trees.
Source repos are read-only (git archive/show/ls-tree only); their `git status
--porcelain` is compared before/after the whole run.

Usage:
  python3 run_audit_workflow.py [--scratch /SCRATCH_NOT_SHIPPED]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KBLINT = os.path.abspath(os.path.join(HERE, "..", "..", "kblint"))
CONFIGS = os.path.join(HERE, "configs")
RAW = os.path.join(HERE, "raw")
NOW = "2026-11-05"
FAIL_ON = "medium"

REPOS = {
    "R2": {
        "path": "/HOME/code/R2",
        "parent": "2bc2feba97ca5ca1e920bab57413b99779402e0a",
        "fix": "29a0bc7e06aefb615eb5c07a46f56480a9bef0af",
        "kb_files": ["AGENTS.md"],
        "committed_config": "R2.kblint.json",
        "generic_config": "R2.generic.json",
    },
    "R3": {
        "path": "/HOME/code/R3",
        "parent": "b674155f2b941b64e0b4110c2c7450badb2c28aa",
        "fix": "07635ed1a8fb97ea17fee4c728788b2e89bfc590",
        "kb_files": ["AGENTS.md"],
        "committed_config": "R3.kblint.json",
        "generic_config": "R3.generic.json",
    },
}

OUTPUT_FILES = ("findings.jsonl", "audit_queue.jsonl", "summary.md", "report.sarif")
SCAN_COUNTS = {
    "docs": re.compile(r"docs scanned: (\d+)"),
    "claims": re.compile(r"claims extracted: (\d+)"),
    "findings": re.compile(r"findings: \*\*(\d+)\*\*"),
    "queue": re.compile(r"audit queue \(not defects\): \*\*(\d+)\*\*"),
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, cwd=None, check=True):
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    if check and proc.returncode not in (0, 1):  # kblint: 1 = findings at threshold
        raise SystemExit("command failed rc=%s: %s\n%s" % (proc.returncode, " ".join(cmd), proc.stderr[-2000:]))
    return proc, elapsed


def git(repo: str, *args, check=True) -> subprocess.CompletedProcess:
    return run(["git", "-C", repo] + list(args), check=check)[0]


def extract_tree(repo: str, commit: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    proc = subprocess.Popen(["git", "-C", repo, "archive", commit], stdout=subprocess.PIPE)
    tar = subprocess.run(["tar", "-x", "-C", dest], stdin=proc.stdout,
                         capture_output=True, text=True)
    proc.stdout.close()
    if proc.wait() != 0 or tar.returncode != 0:
        raise SystemExit("git archive/tar failed for %s: %s %s" % (commit, tar.stderr, proc.stderr))


def prepare(scratch: str) -> dict:
    """Materialize parent and minimal-repair trees; verify repair == fix tree."""
    info = {}
    for repo, cfg in REPOS.items():
        root = os.path.join(scratch, repo)
        parent_dir = os.path.join(root, "parent")
        repaired_dir = os.path.join(root, "repaired")
        fix_check_dir = os.path.join(root, "fix_tree_check")
        shutil.rmtree(root, ignore_errors=True)
        extract_tree(cfg["path"], cfg["parent"], parent_dir)
        shutil.copytree(parent_dir, repaired_dir)
        for kb in cfg["kb_files"]:
            show = git(cfg["path"], "show", "%s:%s" % (cfg["fix"], kb))
            with open(os.path.join(repaired_dir, kb), "w", encoding="utf-8") as f:
                f.write(show.stdout)
        # prove the minimal repair tree is byte-identical to the fix-commit tree
        extract_tree(cfg["path"], cfg["fix"], fix_check_dir)
        diff = subprocess.run(["diff", "-r", repaired_dir, fix_check_dir],
                              capture_output=True, text=True)
        if diff.returncode != 0:
            raise SystemExit("minimal KB repair does not equal fix tree for %s:\n%s"
                             % (repo, diff.stdout[-3000:]))
        info[repo] = {
            "parent_tree": parent_dir,
            "repaired_tree": repaired_dir,
            "minimal_repair_equals_fix_tree": True,
            "kb_files_replaced": cfg["kb_files"],
        }
    return info


def scan(repo: str, condition: str, tree: str, config_file: str, out_dir: str) -> dict:
    cfg_path = os.path.join(CONFIGS, config_file)
    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "kblint", "scan",
           "--repo", tree,
           "--config", cfg_path,
           "--out", out_dir,
           "--format", "json,md,sarif",
           "--fail-on", FAIL_ON,
           "--now", NOW]
    proc, elapsed = run(cmd, cwd=KBLINT, check=False)
    if proc.returncode not in (0, 1):
        raise SystemExit("kblint scan failed %s/%s rc=%s\n%s"
                         % (repo, condition, proc.returncode, proc.stderr[-3000:]))
    with open(os.path.join(out_dir, "stdout.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout)
    with open(os.path.join(out_dir, "stderr.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stderr)

    summary = open(os.path.join(out_dir, "summary.md"), encoding="utf-8").read()
    counts = {k: int(rx.search(summary).group(1)) for k, rx in SCAN_COUNTS.items()
              if rx.search(summary)}
    findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.jsonl"),
                                            encoding="utf-8") if l.strip()]
    queue = [json.loads(l) for l in open(os.path.join(out_dir, "audit_queue.jsonl"),
                                         encoding="utf-8") if l.strip()]
    r9 = [f for f in findings if f.get("rule") == "R9"]
    by_rule = {}
    for f in findings:
        by_rule[f.get("rule")] = by_rule.get(f.get("rule"), 0) + 1

    # determinism: rerun into a scratch dir and compare output hashes
    verify_dir = out_dir + ".verify"
    shutil.rmtree(verify_dir, ignore_errors=True)
    verify_cmd = [sys.executable, "-m", "kblint", "scan",
                  "--repo", tree, "--config", cfg_path, "--out", verify_dir,
                  "--format", "json,md,sarif", "--fail-on", FAIL_ON, "--now", NOW]
    proc2, _ = run(verify_cmd, cwd=KBLINT, check=False)
    hashes = {n: sha256_file(os.path.join(out_dir, n)) for n in OUTPUT_FILES}
    hashes2 = {n: sha256_file(os.path.join(verify_dir, n)) for n in OUTPUT_FILES}
    deterministic = hashes == hashes2 and proc2.returncode == proc.returncode
    shutil.rmtree(verify_dir, ignore_errors=True)

    meta = {
        "repo": repo,
        "condition": condition,
        "config": config_file,
        "tree": tree,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "runtime_s": round(elapsed, 4),
        "counts": counts,
        "findings_total": len(findings),
        "findings_by_rule": by_rule,
        "r9_findings": len(r9),
        "audit_queue_rows": len(queue),
        "output_sha256": hashes,
        "deterministic_rerun_byte_identical": deterministic,
        "r9_rows": [
            {"finding_id": f.get("finding_id"), "rule": f.get("rule"),
             "severity": f.get("severity"), "locator": f.get("locator"),
             "subject": f.get("subject"), "claim_text": f.get("claim_text"),
             "expected": f.get("expected"), "observed": f.get("observed"),
             "disposition": f.get("disposition")}
            for f in r9
        ],
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default="/SCRATCH_NOT_SHIPPED")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    status_before = {r: git(c["path"], "status", "--porcelain").stdout for r, c in REPOS.items()}

    prepared = prepare(args.scratch)
    scans = []
    for repo, cfg in REPOS.items():
        for condition, tree_key in (("parent-stale", "parent_tree"),
                                    ("repaired", "repaired_tree")):
            tree = prepared[repo][tree_key]
            for cfg_kind in ("committed_config", "generic_config"):
                name = cfg[cfg_kind].replace(".json", "")
                out_dir = os.path.join(RAW, repo, "%s__%s" % (condition, name))
                scans.append(scan(repo, condition, tree, cfg[cfg_kind], out_dir))

    status_after = {r: git(c["path"], "status", "--porcelain").stdout for r, c in REPOS.items()}
    source_unchanged = all(status_before[r] == status_after[r] for r in REPOS)

    summary = {
        "task": "task-72 end-to-end real-repo KB audit workflow",
        "kblint_version": "0.2.1",
        "now": NOW,
        "fail_on": FAIL_ON,
        "no_model_calls": True,
        "repos": {r: {k: v for k, v in c.items() if k != "path"} for r, c in REPOS.items()},
        "prepared": prepared,
        "source_repos_unchanged": source_unchanged,
        "source_git_status_before": status_before,
        "source_git_status_after": status_after,
        "scans": scans,
    }
    with open(os.path.join(RAW, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # compact console table
    print("%-12s %-16s %-22s %6s %6s %6s %5s %5s %8s" % (
        "repo", "condition", "config", "docs", "claims", "find", "R9", "queue", "exit/s"))
    for s in scans:
        c = s["counts"]
        print("%-12s %-16s %-22s %6s %6s %6s %5d %5d %8s" % (
            s["repo"], s["condition"], s["config"], c.get("docs"), c.get("claims"),
            c.get("findings"), s["r9_findings"], s["audit_queue_rows"],
            "%s/%.3fs" % (s["exit_code"], s["runtime_s"])))
    print("\nsource repos unchanged (git status):", source_unchanged)
    print("summary:", os.path.join(RAW, "summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
