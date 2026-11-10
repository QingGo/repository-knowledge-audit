#!/usr/bin/env python3
"""Real-repo coding counterfactual — deterministic runner (task-70 Phase 2).

One deepseek-chat call per (case, arm, seed), no tool loop. The model receives a task brief,
a context block (existing file content only, never a path), and for KB arms the parent/fix KB
text; it returns a JSON object containing a unified diff. We apply the diff in a fresh temp copy
of the parent commit and run deterministic hidden checks plus the pre-declared repo-test subset.

Usage:
  python3 coding_cf.py --dry-run
  python3 coding_cf.py --run
  python3 coding_cf.py --summary

The API key is read by probe_screen.run_probes.load_env and never printed or persisted.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
STUDY = HERE.parents[2]
CODE = HERE.parents[3]
REPLAY = STUDY / "kb-health" / "analysis" / "replay"
sys.path.insert(0, str(STUDY / "kb-health" / "probe_screen"))

from run_probes import chat, load_env, usage_cost  # noqa: E402

TASKS = json.loads((HERE / "tasks.json").read_text())
ARMS = ("no_kb", "stale_kb", "corrected_kb", "stale_plus_report")
RESULTS = HERE / "results"
RAW = RESULTS / "raw.jsonl"
SUMMARY = RESULTS / "summary.json"
REPORT = HERE / "REPORT.md"
WORK = pathlib.Path("/tmp/coding_cf/work")
WECHAT_NODE_MODULES = pathlib.Path("/tmp/cf-phase1/R5/node_modules")
ENGRAM_DEPS = pathlib.Path("/tmp/cf-phase1/engram-deps313")
ENGRAM_PY = "/HOME/.pyenv/versions/3.13.2/bin/python3"


def git_show(repo: str, rev: str, path: str) -> str:
    r = subprocess.run(["git", "-C", str(CODE / repo), "show", f"{rev}:{path}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git show failed for {repo} {rev} {path}: {r.stderr[:300]}")
    return r.stdout


def case_map() -> dict:
    d = json.loads((REPLAY / "cases.json").read_text())
    return d["cases"]


def kb_text(case: dict, arm: str) -> str:
    rev = case["parent_sha"] if arm in ("stale_kb", "stale_plus_report") else case["fix_sha"]
    return git_show(case["repo"], rev, case["kb_path"])


def drift_report(case: dict) -> str:
    c = case_map().get(case["id"])
    if not c:
        # case ids in tasks.json use names; map by repo
        for v in case_map().values():
            if v.get("repo") == case["repo"]:
                c = v
                break
    if not c:
        return "(no drift report available)"
    return c.get("drift_report", "")


def context_text(case: dict) -> str:
    ref = case.get("context_ref")
    if not ref:
        return ""
    return git_show(case["repo"], case["parent_sha"], ref)


def build_messages(case: dict, arm: str) -> list[dict]:
    task = case["task"]
    parts = [f"Repository: {case['repo']} at parent commit {case['parent_sha']}.",
             "", "TASK:", task, ""]
    if case.get("context_ref"):
        content = context_text(case)
        parts += ["EXISTING CONTENT (the KB tells you where this lives; path not provided):",
                  "```", content, "```", ""]
    if arm == "no_kb":
        parts += ["AGENT KB: none provided.", ""]
    else:
        text = kb_text(case, arm)
        parts += [f"AGENT KB ({case['kb_path']}):", "```", text, "```",
                  "Paths in the KB are relative to the KB file's directory.", ""]
        if arm == "stale_plus_report":
            parts += ["DRIFT REPORT (deterministic):", drift_report(case), ""]
    parts += ["OUTPUT CONTRACT: Return a JSON object with exactly one key `diff` whose value is a "
              "complete unified diff (starting with `diff --git`) that applies cleanly at the "
              "repository root. No markdown fences and no prose outside the JSON."]
    return [{"role": "system", "content": "You are an expert software engineer. You cannot run "
             "commands or inspect the repository. Return only JSON."},
            {"role": "user", "content": "\n".join(parts)}]


def extract_diff(raw: str) -> tuple[str, str]:
    """Return (diff, parse_status)."""
    raw = raw or ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and isinstance(obj.get("diff"), str):
            return obj["diff"], "json"
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and isinstance(obj.get("diff"), str):
                return obj["diff"], "json-recovered"
        except Exception:
            pass
    m = re.search(r"```(?:diff)?\s*(diff --git.*?)```", raw, flags=re.S)
    if m:
        return m.group(1).strip() + "\n", "fenced"
    m = re.search(r"(diff --git .*)$", raw, flags=re.S)
    if m:
        return m.group(1).strip() + "\n", "bare"
    return "", "unparsed"


def prepare_work(case: dict) -> pathlib.Path:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    # materialize parent commit without touching the source repo
    proc = subprocess.run(["git", "-C", str(CODE / case["repo"]), "archive",
                           "--format=tar", case["parent_sha"]], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git archive failed: {proc.stderr[:300]}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tf:
        tf.extractall(WORK)
    if case["id"] == "R5" and WECHAT_NODE_MODULES.exists():
        link = WORK / "node_modules"
        if not link.exists():
            os.symlink(WECHAT_NODE_MODULES, link)
    return WORK


def changed_files(diff: str) -> list[str]:
    paths = set(re.findall(r"(?m)^diff --git a/(\S+) b/\S+", diff or ""))
    norm = normalize_patch(diff or "")
    paths.update(re.findall(r"(?m)^diff --git a/(\S+) b/\S+", norm))
    return sorted(paths)


def normalize_patch(diff: str) -> str:
    """Mechanically repair a common LLM diff-format error: missing per-file `diff --git`
    headers when several files are concatenated. Never changes hunk content; `git apply
    --recount` is used later for hunk line-count errors."""
    import re as _re
    lines = (diff or "").splitlines()
    if not lines:
        return ""
    starts = []
    for i, line in enumerate(lines):
        if _re.match(r"^(diff --git |new file mode |deleted file mode)", line):
            starts.append(i)
        elif _re.match(r"^(--- a/|--- /dev/null)", line):
            # A `---` header directly after a diff/new-file header belongs to that block;
            # otherwise it starts a block whose diff --git header was omitted.
            prev = lines[i - 1] if i else ""
            if not _re.match(r"^(diff --git |new file mode |deleted file mode)", prev):
                starts.append(i)
    if not starts:
        return diff
    starts = sorted(set(starts))
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = lines[start:end]
        if not block:
            continue
        first = block[0]
        if first.startswith("diff --git "):
            blocks.append(block)
            continue
        path = None
        for ln in block:
            if ln.startswith("--- a/"):
                path = ln[len("--- a/"):].strip()
                break
            if ln.startswith("+++ b/"):
                path = ln[len("+++ b/"):].strip()
                break
        if not path:
            blocks.append(block)
            continue
        blocks.append([f"diff --git a/{path} b/{path}"] + block)
    return "\n".join(x for b in blocks for x in b) + "\n"


def apply_patch(work: pathlib.Path, diff: str) -> tuple[bool, str, bool]:
    if not diff.strip():
        return False, "empty diff", False
    attempts = [("raw", diff), ("normalized", normalize_patch(diff))]
    last = ""
    for label, text in attempts:
        pf = work / f".coding_cf.{label}.patch"
        pf.write_text(text if text.endswith("\n") else text + "\n")
        check = subprocess.run(["git", "apply", "--check", "--recount", str(pf)], cwd=work,
                               capture_output=True, text=True)
        if check.returncode != 0:
            last = (check.stderr or check.stdout)[:1000]
            continue
        app = subprocess.run(["git", "apply", "--recount", str(pf)], cwd=work,
                             capture_output=True, text=True)
        if app.returncode == 0:
            return True, "", (label == "normalized")
        last = (app.stderr or app.stdout)[:1000]
    return False, last, False


def check_hugo(work: pathlib.Path) -> tuple[bool, dict]:
    path = work / "docs/layouts/_partials/layouts/icons.html"
    stale = work / "docs/layouts/_partials/icons.html"
    info = {"expected_path_exists": path.exists(), "stale_path_exists": stale.exists()}
    if not path.exists():
        return False, info
    import xml.etree.ElementTree as ET
    text = path.read_text()
    try:
        root = ET.fromstring("<root>" + text + "</root>")
        symbols = [e for e in root.iter() if e.tag.endswith("symbol")]
        found = [e for e in symbols if e.get("id") == "icon--terminal"]
        ok = bool(found) and bool(found[0].get("viewBox")) and any(
            (e.tag.endswith("path") and (e.get("d") or e.text)) for e in found[0].iter())
    except Exception as exc:  # noqa: BLE001
        info["xml_error"] = str(exc)[:200]
        return False, info
    info["symbol_found"] = bool(found)
    info["dual_stale_path"] = stale.exists() and "icon--terminal" in stale.read_text()
    return ok, info


def check_wechat(work: pathlib.Path) -> tuple[bool, dict]:
    root = work / "miniprogram"
    page = root / "pages/stats"
    info = {"page_dir_exists": page.is_dir(),
            "files": {x: (page / f"stats.{x}").exists() for x in ("js", "json", "wxml", "wxss")},
            "stale_root_page": (work / "pages/stats/stats.js").exists()}
    app = root / "app.json"
    info["app_exists"] = app.exists()
    if not all(info["files"].values()) or not app.exists():
        return False, info
    try:
        pages = json.loads(app.read_text()).get("pages") or []
    except Exception as exc:  # noqa: BLE001
        info["app_json_error"] = str(exc)[:200]
        return False, info
    info["route_registered"] = "pages/stats/stats" in pages
    js = page / "stats.js"
    info["node_check"] = subprocess.run(["node", "--check", str(js)],
                                        capture_output=True, text=True).returncode == 0
    info["page_call"] = "Page(" in js.read_text()
    return bool(info["route_registered"] and info["node_check"] and info["page_call"]), info


def check_engram(work: pathlib.Path) -> tuple[bool, dict]:
    skill = work / ".agents/skills/short-term-memory"
    stale_skill = work / ".agents/skills/memory-update"
    scripts = sorted(skill.rglob("*.py")) if skill.exists() else []
    info = {"skill_exists": skill.exists(), "scripts": [str(p.relative_to(work)) for p in scripts],
            "dual_stale_skill": stale_skill.exists()}
    if not scripts:
        return False, info
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "memory.md"
        proc = subprocess.run([sys.executable, str(scripts[0]), "--session-id", "s1",
                               "--output", str(out)], cwd=work, capture_output=True,
                              text=True, timeout=30)
        info["run_rc"] = proc.returncode
        info["run_err"] = (proc.stderr or "")[:500]
        txt = out.read_text() if out.exists() else ""
        info["output_exists"] = out.exists()
        info["has_section"] = bool(re.search(r"(?i)Gotchas\s*&\s*Context", txt))
        info["has_bullet"] = bool(re.search(r"(?m)^\s*[-*].*s1", txt))
        return bool(proc.returncode == 0 and info["has_section"] and info["has_bullet"]), info


def run_repo_test(case: dict, work: pathlib.Path) -> tuple[bool, str]:
    t = case["repo_test"]
    cmd = list(t["cmd"])
    env = dict(os.environ)
    if case["id"] == "R5":
        env["PATH"] = os.environ.get("PATH", "")
    if case["id"] == "R3":
        env["PYTHONPATH"] = f"{ENGRAM_DEPS}:{work / 'src'}"
    try:
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=300, env=env)
        tail = (r.stdout + "\n" + r.stderr).strip()[-800:]
        return r.returncode == 0, tail
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def regrade() -> int:
    """Re-run deterministic grading over stored model diffs WITHOUT new API calls.

    The pre-registered strict `git apply` result is preserved as `strict_diff_applies`; the
    fallback mechanically inserts missing repeated `diff --git` headers and uses
    `git apply --recount` (no hunk content changed). This is reported separately.
    """
    if not RAW.exists():
        print("no results to regrade", file=sys.stderr)
        return 1
    rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
    backup = RESULTS / "raw_strict.jsonl"
    if not backup.exists():
        backup.write_text(RAW.read_text())
    by_id = {c["id"]: c for c in TASKS["cases"]}
    out = []
    for r in rows:
        rec = dict(r)
        rec["strict_diff_applies"] = bool(r.get("strict_diff_applies", r.get("diff_applies")))
        rec["strict_apply_msg"] = r.get("apply_msg", "")
        case = by_id[r["case"]]
        work = prepare_work(case)
        diff = rec.get("diff") or ""
        ok_apply, apply_msg, repair_used = apply_patch(work, diff)
        rec["diff_applies"] = ok_apply
        rec["format_repair"] = repair_used
        rec["apply_msg"] = apply_msg
        rec["changed_files"] = changed_files(diff)
        if ok_apply:
            if case["id"] == "R4":
                hidden, info = check_hugo(work)
            elif case["id"] == "R5":
                hidden, info = check_wechat(work)
            else:
                hidden, info = check_engram(work)
            rec["hidden_pass"] = hidden
            rec["hidden_info"] = info
            rt, rt_msg = run_repo_test(case, work)
            rec["repo_test_pass"] = rt
            rec["repo_test_tail"] = rt_msg
        else:
            rec["hidden_pass"] = False
            rec["hidden_info"] = {}
            rec["repo_test_pass"] = False
            rec["repo_test_tail"] = "not run: diff did not apply"
        out.append(rec)
    RAW.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n")
    print(f"regraded {len(out)} rows; backup {backup}", file=sys.stderr)
    return 0


def load_done() -> set:
    done = set()
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            try:
                r = json.loads(line)
                done.add((r["case"], r["arm"], r["seed"]))
            except Exception:
                pass
    return done


def run(limit: int | None = None) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    env = load_env()  # never print; only key names exist in env
    model = env.get("DEEPSEEK_MODEL", "deepseek-chat")
    done = load_done()
    total = 0.0
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            try:
                total += float(json.loads(line).get("cost_cny") or 0.0)
            except Exception:
                pass
    calls = 0
    for case in TASKS["cases"]:
        for arm in ARMS:
            for seed in TASKS["seeds"]:
                key = (case["id"], arm, seed)
                if key in done:
                    continue
                if total >= TASKS["stop_at_cny"]:
                    print(f"STOP cost cap {total:.4f} CNY", file=sys.stderr)
                    return 0
                if limit is not None and calls >= limit:
                    return 0
                messages = build_messages(case, arm)
                temp = TASKS["temperatures"][str(seed)]
                t0 = time.time()
                rec = {"case": case["id"], "repo": case["repo"], "arm": arm, "seed": seed,
                       "temperature": temp, "model": model, "parent_sha": case["parent_sha"],
                       "fix_sha": case["fix_sha"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "prompt_chars": sum(len(m["content"]) for m in messages)}
                try:
                    resp = chat(env, messages, model, temperature=temp,
                                max_tokens=TASKS["max_tokens"])
                    raw = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                    usage = resp.get("usage") or {}
                    rec["usage"] = usage
                    rec["cost_cny"] = usage_cost(usage)
                    total += rec["cost_cny"]
                    diff, parse_status = extract_diff(raw)
                    rec["parse_status"] = parse_status
                    rec["diff"] = diff
                    rec["raw_len"] = len(raw)
                    work = prepare_work(case)
                    ok_apply, apply_msg, repair_used = apply_patch(work, diff)
                    rec["diff_applies"] = ok_apply
                    rec["format_repair"] = repair_used
                    rec["apply_msg"] = apply_msg
                    rec["changed_files"] = changed_files(diff)
                    if ok_apply:
                        if case["id"] == "R4":
                            hidden, info = check_hugo(work)
                        elif case["id"] == "R5":
                            hidden, info = check_wechat(work)
                        else:
                            hidden, info = check_engram(work)
                        rec["hidden_pass"] = hidden
                        rec["hidden_info"] = info
                        rt, rt_msg = run_repo_test(case, work)
                        rec["repo_test_pass"] = rt
                        rec["repo_test_tail"] = rt_msg
                    else:
                        rec["hidden_pass"] = False
                        rec["hidden_info"] = {}
                        rec["repo_test_pass"] = False
                        rec["repo_test_tail"] = "not run: diff did not apply"
                except Exception as exc:  # noqa: BLE001
                    rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
                    rec["hidden_pass"] = False
                    rec["diff_applies"] = False
                    rec["repo_test_pass"] = False
                rec["latency_s"] = round(time.time() - t0, 2)
                with RAW.open("a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                calls += 1
                print(f"{case['id']} {arm} s{seed}: hidden={rec.get('hidden_pass')} "
                      f"apply={rec.get('diff_applies')} cost={rec.get('cost_cny')} "
                      f"total={total:.4f}", file=sys.stderr)
    return 0


def summarize() -> int:
    rows = []
    if RAW.exists():
        rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
    by = {}
    for r in rows:
        by.setdefault((r["case"], r["arm"]), []).append(r)
    summary = {"n_runs": len(rows), "by_cell": {}, "by_arm": {}, "total_cost_cny": 0.0}
    for (case, arm), rs in sorted(by.items()):
        summary["by_cell"][f"{case}/{arm}"] = {
            "n": len(rs), "hidden_pass": sum(bool(r.get("hidden_pass")) for r in rs),
            "diff_applies": sum(bool(r.get("diff_applies")) for r in rs),
            "repo_test_pass": sum(bool(r.get("repo_test_pass")) for r in rs),
            "strict_apply": sum(bool(r.get("strict_diff_applies", r.get("diff_applies"))) for r in rs),
            "repaired_apply": sum(bool(r.get("format_repair")) for r in rs),
            "parse_json": sum(r.get("parse_status", "").startswith("json") for r in rs),
            "changed_files_ok": sum(bool(r.get("changed_files")) for r in rs),
        }
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        summary["by_arm"][arm] = {"n": len(rs),
                                  "hidden_pass": sum(bool(r.get("hidden_pass")) for r in rs)}
    summary["total_cost_cny"] = round(sum(float(r.get("cost_cny") or 0) for r in rows), 6)
    summary["total_prompt_tokens"] = sum((r.get("usage") or {}).get("prompt_tokens") or 0 for r in rows)
    summary["total_completion_tokens"] = sum((r.get("usage") or {}).get("completion_tokens") or 0 for r in rows)
    RESULTS.mkdir(exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2))
    write_report(rows, summary)
    print(json.dumps(summary, indent=2))
    return 0


def write_report(rows: list[dict], summary: dict) -> None:
    lines = ["# Real-repo coding counterfactual — Phase 2 results", "",
             "**Model:** deepseek-chat; single call per cell; no tool loop; max_tokens 4000.",
             f"**Runs:** {summary['n_runs']}/24; **cost:** ¥{summary['total_cost_cny']:.4f} "
             f"(cap ¥3.0, stop ¥2.7); prompt/completion tokens: "
             f"{summary['total_prompt_tokens']}/{summary['total_completion_tokens']}.", "",
             "| case | arm | n | hidden pass | strict apply | repaired apply | repo tests | JSON parse |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in summary["by_cell"].items():
        case, arm = k.split("/", 1)
        lines.append(f"| {case} | {arm} | {v['n']} | {v['hidden_pass']}/{v['n']} | "
                     f"{v['strict_apply']}/{v['n']} | {v['repaired_apply']}/{v['n']} | "
                     f"{v['repo_test_pass']}/{v['n']} | {v['parse_json']}/{v['n']} |")
    lines += ["", "## Hidden pass by arm", "", "| arm | n | hidden pass |", "|---|---:|---:|"]
    for arm, v in summary["by_arm"].items():
        lines.append(f"| {arm} | {v['n']} | {v['hidden_pass']}/{v['n']} |")
    lines += ["", "## Per-run detail", "",
              "| case | arm | seed | applies | hidden | repo test | changed files | note |",
              "|---|---|---:|---|---|---|---|---|"]
    for r in rows:
        note = ""
        info = r.get("hidden_info") or {}
        if info.get("dual_stale_path") or info.get("stale_root_page") or info.get("dual_stale_skill"):
            note = "dual-path"
        if r.get("format_repair"):
            note = (note + "; " if note else "") + "format-repair"
        if r.get("error"):
            note = r["error"][:80]
        lines.append(f"| {r['case']} | {r['arm']} | {r['seed']} | {r.get('diff_applies')} | "
                     f"{r.get('hidden_pass')} | {r.get('repo_test_pass')} | "
                     f"{','.join(r.get('changed_files') or [])[:160]} | {note} |")
    lines += ["", "## Honest reading", "",
              "- The primary outcome is the deterministic hidden check; repo tests are a separate "
              "regression gate (they are not folded into the hidden pass).",
              "- Any arm-level null is reported as-is; no bootstrap is used (exact counts).",
              "- Dual-path/recovery notes flag cells where the model wrote both the stale and the "
              "correct location (or otherwise made the check trivially recoverable).",
              ""]
    REPORT.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--regrade", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.dry_run:
        for case in TASKS["cases"]:
            for arm in ARMS:
                m = build_messages(case, arm)
                print(case["id"], arm, "prompt_chars", sum(len(x["content"]) for x in m))
        print("dry-run: no API calls; total cells", len(TASKS["cases"]) * len(ARMS) * len(TASKS["seeds"]))
        return 0
    if a.regrade:
        return regrade()
    if a.summary:
        return summarize()
    if a.run:
        return run(limit=a.limit)
    print("use --dry-run, --run, or --summary", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
