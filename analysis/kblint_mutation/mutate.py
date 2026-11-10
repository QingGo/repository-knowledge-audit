#!/usr/bin/env python3
"""Build controlled mutation fixtures for the kblint mutation evaluation.

Deterministic, offline, stdlib only. Writes ONLY under this directory.

Base fixtures (built from scratch in the style of kblint/examples/sample_repo, so each
claim starts VALID and the negative control is genuinely a non-finding):

  fixtures/repos/base_r1r6/   docs + artifact index for R1,R2,R3,R5,R6
  fixtures/repos/base_git/    small git repo for R7 (tracked/untracked/owner)
  fixtures/repos/base_r9/     reference-valid repo for R9 (paths / make / npm / links)

Each mutation is a (base repo, edits) pair producing one fixture repo + one config:
  negative_control : unchanged                     -> must NOT fire on the target doc
  positive         : referenced truth broken       -> MUST fire on the target doc
  hard_negative    : benign change, claim stays valid -> must NOT fire on the target doc

Run: python3 mutate.py build      (rewrites fixtures/repos, fixtures/configs, MANIFEST)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
REPOS = FIX / "repos"
CONFIGS = FIX / "configs"
NOW = "2026-11-05"
GIT_DATE = "2026-11-01T00:00:00+08:00"


def w(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def base_r1r6(root: Path):
    w(root, "docs/pins.md",
      "# Environment pins\n\n"
      "The training environment uses torch 2.14.1+cu130 for all reported runs.\n")
    w(root, "docs/numbers.md",
      "# Reported numbers\n\n"
      "The best dW13 tile reaches 358.093 TFLOPS [artifacts/bench.json].\n")
    w(root, "docs/nums_round.md",
      "# Step time\n\n"
      "The best dW13 tile step is 60.94 ms for the best configuration [artifacts/bench.json].\n")
    w(root, "docs/conflict_a.md",
      "# Run A notes\n\nR49 configuration best step is 60.94 ms in the primary sweep.\n")
    w(root, "docs/conflict_b.md",
      "# Run B notes\n\nR49 configuration best step is 60.94 ms in the replicated sweep.\n")
    w(root, "docs/negative.md",
      "# FP8 experiment log\n\n"
      "2026-10-20: FP8 MoE showed no gain under the new build; still paused.\n")
    w(root, "docs/neg2.md",
      "# Grouped dW probe\n\n"
      "2026-10-15: the grouped dW route showed no gain and was paused.\n")
    w(root, "docs/canonical.md",
      "# Acceptance target\n\n"
      "The acceptance target is 35.83 ms discounted.\n")
    w(root, "docs/other.md",
      "# Acceptance notes\n\n"
      "The acceptance target is 35.83 ms discounted; see docs/canonical.md for the definition.\n")
    w(root, "docs/other2.md",
      "# Target recap\n\n"
      "The acceptance target definition is in docs/canonical.md.\n")
    w(root, "artifacts/bench.json", json.dumps({
        "dw13_tile_tflops": 358.093,
        "dw13_tile_step_ms": 60.94,
        "variants": 4,
    }, indent=1) + "\n")
    w(root, "artifacts/env1.json",
      json.dumps({"torch": "2.14.1+cu130", "run_id": "env1"}, indent=1) + "\n")
    w(root, "artifacts/env2.json",
      json.dumps({"torch": "2.14.1+cu130", "run_id": "env2"}, indent=1) + "\n")
    w(root, "artifacts/target.json",
      json.dumps({"acceptance_target_ms": 35.83, "kind": "discounted"}, indent=1) + "\n")


def base_git(root: Path):
    w(root, "docs/guide.md",
      "---\nowner: qinggo\n---\n\n# Guide\n\n"
      "The training recipe uses torch 2.14.1+cu130.\n")
    w(root, "docs/notes.md",
      "---\nowner: qinggo\n---\n\n# Notes\n\n"
      "The measured step is 60.94 ms.\n")
    w(root, "README.md", "# base git fixture\n\nSee docs/guide.md.\n")


def base_r9(root: Path):
    """Reference-valid fixture: docs reference real paths, make target, npm script and link."""
    w(root, "docs/guide.md",
      "# Build guide\n\n"
      "The training entry point is `src/train.py`.\n\n"
      "Run `make test` before publishing.\n\n"
      "The web UI is built with `npm run build`.\n\n"
      "See the [setup section](setup.md) for prerequisites.\n")
    w(root, "docs/setup.md", "# Setup\n\nInstall the local requirements first.\n")
    w(root, "src/train.py", "# training entry point\n")
    w(root, "Makefile", "test:\n\tpython3 -m pytest -q\n\nlint:\n\tpython3 -m py_compile src/train.py\n")
    w(root, "package.json", json.dumps(
        {"name": "ref-fixture", "scripts": {"build": "node build.js", "test": "node test.js"}},
        indent=1) + "\n")
    w(root, "build.js", "// build\n")
    w(root, "test.js", "// test\n")


def cfg(repo_rel: str, **over) -> dict:
    c = {
        "repo": f"../repos/{repo_rel}",
        "docs": ["docs/**/*.md"],
        "exclude": [".git/**"],
        "tolerance": {"relative": 0.0005},
        "git": {"enabled": False},
        "now": NOW,
        "rules": {"R4": False},
    }
    c.update(over)
    return c


R1R6_CONFIG = dict(
    artifacts=["artifacts/*.json"],
    pins=[{
        "doc_glob": "docs/pins.md",
        "artifact_glob": "artifacts/env*.json",
        "artifact_keys": ["torch"],
        "doc_patterns": [r"torch\s+([0-9.]+\+cu[0-9]+)"],
    }],
    source_of_truth=[{"topic": "acceptance target",
                      "canonical_doc": "docs/canonical.md", "canonical_locator": "#L3"}],
    expiry={"env_change_date": "2026-10-01", "negative_flag_regex": []},
)
GIT_CONFIG = dict(git={"enabled": True}, owner={"frontmatter_keys": ["owner"]})
R9_CONFIG = dict(references={"enabled": True})


def _git(root: Path, *args: str):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": GIT_DATE, "GIT_COMMITTER_DATE": GIT_DATE,
    })
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   text=True, env=env)


def init_git(root: Path):
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture: base")


# ---------------------------------------------------------------------------
# mutation cases
# ---------------------------------------------------------------------------
def cases():
    """Each case: dict with id, rule, mutation, base, edits[], git_ops[], config, target_doc,
    target_claim (description), expect: detected|not_detected, expected_dispositions[]."""
    C = []

    def add(cid, rule, mutation, base, target_doc, expect, **kw):
        c = {"id": cid, "rule": rule, "mutation": mutation, "base": base,
             "target_doc": target_doc, "expect": expect,
             "edits": kw.get("edits", []), "git_ops": kw.get("git_ops", []),
             "config": kw.get("config"), "target_claim": kw.get("target_claim", ""),
             "expected_dispositions": kw.get("expected_dispositions", [])}
        C.append(c)

    # ---- R1 pin/version ---------------------------------------------------
    r1c = dict(R1R6_CONFIG)
    add("R1-NC", "R1", "negative_control", "base_r1r6", "docs/pins.md", "not_detected",
        config=r1c, target_claim="torch 2.14.1+cu130 pin matches both artifacts")
    add("R1-POS-single", "R1", "positive", "base_r1r6", "docs/pins.md", "detected",
        config=r1c, expected_dispositions=["confirmed"],
        target_claim="both artifacts moved to torch 2.13.1+cu130 while doc pins 2.14.1",
        edits=[("write", "artifacts/env1.json", json.dumps(
            {"torch": "2.13.1+cu130", "run_id": "env1"}, indent=1) + "\n"),
               ("write", "artifacts/env2.json", json.dumps(
                   {"torch": "2.13.1+cu130", "run_id": "env2"}, indent=1) + "\n")])
    add("R1-POS-mixed", "R1", "positive", "base_r1r6", "docs/pins.md", "detected",
        config=r1c, expected_dispositions=["unresolved"],
        target_claim="artifact pool mixed 2.13.1/2.14.1 while doc pins 2.14.1",
        edits=[("write", "artifacts/env1.json", json.dumps(
            {"torch": "2.13.1+cu130", "run_id": "env1"}, indent=1) + "\n")])
    add("R1-HN-unrelated", "R1", "hard_negative", "base_r1r6", "docs/pins.md",
        "not_detected", config=r1c,
        target_claim="prose note added + third artifact with the same pin",
        edits=[("append", "docs/pins.md", "\nThis note is prose and states no environment pin.\n"),
               ("write", "artifacts/env3.json", json.dumps(
                   {"torch": "2.14.1+cu130", "run_id": "env3", "note": "extra"}, indent=1) + "\n")])
    add("R1-HN-newdoc", "R1", "hard_negative", "base_r1r6", "docs/pins.md",
        "not_detected", config=r1c,
        target_claim="a second doc states the same correct pin; governed by same artifacts",
        edits=[("write", "docs/pins_extra.md",
                "# Extra pins\n\nThe environment uses torch 2.14.1+cu130 as well.\n")])

    # ---- R2 number provenance --------------------------------------------
    r2c = dict(R1R6_CONFIG)
    add("R2-NC", "R2", "negative_control", "base_r1r6", "docs/numbers.md", "not_detected",
        config=r2c, target_claim="358.093 TFLOPS matches dw13_tile_tflops")
    add("R2-POS-mismatch", "R2", "positive", "base_r1r6", "docs/numbers.md", "detected",
        config=r2c, expected_dispositions=["confirmed"],
        target_claim="artifact dw13_tile_tflops changed 358.093 -> 400.0",
        edits=[("write", "artifacts/bench.json", json.dumps({
            "dw13_tile_tflops": 400.0, "dw13_tile_step_ms": 60.94, "variants": 4},
            indent=1) + "\n")])
    add("R2-POS-missing", "R2", "positive", "base_r1r6", "docs/numbers.md", "detected",
        config=r2c, expected_dispositions=["revalidation_due"],
        target_claim="cited artifact file deleted",
        edits=[("delete", "artifacts/bench.json")])
    add("R2-HN-rounding", "R2", "hard_negative", "base_r1r6", "docs/numbers.md",
        "not_detected", config=r2c,
        target_claim="artifact value 358.0934 differs only below display precision",
        edits=[("write", "artifacts/bench.json", json.dumps({
            "dw13_tile_tflops": 358.0934, "dw13_tile_step_ms": 60.94, "variants": 4},
            indent=1) + "\n")])
    add("R2-HN-unrelated", "R2", "hard_negative", "base_r1r6", "docs/numbers.md",
        "not_detected", config=r2c,
        target_claim="unrelated artifact fields changed; cited number unchanged",
        edits=[("write", "artifacts/bench.json", json.dumps({
            "dw13_tile_tflops": 358.093, "dw13_tile_step_ms": 60.79, "variants": 5},
            indent=1) + "\n")])
    add("R2b-NC", "R2", "negative_control", "base_r1r6", "docs/nums_round.md",
        "not_detected", config=r2c, target_claim="60.94 ms matches dw13_tile_step_ms")
    add("R2b-POS-mismatch", "R2", "positive", "base_r1r6", "docs/nums_round.md", "detected",
        config=r2c, expected_dispositions=["confirmed"],
        target_claim="artifact dw13_tile_step_ms changed 60.94 -> 60.79",
        edits=[("write", "artifacts/bench.json", json.dumps({
            "dw13_tile_tflops": 358.093, "dw13_tile_step_ms": 60.79, "variants": 4},
            indent=1) + "\n")])

    add("R2-HN-boundary", "R2", "hard_negative", "base_r1r6", "docs/numbers.md",
        "not_detected", config=r2c,
        target_claim="artifact 358.0936 differs by 0.0006 (more than display half 0.0005 but "
                     "inside the configured 5e-4 relative tolerance) -> correctly not flagged",
        edits=[("write", "artifacts/bench.json", json.dumps({
            "dw13_tile_tflops": 358.0936, "dw13_tile_step_ms": 60.94, "variants": 4},
            indent=1) + "\n")])
    # ---- R3 cross-doc conflict -------------------------------------------
    r3c = dict(R1R6_CONFIG)
    add("R3-NC", "R3", "negative_control", "base_r1r6", "docs/conflict_a.md",
        "not_detected", config=r3c, target_claim="conflict_a and conflict_b both state 60.94")
    add("R3-POS-conflict", "R3", "positive", "base_r1r6", "docs/conflict_a.md", "detected",
        config=r3c, expected_dispositions=["confirmed"],
        target_claim="conflict_b changed 60.94 -> 61.93",
        edits=[("write", "docs/conflict_b.md",
                "# Run B notes\n\nR49 configuration best step is 61.93 ms in the replicated sweep.\n")])
    add("R3-HN-tolerance", "R3", "hard_negative", "base_r1r6", "docs/conflict_a.md",
        "not_detected", config=r3c,
        target_claim="conflict_b changed to 60.9405, within the conflict tolerance",
        edits=[("write", "docs/conflict_b.md",
                "# Run B notes\n\nR49 configuration best step is 60.9405 ms in the replicated sweep.\n")])
    add("R3-HN-supersede", "R3", "hard_negative", "base_r1r6", "docs/conflict_a.md",
        "not_detected", config=r3c,
        target_claim="conflicting value added but the section is explicitly marked superseded",
        edits=[("write", "docs/conflict_b.md",
                "# Run B notes\n\nSuperseded: the R49 configuration best step was 61.93 ms in the "
                "replicated sweep.\n")])

    # ---- R5 expiry --------------------------------------------------------
    r5c = dict(R1R6_CONFIG)
    add("R5-NC", "R5", "negative_control", "base_r1r6", "docs/negative.md", "not_detected",
        config=r5c, target_claim="negative claim dated 2026-10-20 is after env change 2026-10-01")
    add("R5-HN-boundary", "R5", "hard_negative", "base_r1r6", "docs/negative.md",
        "not_detected", config=r5c,
        target_claim="negative claim dated exactly on env_change_date (rule treats as current)",
        edits=[("replace", "docs/negative.md", "2026-10-20", "2026-10-01")])
    add("R5-POS-old", "R5", "positive", "base_r1r6", "docs/negative.md", "detected",
        config=r5c, expected_dispositions=["confirmed"],
        target_claim="negative claim re-dated to 2026-09-01 (before env change)",
        edits=[("replace", "docs/negative.md", "2026-10-20", "2026-09-01")])
    add("R5-POS-undated", "R5", "positive", "base_r1r6", "docs/negative.md", "detected",
        config=r5c, expected_dispositions=["revalidation_due"],
        target_claim="negative claim date removed (expiry unknown -> queue)",
        edits=[("replace", "docs/negative.md", "2026-10-20: ", "")])
    add("R5-HN-new", "R5", "hard_negative", "base_r1r6", "docs/negative.md",
        "not_detected", config=r5c,
        target_claim="negative claim re-dated 2026-10-28 (after env change)",
        edits=[("replace", "docs/negative.md", "2026-10-20", "2026-10-28")])
    add("R5-HN-supersede", "R5", "hard_negative", "base_r1r6", "docs/negative.md",
        "not_detected", config=r5c,
        target_claim="old negative claim explicitly superseded/retracted",
        edits=[("write", "docs/negative.md",
                "# FP8 experiment log\n\n2026-09-01: FP8 MoE showed no gain under the old build; "
                "superseded and no longer valid after the rebuild.\n")])
    add("R5b-NC", "R5", "negative_control", "base_r1r6", "docs/neg2.md", "not_detected",
        config=r5c, target_claim="second negative claim dated after env change")
    add("R5b-POS-old", "R5", "positive", "base_r1r6", "docs/neg2.md", "detected",
        config=r5c, expected_dispositions=["confirmed"],
        target_claim="grouped dW negative claim re-dated to 2026-09-15",
        edits=[("replace", "docs/neg2.md", "2026-10-15", "2026-09-15")])

    # ---- R6 source-of-truth ----------------------------------------------
    r6c = dict(R1R6_CONFIG)
    add("R6-NC", "R6", "negative_control", "base_r1r6", "docs/other2.md", "not_detected",
        config=r6c, target_claim="non-canonical doc references docs/canonical.md")
    add("R6-POS-missing", "R6", "positive", "base_r1r6", "docs/other2.md", "detected",
        config=r6c, expected_dispositions=["unresolved"],
        target_claim="canonical reference removed from the topic claim",
        edits=[("write", "docs/other2.md",
                "# Target recap\n\nThe acceptance target definition is recorded above.\n")])
    add("R6-HN-reference", "R6", "hard_negative", "base_r1r6", "docs/other2.md",
        "not_detected", config=r6c,
        target_claim="reference retained in a longer memo",
        edits=[("append", "docs/other2.md",
                "\nFor the current values see docs/canonical.md.\n")])
    add("R6-HN-canonical-edit", "R6", "hard_negative", "base_r1r6", "docs/other2.md",
        "not_detected", config=r6c,
        target_claim="canonical doc itself edited (canonical doc is exempt)",
        edits=[("write", "docs/canonical.md",
                "# Acceptance target\n\nThe acceptance target remains 35.83 ms discounted.\n")])

    # ---- R7 git -----------------------------------------------------------
    g = dict(GIT_CONFIG)
    add("R7-NC", "R7", "negative_control", "base_git", "docs/guide.md", "not_detected",
        config=g, target_claim="tracked clean docs with owner frontmatter")
    add("R7-POS-untracked", "R7", "positive", "base_git", "docs/new_doc.md", "detected",
        config=g, expected_dispositions=["provenance_gap"],
        target_claim="new markdown doc added but never git-added",
        edits=[("write", "docs/new_doc.md", "# New doc\n\nThe best step is 60.94 ms.\n")])
    add("R7-POS-uncommitted", "R7", "positive", "base_git", "docs/guide.md", "detected",
        config=g, expected_dispositions=["confirmed"],
        target_claim="tracked doc edited in the working tree without a commit",
        edits=[("append", "docs/guide.md", "\nEdited working-tree line, not committed.\n")])
    add("R7-POS-owner", "R7", "positive", "base_git", "docs/notes.md", "detected",
        config=g, expected_dispositions=["unresolved"],
        target_claim="owner frontmatter removed and committed (tracked clean, owner absent)",
        edits=[("write", "docs/notes.md", "# Notes\n\nThe measured step is 60.94 ms.\n")],
        git_ops=["commit"])
    add("R7-HN-commit", "R7", "hard_negative", "base_git", "docs/guide.md", "not_detected",
        config=g,
        target_claim="tracked doc edited and committed (clean, owner present)",
        edits=[("append", "docs/guide.md", "\nCommitted clarification line.\n")],
        git_ops=["commit"])
    add("R7-HN-nonmd", "R7", "hard_negative", "base_git", "docs/guide.md", "not_detected",
        config=g,
        target_claim="untracked non-markdown file is outside the docs glob",
        edits=[("write", "notes.txt", "not a knowledge doc\n")])
    add("R7-HN-owner-present", "R7", "hard_negative", "base_git", "docs/notes.md",
        "not_detected", config=g,
        target_claim="owner frontmatter present in a committed tracked doc",
        edits=[("append", "docs/notes.md", "\nOwner: qinggo.\n")],
        git_ops=["commit"])

    # ---- R9 reference check (added when the rule/config lands; see r9.py hook) -----
    C.extend(_r9_cases())
    return C


def _r9_cases():
    """R9 reference-check cases on minimal copies of the 5 local repos + R7 git-copy cases.
    R9 config schema read from kblint config.py at integration time (see REPORT.md)."""
    import real_specs
    return real_specs.cases()


def add_helpers():
    return {"cfg": cfg, "R9_CONFIG": R9_CONFIG, "w": w}


# ---------------------------------------------------------------------------
def apply_case(case):
    root = REPOS / case["id"]
    if root.exists():
        shutil.rmtree(root)
    if case.get("copy_mode") == "gitcopy":
        # full copy including .git; source repos are read-only (no checkout/reset in place)
        shutil.copytree(case["source_repo"], root, symlinks=True)
    elif case.get("copy_mode") == "mini":
        root.mkdir(parents=True)
        for rel in case["source_files"]:
            src = Path(case["source_repo"]) / rel
            if not src.is_file():
                raise SystemExit(f"missing source file {src}")
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    else:
        src = REPOS / f"__base__{case['base']}"
        shutil.copytree(src, root)
    for op in case["edits"]:
        kind = op[0]
        if kind == "write":
            w(root, op[1], op[2])
        elif kind == "delete":
            p = root / op[1]
            if p.exists():
                p.unlink()
        elif kind == "replace":
            p = root / op[1]
            text = p.read_text(encoding="utf-8")
            if op[2] not in text:
                raise SystemExit(f"replace target missing in {case['id']}: {op[2]!r}")
            p.write_text(text.replace(op[2], op[3]), encoding="utf-8")
        elif kind == "append":
            with open(root / op[1], "a", encoding="utf-8") as fh:
                fh.write(op[2])
        else:
            raise SystemExit(f"unknown edit op {kind}")
    if "stage" in case["git_ops"]:
        _git(root, "add", "-A")
    if "commit" in case["git_ops"]:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "fixture: mutation")
    # config (always point at this fixture copy; synthetic cases get defaults)
    case_cfg = dict(case["config"])
    case_cfg.setdefault("repo", f"../repos/{case['id']}")
    case_cfg.setdefault("docs", ["docs/**/*.md"])
    case_cfg.setdefault("exclude", [".git/**"])
    cfg_path = CONFIGS / f"{case['id']}.json"
    cfg_path.write_text(json.dumps(case_cfg, indent=1) + "\n", encoding="utf-8")
    case["config"] = case_cfg
    case["config_path"] = str(cfg_path.relative_to(HERE))
    case["repo_path"] = str(root.relative_to(HERE))
    return case


def build():
    if FIX.exists():
        shutil.rmtree(FIX)
    REPOS.mkdir(parents=True)
    CONFIGS.mkdir(parents=True)
    base_r1r6(REPOS / "__base__base_r1r6")
    base_git(REPOS / "__base__base_git")
    init_git(REPOS / "__base__base_git")
    base_r9(REPOS / "__base__base_r9")
    built = [apply_case(c) for c in cases()]
    manifest = {
        "generated_by": "mutate.py",
        "kblint_rules_under_test": ["R1", "R2", "R3", "R5", "R6", "R7", "R9"],
        "r9_integrated": any(c["rule"] == "R9" for c in built),
        "now": NOW,
        "cases": built,
    }
    (FIX / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n",
                                       encoding="utf-8")
    print(f"[mutate] fixtures built: {len(built)} cases "
          f"({sum(1 for c in built if c['mutation']=='positive')} positive, "
          f"{sum(1 for c in built if c['mutation']!='positive')} controls)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
