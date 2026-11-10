#!/usr/bin/env python3
"""Find historical events that likely exercise the gate: KB-referenced path removals/renames.

Targets two natural-audit repos whose HEAD KBs are known to contain stale pointers:
  avelino/awesome-go        - KB references .github/scripts/check-quality.js (now a Go dir)
  mvanhorn/last30days-skill - root KB references scripts/tests/docs paths that moved under skills/last30days/
Uses public atom feeds + compare .diff endpoints (no REST API quota).
"""
import json, os, re, subprocess, sys, time
HERE=os.path.dirname(os.path.abspath(__file__))
NAT=os.path.join(HERE,"..","natural_checkout_audit")
CACHE="/tmp/pr_replay/signal_cache.json"
REPOS={
 "avelino/awesome-go":{"kb_file":"AGENTS.md","pattern":re.compile(r"check-quality|quality",re.I)},
 "mvanhorn/last30days-skill":{"kb_file":"AGENTS.md","pattern":re.compile(r"last30days|skill|package|restructur|move|layout|script|test",re.I)},
}
def curl(url,t=60):
    p=subprocess.run(["curl","-sSL","--compressed","-m",str(t),"-w","\n%{http_code}",url],capture_output=True,text=True)
    body,_,code=p.stdout.rpartition("\n")
    if code.strip()!="200": raise RuntimeError("%s -> %s"%(url,code.strip()))
    return body
def atom(repo,page): return curl("https://github.com/%s/commits/main.atom?page=%d"%(repo,page))
def parse(xml):
    out=[]
    for b in xml.split("<entry>")[1:]:
        m=re.search(r"<id>tag:github.com,2008:Grit::Commit/([0-9a-f]{40})</id>",b)
        t=re.search(r"<title>\s*(.*?)\s*</title>",b,re.S)
        if m: out.append({"sha":m.group(1),"title":re.sub(r"\s+"," ",t.group(1)) if t else ""})
    return out
def compare(repo,base,head):
    txt=curl("https://github.com/%s/compare/%s...%s.diff"%(repo,base,head))
    files,cur=[],None
    for line in txt.splitlines():
        m=re.match(r"^diff --git a/(\S+) b/(\S+)$",line)
        if m:
            cur={"filename":m.group(2),"previous":m.group(1),"status":"modified"};files.append(cur);continue
        if cur is None: continue
        if line.startswith("new file mode"): cur["status"]="added"
        elif line.startswith("deleted file mode"): cur["status"]="removed"
        elif line.startswith("rename from "): cur["previous"]=line[len("rename from "):].strip();cur["status"]="renamed"
    return files
def main():
    cache=json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    nat=json.load(open(os.path.join(NAT,"fetch_meta.json"),encoding="utf-8"))["repos"]
    out=[]
    for repo,spec in REPOS.items():
        entries=[]
        for page in (1,2,3,4,5,6):
            try: entries+=parse(atom(repo,page))
            except RuntimeError as e: print("atom fail",repo,page,str(e)[:60])
            time.sleep(0.25)
        seen,uniq=set(),[]
        for e in entries:
            if e["sha"] not in seen: seen.add(e["sha"]);uniq.append(e)
        print(repo,"commits:",len(uniq))
        pairs=[(uniq[i+1]["sha"],uniq[i]["sha"],uniq[i]["title"]) for i in range(len(uniq)-1)]
        cands=[]
        for base,head,title in pairs:
            if not spec["pattern"].search(title or ""): continue
            key="%s|%s|%s"%(repo,base[:12],head[:12])
            if key not in cache:
                try: cache[key]=compare(repo,base,head)
                except RuntimeError as ex: print("  compare fail",key,str(ex)[:60]);continue
                time.sleep(0.3)
            files=cache[key]
            if not files: continue
            kb_edit=any(f["filename"]==spec["kb_file"] for f in files)
            moved=[f for f in files if f["status"] in ("renamed","removed")]
            rel=[f for f in files if spec["pattern"].search(f["filename"]) or spec["pattern"].search(f.get("previous") or "")]
            cands.append({"repo":repo,"kb_file":spec["kb_file"],"base":base,"head":head,"title":title,
                          "files":files,"kb_edit":kb_edit,"moved":moved,"relevant":rel})
        # score: relevant removed/renamed; kb edit; moved count
        for c in cands:
            c["score"]= (3 if any(f["status"] in ("removed","renamed") for f in c["relevant"]) else 0) + (2 if c["kb_edit"] else 0) + min(len(c["moved"]),3)
        cands.sort(key=lambda c:(-c["score"],c["head"]))
        print("  candidates:",[(c["head"][:10],c["score"],c["title"][:50],[f["filename"] for f in c["files"]][:3]) for c in cands[:6]])
        picked=[c for c in cands if c["score"]>=2][:3]
        for c in picked: out.append(c)
    json.dump(cache,open(CACHE,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    # append/replace events in events.json
    ev=json.load(open(os.path.join(HERE,"events.json"),encoding="utf-8"))
    existing={(e["repo"],e["head"]) for e in ev["events"]}
    for c in out:
        if (c["repo"],c["head"]) in existing: continue
        e={"repo":c["repo"],"kb_file":c["kb_file"],"base":c["base"],"head":c["head"],
           "title":c["title"],"files":c["files"],
           "kind":"kb_referenced_move" if c["moved"] else ("kb_edit" if c["kb_edit"] else "build_change"),
           "negative_control":False,
           "event_id":"%s@%s"%(c["repo"].replace("/","__"),c["head"][:10])}
        ev["events"].append(e)
    json.dump(ev,open(os.path.join(HERE,"events.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("added signal events:",len(out),"total:",len(ev["events"]))
    for c in out: print("  add",c["repo"],c["head"][:10],c["title"][:70])
if __name__=="__main__": main()
