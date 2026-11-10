#!/usr/bin/env python3
"""Head-to-head: conventional document checkers vs kblint's reference rule (R9) and full rule set.

Two offline comparisons (no API calls):
  A. Real repositories: the 16 pinned checkouts / 28 adjudicated R9 findings from
     analysis/natural_checkout_audit. How much of kblint's R9 output does a markdown link
     checker, a path-token existence script, or an extended existence script reproduce?
  B. Controlled mutations: the 25 positive injected breakages from analysis/kblint_mutation.
     Which injected breakages can conventional checkers see at all (comparing the positive
     fixture with its negative-control sibling)?

The baselines are deliberately small and literal (the "30-line script" argument):
  - link : markdown inline/auto links -> local target existence
  - path : backticked path tokens + prose tokens that carry a file extension -> existence
  - ext  : path + link + make targets and npm/pnpm/yarn scripts -> existence (maximal
           conventional existence checking; still no claim/evidence model)
"""
from __future__ import annotations
import json, re, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parent
NA = KB / "natural_checkout_audit"
MUT = KB / "kblint_mutation"
OUT = HERE / "results"

# ---------------------------------------------------------------- helpers
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AUTO_RE = re.compile(r"<((?:https?://|mailto:)[^>\s]+|[\w./-]+\.\w+)>")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
PROSE_PATH_RE = re.compile(r"(?<![\w/$.`-])((?:[\w.-]+/)+[\w.-]+)")
PROSE_FILE_RE = re.compile(
    r"(?<![\w/$.`-])([\w.-]+\.(?:md|py|js|mjs|cjs|ts|tsx|jsx|json|ya?ml|toml|sh|txt|cfg|ini|go|rs|java|lock))"
    r"(?![\w/-])")
MAKE_RE = re.compile(r"(?<![\w-])make\s+([A-Za-z0-9_.:-]+)")
NPM_RE = re.compile(r"(?<![\w-])(?:npm|pnpm|yarn)\s+run\s+([A-Za-z0-9_.:-]+)")
SKIP_TOKENS = re.compile(r"[*?\[\]{}<>^$|`'\"@]")


def norm_target(t: str) -> str:
    t = t.strip().strip("<>`'\"")
    t = t.split("#")[0].split("?")[0]
    t = t.replace("\\", "/")
    while t.startswith("./"):
        t = t[2:]
    t = t.lstrip("/")
    return t


def doc_join(root: Path, doc: str, target: str) -> list[Path]:
    t = target
    if t.startswith("/"):
        t = t.lstrip("/")
        return [root / t]
    return [root / t, (root / doc).parent / t]


def missing(root: Path, doc: str, target: str) -> bool:
    if not target:
        return False
    try:
        return not any(p.exists() for p in doc_join(root, doc, target))
    except OSError:
        return True


def link_findings(root: Path, doc: str, text: str) -> set[str]:
    out = set()
    cands = [m.group(1) for m in LINK_RE.finditer(text)]
    cands += [m.group(1) for m in AUTO_RE.finditer(text)]
    for c in cands:
        c = c.strip()
        if not c or c.startswith(("#", "http://", "https://", "mailto:", "tel:", "ftp:")):
            continue
        t = norm_target(c)
        if not t or SKIP_TOKENS.search(t):
            continue
        if missing(root, doc, t):
            out.add(t)
    return out


PATHISH = re.compile(r"[\w.-]+/[\w./-]+|[\w.-]+\.(?:md|py|js|mjs|cjs|ts|tsx|jsx|json|ya?ml|toml|sh|txt|cfg|ini|go|rs|java|lock)")


def path_findings(root: Path, doc: str, text: str) -> set[str]:
    out = set()
    cands = [m.group(1).strip() for m in BACKTICK_RE.finditer(text)]
    for c in cands:
        if " " in c or not PATHISH.fullmatch(c):
            continue
        t = norm_target(c)
        if not t or SKIP_TOKENS.search(t) or t.startswith(("http://", "https://", "mailto:")):
            continue
        if missing(root, doc, t):
            out.add(t)
    for rx in (PROSE_PATH_RE, PROSE_FILE_RE):
        for m in rx.finditer(text):
            t = norm_target(m.group(1))
            if not t or SKIP_TOKENS.search(t):
                continue
            if missing(root, doc, t):
                out.add(t)
    return out


def make_targets(root: Path) -> set[str]:
    mk = root / "Makefile"
    if not mk.exists():
        return set()
    out = set()
    for line in mk.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([A-Za-z0-9_.%-]+)\s*:(?!=)", line)
        if m and not m.group(1).startswith("."):
            out.add(m.group(1))
    return out


def npm_scripts(root: Path) -> set[str]:
    pkg = root / "package.json"
    if not pkg.exists():
        return set()
    try:
        return set(json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {}))
    except Exception:
        return set()


def ext_findings(root: Path, doc: str, text: str) -> set[str]:
    out = set()
    mts, scripts = make_targets(root), npm_scripts(root)
    for m in MAKE_RE.finditer(text):
        t = m.group(1)
        if mts and t not in mts and not t.startswith("-"):
            out.add("make:" + t)
    for m in NPM_RE.finditer(text):
        t = m.group(1)
        if scripts and t not in scripts:
            out.add("npm:" + t)
    return out


def scan_docs(root: Path, docs: list[str]):
    """Return {method: set of finding ids} where ids are target strings (plus make:/npm:)."""
    res = {"link": set(), "path": set(), "ext": set()}
    for doc in docs:
        p = root / doc
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        res["link"] |= link_findings(root, doc, text)
        res["path"] |= path_findings(root, doc, text)
        res["ext"] |= ext_findings(root, doc, text)
    res["ext"] |= res["path"] | res["link"]
    return res


# ---------------------------------------------------------------- A. real repositories
def part_a():
    repos = json.load(open(NA / "fetch_meta.json"))["repos"]
    adj = [json.loads(l) for l in open(NA / "adjudication.jsonl") if l.strip()]
    r9 = [r for r in adj if r.get("adjudication_type") == "R9_finding"]
    configs = {}
    for f in (NA / "configs").glob("*.kblint.json"):
        cfg = json.load(open(f))
        configs[cfg.get("repo", ".")] = cfg
    rows, t0 = [], time.time()
    for repo, meta in repos.items():
        root = Path(meta["tree"])
        cfg = json.load(open((NA / "configs") / (repo.replace("/", "__") + ".kblint.json")))
        docs = cfg.get("docs") or [meta["kb_file"]]
        per = scan_docs(root, docs)
        find = [r for r in r9 if r["repo"] == repo]
        row = {"repo": repo, "n_r9": len(find), "docs": docs}
        for method in ("link", "path", "ext"):
            row[method] = sorted(per[method])
        rows.append(row)
    runtime = time.time() - t0
    # match findings to the adjudicated R9 findings (same doc + same target)
    match = {m: {"true_stale": 0, "false_positive": 0, "runtime_unavailable": 0,
                 "matched": 0, "extra": 0} for m in ("link", "path", "ext")}
    for row in rows:
        by_repo = [r for r in r9 if r["repo"] == row["repo"]]
        for method in ("link", "path", "ext"):
            got = set(row[method])
            used = set()
            for r in by_repo:
                t = norm_target(r.get("target", ""))
                if r.get("kind") == "link":
                    hit = t in got
                elif r.get("kind") == "path":
                    hit = t in got
                else:
                    hit = t in got
                if hit:
                    match[method][r["class"]] += 1
                    match[method]["matched"] += 1
                    used.add(t)
            match[method]["extra"] = sum(1 for g in got if g not in used)
    kblint = {"findings": len(r9),
              "true_stale": sum(r["class"] == "true_stale" for r in r9),
              "false_positive": sum(r["class"] == "false_positive" for r in r9),
              "runtime_unavailable": sum(r["class"] == "runtime_unavailable" for r in r9),
              "runtime_s": json.load(open(NA / "results/summary.json"))["aggregate"]["scan_runtime_s"]}
    # command references in the same KB docs: existence checkers cannot verify these unless
    # extended (and even then only structurally, not semantically)
    cmd_counts = {"make": 0, "npm": 0}
    for repo, meta in repos.items():
        cfg = json.load(open((NA / "configs") / (repo.replace("/", "__") + ".kblint.json")))
        for doc in (cfg.get("docs") or [meta["kb_file"]]):
            p = Path(meta["tree"]) / doc
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            cmd_counts["make"] += len(MAKE_RE.findall(txt))
            cmd_counts["npm"] += len(NPM_RE.findall(txt))
    summary = {"n_repos": len(rows), "n_r9": len(r9), "kblint": kblint,
               "baselines": match, "baseline_runtime_s": round(runtime, 2),
               "command_refs_in_kb_docs": cmd_counts,
               "note": ("matched = baseline finding equals an adjudicated R9 target; extra = "
                        "baseline findings not in the adjudicated R9 set (not adjudicated).")}
    (OUT / "real_repo_head_to_head.json").write_text(json.dumps(summary, indent=1))
    return summary, rows


# ---------------------------------------------------------------- B. mutations
def part_b():
    cases = [json.loads(l) for l in open(MUT / "results/cases.jsonl")]
    injected = {}
    for l in open(MUT / "results/findings_injected.jsonl"):
        f = json.loads(l)
        injected.setdefault(f["case_id"], []).append(f)
    pos = [c for c in cases if c["mutation"] == "positive"]
    nc = {c["case_id"].replace("-POS-", "-NC-").replace("-POS", "-NC").split("-NC")[0]: c for c in cases
          if c["mutation"] == "negative_control"}
    # robust NC lookup: same prefix before "-POS"
    def nc_for(case):
        prefix = case["case_id"].split("-POS")[0]
        for c in cases:
            if c["mutation"] == "negative_control" and c["case_id"].startswith(prefix + "-NC"):
                return c
        return None
    rows = []
    for c in pos:
        fid = c["case_id"]
        root = MUT / "fixtures" / "repos" / fid
        twin = nc_for(c)
        root_nc = MUT / "fixtures" / "repos" / twin["case_id"] if twin else None
        doc = c["target_doc"]
        def scan(r, d):
            if r is None or not (r / d).exists():
                return {m: set() for m in ("link", "path", "ext")}
            txt = (r / d).read_text(encoding="utf-8", errors="replace")
            return {"link": link_findings(r, d, txt), "path": path_findings(r, d, txt),
                    "ext": ext_findings(r, d, txt) | path_findings(r, d, txt) | link_findings(r, d, txt)}
        a = scan(root, doc)
        b = scan(root_nc, doc)
        new = {m: a[m] - b[m] for m in a}
        # which kblint findings are new in this positive fixture vs its NC sibling?
        new_subj = [f for f in injected.get(fid, []) if f["locator"] not in
                    {g["locator"] for g in injected.get(twin["case_id"], [])}] if twin else injected.get(fid, [])
        targets = []
        for f in injected.get(fid, []):
            m = re.search(r"(?:file path|markdown link|make target|package script) does not exist: (.+)$", f["subject"])
            if m:
                targets.append(("make:" if "make target" in f["subject"] else
                                "npm:" if "package script" in f["subject"] else "", norm_target(m.group(1))))
        det = {m: 0 for m in ("link", "path", "ext")}
        for method in det:
            for prefix, t in targets:
                if method == "ext" and prefix:
                    if prefix + t in new["ext"]:
                        det[method] = 1
                elif not prefix and (t in new[method] or (method == "ext" and t in new["ext"])):
                    det[method] = 1
        rows.append({"case": fid, "rule": c["rule"], "detected": det,
                     "kblint": 1 if c["detected"] else 0, "n_new_kblint_targets": len(targets)})
    agg = {"n_positive": len(pos),
           "kblint_detected": sum(r["kblint"] for r in rows),
           "by_method": {m: sum(r["detected"][m] for r in rows) for m in ("link", "path", "ext")},
           "by_rule_group": {}}
    for r in rows:
        g = "R9" if r["rule"] == "R9" else "other rules (R1-R7)"
        agg["by_rule_group"].setdefault(g, {"n": 0, "link": 0, "path": 0, "ext": 0, "kblint": 0})
        gg = agg["by_rule_group"][g]
        gg["n"] += 1
        for m in ("link", "path", "ext"):
            gg[m] += r["detected"][m]
        gg["kblint"] += r["kblint"]
    (OUT / "mutation_coverage.json").write_text(json.dumps({"cases": rows, "aggregate": agg}, indent=1))
    return agg, rows


if __name__ == "__main__":
    a, _ = part_a()
    b, _ = part_b()
    print(json.dumps(a, indent=1))
    print(json.dumps(b, indent=1))
