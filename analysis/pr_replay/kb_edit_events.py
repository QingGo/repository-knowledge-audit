#!/usr/bin/env python3
"""Build a curated event set: KB-edit commits (via public commit-history HTML, no API quota)
plus one code/build event and one docs-only negative control per repo."""
import json, os, re, subprocess, time, sys
HERE=os.path.dirname(os.path.abspath(__file__))
NAT=os.path.join(HERE,"..","natural_checkout_audit")
REPOS={
 "blader/humanizer":{"kb_file":"AGENTS.md"},
 "mattpocock/skills":{"kb_file":"CLAUDE.md"},
 "addyosmani/agent-skills":{"kb_file":"AGENTS.md"},
 "modelcontextprotocol/servers":{"kb_file":"AGENTS.md"},
}
def curl(url,t=60):
    p=subprocess.run(["curl","-sSL","--compressed","-m",str(t),"-w","\n%{http_code}",url],capture_output=True,text=True)
    body,_,code=p.stdout.rpartition("\n")
    if code.strip()!="200": raise RuntimeError("%s -> %s"%(url,code.strip()))
    return body
def commit_hist(repo,kb):
    h=curl("https://github.com/%s/commits/main/%s"%(repo,kb))
    out=[]
    for m in re.finditer(r'href="/%s/commit/([0-9a-f]{40})"[^>]*>(.*?)</a>'%re.escape(repo),h,re.S):
        sha=m.group(1); text=re.sub(r"<[^>]+>","",m.group(2)).strip()
        if sha not in [x["sha"] for x in out]: out.append({"sha":sha,"title":text})
    return out
def parent_of(repo,sha):
    h=curl("https://github.com/%s/commit/%s"%(repo,sha))
    others=[s for s in re.findall(r'/commit/([0-9a-f]{40})',h) if s!=sha]
    return others[0] if others else None
def main():
    cur=json.load(open(os.path.join(HERE,"events.json"),encoding="utf-8"))
    byrepo={}
    for e in cur["events"]: byrepo.setdefault(e["repo"],[]).append(e)
    events=[]
    for repo,spec in REPOS.items():
        old=byrepo.get(repo,[])
        code=[e for e in old if not e.get("negative_control") and e["kind"]!="docs_only"]
        neg=[e for e in old if e.get("negative_control") or e["kind"]=="docs_only"]
        try:
            hist=commit_hist(repo,spec["kb_file"])
        except RuntimeError as ex:
            print("hist fail",repo,ex); hist=[]
        print(repo,"KB-edit commits found:",len(hist),[x["sha"][:10] for x in hist[:5]])
        kb_events=[]
        for h in hist[:5]:
            if len(kb_events)>=2: break
            try: base=parent_of(repo,h["sha"])
            except RuntimeError as ex: print("  parent fail",h["sha"][:10],ex); continue
            if not base: continue
            kb_events.append({"repo":repo,"kb_file":spec["kb_file"],"base":base,"head":h["sha"],
                              "title":h["title"] or "KB edit","files":[],
                              "kind":"kb_edit","negative_control":False,
                              "event_id":"%s@%s"%(repo.replace("/","__"),h["sha"][:10])})
            time.sleep(0.2)
        picked=kb_events[:2]
        if code: picked.append(code[0])
        if neg: picked.append(neg[0])
        for e in picked[:4]:
            e=dict(e); e.pop("files",None) if False else None
            events.append(e)
        print("  picked:",[(e["head"][:10],e["kind"]) for e in picked[:4]])
    json.dump({"now":"2026-11-09","fail_on_new":"medium","events":events,
               "sampling_rule":("per repo: 2 recent KB-file edit commits (from public commit-history "
                                "HTML) + 1 code/build event from the 20-commit window + 1 docs-only "
                                "negative control = 4 events/repo, 16 total; SHAs pinned, base = "
                                "commit parent from the public commit page; no REST API quota used")},
              open(os.path.join(HERE,"events.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("total events:",len(events))
if __name__=="__main__": main()
