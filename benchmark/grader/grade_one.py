#!/usr/bin/env python3
"""Deterministic saved-completion grader for the 54-task benchmark (no API, no network).

Grades a saved solution against a task's hidden pytest suite from `benchmark/tasks/conventions.py`:

  python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 --code path/to/saved.py
  python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 --code saved.py --json

Exit status: 0 pass, 1 fail, 2 usage/unknown task. The same completion always yields the same verdict.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH / "tasks"))
from conventions import TASKS  # noqa: E402

PY = sys.executable


def run_tests(code: str, tests: str):
    if not code.strip():
        return False, "no code"
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)
        (p / "solution.py").write_text(code)
        (p / "test_solution.py").write_text(tests)
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": d, "HOME": d}
        try:
            r = subprocess.run([PY, "-m", "pytest", "-q", "test_solution.py"], cwd=d,
                               capture_output=True, text=True, timeout=90, env=env)
            out = (r.stdout + r.stderr)[-2000:].replace(d, "<tmp>")
            return r.returncode == 0, out
        except Exception as exc:  # noqa: BLE001
            return False, f"runner error: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="task id, e.g. M1_valid_zeros_f32 (see tasks/conventions.py)")
    ap.add_argument("--code", required=True, help="path to a saved solution.py completion")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    task = next((t for t in TASKS if t["tid"] == a.task), None)
    if task is None:
        print(f"unknown task {a.task!r}; {len(TASKS)} tasks known", file=sys.stderr)
        return 2
    code = pathlib.Path(a.code).read_text()
    ok, out = run_tests(code, task["tests"])
    rec = {"task": a.task, "family": task["family"], "pass": bool(ok), "tests_output_tail": out[-2000:]}
    if a.json:
        print(json.dumps(rec, indent=1))
    else:
        print(f"{a.task}: {'PASS' if ok else 'FAIL'}")
        print(out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
