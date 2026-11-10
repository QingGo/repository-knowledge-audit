"""Incremental baseline diff tests (NEW / PERSISTING / FIXED, exit policy). No network."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SAMPLE_REPO = os.path.join(PKG, "examples", "sample_repo")


def run_cli(args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = PKG
    return subprocess.run([sys.executable, "-m", "kblint", *args],
                          capture_output=True, text=True, cwd=cwd or PKG,
                          env=env, timeout=180)


def load_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def finding(rule="R9", severity="medium", disposition="confirmed", doc="docs/a.md",
            locator="docs/a.md#L5", subject="file path does not exist: x.sh",
            observed="missing x.sh", expected="path exists", fid=None):
    return {"finding_id": fid or f"F-{rule}-{doc}-{subject[:8]}", "rule": rule,
            "severity": severity, "disposition": disposition, "doc": doc,
            "locator": locator, "subject": subject, "observed": observed,
            "expected": expected, "evidence": [], "verification_method": "test",
            "confidence": "high", "suggested_action": "repair", "tags": []}


def write_report(directory, rows):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "findings.jsonl"), "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return directory


def refs_config(repo, path):
    cfg = {"repo": repo, "docs": ["docs/**/*.md"], "exclude": ["**/.git/**"],
           "git": {"enabled": False}, "now": "2026-11-05",
           "references": {"enabled": True, "check_paths": True, "check_links": True,
                          "check_make": True, "check_npm": True,
                          "allow_missing": ["^(weights|runs|outputs|dist|build|node_modules)/"],
                          "inventory": []}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    return path


def scan(repo, cfg, out, cwd=None):
    return run_cli(["scan", "--repo", repo, "--config", cfg, "--out", out,
                    "--format", "json,md,sarif", "--now", "2026-11-05", "--fail-on", "none"],
                   cwd=cwd)


# ---------------------------------------------------------------- unit classifications
def test_finding_key_is_stable_across_line_shifts():
    from kblint.diff import classify, finding_key
    a = finding(locator="docs/a.md#L5")
    b = finding(locator="docs/a.md#L42")  # same claim, shifted lines
    assert finding_key(a) == finding_key(b)
    result = classify([a], [b])
    assert result["counts"] == {"before": 1, "after": 1, "new": 0, "new_blocking": 0,
                                "new_unknown_non_blocking": 0, "persisting": 1, "fixed": 0}
    assert result["exit_code"] == 0


def test_new_persisting_fixed_classification_and_outputs(tmp_path):
    before = [finding(doc="docs/a.md", locator="docs/a.md#L5", subject="old target A"),
              finding(doc="docs/b.md", locator="docs/b.md#L2", subject="kept target B")]
    after = [finding(doc="docs/b.md", locator="docs/b.md#L9", subject="kept target B"),
             finding(doc="docs/c.md", locator="docs/c.md#L1", subject="new target C")]
    bdir = write_report(str(tmp_path / "before"), before)
    adir = write_report(str(tmp_path / "after"), after)
    out = str(tmp_path / "out")
    proc = run_cli(["diff", "--before", bdir, "--after", adir, "--out", out,
                    "--format", "md,json", "--fail-on-new", "medium"])
    assert proc.returncode == 1, proc.stdout + proc.stderr  # new confirmed medium blocks
    data = json.load(open(os.path.join(out, "diff.json")))
    assert data["counts"]["new"] == 1 and data["counts"]["persisting"] == 1
    assert data["counts"]["fixed"] == 1
    assert data["new"][0]["finding"]["subject"] == "new target C"
    assert data["fixed"][0]["finding"]["subject"] == "old target A"
    md = open(os.path.join(out, "diff.md")).read()
    assert "## NEW findings" in md and "new target C" in md and "old target A" in md


def test_unknown_new_finding_is_non_blocking(tmp_path):
    bdir = write_report(str(tmp_path / "b"), [])
    adir = write_report(str(tmp_path / "a"),
                        [finding(rule="R1", severity="medium", disposition="unresolved",
                                 subject="mixed artifact environments")])
    proc = run_cli(["diff", "--before", bdir, "--after", adir, "--out", str(tmp_path / "o"),
                    "--fail-on-new", "medium"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.load(open(str(tmp_path / "o" / "diff.json")))
    assert data["counts"]["new"] == 1
    assert data["counts"]["new_blocking"] == 0
    assert data["counts"]["new_unknown_non_blocking"] == 1
    assert data["new"][0]["blocking"] is False


def test_fail_on_new_severity_thresholds(tmp_path):
    bdir = write_report(str(tmp_path / "b"), [])
    adir = write_report(str(tmp_path / "a"), [finding(severity="medium")])
    for threshold, expected in (("medium", 1), ("high", 0), ("none", 0)):
        proc = run_cli(["diff", "--before", bdir, "--after", adir,
                        "--out", str(tmp_path / f"o-{threshold}"),
                        "--fail-on-new", threshold, "--quiet"])
        assert proc.returncode == expected, (threshold, proc.returncode, proc.stderr)


def test_persisting_high_severity_does_not_block(tmp_path):
    row = finding(severity="high", subject="pre-existing high")
    bdir = write_report(str(tmp_path / "b"), [row])
    adir = write_report(str(tmp_path / "a"), [row])
    proc = run_cli(["diff", "--before", bdir, "--after", adir, "--out", str(tmp_path / "o"),
                    "--fail-on-new", "low", "--quiet"])
    assert proc.returncode == 0
    data = json.load(open(str(tmp_path / "o" / "diff.json")))
    assert data["counts"]["persisting"] == 1 and data["counts"]["new_blocking"] == 0


def test_empty_baseline_and_empty_current(tmp_path):
    empty = write_report(str(tmp_path / "empty"), [])
    adir = write_report(str(tmp_path / "a"), [finding(severity="low")])
    # empty baseline -> current low is NEW; fail-on-new medium does not block
    proc = run_cli(["diff", "--before", empty, "--after", adir, "--out", str(tmp_path / "o1"),
                    "--fail-on-new", "medium"])
    assert proc.returncode == 0
    data = json.load(open(str(tmp_path / "o1" / "diff.json")))
    assert data["counts"]["new"] == 1 and data["counts"]["persisting"] == 0
    # empty current -> everything FIXED, clean
    proc = run_cli(["diff", "--before", adir, "--after", empty, "--out", str(tmp_path / "o2"),
                    "--fail-on-new", "low"])
    assert proc.returncode == 0
    data = json.load(open(str(tmp_path / "o2" / "diff.json")))
    assert data["counts"]["fixed"] == 1 and data["counts"]["new"] == 0


def test_missing_before_path_is_an_error(tmp_path):
    adir = write_report(str(tmp_path / "a"), [])
    proc = run_cli(["diff", "--before", str(tmp_path / "does-not-exist"),
                    "--after", adir, "--out", str(tmp_path / "o")])
    assert proc.returncode == 2
    assert "not found" in (proc.stdout + proc.stderr)


# ---------------------------------------------------------------- end-to-end sample repo
def _temp_sample(tmp_path):
    repo = str(tmp_path / "sample_repo")
    shutil.copytree(SAMPLE_REPO, repo)
    cfg = refs_config(repo, str(tmp_path / "refs.json"))
    return repo, cfg


def test_end_to_end_one_new_broken_reference(tmp_path):
    repo, cfg = _temp_sample(tmp_path)
    before = scan(repo, cfg, str(tmp_path / "before"))
    assert before.returncode == 0, before.stderr
    # break exactly one reference in the knowledge surface
    with open(os.path.join(repo, "docs", "clean.md"), "a", encoding="utf-8") as fh:
        fh.write("\nSee `docs/missing_after_pr.md` for details.\n")
    after = scan(repo, cfg, str(tmp_path / "after"))
    assert after.returncode == 0
    out = str(tmp_path / "diff")
    proc = run_cli(["diff", "--before", str(tmp_path / "before"),
                    "--after", str(tmp_path / "after"), "--out", out,
                    "--format", "md,json", "--fail-on-new", "medium"])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    data = json.load(open(os.path.join(out, "diff.json")))
    assert data["counts"]["new"] == 1, data["counts"]
    assert data["new"][0]["finding"]["rule"] == "R9"
    assert data["new"][0]["blocking"] is True
    assert data["counts"]["fixed"] == 0


def test_end_to_end_repair_is_fixed_and_clean(tmp_path):
    repo, cfg = _temp_sample(tmp_path)
    doc = os.path.join(repo, "docs", "clean.md")
    with open(doc, "a", encoding="utf-8") as fh:
        fh.write("\nSee `docs/missing_before_pr.md` for details.\n")
    before = scan(repo, cfg, str(tmp_path / "before"))
    assert before.returncode == 0
    with open(doc, encoding="utf-8") as fh:
        text = fh.read()
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write(text.replace("`docs/missing_before_pr.md`", "`docs/clean.md`"))
    after = scan(repo, cfg, str(tmp_path / "after"))
    out = str(tmp_path / "diff")
    proc = run_cli(["diff", "--before", str(tmp_path / "before"),
                    "--after", str(tmp_path / "after"), "--out", out,
                    "--fail-on-new", "medium"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.load(open(os.path.join(out, "diff.json")))
    assert data["counts"]["fixed"] >= 1 and data["counts"]["new"] == 0
