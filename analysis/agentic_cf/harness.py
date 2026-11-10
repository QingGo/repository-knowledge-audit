#!/usr/bin/env python3
"""Real-repo agentic coding counterfactual: tools + stale/corrected KB (task-77).

Pre-registration: PREREG.md (sha256 in PREREG.sha256, frozen before any model call).
One run = a fresh `git archive` workspace of the parent commit + a 25-step JSON-action tool loop
(deepseek-chat) + deterministic hidden-check grading + pre-declared repo-test regression attempt.
The ONLY manipulated difference across conditions is the designated KB file (absent / parent bytes /
fix bytes). The KB is not inlined in the prompt: the agent must discover it in the workspace.

Usage:
  python3 harness.py --dry-run                 # zero API calls: workspaces, KB arms, tools, grading
  python3 harness.py --run --validation        # one validation run (R4/corrected_kb/seed0)
  python3 harness.py --run                     # remaining runs (resume-safe)
  python3 harness.py --summarize               # results/summary.json + REPORT.md tables
The API key is loaded by probe_screen.run_probes.load_env and never printed or persisted.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
KBH = HERE.parents[1]                       # kb-health/
STUDY = HERE.parents[2]                     # study/
CODE = HERE.parents[3]                      # code/ (read-only repo clones)
CODING_CF = KBH / "analysis" / "coding_cf"
PROBE = KBH / "probe_screen"
sys.path.insert(0, str(PROBE))
sys.path.insert(0, str(CODING_CF))
from run_probes import chat, load_env, parse_json, usage_cost  # noqa: E402
from coding_cf import (check_engram, check_hugo, check_wechat, changed_files,  # noqa: E402
                       normalize_patch, run_repo_test)

RESULTS = HERE / "results"
RUNS = RESULTS / "runs.jsonl"
SUMMARY = RESULTS / "summary.json"
DIFFS = RESULTS / "diffs"
TRANSCRIPTS = RESULTS / "transcripts"
WORKROOT = pathlib.Path("/tmp/agentic_cf/work")
WECHAT_NODE_MODULES = pathlib.Path("/tmp/cf-phase1/R5/node_modules")
ENGRAM_DEPS = "/tmp/cf-phase1/engram-deps313"

CASES = {c["id"]: c for c in json.loads((CODING_CF / "tasks.json").read_text())["cases"]}
CASE_ORDER = ["R4", "R5", "R3"]
ARMS = ("no_kb", "stale_kb", "corrected_kb")
SEED_TEMPS = {0: 0.2, 1: 0.3}
MODEL = "deepseek-chat"
MAX_STEPS = 25
MAX_TOKENS_PER_STEP = 1200
COST_CAP_CNY = 20.0
STOP_AT_CNY = 18.0
MAX_WORKERS = 2
RUNTIME_PATH = ("/opt/homebrew/bin:/HOME/.nvm/versions/node/v24.8.0/bin:"
                "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
CHECK = {"R4": check_hugo, "R5": check_wechat, "R3": check_engram}
# tokens that identify the stale reference of each case (for inspection/leak metrics)
STALE_TOKENS = {
    "R4": ["layouts/_partials/icons.html"],
    "R5": ["pages/", "static/", "user/", "pay/"],
    "R3": ["memory-update"],
}
SYSTEM_PROMPT = """You are an autonomous software engineer working in a fresh copy of a real repository.
You can take ONE action per turn. Return ONLY a JSON object (no markdown fences, no prose) with one of:
  {"action":"ls","path":"<relative dir, default .>"}
  {"action":"read_file","path":"<relative file>"}
  {"action":"grep","pattern":"<python regex>","path":"<relative dir or file, default .>"}
  {"action":"write_file","path":"<relative file>","content":"<full file contents>"}
  {"action":"apply_patch","patch":"<unified diff starting with diff --git>"}
  {"action":"run","cmd":"<one allowlisted command>"}
  {"action":"submit"}
Rules: paths are relative to the repository root; stay inside the workspace; no network.
Allowlisted run commands: the repository test subset shown in the task context, `git status`,
`git diff`, `python -m py_compile <file>`, `node --check <file>`, `gofmt -l <file>`.
The repository may contain knowledge files (e.g. AGENTS.md, CLAUDE.md, docs/AGENTS.md);
consult them if useful. Work step by step: inspect the repository, make the change, verify when
possible, then submit. You have at most {max_steps} actions; at the limit the current state is
graded automatically."""


# --------------------------------------------------------------------------- helpers
def run_id(case_id: str, arm: str, seed: int) -> str:
    return f"{case_id}__{arm}__s{seed}"


def git_show(repo: str, rev: str, path: str) -> bytes:
    r = subprocess.run(["git", "-C", str(CODE / repo), "show", f"{rev}:{path}"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git show failed {repo} {rev} {path}: {r.stderr[:300]}")
    return r.stdout


def kb_present(case: dict, arm: str) -> bool:
    return arm in ("stale_kb", "corrected_kb")


def kb_bytes(case: dict, arm: str) -> bytes:
    rev = case["parent_sha"] if arm == "stale_kb" else case["fix_sha"]
    return git_show(case["repo"], rev, case["kb_path"])


def prompt_text(case: dict) -> str:
    cmd = " ".join(case["repo_test"]["cmd"])
    return (f"Repository: {case['repo']} (parent commit {case['parent_sha']}).\n\n"
            f"TASK:\n{case['task']}\n\n"
            f"Repository test subset you may run with `run`: {cmd}\n\n"
            'When done, submit with {"action":"submit"}. Reply with one JSON action per turn.')


def cell_prompt(case: dict) -> list[dict]:
    system = SYSTEM_PROMPT.replace("{max_steps}", str(MAX_STEPS))
    return [{"role": "system", "content": system},
            {"role": "user", "content": prompt_text(case)}]


def prepare_workspace(case: dict, arm: str, rid: str) -> pathlib.Path:
    ws = WORKROOT / rid
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    proc = subprocess.run(["git", "-C", str(CODE / case["repo"]), "archive",
                           "--format=tar", case["parent_sha"]], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git archive failed: {proc.stderr[:300]}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tf:
        try:
            tf.extractall(ws, filter="data")
        except TypeError:  # Python < 3.12
            tf.extractall(ws)
    kb = ws / case["kb_path"]
    if kb_present(case, arm):
        kb.parent.mkdir(parents=True, exist_ok=True)
        kb.write_bytes(kb_bytes(case, arm))
    else:
        if kb.exists():
            kb.unlink()
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "agentic-cf", "GIT_AUTHOR_EMAIL": "cf@local",
                "GIT_COMMITTER_NAME": "agentic-cf", "GIT_COMMITTER_EMAIL": "cf@local"})
    for cmd in (["git", "init", "-q"],
                ["git", "-c", "core.autocrlf=false", "add", "-A"],
                ["git", "commit", "-qm", "base", "--no-gpg-sign"]):
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"{cmd} failed in {ws}: {r.stderr[:300]}")
    if case["id"] == "R5" and WECHAT_NODE_MODULES.exists():
        link = ws / "node_modules"
        if not link.exists():
            os.symlink(WECHAT_NODE_MODULES, link)
        excl = ws / ".git" / "info" / "exclude"
        excl.parent.mkdir(parents=True, exist_ok=True)
        excl.write_text(excl.read_text() + "\nnode_modules\n" if excl.exists() else "node_modules\n")
    return ws


def parse_action(raw: str) -> dict:
    """Recover the FIRST complete JSON object from a model reply (deterministic).

    The one-action protocol is enforced by the prompt, but chat models often wrap a single action
    in prose or emit several JSON objects in one turn. The previous `parse_json` used a greedy
    {.*} match and silently rejected those turns (only the first-object-of-several problem is a
    protocol violation; prose/fences are tolerated here).
    """
    if not isinstance(raw, str) or not raw.strip():
        return {}
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    candidates = list(fenced)
    # balanced-brace scan over the whole reply
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(raw[start:i + 1])
                    start = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and "action" in obj:
            return obj
    return {}


def file_manifest(ws: pathlib.Path, limit_bytes: int = 2_000_000) -> dict:
    """Deterministic baseline manifest (rel -> size/quick hash), used for final change accounting.

    The repositories ignore different trees (e.g. engram's `.gitignore` ignores `.agents/...`), so
    `git status`/`git diff` alone under-count agent-created files. Files >2 MB use size+mtime only.
    """
    import hashlib
    out = {}
    for p in ws.rglob("*"):
        if not p.is_file():
            continue
        parts = p.parts
        if any(x in parts for x in (".git", "node_modules", "__pycache__")):
            continue
        rel = str(p.relative_to(ws)).replace(os.sep, "/")
        try:
            st = p.stat()
            if st.st_size <= limit_bytes:
                h = hashlib.sha256(p.read_bytes()).hexdigest()[:20]
            else:
                h = f"{st.st_size}:{int(st.st_mtime_ns)}"
            out[rel] = h
        except OSError:
            out[rel] = "unreadable"
    return out


def manifest_delta(ws: pathlib.Path, base: dict) -> dict:
    cur = file_manifest(ws)
    added = sorted(set(cur) - set(base))
    removed = sorted(set(base) - set(cur))
    modified = sorted(k for k in set(cur) & set(base) if cur[k] != base[k])
    return {"added": added, "removed": removed, "modified": modified,
            "changed_files": sorted(added + removed + modified)}


def safe_rel(ws: pathlib.Path, rel: str) -> pathlib.Path | None:
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        return None
    if os.path.isabs(rel):
        return None
    p = (ws / rel).resolve()
    base = ws.resolve()
    if p != base and base not in p.parents:
        return None
    return p


def _rel(ws: pathlib.Path, p: pathlib.Path) -> str:
    return str(p.relative_to(ws.resolve())).replace(os.sep, "/")


class Tools:
    def __init__(self, ws: pathlib.Path, case: dict):
        self.ws = ws
        self.case = case

    # -- read-only ------------------------------------------------------
    def ls(self, path: str = ".") -> str:
        p = safe_rel(self.ws, path or ".")
        if p is None or not p.exists() or not p.is_dir():
            return f"error: not a directory inside the workspace: {path!r}"
        entries = []
        for name in sorted(os.listdir(p)):
            if name in (".git", "node_modules", "__pycache__"):
                continue
            fp = p / name
            if fp.is_dir():
                entries.append(name + "/")
            else:
                try:
                    entries.append(f"{name} ({fp.stat().st_size}B)")
                except OSError:
                    entries.append(name)
        return "\n".join(entries[:400]) or "(empty)"

    def read_file(self, path: str) -> str:
        p = safe_rel(self.ws, path)
        if p is None or not p.is_file():
            return f"error: not a readable file inside the workspace: {path!r}"
        try:
            data = p.read_bytes()
        except OSError as exc:
            return f"error: {exc}"
        if b"\x00" in data[:4096]:
            return "error: binary file"
        text = data[:40000].decode("utf-8", "replace")
        suffix = "\n...[truncated at 40000 bytes]" if len(data) > 40000 else ""
        return text + suffix

    def grep(self, pattern: str, path: str = ".") -> str:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"error: invalid regex: {exc}"
        start = safe_rel(self.ws, path or ".")
        if start is None or not start.exists():
            return f"error: path not found: {path!r}"
        files = [start] if start.is_file() else [q for q in start.rglob("*") if q.is_file()]
        hits, scanned = [], 0
        for f in files:
            if scanned >= 4000 or len(hits) >= 80:
                break
            parts = f.parts
            if any(x in parts for x in (".git", "node_modules", "__pycache__")):
                continue
            try:
                if f.stat().st_size > 400_000:
                    continue
                data = f.read_bytes()
                if b"\x00" in data[:2048]:
                    continue
            except OSError:
                continue
            scanned += 1
            for i, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{_rel(self.ws, f)}:{i}:{line[:200]}")
                    if len(hits) >= 80:
                        break
        return "\n".join(hits) or "(no matches)"

    # -- write ----------------------------------------------------------
    def write_file(self, path: str, content: str) -> str:
        p = safe_rel(self.ws, path)
        if p is None:
            return f"error: path must be relative and inside the workspace: {path!r}"
        if not isinstance(content, str):
            return "error: content must be a string"
        content = content[:200_000]
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"error: {exc}"
        return f"wrote {path} ({len(content)} chars)"

    def apply_patch(self, patch: str) -> str:
        if not isinstance(patch, str) or not patch.strip():
            return "error: empty patch"
        last = ""
        for label, text in (("raw", patch), ("normalized", normalize_patch(patch))):
            fd, pf = tempfile.mkstemp(prefix="agentic_cf_", suffix=".patch")
            os.close(fd)
            try:
                with open(pf, "w", encoding="utf-8") as f:
                    f.write(text if text.endswith("\n") else text + "\n")
                chk = subprocess.run(["git", "apply", "--recount", "--check", pf],
                                     cwd=self.ws, capture_output=True, text=True)
                if chk.returncode != 0:
                    last = (chk.stderr or chk.stdout)[:800]
                    continue
                app = subprocess.run(["git", "apply", "--recount", pf], cwd=self.ws,
                                     capture_output=True, text=True)
                if app.returncode == 0:
                    extra = " (diff --git headers repaired by harness)" if label == "normalized" else ""
                    return "patch applied" + extra
                last = (app.stderr or app.stdout)[:800]
            finally:
                try:
                    os.unlink(pf)
                except OSError:
                    pass
        return "error: patch did not apply: " + last

    # -- run ------------------------------------------------------------
    def _allowed(self, toks: list[str]) -> str:
        case_cmd = list(self.case["repo_test"]["cmd"])
        if toks == case_cmd:
            return "repo_test"
        if toks and toks[0] == "git" and len(toks) >= 2 and toks[1] in ("status", "diff"):
            if all(t.startswith("-") or t in ("status", "diff") for t in toks[1:]):
                return "git"
        if len(toks) == 4 and toks[0] in ("python", "python3") and toks[1] == "-m" \
                and toks[2] in ("py_compile", "compileall"):
            return "python"
        if len(toks) == 3 and toks[0] == "node" and toks[1] == "--check":
            return "node"
        if len(toks) == 3 and toks[0] == "gofmt" and toks[1] == "-l":
            return "gofmt"
        return ""

    def run(self, cmd: str) -> str:
        if not isinstance(cmd, str) or not cmd.strip():
            return "error: empty command"
        try:
            toks = shlex.split(cmd)
        except ValueError as exc:
            return f"error: cannot parse command: {exc}"
        if not toks:
            return "error: empty command"
        kind = self._allowed(toks)
        if not kind:
            return ("command not allowed; allowed: the repository test subset, git status/diff, "
                    "python -m py_compile <file>, node --check <file>, gofmt -l <file>")
        env = dict(os.environ)
        env["PATH"] = RUNTIME_PATH + ":" + env.get("PATH", "")
        if self.case["id"] == "R3":
            env["PYTHONPATH"] = f"{ENGRAM_DEPS}:{self.ws / 'src'}"
        if kind == "python":
            exe = str(toks[0])
            toks = [sys.executable if exe in ("python", "python3") else exe] + toks[1:]
        try:
            r = subprocess.run(toks, cwd=self.ws, capture_output=True, text=True,
                               timeout=120, env=env)
        except subprocess.TimeoutExpired:
            return "error: command timed out (120s)"
        except OSError as exc:
            return f"error: {exc}"
        out = (r.stdout or "") + (r.stderr or "")
        return f"rc={r.returncode}\n" + out[-1800:]


def kb_signatures(case: dict, arm: str) -> list[str]:
    """Distinctive lines of the arm KB, used to detect whether the agent actually SAW the KB
    (via read_file or grep/ls output). Metric only; never used for grading."""
    if not kb_present(case, arm):
        return []
    text = kb_bytes(case, arm).decode("utf-8", "replace")
    sig, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 25 and line not in seen:
            seen.add(line)
            sig.append(line[:120])
        if len(sig) >= 4:
            break
    return sig


def kb_seen(messages: list[dict], signatures: list[str]) -> bool:
    if not signatures:
        return False
    blob = "\n".join((m.get("content") or "") for m in messages
                      if m.get("role") == "user")
    return any(sig in blob for sig in signatures)


def classify_actions(actions: list[dict], case: dict, ws: pathlib.Path) -> dict:
    """Count stale-path inspections/edits and KB reads from the logged tool actions."""
    stale_tokens = STALE_TOKENS.get(case["id"], [])
    insp = 0
    edits = 0
    for a in actions:
        blob = json.dumps(a, ensure_ascii=False)
        hit = False
        for tok in stale_tokens:
            if tok not in blob:
                continue
            if case["id"] == "R5" and tok == "pages/":
                if re.search(r"(?<!miniprogram/)pages/", blob):
                    hit = True
            else:
                hit = True
        if hit:
            insp += 1
            if a.get("action") in ("write_file", "apply_patch"):
                edits += 1
    kb = case["kb_path"]
    kb_read = any(a.get("action") == "read_file" and str(a.get("path", "")).strip("./").endswith(kb)
                  for a in actions)
    return {"stale_inspections": insp, "stale_edit_actions": edits, "kb_read": kb_read,
            "tool_calls": dict(sorted((k, sum(1 for a in actions if a.get("action") == k))
                                      for k in {a.get("action") for a in actions}))}


def stale_path_patterns(case: dict) -> list[str]:
    if case["id"] == "R4":
        return [r"(^|/)docs/layouts/_partials/icons\.html$"]
    if case["id"] == "R5":
        return [r"^(pages|static|user|pay|app\.json)"]
    return [r"(^|/)\.agents/skills/memory-update/"]


def final_state(ws: pathlib.Path, case: dict, base_manifest: dict) -> dict:
    """Capture changed files + diff BEFORE deterministic checks mutate the workspace.

    Change accounting uses a filesystem manifest (independent of git ignores); the diff is captured
    by force-staging only the changed paths (ignored trees excluded) so new/ignored files appear.
    """
    delta = manifest_delta(ws, base_manifest)
    files = delta["changed_files"]
    excl = ":(exclude)node_modules"
    subprocess.run(["git", "add", "-A", "-f", "--", ".", excl], cwd=ws, capture_output=True)
    diff = ""
    if files:
        subprocess.run(["git", "add", "-f", "--"] + files, cwd=ws, capture_output=True)
        diff = subprocess.run(["git", "diff", "--cached", "--no-color", "--"] + files,
                              cwd=ws, capture_output=True, text=True).stdout
    stale_rx = [re.compile(p) for p in stale_path_patterns(case)]
    wrong = [f for f in files if any(rx.search(f) for rx in stale_rx)]
    expected = case.get("expected_paths") or []
    def _expected(f: str) -> bool:
        for e in expected:
            e = e.strip()
            if e.endswith("/"):
                if f.startswith(e) or ("/" + e) in f:
                    return True
            elif f == e:
                return True
        return False
    unrelated = [f for f in files if not _expected(f)]
    return {"changed_files": files, "wrong_path_final_edits": wrong,
            "unrelated_files_changed": unrelated,
            "dual_path": bool(wrong) and any(_expected(f) for f in files),
            "diff_chars": len(diff), "diff": diff}


def grade(ws: pathlib.Path, case: dict) -> dict:
    check = CHECK[case["id"]]
    hidden, info = check(ws)
    try:
        rt, rt_tail = run_repo_test(case, ws)
        rt_status = "pass" if rt else "fail"
    except Exception as exc:  # noqa: BLE001
        rt, rt_tail, rt_status = False, f"{type(exc).__name__}: {exc}", "error"
    return {"hidden_pass": bool(hidden), "hidden_info": info,
            "repo_test_pass": bool(rt), "repo_test_status": rt_status,
            "repo_test_tail": (rt_tail or "")[-800:]}


# --------------------------------------------------------------------------- agent loop
def agent_run(env: dict, case: dict, arm: str, seed: int, rid: str) -> dict:
    temp = SEED_TEMPS[seed]
    t0 = time.time()
    ws = prepare_workspace(case, arm, rid)
    base_manifest = file_manifest(ws)
    messages = cell_prompt(case)
    actions: list[dict] = []
    steps = 0
    auto_submit = False
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0,
                 "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0}
    cost = 0.0
    error = None
    submitted = False
    api_retry_used = False
    while steps < MAX_STEPS:
        steps += 1
        try:
            resp = chat(env, messages, MODEL, temperature=temp,
                        max_tokens=MAX_TOKENS_PER_STEP)
        except Exception as exc:  # noqa: BLE001
            if not api_retry_used:
                api_retry_used = True
                steps -= 1
                time.sleep(2)
                continue
            error = f"{type(exc).__name__}: {exc}"[:500]
            break
        raw = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        usage = resp.get("usage") or {}
        for k in usage_tot:
            usage_tot[k] += int(usage.get(k) or 0)
        cost += usage_cost(usage)
        act = parse_action(raw)
        messages.append({"role": "assistant", "content": raw[:2500]})
        if not isinstance(act, dict) or "action" not in act:
            messages.append({"role": "user",
                             "content": "Return ONLY the JSON action object (ls/read_file/grep/"
                                        "write_file/apply_patch/run/submit)."})
            actions.append({"action": "invalid_json"})
            continue
        a = str(act.get("action", "")).lower()
        actions.append({"action": a, **{k: (str(v)[:1000] if k != "content" else str(v)[:2000])
                                       for k, v in act.items() if k != "action"}})
        tools = Tools(ws, case)
        if a in ("ls", "list"):
            out = tools.ls(act.get("path") or ".")
        elif a in ("read_file", "read", "cat"):
            out = tools.read_file(act.get("path") or "")
        elif a in ("grep", "search"):
            out = tools.grep(act.get("pattern") or "", act.get("path") or ".")
        elif a in ("write_file", "write", "create"):
            out = tools.write_file(act.get("path") or "", act.get("content") or "")
        elif a in ("apply_patch", "patch"):
            out = tools.apply_patch(act.get("patch") or act.get("diff") or "")
        elif a in ("run", "bash", "exec"):
            out = tools.run(act.get("cmd") or act.get("command") or "")
        elif a in ("submit", "finish", "done"):
            submitted = True
            messages.append({"role": "user", "content": "state submitted"})
            break
        else:
            out = "unknown action; use ls/read_file/grep/write_file/apply_patch/run/submit"
        messages.append({"role": "user", "content": "tool output:\n" + out[:1800]})
    if not submitted:
        auto_submit = True
    classification = classify_actions(actions, case, ws)
    classification["kb_seen_in_tool_output"] = kb_seen(messages, kb_signatures(case, arm))
    state = final_state(ws, case, base_manifest)
    graded = grade(ws, case)
    DIFFS.mkdir(parents=True, exist_ok=True)
    (DIFFS / f"{rid}.diff").write_text(state["diff"])
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    (TRANSCRIPTS / f"{rid}.json").write_text(json.dumps(
        [{"role": m.get("role"), "content": (m.get("content") or "")[:1800]} for m in messages],
        ensure_ascii=False, indent=1))
    rec = {
        "run_id": rid, "case": case["id"], "repo": case["repo"], "arm": arm, "seed": seed,
        "temperature": temp, "model": MODEL, "parent_sha": case["parent_sha"],
        "fix_sha": case["fix_sha"], "kb_path": case["kb_path"],
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "steps": steps, "submitted": submitted, "auto_submit": auto_submit,
        "api_retry_used": api_retry_used, "error": error,
        "usage": usage_tot, "cost_cny": round(cost, 6),
        "latency_s": round(time.time() - t0, 2),
        "hidden_pass": graded["hidden_pass"], "hidden_info": graded["hidden_info"],
        "repo_test_pass": graded["repo_test_pass"], "repo_test_status": graded["repo_test_status"],
        "repo_test_tail": graded["repo_test_tail"],
        "changed_files": state["changed_files"],
        "files_added": state.get("added", []), "files_removed": state.get("removed", []),
        "files_modified": state.get("modified", []),
        "wrong_path_final_edits": state["wrong_path_final_edits"],
        "unrelated_files_changed": state["unrelated_files_changed"],
        "dual_path": state["dual_path"],
        "diff_chars": state["diff_chars"], "diff_file": f"diffs/{rid}.diff",
        "transcript_file": f"transcripts/{rid}.json",
        **classification,
    }
    return rec


# --------------------------------------------------------------------------- analysis
def cp_ci(k: int, n: int, alpha: float = 0.05) -> list[float]:
    """Clopper-Pearson exact 95% CI via bisection on the binomial CDF (stdlib only)."""
    if n <= 0:
        return [0.0, 0.0]
    def cdf(p: float) -> float:
        return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(0, k + 1))
    def sf(p: float) -> float:
        return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))
    lo, hi = 0.0, 1.0
    if k == 0:
        lo = 0.0
    else:
        for _ in range(80):
            mid = (lo + hi) / 2
            if sf(mid) < alpha / 2:
                lo = mid
            else:
                hi = mid
        lo = (lo + hi) / 2
    lo2, hi2 = 0.0, 1.0
    if k == n:
        hi = 1.0
    else:
        for _ in range(80):
            mid = (lo2 + hi2) / 2
            if cdf(mid) > alpha / 2:
                lo2 = mid
            else:
                hi2 = mid
        hi = (lo2 + hi2) / 2
    return [round(lo, 4), round(hi, 4)]


def fisher_one_sided(a: int, b: int, c: int, d: int) -> float:
    """P(X >= a) for the 2x2 table [[a,b],[c,d]] (hypergeometric, exact)."""
    n1, n2, col = a + b, c + d, a + c
    total = n1 + n2
    if col == 0 or n1 == 0 or n2 == 0:
        return 1.0
    lo, hi = max(0, col - n2), min(n1, col)
    denom = math.comb(total, col)
    p = 0.0
    for x in range(max(a, lo), hi + 1):
        p += math.comb(n1, x) * math.comb(n2, col - x)
    return min(1.0, p / denom)


def load_runs() -> list[dict]:
    if not RUNS.exists():
        return []
    out = []
    for line in RUNS.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return out


def done_cells() -> set:
    return {(r["case"], r["arm"], r["seed"]) for r in load_runs()}


def dry_run() -> int:
    """Zero API calls: exercise workspace construction, KB arms, tool API, grading mechanics."""
    WORKROOT.mkdir(parents=True, exist_ok=True)
    report = {"model_calls": 0, "cells": [], "tool_api_check": {}, "repo_test_baseline": {}}
    for cid in CASE_ORDER:
        case = CASES[cid]
        for arm in ARMS:
            rid = "dry__" + run_id(cid, arm, 0)
            ws = prepare_workspace(case, arm, rid)
            kb = ws / case["kb_path"]
            info = {"case": cid, "arm": arm,
                    "kb_present": kb.exists(),
                    "kb_sha256_16": __import__("hashlib").sha256(
                        kb.read_bytes()).hexdigest()[:16] if kb.exists() else None,
                    "n_files": sum(1 for _ in ws.rglob("*") if _.is_file()),
                    "prompt_chars": sum(len(m["content"]) for m in cell_prompt(case))}
            report["cells"].append(info)
            if arm == "corrected_kb" and cid == "R4":
                parser_cases = [
                    ("prose wrapping", 'I will inspect.\n{"action":"ls","path":"."}\nthanks', "ls"),
                    ("fenced", '```json\n{"action":"submit"}\n```', "submit"),
                    ("two objects", '{"action":"ls","path":"."}\n{"action":"submit"}', "ls"),
                    ("no json", "plain prose", None),
                ]
                report["parser_check"] = [
                    {"name": n, "expected": e, "got": parse_action(r).get("action")}
                    for n, r, e in parser_cases]
                t = Tools(ws, case)
                seq = [t.ls("."), t.read_file(case["kb_path"]), t.grep("icons", "."),
                       t.run("git status --porcelain"), t.run("git diff"),
                       t.write_file("docs/layouts/_partials/layouts/_probe.txt", "probe\n"),
                       t.read_file("docs/layouts/_partials/layouts/_probe.txt"),
                       t.run("rm -rf /tmp/agentic_cf_never"), t.run("node --check main.go")]
                report["tool_api_check"] = {
                    "steps": seq, "probe_file_exists": (ws / "docs/layouts/_partials/layouts/_probe.txt").exists(),
                    "probe_file_read_ok": "probe" in seq[6],
                    "disallowed_cmd_rejected": seq[7].startswith("command not allowed"),
                    "allowed_node_check_ran": seq[8].startswith("rc=")}
            base_grade = grade(ws, case)
            report["repo_test_baseline"][f"{cid}/{arm}"] = {
                "hidden_pass_on_base": base_grade["hidden_pass"],
                "repo_test_status": base_grade["repo_test_status"],
                "repo_test_tail": base_grade["repo_test_tail"][-300:]}
            shutil.rmtree(ws, ignore_errors=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "dry_run.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report["tool_api_check"], indent=1)[:1500])
    print("dry-run cells:", len(report["cells"]), "| model calls: 0 | wrote results/dry_run.json")
    bad = [c for c in report["cells"] if c["kb_present"] != (c["arm"] != "no_kb")]
    print("KB-arm checks:", "OK" if not bad else f"FAIL {bad}")
    pc = report.get("parser_check") or []
    print("parser checks:", "OK" if pc and all(x["got"] == x["expected"] for x in pc) else f"FAIL {pc}")
    return 0


def summarize() -> int:
    rows = load_runs()
    cells = {}
    for r in rows:
        cells.setdefault((r["case"], r["arm"]), []).append(r)
    summary: dict = {"n_runs": len(rows),
                     "prereg_sha256": (HERE / "PREREG.sha256").read_text().split()[0],
                     "model": MODEL, "max_steps": MAX_STEPS,
                     "by_cell": {}, "by_condition": {}, "by_repo": {}, "total_cost_cny": 0.0}
    for (cid, arm), rs in sorted(cells.items()):
        summary["by_cell"][f"{cid}/{arm}"] = {
            "n": len(rs), "hidden_pass": sum(bool(r.get("hidden_pass")) for r in rs),
            "repo_test_pass": sum(bool(r.get("repo_test_pass")) for r in rs),
            "submitted": sum(bool(r.get("submitted")) for r in rs),
            "med_steps": sorted(r.get("steps") or 0 for r in rs)[len(rs) // 2],
            "cost_cny": round(sum(float(r.get("cost_cny") or 0) for r in rs), 6),
        }
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        k, n = sum(bool(r.get("hidden_pass")) for r in rs), len(rs)
        summary["by_condition"][arm] = {
            "n": n, "hidden_pass": k, "repo_test_pass": sum(bool(r.get("repo_test_pass")) for r in rs),
            "cp95": cp_ci(k, n) if n else [0.0, 0.0],
            "total_steps": sum(int(r.get("steps") or 0) for r in rs),
            "total_tool_calls": sum(int((r.get("tool_calls") or {}).get(t, 0))
                                    for r in rs for t in (r.get("tool_calls") or {})),
            "stale_inspections": sum(int(r.get("stale_inspections") or 0) for r in rs),
            "wrong_path_final_edits": sum(bool(r.get("wrong_path_final_edits")) for r in rs),
            "kb_read": sum(bool(r.get("kb_read")) for r in rs),
        }
    for cid in CASE_ORDER:
        summary["by_repo"][cid] = {
            arm: {"n": len([r for r in rows if r["case"] == cid and r["arm"] == arm]),
                  "hidden_pass": sum(bool(r.get("hidden_pass")) for r in rows
                                     if r["case"] == cid and r["arm"] == arm)}
            for arm in ARMS}
    corr = summary["by_condition"]["corrected_kb"]["hidden_pass"]
    stale = summary["by_condition"]["stale_kb"]["hidden_pass"]
    nokb = summary["by_condition"]["no_kb"]["hidden_pass"]
    n = len([r for r in rows if r["arm"] == "corrected_kb"])
    ns = len([r for r in rows if r["arm"] == "stale_kb"])
    nn = len([r for r in rows if r["arm"] == "no_kb"])
    summary["fisher"] = {
        "corrected_vs_stale_one_sided_p": round(fisher_one_sided(corr, n - corr, stale, ns - stale), 6)
        if n and ns else None,
        "corrected_vs_no_kb_one_sided_p": round(fisher_one_sided(corr, n - corr, nokb, nn - nokb), 6)
        if n and nn else None,
    }
    summary["total_cost_cny"] = round(sum(float(r.get("cost_cny") or 0) for r in rows), 6)
    addendum = HERE / "PREREG_ADDENDUM.sha256"
    if addendum.exists():
        summary["prereg_addendum_sha256"] = addendum.read_text().split()[0]
    v1 = HERE / "results_v1" / "runs_v1_parser_greedy.jsonl"
    if v1.exists():
        v1_rows = [json.loads(x) for x in v1.read_text().splitlines() if x.strip()]
        summary["v1_sensitivity_instrument_bug"] = {
            "note": "parser-defect run; not used for condition comparison (see PREREG_ADDENDUM.md)",
            "n_runs": len(v1_rows),
            "by_condition_hidden_pass": {arm: sum(bool(r.get("hidden_pass")) for r in v1_rows
                                                  if r["arm"] == arm) for arm in ARMS},
            "cost_cny": round(sum(float(r.get("cost_cny") or 0) for r in v1_rows), 6)}
    summary["total_prompt_tokens"] = sum((r.get("usage") or {}).get("prompt_tokens") or 0 for r in rows)
    summary["total_completion_tokens"] = sum((r.get("usage") or {}).get("completion_tokens") or 0
                                            for r in rows)
    SUMMARY.write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["by_condition"], indent=1))
    print("fisher:", summary["fisher"], "| cost:", summary["total_cost_cny"])
    return 0


def run(limit: int | None = None, validation: bool = False, workers: int = 1,
        cells_filter: list[str] | None = None) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    DIFFS.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    done = done_cells()
    if validation:
        cells = [("R4", "corrected_kb", 0)]
        if cells[0] in done:
            print("validation cell already done", file=sys.stderr)
            return 0
    else:
        cells = [(cid, arm, seed) for cid in CASE_ORDER for arm in ARMS for seed in (0, 1)
                 if (cid, arm, seed) not in done]
    if cells_filter:
        wanted = set(cells_filter)
        cells = [c for c in cells if run_id(*c) in wanted]
    if limit is not None:
        cells = cells[:limit]
    env = load_env()
    total_cost = sum(float(r.get("cost_cny") or 0) for r in load_runs())
    print(f"planned cells: {len(cells)}; spent so far: {total_cost:.4f} CNY", file=sys.stderr)

    def one(cell):
        cid, arm, seed = cell
        rid = run_id(cid, arm, seed)
        rec = agent_run(env, CASES[cid], arm, seed, rid)
        with RUNS.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{rid}: hidden={rec['hidden_pass']} steps={rec['steps']} "
              f"cost={rec['cost_cny']} err={rec['error']} kb_read={rec['kb_read']}", file=sys.stderr)
        return rec

    if workers <= 1:
        for cell in cells:
            if total_cost >= STOP_AT_CNY:
                print(f"STOP: cost {total_cost:.4f} >= {STOP_AT_CNY} CNY", file=sys.stderr)
                break
            rec = one(cell)
            total_cost += float(rec.get("cost_cny") or 0)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, MAX_WORKERS)) as ex:
            futs = {ex.submit(one, c): c for c in cells}
            for fut in as_completed(futs):
                fut.result()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--cells", default=None,
                    help="comma-separated run ids (e.g. R5__stale_kb__s0) to (re)run")
    a = ap.parse_args()
    if a.dry_run:
        return dry_run()
    if a.summarize:
        return summarize()
    if a.run:
        filt = [x.strip() for x in a.cells.split(",") if x.strip()] if a.cells else None
        return run(limit=a.limit, validation=a.validation, workers=a.workers, cells_filter=filt)
    print("use --dry-run, --run [--validation] [--limit N] [--workers N], or --summarize",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
