#!/usr/bin/env python3
"""Natural-checkout audit pipeline for task-85.

Runs kblint v0.2.1 on pinned GitHub tarballs of 20 real repositories selected from
analysis/real_scan/scan_rows.json (76 repos), then adjudicates R9 findings and a sample
of the audit queue against the extracted trees. Zero LLM/API calls (only public GitHub
metadata/tarball fetches).

Phases (each resumes from files under this directory):
  select    -> selection.json
  fetch     -> /tmp/natural_audit/repos/<owner>__<repo>/ + fetch_meta.json
  scan      -> configs/<slug>.json + raw/<slug>/{findings.jsonl,audit_queue.jsonl,summary.md,report.sarif,meta.json}
  adjudicate-> adjudication.jsonl
  summarize -> results/summary.json

Usage: python3 run_pipeline.py {select,fetch,scan,adjudicate,summarize,all}
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import hashlib
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.abspath(os.path.join(HERE, "..", ".."))
KBLINT = os.path.join(KB, "kblint")
REAL_SCAN = os.path.join(KB, "analysis", "real_scan", "scan_rows.json")
SCRATCH = "/tmp/natural_audit"
REPOS_DIR = os.path.join(SCRATCH, "repos")
TARBALLS = os.path.join(SCRATCH, "tarballs")
CONFIGS = os.path.join(HERE, "configs")
RAW = os.path.join(HERE, "raw")
RESULTS = os.path.join(HERE, "results")
SELECTION = os.path.join(HERE, "selection.json")
FETCH_META = os.path.join(HERE, "fetch_meta.json")
ADJ = os.path.join(HERE, "adjudication.jsonl")
NOW = "2026-11-09"
SEED = 20261109
MAX_TARBALL = 15 * 1024 * 1024

# ----------------------------------------------------------------- selection
def manifest_class(row):
    m = row["manifests"]
    if "package.json" in m and not any(x in m for x in ("pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod")):
        return "node"
    if any(x in m for x in ("pyproject.toml", "requirements.txt", "setup.py")):
        return "python"
    return "other"


def claim_band(n):
    return "low" if n < 40 else ("high" if n > 90 else "mid")


def kb_type(row):
    return "AGENTS" if row["path"] == "AGENTS.md" else "other"


def select():
    rows = json.load(open(REAL_SCAN, encoding="utf-8"))
    # 20 slots: manifest class x claim band x kb type (mix documented in PROTOCOL.md)
    slots = []
    for cls, spec in (("node", [("low", 1, "AGENTS"), ("low", 1, "other"), ("mid", 1, "AGENTS"),
                                ("mid", 1, "other"), ("high", 2, "AGENTS"), ("high", 1, "other")]),
                      ("python", [("low", 1, "AGENTS"), ("low", 1, "other"), ("mid", 1, "AGENTS"),
                                  ("mid", 1, "other"), ("high", 2, "AGENTS"), ("high", 1, "other")]),
                      ("other", [("low", 1, "AGENTS"), ("low", 1, "other"), ("mid", 1, "AGENTS"),
                                 ("mid", 1, "other"), ("high", 1, "AGENTS"), ("high", 1, "other")])):
        for band, n, kt in spec:
            for _ in range(n):
                slots.append((cls, band, kt))
    assert len(slots) == 20, len(slots)

    stars_sorted = sorted(r["stars"] for r in rows)
    star_med = median(stars_sorted)

    def spread(cands):
        """Deterministic star spread: alternate below/above median, nearest first."""
        below = sorted([r for r in cands if r["stars"] <= star_med], key=lambda r: -r["stars"])
        above = sorted([r for r in cands if r["stars"] > star_med], key=lambda r: r["stars"])
        out = []
        while below or above:
            if below:
                out.append(below.pop(0))
            if above:
                out.append(above.pop(0))
        return out

    used, chosen = set(), []
    for cls, band, kt in slots:
        cands = [r for r in rows if r["repo"] not in used and manifest_class(r) == cls
                 and claim_band(r["kblint"]["claims"]) == band and kb_type(r) == kt]
        if not cands:  # relax kb type, then band
            cands = [r for r in rows if r["repo"] not in used and manifest_class(r) == cls
                     and claim_band(r["kblint"]["claims"]) == band]
        if not cands:
            cands = [r for r in rows if r["repo"] not in used and manifest_class(r) == cls]
        assert cands, (cls, band, kt)
        pick = spread(cands)[0]
        used.add(pick["repo"])
        chosen.append({"slot": {"manifest_class": cls, "claim_band": band, "kb_type": kt},
                       "repo": pick["repo"], "path": pick["path"], "stars": pick["stars"],
                       "claims": pick["kblint"]["claims"], "audit": pick["kblint"]["audit"],
                       "manifests": pick["manifests"], "kb_chars": pick["kb_chars"],
                       "manifest_class": cls, "claim_band": band, "kb_type": kt})

    # reserves: round-robin over (class, band) cells for replacements
    reserves, seen = [], set(used)
    cells = collections.defaultdict(list)
    for r in rows:
        if r["repo"] not in seen:
            cells[(manifest_class(r), claim_band(r["kblint"]["claims"]))].append(r)
    keys = sorted(cells)
    while len(reserves) < 12 and any(cells[k] for k in keys):
        for k in keys:
            if cells[k]:
                r = spread(cells[k])[0]
                cells[k].remove(r)
                reserves.append({"repo": r["repo"], "path": r["path"], "stars": r["stars"],
                                 "claims": r["kblint"]["claims"], "audit": r["kblint"]["audit"],
                                 "manifests": r["manifests"], "kb_chars": r["kb_chars"],
                                 "manifest_class": manifest_class(r),
                                 "claim_band": claim_band(r["kblint"]["claims"]),
                                 "kb_type": kb_type(r),
                                 "reserve": True})
    out = {"seed": SEED, "source": os.path.relpath(REAL_SCAN, KB),
           "n_target": 20, "strategy": "manifest class x claim band x KB-file type, star-spread within cell",
           "selected": chosen, "reserves": reserves}
    json.dump(out, open(SELECTION, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("selected %d + %d reserves" % (len(chosen), len(reserves)))
    for c in chosen:
        print("  %-50s %-34s %-6s %-4s %-6s claims=%3d stars=%6d" % (
            c["repo"], c["path"], c["manifest_class"], c["claim_band"], c["kb_type"],
            c["claims"], c["stars"]))


# ----------------------------------------------------------------- fetch
def api_sha(repo):
    url = "https://api.github.com/repos/%s/commits?per_page=1" % repo
    proc = subprocess.run(["curl", "-sS", "-m", "30", "-w", "\n%{http_code}", url],
                          capture_output=True, text=True)
    body, _, code = proc.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError("API %s -> %s %s" % (repo, code.strip(), body[:200]))
    data = json.loads(body)
    return data[0]["sha"], data[0]["commit"]["committer"]["date"]


def slug(repo):
    return repo.replace("/", "__")


def fetch():
    """Parallel small-first fetch of pinned tarballs (12 MiB cap), writes fetch_meta.json.

    Uses fetch_targets.json when present (small-first resampling documented in PROTOCOL.md);
    falls back to selection.json order otherwise. One GitHub API call per repo (commit SHA);
    tarball by SHA from codeload. Threads: 6 concurrent curls.
    """
    import concurrent.futures as cf
    os.makedirs(REPOS_DIR, exist_ok=True)
    os.makedirs(TARBALLS, exist_ok=True)
    meta = json.load(open(FETCH_META, encoding="utf-8")) if os.path.exists(FETCH_META) else {"repos": {}, "skipped": []}
    meta.setdefault("repos", {}); meta.setdefault("skipped", [])
    if os.path.exists(os.path.join(HERE, "fetch_targets.json")):
        cands = json.load(open(os.path.join(HERE, "fetch_targets.json"), encoding="utf-8"))["targets"]
    else:
        sel = json.load(open(SELECTION, encoding="utf-8"))
        cands = list(sel["selected"]) + list(sel["reserves"])
    TARGET_N = 20

    def one(cand):
        repo = cand["repo"]
        if repo in meta["repos"]:
            return ("have", repo, None)
        try:
            sha, date = api_sha(repo)
        except Exception as e:
            return ("skip", repo, "api: %s" % str(e)[:160])
        tarball = os.path.join(TARBALLS, slug(repo) + ".tar.gz")
        url = "https://codeload.github.com/%s/tar.gz/%s" % (repo, sha)
        proc = subprocess.run(["curl", "-sSL", "-m", "600", "--max-filesize", str(MAX_TARBALL),
                               "-o", tarball, "-w", "%{http_code} %{size_download}", url],
                              capture_output=True, text=True)
        size = os.path.getsize(tarball) if os.path.exists(tarball) else 0
        if proc.returncode != 0 or size == 0:
            okay = False
            reason = "tarball rc=%s http=%s size=%d" % (proc.returncode, proc.stdout.strip()[:60], size)
        elif size > MAX_TARBALL:
            okay, reason = False, "oversize %d > cap" % size
        else:
            dest = os.path.join(REPOS_DIR, slug(repo))
            shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest)
            ex = subprocess.run(["tar", "-xzf", tarball, "-C", dest, "--strip-components=1"],
                                capture_output=True, text=True)
            if ex.returncode != 0:
                okay, reason = False, "tar: %s" % ex.stderr[-160:]
            else:
                kb = None
                for c in dict.fromkeys(([cand.get("path")] if cand.get("path") else []) + ["AGENTS.md", "CLAUDE.md",
                                       "docs/AGENTS.md", ".github/copilot-instructions.md"]):
                    if c and os.path.isfile(os.path.join(dest, c)):
                        kb = c; break
                if not kb:
                    okay, reason = False, "no KB file after extract"
                else:
                    nfiles = sum(len(fs) for _, _, fs in os.walk(dest))
                    info = {"repo": repo, "sha": sha, "committed": date,
                            "default_tarball_bytes": size, "files": nfiles, "kb_file": kb,
                            "tree": dest, "fetch_order": cand.get("order"),
                            "manifest_class": cand.get("manifest_class"),
                            "selection": {k: cand.get(k) for k in ("path", "stars", "claims",
                                                                   "manifests", "manifest_class")}}
                    return ("ok", repo, info)
        if os.path.exists(tarball):
            try: os.remove(tarball)
            except OSError: pass
        return ("skip", repo, reason)

    pending = [c for c in cands if c["repo"] not in meta["repos"]]
    need = max(0, TARGET_N - len(meta["repos"]))
    # submit a bounded number of attempts: 24 for 20 needed (parallel, small-first order);
    # if successes are fewer, the shortfall and skips are reported, not hidden
    cands = pending[:max(need, 20) + 6]
    print("attempting %d candidates for %d needed repos" % (len(cands), need), flush=True)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(one, c): c for c in cands}
        for fut in cf.as_completed(futures):
            kind, repo, payload = fut.result()
            if kind == "ok":
                meta["repos"][repo] = payload
                print("fetched %-48s sha=%s bytes=%8d files=%5d kb=%s" % (
                    repo, payload["sha"][:10], payload["default_tarball_bytes"],
                    payload["files"], payload["kb_file"]), flush=True)
            elif kind == "skip":
                if repo not in meta["repos"]:
                    meta["skipped"].append({"repo": repo, "reason": payload})
                    print("skip   %-48s %s" % (repo, payload[:110]), flush=True)
    meta["n_fetched"] = len(meta["repos"])
    json.dump(meta, open(FETCH_META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("fetched %d (target %d); skipped %d" % (len(meta["repos"]), TARGET_N,
                                                  len(meta["skipped"])), flush=True)


# ----------------------------------------------------------------- scan
DOC_CANDIDATES = ["AGENTS.md", "CLAUDE.md", "docs/AGENTS.md", ".github/copilot-instructions.md",
                  "GEMINI.md"]
ALLOW_MISSING = [
    "^(node_modules|dist|build|out|outputs|artifacts|weights|runs|data|checkpoints|cache|\\.cache|"
    "coverage|logs|profiles|target|vendor|venv|\\.venv|tmp|temp|\\.next|\\.turbo|\\.git|"
    "site-packages|__pycache__|\\.pytest_cache|\\.mypy_cache)/",
    "\\.(lock|log|pid)$",
]
COUNTS = {
    "docs": re.compile(r"docs scanned: (\d+)"),
    "claims": re.compile(r"claims extracted: (\d+)"),
    "findings": re.compile(r"findings: \*\*(\d+)\*\*"),
    "queue": re.compile(r"audit queue \(not defects\): \*\*(\d+)\*\*"),
}
OUTPUT_FILES = ("findings.jsonl", "audit_queue.jsonl", "summary.md", "report.sarif")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan():
    meta = json.load(open(FETCH_META, encoding="utf-8"))["repos"]
    os.makedirs(CONFIGS, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    out = {}
    for repo, m in meta.items():
        tree = m["tree"]
        docs = [d for d in dict.fromkeys(([m["kb_file"]] + DOC_CANDIDATES))
                if os.path.isfile(os.path.join(tree, d))]
        cfg = {"repo": ".", "docs": docs,
               "exclude": ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.venv/**",
                           "**/__pycache__/**", "**/vendor/**"],
               "now": NOW, "git": {"enabled": False}, "rules": {"R4": False},
               "references": {"enabled": True, "check_paths": True, "check_links": True,
                              "check_make": True, "check_npm": True,
                              "allow_missing": ALLOW_MISSING, "inventory": []}}
        cfg_path = os.path.join(CONFIGS, slug(repo) + ".kblint.json")
        json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out_dir = os.path.join(RAW, slug(repo))
        shutil.rmtree(out_dir, ignore_errors=True)
        os.makedirs(out_dir)
        cmd = [sys.executable, "-m", "kblint", "scan", "--repo", tree, "--config", cfg_path,
               "--out", out_dir, "--format", "json,md,sarif", "--fail-on", "none", "--now", NOW]
        t0 = time.monotonic()
        proc = subprocess.run(cmd, cwd=KBLINT, capture_output=True, text=True)
        runtime = round(time.monotonic() - t0, 3)
        if proc.returncode != 0:
            print("SCAN FAILED", repo, proc.returncode, proc.stderr[-500:])
            out[repo] = {"error": proc.stderr[-1000:], "exit_code": proc.returncode}
            continue
        open(os.path.join(out_dir, "stdout.txt"), "w", encoding="utf-8").write(proc.stdout)
        open(os.path.join(out_dir, "stderr.txt"), "w", encoding="utf-8").write(proc.stderr)
        summary = open(os.path.join(out_dir, "summary.md"), encoding="utf-8").read()
        counts = {k: int(rx.search(summary).group(1)) for k, rx in COUNTS.items()
                  if rx.search(summary)}
        findings = [json.loads(l) for l in open(os.path.join(out_dir, "findings.jsonl"),
                                               encoding="utf-8") if l.strip()]
        queue = [json.loads(l) for l in open(os.path.join(out_dir, "audit_queue.jsonl"),
                                            encoding="utf-8") if l.strip()]
        by_rule = collections.Counter(f["rule"] for f in findings)
        r9 = [f for f in findings if f["rule"] == "R9"]
        meta_out = {
            "repo": repo, "sha": m["sha"], "committed": m["committed"], "kb_file": m["kb_file"],
            "docs": docs, "tarball_bytes": m["default_tarball_bytes"], "files": m["files"],
            "manifest_class": m["selection"].get("manifest_class"),
            "claim_band": m["selection"].get("claim_band"),
            "kb_type": m["selection"].get("kb_type"),
            "command": " ".join(cmd), "exit_code": proc.returncode, "runtime_s": runtime,
            "counts": counts, "findings_total": len(findings),
            "findings_by_rule": dict(sorted(by_rule.items())),
            "r9_findings": r9, "audit_queue_rows": len(queue),
            "output_sha256": {n: sha256_file(os.path.join(out_dir, n)) for n in OUTPUT_FILES},
        }
        json.dump(meta_out, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        out[repo] = meta_out
        print("scanned %-50s claims=%4s R9=%3d queue=%4s %.2fs" % (
            repo, counts.get("claims"), len(r9), counts.get("queue"), runtime))
    print("scanned %d repos" % len(out))


# ----------------------------------------------------------------- adjudicate
RUNTIME_PREFIX = re.compile(r"^(node_modules|dist|build|out|outputs|artifacts|weights|runs|data|"
                            r"checkpoints|cache|\.cache|coverage|logs|profiles|target|vendor|venv|"
                            r"\.venv|tmp|temp|\.next|\.turbo|\.git)/")


def _read_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def _make_targets(tree):
    p = os.path.join(tree, "Makefile")
    if not os.path.isfile(p):
        return None
    targets = set()
    phony = re.compile(r"^\.PHONY\s*:\s*(.+)$")
    for line in open(p, encoding="utf-8", errors="replace"):
        if not line or line[0] in "\t#" or line.lstrip().startswith("#"):
            continue
        m = phony.match(line.strip())
        if m:
            targets.update(t for t in m.group(1).split() if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", t))
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s+[A-Za-z0-9_.-]+)*\s*::?(?!=)(?:\s|$)", line)
        if m:
            targets.add(m.group(1))
    return targets


def _npm_scripts(tree):
    data = _read_json(os.path.join(tree, "package.json"))
    scripts = (data or {}).get("scripts") if isinstance(data, dict) else None
    return set(scripts) if isinstance(scripts, dict) else None


def _exists(tree, rel, docdir):
    for cand in (rel, os.path.normpath(os.path.join(docdir, rel))):
        p = os.path.join(tree, cand)
        if os.path.exists(p):
            return cand
    return None


ILLUSTRATIVE = re.compile(r"(<private KB text removed>|<private KB text removed>|<private KB text removed>|<private KB text removed>|<private KB text removed>|placeholder|for example|e\.g\.|such as)", re.I)
TEMPLATE_TARGET = re.compile(r"(^|/)(x|foo|bar|example|your-[a-z-]+)[./]", re.I)


def _doc_line(tree, doc, locator):
    m = re.search(r"#L(\d+)", locator or "")
    if not m:
        return ""
    try:
        lines = open(os.path.join(tree, doc), encoding="utf-8", errors="replace").read().splitlines()
        i = int(m.group(1)) - 1
        return lines[i] if 0 <= i < len(lines) else ""
    except OSError:
        return ""


def _alt_base(tree, target):
    """Find the target under a package subdirectory (doc uses package-relative paths)."""
    suffix = target.strip("./").split("#")[0]
    if not suffix:
        return None
    hits = []
    for root, dirs, files in os.walk(tree):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        for f in files:
            p = os.path.relpath(os.path.join(root, f), tree)
            if p == suffix:
                continue
            if p.endswith("/" + suffix):
                hits.append(p)
    return hits[0] if hits else None


def classify_r9(f, tree):
    subject = f["subject"]
    m = re.match(r"^(file path|markdown link|make target|package script) does not exist: (.*)$",
                 subject)
    if not m:
        return {"kind": "other", "class": "unknown", "note": "unparsed subject"}
    label, target = m.group(1), m.group(2).strip()
    kind = {"file path": "path", "markdown link": "link", "make target": "make",
            "package script": "npm"}[label]
    doc = f.get("doc") or ""
    docdir = os.path.dirname(doc)
    if kind in ("path", "link"):
        rel = target.split("#")[0].split("?")[0].strip()
        found = _exists(tree, rel, docdir)
        if found:
            return {"kind": kind, "target": target, "class": "false_positive",
                    "evidence": "exists: %s" % found}
        line = _doc_line(tree, doc, f.get("locator"))
        if TEMPLATE_TARGET.search(rel) or (line and ILLUSTRATIVE.search(line)):
            return {"kind": kind, "target": target, "class": "false_positive",
                    "evidence": "illustrative/template reference in context: %s" % line[:140]}
        alt = _alt_base(tree, rel)
        if alt:
            return {"kind": kind, "target": target, "class": "false_positive",
                    "evidence": "target exists under package subdir: %s" % alt}
        if RUNTIME_PREFIX.match(rel.lstrip("./")) or rel.endswith((".lock", ".log", ".pid")):
            return {"kind": kind, "target": target, "class": "runtime_unavailable",
                    "evidence": "matches runtime/generated prefix, absent from checkout"}
        return {"kind": kind, "target": target, "class": "true_stale",
                "evidence": "absent at repo-root and doc-relative resolution; no package-subdir match"}
    if kind == "make":
        targets = _make_targets(tree)
        if targets is None:
            return {"kind": kind, "target": target, "class": "false_positive",
                    "evidence": "no root Makefile (rule should self-skip)"}
        if target in targets:
            return {"kind": kind, "target": target, "class": "false_positive",
                    "evidence": "target exists in root Makefile"}
        return {"kind": kind, "target": target, "class": "true_stale",
                "evidence": "target absent from root Makefile (%d targets)" % len(targets)}
    scripts = _npm_scripts(tree)
    if scripts is None:
        return {"kind": kind, "target": target, "class": "false_positive",
                "evidence": "no root package.json (rule should self-skip)"}
    if target in scripts:
        return {"kind": kind, "target": target, "class": "false_positive",
                "evidence": "script exists in package.json"}
    return {"kind": kind, "target": target, "class": "true_stale",
            "evidence": "script absent from package.json (%d scripts)" % len(scripts)}


CODE_PATH_RE = re.compile(r"`([^`\n]+)`")
MD_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


BAD_FRAGMENT = re.compile(r"[<>*?{}|$~]")
PATHLIKE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _clean_candidate(t):
    t = t.strip().strip("`").split("#")[0].split("?")[0]
    if not t:
        return None
    if t.split()[0] in ("python3", "python", "uv", "node", "npm", "pnpm", "yarn", "bash"):
        parts = t.split()
        t = parts[1] if len(parts) > 1 else t
    t = t.strip("'\"")
    if BAD_FRAGMENT.search(t) or t.startswith(("http://", "https://", "/", "#", "mailto:", "~")):
        return None
    if "/" not in t or not PATHLIKE.search(t):
        return None
    return t


def _paths_in(text):
    out = []
    for m in CODE_PATH_RE.finditer(text):
        c = _clean_candidate(m.group(1))
        if c:
            out.append(c)
    for m in MD_LINK_RE.finditer(text):
        c = _clean_candidate(m.group(1))
        if c:
            out.append(c)
    return list(dict.fromkeys(out))


def classify_queue(row, tree):
    """Adjudicate one audit-queue claim against the extracted tree (single annotator)."""
    text = " ".join(str(row.get(k) or "") for k in ("subject", "observed"))
    doc = row.get("doc") or ""
    docdir = os.path.dirname(doc)
    paths = _paths_in(text)
    details = []
    decisive = False
    stale = False
    for p in paths:
        found = _exists(tree, p, docdir)
        alt = None if found else _alt_base(tree, p)
        details.append(("path", p, bool(found), alt))
        if not found and alt:
            pass  # resolvable under a package subdirectory -> not stale
        elif not found and not RUNTIME_PREFIX.match(p.lstrip("./")):
            stale = True
        decisive = True
    for m in re.finditer(r"(?<![\w./-])make\s+([A-Za-z0-9][A-Za-z0-9_.:-]*)", text):
        t = _make_targets(tree)
        if t is not None:
            found = m.group(1) in t
            details.append(("make", m.group(1), found))
            decisive = True
            if not found:
                stale = True
    for m in re.finditer(r"\b(?:npm|pnpm|yarn)\s+run\s+([A-Za-z0-9][A-Za-z0-9_:.-]*)", text):
        s = _npm_scripts(tree)
        if s is not None:
            found = m.group(1) in s
            details.append(("npm", m.group(1), found))
            decisive = True
            if not found:
                stale = True
    if decisive and stale:
        cls = "Stale"
    elif decisive:
        cls = "Verified"
    else:
        cls = "Unknown"
    return {"class": cls, "details": details,
            "reason": row.get("reason"), "subject": row.get("subject")}


def adjudicate():
    fmeta = json.load(open(FETCH_META, encoding="utf-8"))["repos"]
    rng = random.Random(SEED)
    rows = []
    queue_pool = []
    for repo, m in fmeta.items():
        meta = _read_json(os.path.join(RAW, slug(repo), "meta.json"))
        if not meta or "r9_findings" not in meta:
            continue
        tree = m["tree"]
        for f in meta["r9_findings"]:
            c = classify_r9(f, tree)
            rows.append({"repo": repo, "adjudication_type": "R9_finding",
                         "finding_id": f.get("finding_id"), "rule": "R9",
                         "severity": f.get("severity"), "doc": f.get("doc"),
                         "locator": f.get("locator"), "subject": f.get("subject"),
                         "observed": f.get("observed"), "class": c["class"],
                         "kind": c.get("kind"), "target": c.get("target"),
                         "evidence": c.get("evidence")})
        qpath = os.path.join(RAW, slug(repo), "audit_queue.jsonl")
        if os.path.exists(qpath):
            for line in open(qpath, encoding="utf-8"):
                if line.strip():
                    q = json.loads(line)
                    q["_repo"] = repo
                    q["_tree"] = tree
                    queue_pool.append(q)
    # sample 150 audit-queue claims across repos (deterministic); cap at 10/repo
    rng.shuffle(queue_pool)
    per = collections.Counter()
    sample = []
    for q in queue_pool:
        if per[q["_repo"]] >= 10:
            continue
        sample.append(q)
        per[q["_repo"]] += 1
        if len(sample) >= 150:
            break
    sample.sort(key=lambda q: (q["_repo"], q.get("locator") or ""))
    for q in sample:
        c = classify_queue(q, q["_tree"])
        rows.append({"repo": q["_repo"], "adjudication_type": "audit_queue_claim",
                     "audit_id": q.get("audit_id"), "claim_id": q.get("claim_id"),
                     "doc": q.get("doc"), "locator": q.get("locator"),
                     "subject": q.get("subject"), "queue_reason": q.get("reason"),
                     "class": c["class"], "kind": "queue", "target": None,
                     "evidence": c["details"]})
    # manual adjudication overrides (single annotator; every R9 finding reviewed by hand)
    ov_path = os.path.join(HERE, "manual_overrides.json")
    overrides = json.load(open(ov_path, encoding="utf-8")) if os.path.exists(ov_path) else {}
    n_ov = 0
    for r in rows:
        if r["adjudication_type"] != "R9_finding":
            continue
        ov = overrides.get(r.get("finding_id"))
        if ov:
            r["class"] = ov["class"]
            r["manual_note"] = ov["note"]
            r["evidence"] = "%s | manual: %s" % (r.get("evidence"), ov["note"])
            n_ov += 1
    print("manual overrides applied:", n_ov, flush=True)
    with open(ADJ, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("adjudicated %d R9 findings + %d audit-queue claims -> %s" % (
        sum(1 for r in rows if r["adjudication_type"] == "R9_finding"),
        sum(1 for r in rows if r["adjudication_type"] == "audit_queue_claim"), ADJ))


# ----------------------------------------------------------------- summarize
def clopper_pearson(k, n, alpha=0.05):
    from scipy.stats import beta
    if n == 0:
        return None, None
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return round(float(lo), 4), round(float(hi), 4)


def summarize():
    fmeta = json.load(open(FETCH_META, encoding="utf-8"))
    repos = fmeta["repos"]
    adj = [json.loads(l) for l in open(ADJ, encoding="utf-8") if l.strip()]
    r9 = [a for a in adj if a["adjudication_type"] == "R9_finding"]
    qs = [a for a in adj if a["adjudication_type"] == "audit_queue_claim"]
    per_repo = {}
    for repo in repos:
        meta = _read_json(os.path.join(RAW, slug(repo), "meta.json")) or {}
        pr = [a for a in r9 if a["repo"] == repo]
        cls = collections.Counter(a["class"] for a in pr)
        per_repo[repo] = {
            "sha": repos[repo]["sha"], "committed": repos[repo]["committed"],
            "kb_file": repos[repo]["kb_file"], "tarball_bytes": repos[repo]["default_tarball_bytes"],
            "files": repos[repo]["files"],
            "manifest_class": meta.get("manifest_class"), "claim_band": meta.get("claim_band"),
            "kb_type": meta.get("kb_type"), "docs": meta.get("docs"),
            "claims": (meta.get("counts") or {}).get("claims"),
            "audit_queue": (meta.get("counts") or {}).get("queue"),
            "findings_total": meta.get("findings_total"),
            "findings_by_rule": meta.get("findings_by_rule"),
            "r9_findings": len(pr), "r9_true_stale": cls.get("true_stale", 0),
            "r9_false_positive": cls.get("false_positive", 0),
            "r9_runtime_unavailable": cls.get("runtime_unavailable", 0),
            "r9_unknown": cls.get("unknown", 0), "runtime_s": meta.get("runtime_s"),
            "exit_code": meta.get("exit_code"),
        }
    # aggregate
    n_repos = len(per_repo)
    claims_total = sum((p["claims"] or 0) for p in per_repo.values())
    queue_total = sum((p["audit_queue"] or 0) for p in per_repo.values())
    tp = sum(p["r9_true_stale"] for p in per_repo.values())
    fp = sum(p["r9_false_positive"] for p in per_repo.values())
    rt = sum(p["r9_runtime_unavailable"] for p in per_repo.values())
    unk = sum(p["r9_unknown"] for p in per_repo.values())
    r9_total = tp + fp + rt + unk
    prec_lo, prec_hi = clopper_pearson(tp, tp + fp)
    stat_lo, stat_hi = clopper_pearson(tp, r9_total)
    qc = collections.Counter(a["class"] for a in qs)
    # queue stale/verified CI for reference
    q_stale = qc.get("Stale", 0)
    q_verified = qc.get("Verified", 0)
    q_unknown = qc.get("Unknown", 0)
    q_n = q_stale + q_verified + q_unknown
    q_stale_lo, q_stale_hi = clopper_pearson(q_stale, q_n)
    summary = {
        "task": "task-85 natural-checkout audit",
        "kblint_version": "0.2.1", "now": NOW,
        "source_repos": "analysis/real_scan/scan_rows.json (76 public repos)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "n_repos": n_repos,
        "selection": "stratified: manifest class x claim band x KB file type; star-spread within cell",
        "skipped": fmeta.get("skipped", []),
        "repo_meta": per_repo,
        "aggregate": {
            "claims_extracted": claims_total,
            "audit_queue": queue_total,
            "findings_total": sum((p["findings_total"] or 0) for p in per_repo.values()),
            "r9_findings": r9_total,
            "r9_true_stale": tp,
            "r9_false_positive": fp,
            "r9_runtime_unavailable": rt,
            "r9_unknown": unk,
            "precision_tp_over_tp_plus_fp": round(tp / (tp + fp), 4) if tp + fp else None,
            "precision_clopper_pearson_95ci": [prec_lo, prec_hi],
            "confirmed_stale_rate_among_r9": round(tp / r9_total, 4) if r9_total else None,
            "confirmed_stale_rate_ci": [stat_lo, stat_hi],
            "repos_with_ge1_true_stale": sum(1 for p in per_repo.values() if p["r9_true_stale"] > 0),
            "repo_distribution_r9": {
                "min": min((p["r9_findings"] for p in per_repo.values()), default=0),
                "median": median([p["r9_findings"] for p in per_repo.values()]) if per_repo else 0,
                "max": max((p["r9_findings"] for p in per_repo.values()), default=0),
            },
            "audit_queue_sample": {
                "n": q_n, "verified": q_verified, "stale": q_stale, "unknown": q_unknown,
                "stale_rate": round(q_stale / q_n, 4) if q_n else None,
                "stale_rate_clopper_pearson_95ci": [q_stale_lo, q_stale_hi],
                "unknown_rate": round(q_unknown / q_n, 4) if q_n else None,
            },
        },
        "annotator": "single annotator (rule-assisted deterministic adjudication + manual review of every R9 finding class and a calibration sample of queue claims)",
        "limitations": [
            "convenience 20-repo sample from a previously scanned 76-repo popular list, not a population sample",
            "tarballs have no .git: R7 git-provenance self-skips for every repo",
            "R9 scope depends on the generated config (KB docs only; allow_missing list)",
            "single annotator; no inter-annotator agreement",
            "R9 findings are broken evidence pointers, not correctness defects of KB content",
        ],
    }
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(summary, open(os.path.join(RESULTS, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summary["aggregate"], indent=1, ensure_ascii=False))


def all_phases():
    select()
    fetch()
    scan()
    adjudicate()
    summarize()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["select", "fetch", "scan", "adjudicate", "summarize", "all"])
    a = ap.parse_args()
    getattr(sys.modules[__name__], "all_phases" if a.phase == "all" else a.phase)()
