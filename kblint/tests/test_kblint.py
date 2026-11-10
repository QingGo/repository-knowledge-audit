"""kblint test suite (pytest). Deterministic: no network, no writes outside tmp dirs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SAMPLE_REPO = os.path.join(PKG, "examples", "sample_repo")
SAMPLE_CFG = os.path.join(PKG, "examples", "sample.kblint.json")
NANOV41_REPO = "/REPOS_ROOT/R0"
NANOV41_CFG = os.path.join(PKG, "examples", "R0.kblint.json")


def run_cli(args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = PKG
    return subprocess.run([sys.executable, "-m", "kblint", *args],
                          capture_output=True, text=True, cwd=cwd or PKG,
                          env=env, timeout=180)


def load_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def scan_sample(out_dir, extra=()):
    return run_cli(["scan", "--repo", SAMPLE_REPO, "--config", SAMPLE_CFG,
                    "--out", str(out_dir), "--now", "2026-11-05", "--format",
                    "json,md,sarif", *extra])


# ---------------------------------------------------------------- extractor
def test_extractor_table_rows_code_fences_and_locators(tmp_path):
    from kblint.config import Config
    from kblint.extract import parse_doc
    md = (
        "---\nowner: test\n---\n"
        "# Title\n"
        "\n"
        "| item | value |\n"
        "|---|---|\n"
        "| step | 60.94 ms |\n"
        "\n"
        "```\n"
        "torch 9.9.9+cu999  (fenced code must be skipped)\n"
        "```\n"
        "\n"
        "- [only a link](https://example.com)\n"
        "\n"
        "The best step is 60.94 ms and it is stable.\n"
    )
    claims, meta = parse_doc("docs/x.md", md, Config())
    assert meta["frontmatter"] == {"owner": "test"}
    texts = [c.text for c in claims]
    assert any("value: 60.94 ms" in t for t in texts), texts  # table row keeps header key
    assert not any("9.9.9" in t for t in texts)              # code fence skipped
    assert all("#L" in c.locator for c in claims)
    row = [c for c in claims if c.form == "table_row"][0]
    num = [n for n in row.features["numbers"] if n["value"] == 60.94][0]
    assert num["unit"] == "ms" and num["context"] == "value"
    # link-only line produces no claim
    assert not any("only a link" in t for t in texts)


def test_extractor_features():
    from kblint.config import Config
    from kblint.extract import extract_features
    md = "torch 2.14.1+cu130 on 2026-10-30; 358.8 TFLOPS; 15 variants; NANOV41_X=1."
    feats = extract_features(md, Config())
    assert feats["pins"]["torch"] == ["2.14.1+cu130"]
    assert feats["dates"] == ["2026-10-30"]
    assert {n["value"] for n in feats["numbers"]} >= {358.8, 15.0}
    assert "NANOV41_X=1" in feats["flags"]
    assert feats["counts"][0]["noun"] == "variants"


# -------------------------------------------------------------------- rules
def test_each_rule_fires_on_sample_repo(tmp_path):
    out = tmp_path / "out"
    proc = scan_sample(out)
    assert proc.returncode == 1, proc.stderr
    findings = load_jsonl(out / "findings.jsonl")
    by_rule = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6"):
        assert rule in by_rule, f"{rule} did not fire: {sorted(by_rule)}"
    assert any(f["rule"] == "R2" and f["disposition"] == "confirmed" and
               "400" in f["observed"] and "358.093" in f["observed"]
               for f in findings), "R2 artifact mismatch missed"
    assert any(f["rule"] == "R3" for f in findings), "R3 cross-doc conflict missed"
    assert any(f["rule"] == "R4" for f in findings), "R4 missing supersedes missed"
    # R7 is git-gated and the sample repo is not a repo -> no R7
    assert "R7" not in by_rule
    # every finding carries the contract fields
    for f in findings:
        for key in ("finding_id", "rule", "severity", "disposition", "subject",
                    "observed", "expected", "evidence", "verification_method",
                    "confidence", "suggested_action", "tags"):
            assert key in f, (f["rule"], key)
        assert f["disposition"] in ("confirmed", "unresolved", "provenance_gap",
                                    "revalidation_due")


def test_clean_control_repo_yields_no_findings(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "clean.md").write_text(
        "# Clean\n\nThe step time is 60.94 ms [artifacts/bench.json].\n")
    (repo / "artifacts").mkdir()
    (repo / "artifacts" / "bench.json").write_text(json.dumps({"step_ms": 60.94}))
    cfg = {
        "repo": "repo", "docs": ["docs/**/*.md"], "artifacts": ["artifacts/*.json"],
        "run_index": {"path": "repo/artifacts/index.jsonl"} if False else None,
        "expiry": {"env_change_date": "2026-10-01", "negative_flag_regex": []},
        "git": {"enabled": False}, "now": "2026-11-05",
    }
    cfg.pop("run_index")
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    proc = run_cli(["scan", "--config", str(cfg_path), "--out", str(tmp_path / "out"),
                    "--now", "2026-11-05"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert load_jsonl(tmp_path / "out" / "findings.jsonl") == []


def test_r7_git_and_owner_with_monkeypatched_git(tmp_path, monkeypatch):
    from kblint.config import Config
    from kblint.extract import extract_repo
    from kblint.rules import r7_untracked
    from kblint.rules.base import ScanContext, build_artifact_index

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "docs" / "tracked.md").write_text("# Tracked\n\nSome prose sentence here.\n")
    (repo / "docs" / "dirty.md").write_text("# Dirty\n\nSome prose sentence here.\n")
    (repo / "docs" / "untracked.md").write_text("# Untracked\n\nSome prose sentence here.\n")
    cfg = Config.from_dict({"repo": str(repo), "docs": ["docs/**/*.md"],
                            "git": {"enabled": True}})
    claims, dm = extract_repo(str(repo), cfg)
    ctx = ScanContext(repo=str(repo), cfg=cfg, claims=claims, doc_meta=dm,
                      artifacts=build_artifact_index(str(repo), cfg, []))
    fake = {"ls-files": "docs/tracked.md\ndocs/dirty.md\n",
            "status": " M docs/dirty.md\n?? docs/untracked.md\n"}
    monkeypatch.setattr(r7_untracked, "_git",
                        lambda repo_, *a: fake.get(a[0], "") if a else "")
    findings = r7_untracked.run(ctx)
    subjects = " | ".join(f.subject for f in findings)
    assert "untracked.md" in subjects
    assert "dirty.md" in subjects and "uncommitted" in subjects
    # clean control: only tracked.md
    cfg2 = Config.from_dict({"repo": str(repo), "docs": ["docs/tracked.md"],
                             "git": {"enabled": True}})
    claims2, dm2 = extract_repo(str(repo), cfg2)
    ctx2 = ScanContext(repo=str(repo), cfg=cfg2, claims=claims2, doc_meta=dm2,
                       artifacts=build_artifact_index(str(repo), cfg2, []))
    assert r7_untracked.run(ctx2) == []


# ------------------------------------------------------------- config/CLI
def test_config_defaults_docs_only_repo(tmp_path):
    repo = tmp_path / "docsrepo"
    repo.mkdir()
    (repo / "NOTES.md").write_text("# Notes\n\nThe target is 35.83 ms.\n")
    cfg = tmp_path / "default.json"
    cfg.write_text(json.dumps({"repo": str(repo)}))
    proc = run_cli(["scan", "--config", str(cfg), "--out", str(tmp_path / "out"),
                    "--now", "2026-11-05"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    findings = load_jsonl(tmp_path / "out" / "findings.jsonl")
    assert findings == [], findings
    audit = load_jsonl(tmp_path / "out" / "audit_queue.jsonl")
    assert audit, "docs-only repo should still produce an audit queue (R8)"


def test_unknown_config_key_is_error(tmp_path):
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"repo": ".", "docs_glob": ["**/*.md"]}))
    proc = run_cli(["scan", "--config", str(cfg), "--out", str(tmp_path / "o")])
    assert proc.returncode == 2
    assert "unknown config keys" in proc.stderr


def test_cli_exit_codes_and_rules_command(tmp_path):
    out = tmp_path / "out"
    proc = scan_sample(out, extra=["--fail-on", "high"])
    assert proc.returncode == 1  # high findings exist

    proc = scan_sample(tmp_path / "out2", extra=["--fail-on", "none"])
    assert proc.returncode == 0  # findings exist but threshold is none

    proc = run_cli(["rules"])
    assert proc.returncode == 0
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        assert rule in proc.stdout


def test_waiver_suppression(tmp_path):
    cfg = json.load(open(SAMPLE_CFG))
    cfg["run_index"]["path"] = os.path.join(SAMPLE_REPO, "artifacts", "runs_index.jsonl")
    # baseline count
    proc = scan_sample(tmp_path / "base")
    assert proc.returncode == 1
    base = load_jsonl(tmp_path / "base" / "findings.jsonl")
    target = [f for f in base if f["rule"] == "R2" and f["disposition"] == "confirmed"][0]
    cfg["waivers"] = [{"rule": "R2", "doc": "docs/numbers.md"}]
    cfg_path = tmp_path / "waived.json"
    cfg.pop("repo")
    cfg_path.write_text(json.dumps(cfg))
    proc = run_cli(["scan", "--repo", SAMPLE_REPO, "--config", str(cfg_path),
                    "--out", str(tmp_path / "waived"), "--now", "2026-11-05"])
    waived = load_jsonl(tmp_path / "waived" / "findings.jsonl")
    assert len(waived) < len(base)
    assert not any(f["rule"] == "R2" and f["doc"] == "docs/numbers.md" for f in waived)
    assert target  # sanity


def test_sarif_shape(tmp_path):
    scan_sample(tmp_path / "out")
    sarif = json.load(open(tmp_path / "out" / "report.sarif"))
    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif and "sarif" in sarif["$schema"]
    driver = sarif["runs"][0]["tool"]["driver"]
    assert driver["name"] == "kblint" and driver["version"]
    ids = {r["id"] for r in driver["rules"]}
    assert {"R1", "R2", "R8"} <= ids
    assert len(sarif["runs"][0]["results"]) >= 1
    for res in sarif["runs"][0]["results"]:
        assert res["ruleId"] in ids
        assert res["level"] in ("error", "warning", "note")
        assert res["message"]["text"]
        loc = res["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"]
        assert loc["region"]["startLine"] >= 1


def test_byte_identical_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    scan_sample(a)
    scan_sample(b)
    for name in ("findings.jsonl", "audit_queue.jsonl", "report.sarif", "summary.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


# ----------------------------------------------------------- precision fixes
def _write_repo(tmp_path, docs, artifacts, cfg_extra=None):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "artifacts").mkdir(exist_ok=True)
    for rel, text in docs.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    for rel, obj in artifacts.items():
        (repo / rel).write_text(json.dumps(obj))
    cfg = {"repo": str(repo), "docs": ["docs/**/*.md"],
           "artifacts": ["artifacts/*.json"], "tolerance": {"relative": 0.0005},
           "expiry": {"env_change_date": "2026-10-01", "negative_flag_regex": []},
           "git": {"enabled": False}, "now": "2026-11-05"}
    cfg.update(cfg_extra or {})
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    return repo, cfg_path


def test_fix1_rounding_aware_tolerance(tmp_path):
    docs = {
        "docs/rounding.md": (
            "# Rounding\n\n"
            "Step 13.5 ms [artifacts/vals.json].\n\n"
            "Throughput 105 TFLOP/s [artifacts/vals.json].\n\n"
            "Latency 7.5 ms [artifacts/vals.json].\n\n"
            "Budget 9.9 ms [artifacts/vals.json].\n\n"
            "Overhead 1.02 ms [artifacts/vals.json].\n\n"
            "The dW13 tile reaches 358.8 TFLOPS [artifacts/vals.json].\n"
        ),
    }
    artifacts = {"artifacts/vals.json": {
        "step_ms": 13.51, "tflops": 105.365, "latency_ms": 7.55,
        "budget_ms": 9.93, "overhead_ms": 1.017, "dw13_tile_tflops": 358.093}}
    repo, cfg_path = _write_repo(tmp_path, docs, artifacts)
    proc = run_cli(["scan", "--config", str(cfg_path), "--out", str(tmp_path / "out")])
    findings = load_jsonl(tmp_path / "out" / "findings.jsonl")
    r2 = [f for f in findings if f["rule"] == "R2"]
    # rounding cases (13.5/105/7.5/9.9/1.02) are matches; 358.8 vs 358.093 must stay
    confirmed = [f for f in r2 if f["disposition"] == "confirmed"]
    assert len(confirmed) == 1, r2
    assert "358.8" in confirmed[0]["observed"] and "358.093" in confirmed[0]["observed"]
    assert not any(("13.5" in f["observed"] or "105" in f["observed"]
                    or "7.5" in f["observed"] or "9.9" in f["observed"]
                    or "1.02" in f["observed"]) for f in confirmed), confirmed
    # display-precision unit checks
    from kblint.rules.r2_number import display_half_unit, within_display_precision
    assert display_half_unit("655") == 0.5
    assert display_half_unit("358.8") == 0.05
    assert within_display_precision(105, 105.365, "105", 5e-4)
    assert within_display_precision(1.02, 1.017, "1.02", 5e-4)
    assert not within_display_precision(358.8, 358.093, "358.8", 5e-4)


def test_fix2_target_language_is_not_confirmed(tmp_path):
    docs = {"docs/target.md": (
        "# Target\n\nThe target is 60% MFU [artifacts/run.json].\n")}
    artifacts = {"artifacts/run.json": {"discounted_mfu_pct": 38.41}}
    repo, cfg_path = _write_repo(tmp_path, docs, artifacts)
    run_cli(["scan", "--config", str(cfg_path), "--out", str(tmp_path / "out")])
    findings = load_jsonl(tmp_path / "out" / "findings.jsonl")
    r2 = [f for f in findings if f["rule"] == "R2"]
    assert not any(f["disposition"] == "confirmed" for f in r2), r2
    assert any(f["disposition"] == "revalidation_due" for f in r2), r2


def test_fix3_r4_disabled_by_default(tmp_path):
    cfg = json.load(open(SAMPLE_CFG))
    cfg["repo"] = SAMPLE_REPO
    cfg["run_index"]["path"] = os.path.join(SAMPLE_REPO, "artifacts", "runs_index.jsonl")
    cfg.pop("rules", None)
    p = tmp_path / "default.json"
    p.write_text(json.dumps(cfg))
    run_cli(["scan", "--config", str(p), "--out", str(tmp_path / "default")])
    default = load_jsonl(tmp_path / "default" / "findings.jsonl")
    assert not any(f["rule"] == "R4" for f in default)
    cfg["rules"] = {"R4": {"enabled": True}}
    p.write_text(json.dumps(cfg))
    run_cli(["scan", "--config", str(p), "--out", str(tmp_path / "enabled")])
    enabled = load_jsonl(tmp_path / "enabled" / "findings.jsonl")
    assert any(f["rule"] == "R4" for f in enabled)
    summary = (tmp_path / "enabled" / "summary.md").read_text()
    assert "R4 (missing supersedes) is ENABLED" in summary


def test_fix4_mixed_pin_environments_unresolved(tmp_path):
    docs = {"docs/pins.md": "# Pins\n\nThe environment uses torch 2.14.1+cu130.\n"}
    artifacts = {"artifacts/a.json": {"torch": "2.12.1+cu130"},
                 "artifacts/b.json": {"torch": "2.14.1+cu130"}}
    pins = [{"doc_glob": "docs/**/*.md", "artifact_glob": "artifacts/*.json",
             "artifact_keys": ["torch"],
             "doc_patterns": ["torch\\s+([0-9.]+\\+cu[0-9]+)"]}]
    repo, cfg_path = _write_repo(tmp_path, docs, artifacts, {"pins": pins})
    run_cli(["scan", "--config", str(cfg_path), "--out", str(tmp_path / "mixed")])
    r1 = [f for f in load_jsonl(tmp_path / "mixed" / "findings.jsonl") if f["rule"] == "R1"]
    assert len(r1) == 1, r1
    assert r1[0]["disposition"] == "unresolved" and r1[0]["severity"] == "low"
    assert "mixed artifact environments" in r1[0]["subject"]
    # single-environment pool still yields a confirmed high finding
    artifacts_single = {"artifacts/a.json": {"torch": "2.12.1+cu130"}}
    repo2 = tmp_path / "repo2"
    (repo2 / "docs").mkdir(parents=True, exist_ok=True)
    (repo2 / "artifacts").mkdir()
    (repo2 / "docs" / "pins.md").write_text(docs["docs/pins.md"])
    (repo2 / "artifacts" / "a.json").write_text(json.dumps(artifacts_single["artifacts/a.json"]))
    cfg = {"repo": str(repo2), "docs": ["docs/**/*.md"], "artifacts": ["artifacts/*.json"],
           "pins": pins, "git": {"enabled": False}, "now": "2026-11-05"}
    p2 = tmp_path / "cfg2.json"
    p2.write_text(json.dumps(cfg))
    run_cli(["scan", "--config", str(p2), "--out", str(tmp_path / "single")])
    r1s = [f for f in load_jsonl(tmp_path / "single" / "findings.jsonl") if f["rule"] == "R1"]
    assert len(r1s) == 1 and r1s[0]["disposition"] == "confirmed" and r1s[0]["severity"] == "high"


# --------------------------------------------------------------- regression
@pytest.mark.skipif(not os.path.isdir(NANOV41_REPO), reason="R0 design repo not present")
def test_R0_smoke_and_known_issues(tmp_path):
    start = time.time()
    proc = run_cli(["scan", "--config", NANOV41_CFG, "--out", str(tmp_path / "out"),
                    "--now", "2026-11-05", "--quiet"])
    elapsed = time.time() - start
    assert proc.returncode == 1, proc.stderr
    assert elapsed < 60, elapsed
    findings = load_jsonl(tmp_path / "out" / "findings.jsonl")
    confirmed = [f for f in findings if f["disposition"] == "confirmed"]
    assert len(confirmed) >= 5
    # (b) known doc/artifact drift: 358.8 TFLOPS stated vs 358.093 in the cited run
    assert any(f["rule"] == "R2" and "358.8" in f["observed"] and "358.093" in f["observed"]
               for f in confirmed)
    # (a) committed-vs-worktree drift on docs/benchmarks.md
    assert any(f["rule"] == "R7" and "docs/benchmarks.md" in (f["doc"] or "")
               and "uncommitted" in f["subject"] for f in confirmed)
    # R1 pin handling: R0's artifact pool has mixed environments (2.12.1/2.14.1),
    # so R1 must emit unresolved mixed-environment findings, not confirmed defects.
    r1 = [f for f in findings if f["rule"] == "R1"]
    assert r1 and all(f["disposition"] == "unresolved" for f in r1), r1[:3]
    assert any("mixed artifact environments" in f["subject"] for f in r1)
    # audit queue exists and is never in findings as R8
    audit = load_jsonl(tmp_path / "out" / "audit_queue.jsonl")
    assert audit and all(a["rule"] == "R8" for a in audit)
    assert not any(f["rule"] == "R8" for f in findings)


# ---------------------------------------------------------------- R9 reference check
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _ref_repo(tmp_path, files, references=None, extra_cfg=None):
    """Create a tiny repo + config for R9 tests; returns (repo, cfg)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    for rel, text in files.items():
        _write(str(repo / rel), text)
    cfg = {"repo": str(repo), "docs": ["**/*.md"],
           "git": {"enabled": False}, "now": "2026-11-05",
           "references": references if references is not None else {"enabled": True}}
    if extra_cfg:
        cfg.update(extra_cfg)
    cfg_path = tmp_path / "kblint.json"
    cfg_path.write_text(json.dumps(cfg))
    return repo, cfg_path


def _scan_repo(repo, cfg_path, out_dir, extra=()):
    return run_cli(["scan", "--repo", str(repo), "--config", str(cfg_path),
                    "--out", str(out_dir), "--now", "2026-11-05",
                    "--format", "json,md,sarif", *extra])


def _r9(out_dir):
    return [f for f in load_jsonl(os.path.join(out_dir, "findings.jsonl"))
            if f["rule"] == "R9"]


def test_r9_missing_and_existing_links(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "# KB\n\n[guide](docs/guide.md) and [gone](docs/gone.md)\n",
        "docs/guide.md": "# Guide\n",
    })
    out = tmp_path / "out"
    r = _scan_repo(repo, cfg, out)
    assert r.returncode == 0, r.stderr
    found = _r9(out)
    assert len(found) == 1, found
    f = found[0]
    assert "docs/gone.md" in f["subject"]
    assert f["doc"] == "AGENTS.md" and f["locator"].startswith("AGENTS.md#L")
    assert f["disposition"] == "confirmed" and f["severity"] == "medium"
    assert f["claim_id"] is None  # doc+locator is set explicitly; not collapsed by claim dedupe


def test_r9_nested_doc_relative_resolution(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "docs/AGENTS.md": "# Nested\n\n[ok](./sub/a.md) [ok2](docs/sub/a.md) "
                          "[bad](sub/missing.md)\n",
        "docs/sub/a.md": "# A\n",
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    assert [f["subject"] for f in found] == ["markdown link does not exist: sub/missing.md"]
    assert "docs/sub/missing.md" in found[0]["evidence"][1]


def test_r9_backticked_paths_and_noise(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": (
            "# KB\n\n"
            "The entry is `compiler/pipeline/__init__.py`; stale: "
            "`compiler/pipeline/gone.py`.\n\n"
            "Ignore `docs/**/*.md`, `/etc/passwd`, `docs/{name}.md`, "
            "`https://x/y.md`, and `$HOME/z.md`.\n"
        ),
        "compiler/pipeline/__init__.py": "x = 1\n",
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    assert len(found) == 1, found
    assert "compiler/pipeline/gone.py" in found[0]["subject"]
    assert found[0]["tags"] == ["references", "path"]


def test_r9_make_targets(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "# KB\n\nRun `make test` then `make deploy`.\n\n"
                     "```bash\nmake build\nmake ghost\n```\n",
        "Makefile": ".PHONY: test build\n\ntest:\n\t@echo ok\nbuild:\n\t@echo build\n",
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    subjects = sorted(f["subject"] for f in found)
    assert subjects == ["make target does not exist: deploy",
                        "make target does not exist: ghost"], subjects
    assert all(f["severity"] == "low" and f["doc"] == "AGENTS.md" for f in found)
    # no root Makefile -> the make check must self-skip entirely
    repo2, cfg2 = _ref_repo(tmp_path / "norepo", {"AGENTS.md": "run `make anything`\n"})
    out2 = tmp_path / "out2"
    _scan_repo(repo2, cfg2, out2)
    assert _r9(out2) == []


def test_r9_npm_scripts(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "# KB\n\n`npm run test`, `pnpm run lint`, `yarn run missing`\n",
        "package.json": json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}),
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    assert len(found) == 1 and "missing" in found[0]["subject"], found
    repo2, cfg2 = _ref_repo(tmp_path / "nopkg", {"AGENTS.md": "`npm run anything`\n"})
    out2 = tmp_path / "out2"
    _scan_repo(repo2, cfg2, out2)
    assert _r9(out2) == []


def test_r9_fence_behavior_is_conservative(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": (
            "# KB\n\n"
            "```text\n├── ghost/file.py\n└── `docs/also-ghost.md`\n```\n\n"
            "```bash\nmake nothere\n```\n"
        ),
        "Makefile": "ok:\n\t@echo ok\n",
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    # tree-diagram paths and inline-code paths inside fences are ignored; run commands are not
    assert [f["subject"] for f in found] == ["make target does not exist: nothere"], found


def test_r9_allow_missing_and_inventory(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "# KB\n\n`vendor/gone.py` and `external/sdk.py` and `src/gone.py`\n",
    }, references={"enabled": True, "allow_missing": ["^vendor/"],
                   "inventory": ["external/**"]})
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    assert [f["subject"] for f in found] == ["file path does not exist: src/gone.py"], found


def test_r9_check_flags_and_rule_switch(tmp_path):
    files = {
        "AGENTS.md": "[gone](docs/gone.md) `src/gone.py` `make nothere`\n",
        "Makefile": "ok:\n\t@echo ok\n",
    }
    for i, (refs, expect) in enumerate([
        ({"enabled": False}, 0),
        ({"check_links": False}, 2),
        ({"check_paths": False}, 2),
        ({"check_make": False}, 2),
    ]):
        repo, cfg = _ref_repo(tmp_path / f"r{i}", files, references=refs)
        out = tmp_path / f"o{i}"
        _scan_repo(repo, cfg, out)
        assert len(_r9(out)) == expect, (refs, _r9(out))
    repo, cfg = _ref_repo(tmp_path / "ruleoff", files, extra_cfg={"rules": {"R9": False}})
    out = tmp_path / "out-ruleoff"
    _scan_repo(repo, cfg, out)
    assert _r9(out) == []


def test_r9_config_validation_errors(tmp_path):
    files = {"AGENTS.md": "run `make x`\n"}
    for i, refs in enumerate(({"unknown_key": True}, {"enabled": "yes"},
                              {"allow_missing": ["("]}, {"inventory": [1]})):
        repo, cfg = _ref_repo(tmp_path / f"bad{i}", files, references=refs)
        r = _scan_repo(repo, cfg, tmp_path / "out")
        assert r.returncode == 2, (refs, r.returncode, r.stderr)
        assert "references" in r.stderr


def test_r9_report_integration_and_exit_codes(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {"AGENTS.md": "[gone](docs/gone.md)\n"})
    out = tmp_path / "out"
    r = _scan_repo(repo, cfg, out, extra=("--fail-on", "medium"))
    assert r.returncode == 1, (r.returncode, r.stdout)
    summary = (out / "summary.md").read_text()
    assert "| R9 | reference check | 1 |" in summary
    sarif = json.loads((out / "report.sarif").read_text())
    rule_ids = {rule["id"] for rule in sarif["runs"][0]["tool"]["driver"]["rules"]}
    assert "R9" in rule_ids
    assert any(res["ruleId"] == "R9" for res in sarif["runs"][0]["results"])
    r2 = _scan_repo(repo, cfg, tmp_path / "out2", extra=("--fail-on", "none"))
    assert r2.returncode == 0


def test_r9_determinism_and_anchor_stripping(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "[ok](docs/guide.md#L10) [bad](docs/gone.md#L3?raw=1)\n",
        "docs/guide.md": "# Guide\n",
    })
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    _scan_repo(repo, cfg, out1)
    _scan_repo(repo, cfg, out2)
    assert (out1 / "findings.jsonl").read_bytes() == (out2 / "findings.jsonl").read_bytes()
    found = _r9(out1)
    assert [f["subject"] for f in found] == ["markdown link does not exist: docs/gone.md"]


def test_r9_illustrative_markers_and_bare_link_stubs(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": (
            "# KB\n\n"
            "Use modern layouts, e.g. `layouts/page.html` for pages.\n"
            "Generated docs may contain stub links [Language](g) and [intro](intro).\n"
            "But a real stale reference `src/gone.py` is still reported.\n"
        ),
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    found = _r9(out)
    assert [f["subject"] for f in found] == ["file path does not exist: src/gone.py"], found


def test_r9_same_missing_target_in_two_docs_is_not_collapsed(tmp_path):
    repo, cfg = _ref_repo(tmp_path, {
        "AGENTS.md": "stale `src/gone.py`\n",
        "docs/AGENTS.md": "also stale `src/gone.py`\n",
    })
    out = tmp_path / "out"
    _scan_repo(repo, cfg, out)
    docs = sorted(f["doc"] for f in _r9(out))
    assert docs == ["AGENTS.md", "docs/AGENTS.md"], docs


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_r7_non_ascii_git_paths_real_repo(tmp_path):
    """Regression: git C-escapes non-ASCII paths by default; R7 must use core.quotepath=false
    (and unquote the remaining quoted status paths) or every tracked non-ASCII doc looks untracked."""
    from kblint.config import Config
    from kblint.extract import extract_repo
    from kblint.rules import r7_untracked
    from kblint.rules.base import ScanContext, build_artifact_index

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    clean = repo / "docs" / "商业计划.md"
    dirty = repo / "docs" / "技术方案.md"
    clean.write_text("# 商业计划\n\nSome prose sentence here.\n")
    dirty.write_text("# 技术方案\n\nSome prose sentence here.\n")

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.email", "kb@example.com")
    git("config", "user.name", "kb")
    git("add", "docs")
    git("commit", "-qm", "init")

    # untracked non-ASCII doc + uncommitted edit to a tracked non-ASCII doc
    (repo / "docs" / "新增文档.md").write_text("# 新增\n\nSome prose sentence here.\n")
    dirty.write_text(dirty.read_text() + "\nChanged line.\n")

    cfg = Config.from_dict({"repo": str(repo), "docs": ["docs/**/*.md"],
                            "git": {"enabled": True}})
    claims, dm = extract_repo(str(repo), cfg)
    ctx = ScanContext(repo=str(repo), cfg=cfg, claims=claims, doc_meta=dm,
                      artifacts=build_artifact_index(str(repo), cfg, []))
    subjects = {f.subject for f in r7_untracked.run(ctx)}
    assert "knowledge doc not tracked in git: docs/新增文档.md" in subjects
    assert "uncommitted change to tracked knowledge doc: docs/技术方案.md" in subjects
    assert not any("商业计划.md" in s for s in subjects), subjects
    # witness that plain git really does C-escape the path (the original bug surface)
    raw = subprocess.run(["git", "-C", str(repo), "ls-files", "docs"],
                         capture_output=True, text=True, check=True).stdout
    assert "\\345" in raw and "商业计划" not in raw
