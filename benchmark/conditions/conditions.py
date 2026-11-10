"""Condition definitions and the exact prompt builder for the 54-task benchmark.

Copied from the paper's `run_bench.py` (prompt construction only; the API runner is not shipped).
Conditions: c0 = no KB; c1 = useful KB; c2 = stale KB; c3 = neutral note; c2v/c2f = stale KB plus one
visible test / the full visible test suite; c1v/c1f = useful KB plus one/full visible test; c2a =
stale note + appended correction; c2ar = correction order reversed; c2an = correction after a neutral
distractor. Two prompt-variant seeds (0/1) differ only by a final instruction sentence.
"""
from __future__ import annotations
import re

HEAD = {
    "c0": "", "c1": "Project knowledge note (verified conventions from the current repo):\n",
    "c2": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c2v": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c2f": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c1v": "Project knowledge note (verified conventions from the current repo):\n",
    "c1f": "Project knowledge note (verified conventions from the current repo):\n",
    "c2a": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c2ar": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c2an": "Project knowledge note (from an older repo snapshot; may be outdated):\n",
    "c3": "Project knowledge note (general repo context):\n",
}


def first_test(tests: str) -> str:
    m = re.search(r"((?:@[^\n]+\n)*def test_[\s\S]*?)(?=\n(?:@[^\n]+\n)*def |\Z)", tests)
    if not m:
        return ""
    return tests[: m.start() + len(m.group(1))].strip()


def prompt_for(task, cond, seed):
    parts = ["You are a Python engineer in a research repository. Implement exactly ONE function in",
             "`solution.py` (numpy only, no I/O, no network, no extra packages).", "",
             "Task:", task["prompt"], ""]
    if cond not in ("c0", "c0v", "c0f", "c2ar"):
        facts = {"c1": task["useful"], "c2": task["stale"], "c2v": task["stale"],
                 "c2f": task["stale"], "c1v": task["useful"], "c1f": task["useful"],
                 "c2a": task["stale"], "c2an": task["stale"], "c3": task["neutral"]}[cond]
        parts.append(HEAD[cond] + "\n".join("- " + f for f in facts))
        if cond == "c2a":
            parts += ["", "A reviewer appended this correction (current repository truth; the note above is the old snapshot):",
                      *["- " + f for f in task["useful"]]]
        if cond == "c2an":
            parts += ["", "An unrelated project note (not a correction):",
                      *["- " + f for f in task["neutral"]], "",
                      "A reviewer appended this correction (current repository truth; the notes above are the old snapshot):",
                      *["- " + f for f in task["useful"]]]
    if cond == "c2ar":
        parts += ["A reviewer flagged this correction first (current repository truth; the note below is the old snapshot):",
                  *["- " + f for f in task["useful"]], "", HEAD[cond] + "\n".join("- " + f for f in task["stale"])]
    if cond in ("c2v", "c0v", "c1v"):
        parts += ["", "A teammate ran this visible test in CI and it passes with the current code:",
                  "```python", first_test(task["tests"]), "```"]
    if cond in ("c2f", "c0f", "c1f"):
        parts += ["", "The full visible test suite is available (it is also used in CI):",
                  "```python", task["tests"].strip(), "```"]
    add = {0: "", 1: "Keep the implementation minimal and robust; use only numpy.",
           2: "Prefer a straightforward implementation with clear dtype handling."}[seed % 3]
    if add:
        parts.append(add)
    parts += ["", 'Return ONLY JSON: {"code": "<full contents of solution.py>"}']
    return [{"role": "user", "content": "\n".join(parts)}]
