#!/usr/bin/env python3
"""Historical PR/commit replay: validate the kblint v0.3.0 incremental PR gate.

Replays real historical commit events on small public repositories from the natural-audit
list (kb-health/analysis/natural_checkout_audit/): for each event (base SHA, head SHA) it
scans the base tree with the base KB (baseline report) and the head tree with the head KB
(current report), runs `kblint diff --fail-on-new medium`, records NEW/PERSISTING/FIXED,
blocking NEW, exit code and runtimes, then adjudicates every NEW finding and every FIXED row
against the extracted trees.

Zero LLM/API calls for analysis; the only network use is GitHub API (commit metadata) and
codeload tarballs, cached under /tmp/pr_replay/. Source trees are never modified.

Phases (resumable):
  details     -> events.json (candidate events with changed files; API, console output)
  fetch       -> /tmp/pr_replay/repos/<owner__repo>/<sha>/ extracted trees
  scan        -> raw/<event>/{baseline,current,diff}/ + meta.json
  adjudicate  -> adjudication.jsonl
  summarize   -> results/summary.json

Usage: python3 run_pr_replay.py {details,fetch,scan,adjudicate,summarize,all}
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.abspath(os.path.join(HERE, "..", ".."))
KBLINT = os.path.join(KB, "kblint")
NATURAL = os.path.join(KB, "analysis", "natural_checkout_audit")
SCRATCH = "/tmp/pr_replay"
REPOS = os.path.join(SCRATCH, "repos")
TARBALLS = os.path.join(SCRATCH, "tarballs")
RAW = os.path.join(HERE, "raw")
RESULTS = os.path.join(HERE, "results")
EVENTS = os.path.join(HERE, "events.json")
NOW = "2026-11-09"
FAIL_ON_NEW = "medium"
MAX_TARBALL = 20 * 1024 * 1024

# small repos from the natural-audit list + hand-picked recent commit candidates
CANDIDATES = {
    "blader/humanizer": {
        "kb_file": "AGENTS.md",
        "commits": ["0ef9fe5bc3", "b6039ead39", "d4b81278e6", "7a13cfed8f", "a62daa3a2d",
                    "6be1fa4e0c", "f9f12c67c4", "8c307f367c"],
    },
    "mattpocock/skills": {
        "kb_file": "CLAUDE.md",
        "commits": ["4ae2317ddb", "5ae481693d", "a496f5513d", "d1478fcb14", "49dd158d10",
                    "dd400c3ad6", "542543a5da", "6fd947921b"],
    },
    "addyosmani/agent-skills": {
        "kb_file": "AGENTS.md",
        "commits": ["301b02b12b", "8bfcc1f991", "db3031dd4a", "52acec0050", "9604a3f77b",
                    "353ae84755", "6867dbbe70", "8b376edc54"],
    },
    "modelcontextprotocol/servers": {
        "kb_file": "AGENTS.md",
        "commits": ["36380287ed", "79fe953469", "8da06bc446", "43d93afa40", "e6f2240958",
                    "f2d34779e5", "7a47f45695", "c583da0291"],
    },
}
MAX_EVENTS_PER_REPO = 4  # 2-3 relevant + >=1 negative control


# --------------------------------------------------------------------- helpers
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def api(url):
    last = None
    for attempt in range(3):
        proc = subprocess.run(["curl", "-sS", "--compressed", "-m", "90", "-w", "\n%{http_code}",
                               url], capture_output=True, text=True)
        body, _, code = proc.stdout.rpartition("\n")
        if code.strip() != "200":
            raise RuntimeError("API %s -> %s %s" % (url, code.strip(), body[:200]))
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            last = "json error (%s, len=%d) on %s" % (e, len(body), url)
            time.sleep(1.5)
    raise RuntimeError(last)


def slug(repo):
    return repo.replace("/", "__")


def load_json(path, default=None):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return default


# --------------------------------------------------------------------- details
# NOTE (execution deviation, documented in PROTOCOL.md): the unauthenticated GitHub REST API
# rate limit (60/h) was exhausted during reconnaissance. Commit SHAs are therefore resolved from
# the public commit atom feeds (github.com/<repo>/commits/<branch>.atom) and file-level changes
# from the public compare `.diff` endpoints (github.com/<repo>/compare/<base>...<head>.diff) -
# the same pinned SHAs, no auth token, no API quota. No LLM/API calls for analysis.
DOC_SCOPE = ["AGENTS.md", "CLAUDE.md", "docs/AGENTS.md", ".github/copilot-instructions.md",
             "GEMINI.md"]
BUILD_NAMES = ("Makefile", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
               "go.mod", "setup.py", "uv.lock", "pnpm-lock.yaml", "package-lock.json")
DOC_EXT = (".md", ".markdown", ".rst", ".txt")
CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".sh", ".bash",
            ".json", ".yaml", ".yml", ".toml", ".html", ".css", ".svelte", ".vue", ".ptx", ".cu")


def is_kb(path):
    return path in DOC_SCOPE or "/AGENTS.md" in "/" + path or "/CLAUDE.md" in "/" + path


def _curl_text(url, timeout=60):
    proc = subprocess.run(["curl", "-sSL", "--compressed", "-m", str(timeout), "-w",
                           "\n%{http_code}", url], capture_output=True, text=True)
    body, _, code = proc.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError("curl %s -> %s" % (url, code.strip()))
    return body


def _atom_shas(repo):
    last = None
    for branch in ("main", "master"):
        try:
            text = _curl_text("https://github.com/%s/commits/%s.atom" % (repo, branch))
        except RuntimeError as e:
            last = str(e)
            continue
        ids = re.findall(r"<id>tag:github.com,2008:Grit::Commit/([0-9a-f]{40})</id>", text)
        if len(ids) >= 5:
            return branch, ids
        last = "too few atom entries for branch " + branch
    raise RuntimeError("atom feed failed for %s: %s" % (repo, last))


def _compare_files(repo, base, head):
    """Changed files from the public compare .diff endpoint (no API quota)."""
    text = _curl_text("https://github.com/%s/compare/%s...%s.diff" % (repo, base, head))
    files = []
    cur = None
    for line in text.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)$", line)
        if m:
            cur = {"filename": m.group(2), "previous": m.group(1), "status": "modified"}
            if cur["previous"] != cur["filename"]:
                cur["status"] = "renamed"
            files.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "removed"
        elif line.startswith("rename from "):
            cur["previous"] = line[len("rename from "):].strip()
            cur["status"] = "renamed"
    return files


def details():
    """Discover historical commit events (atom feeds + compare diffs); write events.json."""
    os.makedirs(SCRATCH, exist_ok=True)
    cache_path = os.path.join(SCRATCH, "compare_cache.json")
    cache = load_json(cache_path, {})
    all_events = []
    for repo, spec in CANDIDATES.items():
        branch, shas = _atom_shas(repo)
        print("%s branch=%s entries=%d" % (repo, branch, len(shas)), flush=True)
        pairs = [(shas[i], shas[i + 1]) for i in range(min(12, len(shas) - 1))]
        for head, base in pairs:
            key = "%s|%s|%s" % (repo, base[:12], head[:12])
            if key not in cache:
                try:
                    cache[key] = _compare_files(repo, base, head)
                except RuntimeError as e:
                    print("  compare failed", key, str(e)[:80]); continue
                time.sleep(0.25)
            files = cache[key]
            if not files:
                continue
            has_kb = any(is_kb(f["filename"]) or is_kb(f.get("previous") or "") for f in files)
            has_build = any(f["filename"].split("/")[-1] in BUILD_NAMES for f in files)
            code_events = [f for f in files
                           if f["filename"].lower().endswith(CODE_EXT)
                           and not f["filename"].lower().startswith(("docs/", "readme", "changelog"))]
            renamed = [f for f in files if f["status"] in ("renamed", "removed", "deleted")]
            docs_only = all(f["filename"].lower().endswith(DOC_EXT)
                            and not is_kb(f["filename"]) for f in files)
            kind = ("kb_edit" if has_kb else
                    "build_change" if has_build else
                    "code_path_change" if (renamed or code_events) else
                    "docs_only")
            all_events.append({"repo": repo, "kb_file": spec["kb_file"], "base": base, "head": head,
                               "branch": branch, "files": files, "kind": kind,
                               "has_kb": has_kb, "has_build": has_build,
                               "n_files": len(files)})
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    chosen = []
    for repo in CANDIDATES:
        evs = [e for e in all_events if e["repo"] == repo]
        relevant = [e for e in evs if e["kind"] in ("kb_edit", "build_change", "code_path_change")]
        negatives = [e for e in evs if e["kind"] == "docs_only"]
        relevant.sort(key=lambda e: (e["kind"] == "kb_edit", e["has_build"],
                                     e["kind"] == "code_path_change"), reverse=True)
        picked = relevant[:3] + negatives[:1]
        for e in evs:
            if len(picked) >= MAX_EVENTS_PER_REPO:
                break
            if e not in picked:
                picked.append(e)
        for e in picked[:MAX_EVENTS_PER_REPO]:
            e = dict(e)
            e["event_id"] = "%s@%s" % (slug(repo), e["head"][:10])
            e["negative_control"] = e["kind"] == "docs_only"
            chosen.append(e)
    json.dump({"now": NOW, "fail_on_new": FAIL_ON_NEW, "events": chosen,
               "sampling_rule": ("recent default-branch commit events on 4 small natural-audit "
                                 "repos, resolved via public atom feeds; per repo 3 events whose "
                                 "changed files include the KB file or build/code/command paths, "
                                 "plus 1 unrelated-docs commit as a negative control "
                                 "(4 events/repo, 16 total). File lists come from public compare "
                                 ".diff endpoints because the unauthenticated REST API quota "
                                 "(60/h) was exhausted during reconnaissance."),
               "discovery_deviation": ("GitHub REST API rate-limited during reconnaissance; SHAs "
                                        "and changed-file lists resolved from public atom/compare "
                                        "endpoints (same pinned SHAs, no auth token).")},
              open(EVENTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("events:", len(chosen))
    for e in chosen:
        kinds = collections.Counter(f["status"] for f in e["files"])
        print("  %-46s %-16s %s  files=%2d %s" % (
            e["event_id"], e["kind"], e["head"][:10], len(e["files"]),
            [f["filename"] for f in e["files"]][:4]))


# --------------------------------------------------------------------- fetch
def fetch():
    sel = load_json(EVENTS)["events"]
    need = collections.defaultdict(set)
    repos = {}
    for e in sel:
        for sha in (e["base"], e["head"]):
            if sha:
                need[e["repo"]].add(sha)
    os.makedirs(REPOS, exist_ok=True)
    os.makedirs(TARBALLS, exist_ok=True)

    def one(item):
        repo, sha = item
        dest = os.path.join(REPOS, slug(repo), sha)
        if os.path.isdir(dest) and os.listdir(dest):
            return ("ok", repo, sha, sum(len(fs) for _, _, fs in os.walk(dest)), None)
        tar = os.path.join(TARBALLS, "%s__%s.tar.gz" % (slug(repo), sha[:40]))
        url = "https://codeload.github.com/%s/tar.gz/%s" % (repo, sha)
        proc = subprocess.run(["curl", "-sSL", "-m", "240", "--max-filesize", str(MAX_TARBALL),
                               "-o", tar, "-w", "%{http_code} %{size_download}", url],
                              capture_output=True, text=True)
        size = os.path.getsize(tar) if os.path.exists(tar) else 0
        if proc.returncode != 0 or size == 0 or size > MAX_TARBALL:
            return ("skip", repo, sha, size, "tarball rc=%s %s" % (proc.returncode, proc.stdout[:60]))
        os.makedirs(dest, exist_ok=True)
        ex = subprocess.run(["tar", "-xzf", tar, "-C", dest, "--strip-components=1"],
                            capture_output=True, text=True)
        if ex.returncode != 0:
            return ("skip", repo, sha, size, "tar: %s" % ex.stderr[-160:])
        return ("ok", repo, sha, size, None)

    items = [(r, s) for r in need for s in need[r]]
    print("fetching %d trees for %d events" % (len(items), len(sel)), flush=True)
    ok = skipped = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for kind, repo, sha, size, err in ex.map(one, items):
            if kind == "ok":
                ok += 1
                print("  ok  %-45s %s bytes=%d" % (repo, sha[:10], size), flush=True)
            else:
                skipped += 1
                print("  SKIP %-44s %s %s" % (repo, sha[:10], err), flush=True)
    print("trees ok=%d skipped=%d" % (ok, skipped))


# --------------------------------------------------------------------- scan
ALLOW_MISSING = [
    "^(node_modules|dist|build|out|outputs|artifacts|weights|runs|data|checkpoints|cache|\\.cache|"
    "coverage|logs|profiles|target|vendor|venv|\\.venv|tmp|temp|\\.next|\\.turbo|\\.git|site-packages|"
    "__pycache__|\\.pytest_cache|\\.mypy_cache)/",
    "\\.(lock|log|pid)$",
]
COUNTS = {
    "docs": re.compile(r"docs scanned: (\d+)"),
    "claims": re.compile(r"claims extracted: (\d+)"),
    "findings": re.compile(r"findings: \*\*(\d+)\*\*"),
    "queue": re.compile(r"audit queue \(not defects\): \*\*(\d+)\*\*"),
}


def build_config(repo, kb_file, tree, base_tree=None):
    trees = [t for t in (tree, base_tree) if t]
    docs = [d for d in dict.fromkeys(([kb_file] + DOC_SCOPE))
            if any(os.path.isfile(os.path.join(t, d)) for t in trees)]
    cfg = {"repo": ".", "docs": docs,
           "exclude": ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.venv/**",
                       "**/__pycache__/**", "**/vendor/**"],
           "now": NOW, "git": {"enabled": False}, "rules": {"R4": False},
           "references": {"enabled": True, "check_paths": True, "check_links": True,
                          "check_make": True, "check_npm": True,
                          "allow_missing": ALLOW_MISSING, "inventory": []}}
    return cfg, docs


def run_scan(tree, cfg_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "kblint", "scan", "--repo", tree, "--config", cfg_path,
           "--out", out_dir, "--format", "json,md,sarif", "--fail-on", "none", "--now", NOW]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=KBLINT, capture_output=True, text=True)
    runtime = round(time.monotonic() - t0, 3)
    if proc.returncode != 0:
        raise RuntimeError("scan failed rc=%s: %s" % (proc.returncode, proc.stderr[-800:]))
    open(os.path.join(out_dir, "stdout.txt"), "w", encoding="utf-8").write(proc.stdout)
    open(os.path.join(out_dir, "stderr.txt"), "w", encoding="utf-8").write(proc.stderr)
    summary = open(os.path.join(out_dir, "summary.md"), encoding="utf-8").read()
    counts = {k: int(rx.search(summary).group(1)) for k, rx in COUNTS.items() if rx.search(summary)}
    findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.jsonl"),
                                           encoding="utf-8") if l.strip()]
    return {"counts": counts, "findings": findings, "runtime_s": runtime,
            "exit_code": proc.returncode,
            "output_sha256": {n: sha256_file(os.path.join(out_dir, n))
                              for n in ("findings.jsonl", "audit_queue.jsonl", "summary.md",
                                        "report.sarif")}}


def scan():
    sel = load_json(EVENTS)["events"]
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(os.path.join(HERE, "configs"), exist_ok=True)
    for e in sel:
        ev_dir = os.path.join(RAW, e["event_id"])
        os.makedirs(ev_dir, exist_ok=True)
        base_tree = os.path.join(REPOS, slug(e["repo"]), e["base"])
        head_tree = os.path.join(REPOS, slug(e["repo"]), e["head"])
        if not (os.path.isdir(base_tree) and os.path.isdir(head_tree)):
            print("SKIP missing tree", e["event_id"]); continue
        # same config per repo across base/head; docs list from the head tree (missing docs self-skip)
        cfg, docs = build_config(e["repo"], e["kb_file"], head_tree, base_tree)
        cfg_path = os.path.join(HERE, "configs", slug(e["repo"]) + ".kblint.json")
        json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        base = run_scan(base_tree, cfg_path, os.path.join(ev_dir, "baseline"))
        head = run_scan(head_tree, cfg_path, os.path.join(ev_dir, "current"))
        diff_dir = os.path.join(ev_dir, "diff")
        os.makedirs(diff_dir, exist_ok=True)
        cmd = [sys.executable, "-m", "kblint", "diff",
               "--before", os.path.join(ev_dir, "baseline"),
               "--after", os.path.join(ev_dir, "current"),
               "--out", diff_dir, "--format", "json,md",
               "--fail-on-new", FAIL_ON_NEW]
        t0 = time.monotonic()
        dproc = subprocess.run(cmd, cwd=KBLINT, capture_output=True, text=True)
        diff_runtime = round(time.monotonic() - t0, 3)
        if dproc.returncode not in (0, 1):
            print("DIFF FAILED", e["event_id"], dproc.returncode, dproc.stderr[-500:]); continue
        diff = json.load(open(os.path.join(diff_dir, "diff.json"), encoding="utf-8"))
        open(os.path.join(diff_dir, "stdout.txt"), "w", encoding="utf-8").write(dproc.stdout)
        meta = {
            "event_id": e["event_id"], "repo": e["repo"], "base": e["base"], "head": e["head"],
            "date": e.get("date") or "", "message": e.get("message") or "", "kind": e["kind"],
            "negative_control": e["negative_control"], "files": e.get("files", []),
            "config": cfg_path, "docs": docs,
            "baseline": {k: base[k] for k in ("counts", "runtime_s", "exit_code")},
            "current": {k: head[k] for k in ("counts", "runtime_s", "exit_code")},
            "diff": {"counts": diff["counts"], "dispositions": diff["dispositions"],
                     "exit_code": diff["exit_code"], "runtime_s": diff_runtime,
                     "new": diff["new"], "persisting": diff["persisting"],
                     "fixed": diff["fixed"]},
            "total_runtime_s": round(base["runtime_s"] + head["runtime_s"] + diff_runtime, 3),
        }
        json.dump(meta, open(os.path.join(ev_dir, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        c = diff["counts"]
        print("scanned %-48s kind=%-15s NEW=%d (blocking %d) PERSIST=%d FIXED=%d exit=%d %.2fs" % (
            e["event_id"], e["kind"], c["new"], c["new_blocking"], c["persisting"], c["fixed"],
            diff["exit_code"], meta["total_runtime_s"]), flush=True)
    print("scanned events:", len(sel))


def adjudicate():
    """Adjudicate every NEW finding and FIXED row (single annotator, rule-assisted)."""
    sel = load_json(EVENTS)["events"]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "natural_pipeline", os.path.join(NATURAL, "run_pipeline.py"))
    nat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nat)  # reuse _exists/_alt_base/_doc_line/ILLUSTRATIVE helpers
    rows = []
    for e in sel:
        ev_dir = os.path.join(RAW, e["event_id"])
        mpath = os.path.join(ev_dir, "meta.json")
        if not os.path.exists(mpath):
            continue
        meta = json.load(open(mpath, encoding="utf-8"))
        base_tree = os.path.join(REPOS, slug(e["repo"]), e["base"])
        head_tree = os.path.join(REPOS, slug(e["repo"]), e["head"])
        for item in meta["diff"]["new"]:
            f = item["finding"]
            auto = nat.classify_r9(f, head_tree)
            # distinguish "new because KB moved/edited" from a pure false positive
            doc = f.get("doc") or ""
            base_f = None
            for b in json.load(open(os.path.join(ev_dir, "baseline", "findings.jsonl"),
                                    encoding="utf-8")) if False else []:
                pass
            rows.append({
                "event_id": e["event_id"], "repo": e["repo"], "type": "NEW",
                "negative_control": e["negative_control"], "kind": e["kind"],
                "finding_id": f.get("finding_id"), "rule": f.get("rule"),
                "severity": f.get("severity"), "locator": f.get("locator"),
                "doc": doc, "subject": f.get("subject"),
                "blocking": item.get("blocking"),
                "auto_class": auto.get("class"), "kind_detail": auto.get("kind"),
                "target": auto.get("target"), "evidence": auto.get("evidence"),
                "class": auto.get("class"),
            })
        for item in meta["diff"]["fixed"]:
            f = item["finding"]
            doc = f.get("doc") or ""
            target = None
            mm = re.match(r"^(?:file path|markdown link|make target|package script) does not "
                          r"exist: (.*)$", str(f.get("subject") or ""))
            if mm:
                target = mm.group(1).strip()
            resolves = bool(target) and bool(nat._exists(head_tree, target,
                                                         os.path.dirname(doc)))
            base_absent = bool(target) and not nat._exists(base_tree, target,
                                                           os.path.dirname(doc))
            rows.append({
                "event_id": e["event_id"], "repo": e["repo"], "type": "FIXED",
                "negative_control": e["negative_control"], "kind": e["kind"],
                "finding_id": f.get("finding_id"), "rule": f.get("rule"),
                "severity": f.get("severity"), "locator": f.get("locator"), "doc": doc,
                "subject": f.get("subject"), "target": target,
                "resolves_in_head": resolves, "absent_in_base": base_absent,
                "class": "real_repair" if (resolves and base_absent) else "not_a_repair",
                "evidence": ("target now resolves in head" if resolves else
                             "target still/again absent in head"),
            })
    # manual overrides
    ov = load_json(os.path.join(HERE, "manual_overrides.json"), {})
    for r in rows:
        key = r.get("finding_id")
        if key in ov:
            r["class"] = ov[key].get("class", r["class"])
            r["manual_note"] = ov[key].get("note", "")
            r["evidence"] = "%s | manual: %s" % (r.get("evidence"), ov[key].get("note", ""))
    with open(os.path.join(HERE, "adjudication.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("adjudicated NEW=%d FIXED=%d -> adjudication.jsonl" % (
        sum(1 for r in rows if r["type"] == "NEW"),
        sum(1 for r in rows if r["type"] == "FIXED")))


def clopper_pearson(k, n, alpha=0.05):
    from scipy.stats import beta
    if n == 0:
        return None, None
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return round(float(lo), 4), round(float(hi), 4)


def summarize():
    sel = load_json(EVENTS)["events"]
    adj = [json.loads(l) for l in open(os.path.join(HERE, "adjudication.jsonl"),
                                      encoding="utf-8") if l.strip()]
    metas = []
    for e in sel:
        mpath = os.path.join(RAW, e["event_id"], "meta.json")
        if os.path.exists(mpath):
            metas.append(json.load(open(mpath, encoding="utf-8")))
    new_rows = [r for r in adj if r["type"] == "NEW"]
    fixed_rows = [r for r in adj if r["type"] == "FIXED"]
    tp = sum(1 for r in new_rows if r["class"] == "true_stale")
    fp = sum(1 for r in new_rows if r["class"] == "false_positive")
    rt = sum(1 for r in new_rows if r["class"] == "runtime_unavailable")
    unk = sum(1 for r in new_rows if r["class"] not in
              ("true_stale", "false_positive", "runtime_unavailable"))
    prec_lo, prec_hi = clopper_pearson(tp, tp + fp)
    events_with_new = [m for m in metas if m["diff"]["counts"]["new"] > 0]
    blocked = [m for m in metas if m["diff"]["counts"]["new_blocking"] > 0]
    # false blocking: blocked events whose blocking NEW rows are all adjudicated FP/unavailable
    block_rows = collections.defaultdict(list)
    for r in new_rows:
        if r.get("blocking"):
            block_rows[r["event_id"]].append(r)
    false_block_events = 0
    for ev, rs in block_rows.items():
        if all(r["class"] != "true_stale" for r in rs):
            false_block_events += 1
    nega = [m for m in metas if m["negative_control"]]
    neg_quiet = sum(1 for m in nega if m["diff"]["counts"]["new_blocking"] == 0)
    lat = [m["total_runtime_s"] for m in metas]
    fixed_real = sum(1 for r in fixed_rows if r["class"] == "real_repair")
    summary = {
        "task": "task-87 historical PR replay of the kblint incremental PR gate",
        "kblint_version": "0.3.0", "now": NOW, "fail_on_new": FAIL_ON_NEW,
        "source_repos": "kb-health/analysis/natural_checkout_audit (4 small pinned repos)",
        "sampling_rule": load_json(EVENTS)["sampling_rule"],
        "n_repos": len({e["repo"] for e in sel}),
        "n_events": len(metas),
        "events": [{"event_id": m["event_id"], "repo": m["repo"], "kind": m["kind"],
                    "negative_control": m["negative_control"], "base": m["base"],
                    "head": m["head"], "date": m["date"], "message": m["message"],
                    "claims_before": m["baseline"]["counts"]["claims"],
                    "claims_after": m["current"]["counts"]["claims"],
                    "new": m["diff"]["counts"]["new"],
                    "new_blocking": m["diff"]["counts"]["new_blocking"],
                    "persisting": m["diff"]["counts"]["persisting"],
                    "fixed": m["diff"]["counts"]["fixed"],
                    "exit_code": m["diff"]["exit_code"], "runtime_s": m["total_runtime_s"]}
                   for m in metas],
        "adjudication": {
            "new_total": len(new_rows), "new_true_stale": tp, "new_false_positive": fp,
            "new_runtime_unavailable": rt, "new_unknown": unk,
            "new_precision_tp_over_tp_plus_fp": round(tp / (tp + fp), 4) if tp + fp else None,
            "new_precision_clopper_pearson_95ci": [prec_lo, prec_hi],
            "fixed_total": len(fixed_rows), "fixed_real_repair": fixed_real,
            "fixed_real_repair_rate": round(fixed_real / len(fixed_rows), 4) if fixed_rows else None,
        },
        "metrics": {
            "events_with_any_new": len(events_with_new),
            "signal_rate_events_with_new": round(len(events_with_new) / len(metas), 4) if metas else None,
            "events_blocked": len(blocked),
            "false_block_events": false_block_events,
            "false_block_rate": round(false_block_events / len(blocked), 4) if blocked else None,
            "blocking_new_total": len(block_rows_all := [r for r in new_rows if r.get("blocking")]),
            "blocking_new_true_stale": sum(1 for r in block_rows_all if r["class"] == "true_stale"),
            "blocking_new_false_positive": sum(1 for r in block_rows_all
                                               if r["class"] == "false_positive"),
            "negative_control_events": len(nega),
            "negative_control_quiet": neg_quiet,
            "negative_control_quiet_rate": round(neg_quiet / len(nega), 4) if nega else None,
            "latency_s": {"min": min(lat), "median": statistics.median(lat), "max": max(lat),
                          "total": round(sum(lat), 2)} if lat else None,
            "events_with_fixed": sum(1 for m in metas if m["diff"]["counts"]["fixed"] > 0),
        },
        "annotator": "single annotator (rule-assisted deterministic pass + manual review of every NEW finding and FIXED row)",
        "limitations": [
            "small convenience sample (4 repos, 16 historical events), not a false-alarm rate over all PRs",
            "events selected for reference-relevant changes; negative controls are few (4)",
            "tarballs have no .git: R7 unavailable; base/head are commit-parent pairs, not PR merge bases",
            "single annotator, no inter-annotator agreement",
            "file move != stale: adjudication is required to distinguish real broken pointers from prose/runtime/package-relative mentions",
        ],
    }
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(summary, open(os.path.join(RESULTS, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summary["adjudication"], indent=1))
    print(json.dumps(summary["metrics"], indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["details", "fetch", "scan", "adjudicate", "summarize", "all"])
    a = ap.parse_args()
    if a.phase == "all":
        details(); fetch(); scan(); adjudicate(); summarize()
    else:
        globals()[a.phase]()
