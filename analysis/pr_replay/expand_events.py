#!/usr/bin/env python3
"""Expand the PR replay event set to reference-relevant historical commits.

Discovery only (no analysis): uses public atom feeds (pages 1-3) and compare .diff endpoints,
then pre-filters events by (a) KB-file edits and (b) changed/deleted paths that actually appear
in the base KB text (fetched from raw.githubusercontent). The goal is to select 5 events/repo
that have a realistic chance of exercising the incremental gate, plus a docs-only negative control.
"""
import collections, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPOS = {
    "blader/humanizer": {"kb_file": "AGENTS.md"},
    "mattpocock/skills": {"kb_file": "CLAUDE.md"},
    "addyosmani/agent-skills": {"kb_file": "AGENTS.md"},
    "modelcontextprotocol/servers": {"kb_file": "AGENTS.md"},
}
KEYS = re.compile(r"(agents|claude|skill|rule|command|target|script|make|npm|path|move|rename|"
                  r"remove|delete|drop|deprecat|refactor|docs?:|readme|plugin|hook|workflow|"
                  r"version|deps?|bump|upgrade)", re.I)
CACHE = "/tmp/pr_replay/expand_cache.json"
KBTEXT = "/tmp/pr_replay/kbtext_cache.json"


def curl(url, timeout=60):
    p = subprocess.run(["curl", "-sSL", "--compressed", "-m", str(timeout),
                        "-w", "\n%{http_code}", url], capture_output=True, text=True)
    body, _, code = p.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError("%s -> %s" % (url, code.strip()))
    return body


def atom(repo, page):
    return curl("https://github.com/%s/commits/main.atom?page=%d" % (repo, page))


def parse_atom(xml):
    out = []
    for block in xml.split("<entry>")[1:]:
        m = re.search(r"<id>tag:github.com,2008:Grit::Commit/([0-9a-f]{40})</id>", block)
        t = re.search(r"<title>\s*(.*?)\s*</title>", block, re.S)
        u = re.search(r"<updated>(.*?)</updated>", block)
        if m:
            out.append({"sha": m.group(1), "title": re.sub(r"\s+", " ", t.group(1)) if t else "",
                        "updated": u.group(1) if u else ""})
    return out


def compare(repo, base, head):
    txt = curl("https://github.com/%s/compare/%s...%s.diff" % (repo, base, head))
    files, cur = [], None
    for line in txt.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)$", line)
        if m:
            cur = {"filename": m.group(2), "previous": m.group(1), "status": "modified"}
            files.append(cur); continue
        if cur is None: continue
        if line.startswith("new file mode"): cur["status"] = "added"
        elif line.startswith("deleted file mode"): cur["status"] = "removed"
        elif line.startswith("rename from "):
            cur["previous"] = line[len("rename from "):].strip(); cur["status"] = "renamed"
    return files


def kb_text(repo, ref, kb_file):
    cache = json.load(open(KBTEXT)) if os.path.exists(KBTEXT) else {}
    key = "%s|%s|%s" % (repo, ref, kb_file)
    if key in cache:
        return cache[key]
    try:
        t = curl("https://raw.githubusercontent.com/%s/%s/%s" % (repo, ref, kb_file))
    except RuntimeError:
        t = ""
    cache[key] = t
    json.dump(cache, open(KBTEXT, "w", encoding="utf-8"), ensure_ascii=False)
    time.sleep(0.15)
    return t


def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    selected = []
    for repo, spec in REPOS.items():
        entries = []
        for page in (1, 2, 3):
            try:
                entries += parse_atom(atom(repo, page))
            except RuntimeError as e:
                print("atom fail", repo, page, e)
            time.sleep(0.2)
        # dedupe by sha keeping order
        seen, uniq = set(), []
        for e in entries:
            if e["sha"] not in seen:
                seen.add(e["sha"]); uniq.append(e)
        print("%s: %d commits over 3 pages" % (repo, len(uniq)))
        pairs = [(uniq[i + 1]["sha"], uniq[i]["sha"], uniq[i]["title"])
                 for i in range(len(uniq) - 1)]
        cand = []
        for base, head, title in pairs:
            key = "%s|%s|%s" % (repo, base[:12], head[:12])
            if key not in cache:
                if not KEYS.search(title or "") and len(cand) > 18:
                    continue
                try:
                    cache[key] = compare(repo, base, head)
                except RuntimeError as ex:
                    print("  compare fail", key, str(ex)[:70]); continue
                time.sleep(0.2)
            files = cache[key]
            if not files:
                continue
            kb_edit = any(f["filename"] == spec["kb_file"] or f["filename"].endswith("/" + spec["kb_file"])
                          for f in files)
            build = any(f["filename"].split("/")[-1] in
                        ("Makefile", "package.json", "pyproject.toml", "requirements.txt",
                         "Cargo.toml", "go.mod") for f in files)
            tr = [f for f in files if f["status"] in ("renamed", "removed")]
            docs_only = all(f["filename"].endswith((".md", ".txt", ".rst")) and
                            f["filename"] != spec["kb_file"] for f in files)
            cand.append({"repo": repo, "kb_file": spec["kb_file"], "base": base, "head": head,
                         "title": title, "files": files, "kb_edit": kb_edit, "build": build,
                         "renamed": tr, "docs_only": docs_only})
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # score: KB edit; deleted/renamed path appearing in base KB text; build change
        for c in cand:
            text = kb_text(repo, c["base"], c["kb_file"]) if (c["renamed"] or c["kb_edit"]) else ""
            hits = []
            for f in c["renamed"] + [x for x in c["files"] if x["filename"] == c["kb_file"]]:
                for p in (f["previous"], f["filename"]):
                    if p and p in text:
                        hits.append(p)
            c["kb_hits"] = sorted(set(hits))
            c["score"] = (3 if c["kb_edit"] else 0) + (3 if c["kb_hits"] else 0) + \
                         (1 if c["build"] else 0) + (1 if c["renamed"] else 0)
        cand.sort(key=lambda c: (-c["score"], c["head"]))
        picked = []
        kbeds = [c for c in cand if c["kb_edit"]]
        moved = [c for c in cand if c["kb_hits"] and not c["kb_edit"]]
        others = [c for c in cand if not c["kb_edit"] and not c["kb_hits"] and not c["docs_only"]]
        negs = [c for c in cand if c["docs_only"]]
        for group, n in ((kbeds, 2), (moved, 2), (others, 1), (negs, 1)):
            for c in group[:n]:
                if len(picked) < 5 and c not in picked:
                    picked.append(c)
        for c in cand:
            if len(picked) >= 5: break
            if c not in picked: picked.append(c)
        print("  picked:", [(p["head"][:10], p["score"], p["title"][:40],
                            "kb_edit" if p["kb_edit"] else ("kb_hit" if p["kb_hits"] else
                             ("docs" if p["docs_only"] else "other"))) for p in picked[:5]])
        selected += picked[:5]
    events = []
    for c in selected:
        events.append({"repo": c["repo"], "kb_file": c["kb_file"], "base": c["base"],
                       "head": c["head"], "title": c["title"], "files": c["files"],
                       "kind": ("kb_edit" if c["kb_edit"] else
                                "kb_referenced_move" if c["kb_hits"] else
                                "docs_only" if c["docs_only"] else
                                "build_change" if c["build"] else "code_path_change"),
                       "kb_hits": c["kb_hits"], "negative_control": c["docs_only"]})
        events[-1]["event_id"] = "%s@%s" % (c["repo"].replace("/", "__"), c["head"][:10])
    json.dump({"now": "2026-11-09", "fail_on_new": "medium", "events": events,
               "sampling_rule": ("recent default-branch commit events (atom pages 1-3) on 4 small "
                                 "natural-audit repos; per repo up to 5 events prioritized by "
                                 "KB-file edit / deleted-or-renamed path that appears in the base KB "
                                 "text / build change, plus one docs-only negative control"),
               "discovery": "public GitHub atom feeds + compare .diff + raw.githubusercontent KB text "
                            "(no REST API quota used); SHAs are full pinned commit SHAs"},
              open(os.path.join(HERE, "events.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("total events:", len(events))


if __name__ == "__main__":
    main()
