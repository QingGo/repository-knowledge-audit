#!/usr/bin/env python3
"""Real-repo mutation specs for the kblint mutation evaluation.

Two families:

A) R9 reference-check mutants on minimal copies of the 5 read-only local repos
   (`/HOME/code/...`, currently at docs-fix commits).  Each mini repo copies
   only the target KB doc + the referenced artifacts + the root manifest (Makefile /
   package.json); the base repo is never modified.  The negative control is the same mini
   repo unchanged (its pre-existing findings are ignored; detection is delta on the target
   token).

B) R7 git mutants on full `git` copies of three repos (R2, R1,
   R5).  The copy keeps `.git`, so `git ls-files` / `git status` work; no
   checkout/reset happens in the source repos.

C) One R7 "bug probe" on R5 with non-ASCII tracked filenames: the expected
   result (no finding) is recorded, but the case is marked `bug_probe` and excluded from
   the headline precision/recall cells (used only to document a detected engine defect).
"""
from __future__ import annotations

REPO = "/HOME/code"
MINI = {
    "R2": ["AGENTS.md", "Makefile",
                  "src/home_seek/inference_engine/parallel.py"],
    "R3": ["AGENTS.md", "Makefile",
                    "src/engram_peft/model.py", "docs/paper_alignment.md"],
    "R5": ["docs/llm/long-term-memory.md", "package.json",
                        "data/transform-questions-json.js"],
    "R4": ["README.md", "CONTRIBUTING.md"],
    "R1": ["AGENTS.md", "README.md", "Makefile", "compiler/compile.py"],
}


def _cfg_mini(cid, docs):
    return {
        "repo": f"../repos/{cid}",
        "docs": docs,
        "exclude": [".git/**"],
        "git": {"enabled": False},
        "now": "2026-11-05",
        "references": {"enabled": True},
    }


def _cfg_git(cid):
    return {
        "repo": f"../repos/{cid}",
        "docs": ["**/*.md"],
        "exclude": [".git/**", "node_modules/**", ".venv/**", ".pytest_cache/**",
                    "dist/**", "build/**", "site/**"],
        "git": {"enabled": True},
        "now": "2026-11-05",
        "references": {"enabled": False},
    }


def cases():
    C = []

    def mini(cid, repo, docs, files, rule, mutation, target_doc, target_tokens, expect,
             edits=(), note=""):
        C.append({
            "id": cid, "rule": rule, "mutation": mutation, "copy_mode": "mini",
            "source_repo": f"{REPO}/{repo}", "source_files": files,
            "target_doc": target_doc, "target_tokens": target_tokens,
            "expect": expect, "edits": list(edits), "git_ops": [],
            "config": _cfg_mini(cid, docs), "target_claim": note,
            "expected_dispositions": (["confirmed"] if rule == "R9" else []),
        })

    # ---- R9: R2 ----------------------------------------------------
    mini("R9R-home-NC", "R2", ["AGENTS.md"], MINI["R2"],
         "R9", "negative_control", "AGENTS.md", ["parallel.py"], "not_detected",
         note="AGENTS.md `src/home_seek/inference_engine/parallel.py` exists")
    mini("R9R-home-POS-path", "R2", ["AGENTS.md"], MINI["R2"],
         "R9", "positive", "AGENTS.md", ["parallel.py"], "detected",
         edits=[("delete", "src/home_seek/inference_engine/parallel.py")],
         note="referenced path file deleted")
    mini("R9R-home-POS-make", "R2", ["AGENTS.md"], MINI["R2"],
         "R9", "positive", "AGENTS.md", ["make target does not exist: profile"], "detected",
         edits=[("replace", "Makefile", "profile: $(PROFILE_DIR)", "profile-run: $(PROFILE_DIR)"),
                ("replace", "Makefile", " test-integration profile profile-light",
                 " test-integration profile-light")],
         note="root Makefile target `profile` renamed")
    mini("R9R-home-HN-content", "R2", ["AGENTS.md"], MINI["R2"],
         "R9", "hard_negative", "AGENTS.md", ["make target does not exist", "high-risk"],
         "not_detected",
         edits=[("append", "AGENTS.md", "\nThis appended paragraph contains no references.\n")],
         note="prose-only edit")
    mini("R9R-home-HN-fence", "R2", ["AGENTS.md"], MINI["R2"],
         "R9", "hard_negative", "AGENTS.md", ["missing/fence_path.py"], "not_detected",
         edits=[("append", "AGENTS.md",
                 "\n```bash\npython tools/missing/fence_path.py\n```\n")],
         note="fenced path is deliberately not checked (documented R9 behaviour)")

    # ---- R9: R3 --------------------------------------------------
    mini("R9R-engram-NC", "R3", ["AGENTS.md"], MINI["R3"],
         "R9", "negative_control", "AGENTS.md", ["model.py"], "not_detected")
    mini("R9R-engram-POS-path", "R3", ["AGENTS.md"], MINI["R3"],
         "R9", "positive", "AGENTS.md", ["model.py"], "detected",
         edits=[("delete", "src/engram_peft/model.py")],
         note="referenced path file deleted")
    mini("R9R-engram-HN-content", "R3", ["AGENTS.md"], MINI["R3"],
         "R9", "hard_negative", "AGENTS.md", ["make target does not exist"], "not_detected",
         edits=[("append", "AGENTS.md", "\nA new prose note with no artifact pointer.\n")],
         note="prose-only edit")
    mini("R9R-engram-HN-external", "R3", ["AGENTS.md"], MINI["R3"],
         "R9", "hard_negative", "AGENTS.md", ["example.com"], "not_detected",
         edits=[("append", "AGENTS.md",
                 "\nSee [the external docs](https://example.com/docs) for background.\n")],
         note="external URL link is not a repo reference")

    # ---- R9: R5 ---------------------------------------------
    mini("R9R-wechat-NC", "R5", ["docs/llm/long-term-memory.md"],
         MINI["R5"],
         "R9", "negative_control", "docs/llm/long-term-memory.md",
         ["transform-questions-json.js", "build:ci"], "not_detected")
    mini("R9R-wechat-POS-path", "R5", ["docs/llm/long-term-memory.md"],
         MINI["R5"],
         "R9", "positive", "docs/llm/long-term-memory.md",
         ["transform-questions-json.js"], "detected",
         edits=[("delete", "data/transform-questions-json.js")],
         note="referenced data path file deleted")
    mini("R9R-wechat-POS-npm", "R5", ["docs/llm/long-term-memory.md"],
         MINI["R5"],
         "R9", "positive", "docs/llm/long-term-memory.md", ["build:ci"], "detected",
         edits=[("replace", "package.json", '"build:ci"', '"bundle:ci"')],
         note="root package.json script `build:ci` renamed")
    mini("R9R-wechat-HN-content", "R5", ["docs/llm/long-term-memory.md"],
         MINI["R5"],
         "R9", "hard_negative", "docs/llm/long-term-memory.md",
         ["make target does not exist"], "not_detected",
         edits=[("append", "docs/llm/long-term-memory.md", "\n<private KB text removed>：<private KB text removed>。\n")],
         note="prose-only edit")

    # ---- R9: R4 ---------------------------------------------------------
    mini("R9R-R4-NC", "R4", ["README.md"], MINI["R4"],
         "R9", "negative_control", "README.md", ["CONTRIBUTING.md"], "not_detected")
    mini("R9R-R4-POS-link", "R4", ["README.md"], MINI["R4"],
         "R9", "positive", "README.md", ["CONTRIBUTING.md"], "detected",
         edits=[("delete", "CONTRIBUTING.md")],
         note="markdown link target file deleted")
    mini("R9R-R4-HN-content", "R4", ["README.md"], MINI["R4"],
         "R9", "hard_negative", "README.md", ["missing-file"], "not_detected",
         edits=[("append", "README.md", "\nA prose note without a reference.\n")],
         note="prose-only edit")
    mini("R9R-R4-HN-make", "R4", ["README.md"], MINI["R4"],
         "R9", "hard_negative", "README.md", ["make target does not exist"], "not_detected",
         edits=[("append", "README.md", "\nRun `make build` if you want a binary.\n")],
         note="repo has no root Makefile: make check self-skips (no finding)")

    # ---- R9: R1 --------------------------------------------
    mini("R9R-llm-NC", "R1", ["AGENTS.md", "README.md"],
         MINI["R1"],
         "R9", "negative_control", "AGENTS.md",
         ["compiler/compile.py", "test-unit"], "not_detected")
    mini("R9R-llm-POS-path", "R1", ["AGENTS.md", "README.md"],
         MINI["R1"],
         "R9", "positive", "AGENTS.md", ["compiler/compile.py"], "detected",
         edits=[("delete", "compiler/compile.py")],
         note="referenced path file deleted")
    mini("R9R-llm-POS-make", "R1", ["AGENTS.md", "README.md"],
         MINI["R1"],
         "R9", "positive", "README.md", ["test-unit"], "detected",
         edits=[("replace", "Makefile", "test-unit: $(VENV)", "unit-tests: $(VENV)"),
                ("replace", "Makefile", "lint-mypy test-unit test-integration",
                 "lint-mypy test-integration")],
         note="root Makefile target `test-unit` renamed")
    mini("R9R-llm-HN-content", "R1", ["AGENTS.md", "README.md"],
         MINI["R1"],
         "R9", "hard_negative", "AGENTS.md", ["missing-fence"], "not_detected",
         edits=[("append", "AGENTS.md",
                 "\n```text\ncompiler/missing-fence/example.py\n```\n")],
         note="fenced path is not checked (documented R9 behaviour)")

    # ---- R7: real git copies ---------------------------------------------
    def gitc(cid, repo, rule, mutation, target_doc, target_tokens, expect, edits=(),
             git_ops=(), probe=False, note=""):
        C.append({
            "id": cid, "rule": rule, "mutation": ("bug_probe" if probe else mutation),
            "copy_mode": "gitcopy", "source_repo": f"{REPO}/{repo}",
            "source_files": [], "target_doc": target_doc,
            "target_tokens": target_tokens, "expect": expect,
            "edits": list(edits), "git_ops": list(git_ops),
            "config": _cfg_git(cid), "target_claim": note,
            "expected_dispositions": (["confirmed"] if rule == "R7" else []),
        })

    gitc("R7R-home-NC", "R2", "R7", "negative_control", "AGENTS.md", [], 
         "not_detected", note="clean git copy")
    gitc("R7R-home-POS-untracked", "R2", "R7", "positive", "docs/kb_note.md",
         ["not tracked in git"], "detected",
         edits=[("write", "docs/kb_note.md", "# KB note\n\nA new untracked knowledge doc.\n")],
         note="new doc never git-added")
    gitc("R7R-home-POS-uncommitted", "R2", "R7", "positive", "AGENTS.md",
         ["uncommitted change"], "detected",
         edits=[("append", "AGENTS.md", "\nWorking-tree-only edit.\n")],
         note="tracked doc modified without commit")
    gitc("R7R-home-HN-commit", "R2", "R7", "hard_negative", "AGENTS.md", [],
         "not_detected",
         edits=[("append", "AGENTS.md", "\nCommitted clarification.\n")], git_ops=["commit"],
         note="tracked doc edited and committed -> clean")
    gitc("R7R-home-POS-staged", "R2", "R7", "positive", "AGENTS.md",
         ["uncommitted change"], "detected",
         edits=[("append", "AGENTS.md", "\nStaged but uncommitted edit.\n")],
         git_ops=["stage"], note="tracked doc staged (git add) but not committed")
    gitc("R7R-llm-NC", "R1", "R7", "negative_control", "README.md", [],
         "not_detected", note="clean git copy")
    gitc("R7R-llm-POS-uncommitted", "R1", "R7", "positive", "README.md",
         ["uncommitted change"], "detected",
         edits=[("append", "README.md", "\nWorking-tree-only edit.\n")],
         note="tracked doc modified without commit")
    gitc("R7R-llm-HN-commit", "R1", "R7", "hard_negative", "README.md", [],
         "not_detected",
         edits=[("append", "README.md", "\nCommitted clarification.\n")], git_ops=["commit"],
         note="tracked doc edited and committed -> clean")
    gitc("R7R-wechat-NC-probe", "R5", "R7", "bug_probe", "docs/<private KB text removed>.md",
         ["not tracked in git"], "not_detected", probe=True,
         note="bug probe: non-ASCII tracked filenames must not be reported untracked")
    gitc("R7R-wechat-POS-uncommitted-probe", "R5", "R7", "bug_probe",
         "docs/<private KB text removed>.md", ["uncommitted change"], "detected", probe=True,
         edits=[("append", "docs/<private KB text removed>.md", "\n<private KB text removed>。\n")],
         note="bug probe: uncommitted change to a non-ASCII filename")
    return C
