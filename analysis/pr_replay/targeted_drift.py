#!/usr/bin/env python3
"""Targeted drift-introduction events (Lead request): replay the commits that moved KB-referenced
paths in the two repos where the natural audit confirmed drift. Uses the GitHub REST API (quota
reset) for path history + parent resolution, codeload for pinned tarballs.
"""
import json, os, re, subprocess, sys, time
HERE=os.path.dirname(os.path.abspath(__file__))
EV=os.path.join(HERE,"events.json")
SCRATCH="/tmp/pr_replay"; REPOS=os.path.join(SCRATCH,"repos"); TAR=os.path.join(SCRATCH,"tarballs")
NAT=os.path.join(HERE,"..","natural_checkout_audit")
TARGETS=[
  ("mvanhorn/last30days-skill","AGENTS.md",["tests/test_plugin_contract.py","scripts/last30days.py",".github/workflows/validate.yml"]),
  ("avelino/awesome-go","AGENTS.md",[".github/scripts/check-quality.js"]),
]
def api(url):
    p=subprocess.run(["curl","-sS","--compressed","-m","60","-w","\n%{http_code}",url],capture_output=True,text=True)
    body,_,code=p.stdout.rpartition("\n")
    if code.strip()!="200": raise RuntimeError("%s -> %s %s"%(url,code.strip(),body[:180]))
    return json.loads(body)
def slug(r): return r.replace("/","__")
def fetch(repo,sha):
    dest=os.path.join(REPOS,slug(repo),sha)
    if os.path.isdir(dest) and os.listdir(dest): return dest
    os.makedirs(os.path.join(REPOS,slug(repo)),exist_ok=True); os.makedirs(TAR,exist_ok=True)
    tarp=os.path.join(TAR,"%s__%s.tar.gz"%(slug(repo),sha))
    url="https://codeload.github.com/%s/tar.gz/%s"%(repo,sha)
    t0=time.monotonic()
    p=subprocess.run(["curl","-sSL","-m","600","--max-filesize","20971520","-o",tarp,url],capture_output=True,text=True)
    dt=time.monotonic()-t0
    size=os.path.getsize(tarp) if os.path.exists(tarp) else 0
    print("  fetched %s %s bytes=%d in %.1fs"%(repo,sha[:10],size,dt),flush=True)
    if p.returncode!=0 or size==0: raise RuntimeError("tarball fail "+url)
    os.makedirs(dest,exist_ok=True)
    subprocess.run(["tar","-xzf",tarp,"-C",dest,"--strip-components=1"],check=True)
    return dest
def find_commit(repo,paths):
    """Most recent commit touching any path; prefer a commit whose detail deletes/moves that path."""
    best=None
    for path in paths:
        try: commits=api("https://api.github.com/repos/%s/commits?path=%s&per_page=10"%(repo,path))
        except Exception as ex: print("  path history fail",path,str(ex)[:100]); continue
        for c in commits:
            detail=api("https://api.github.com/repos/%s/commits/%s"%(repo,c["sha"]))
            files=[(f["filename"],f.get("previous_filename"),f["status"]) for f in detail.get("files",[])]
            moved=[f for f in files if f[2] in ("removed","renamed")]
            if moved:
                return detail, path, files
    return None,None,None
def main():
    ev=json.load(open(EV,encoding="utf-8"))
    have={(e["repo"],e["head"]) for e in ev["events"]}
    added=[]
    for repo,kb,paths in TARGETS:
        print("==",repo)
        detail,path,files=find_commit(repo,paths)
        if not detail:
            print("  no commit found"); continue
        head=detail["sha"]; base=detail["parents"][0]["sha"]
        msg=(detail["commit"]["message"] or "").splitlines()[0][:120]
        print("  commit",head[:10],msg,"| touched via",path,"| files",len(files),"| parent",base[:10])
        print("  moved sample:",[f for f in files if f[2] in ("removed","renamed")][:6])
        # only interesting if a moved/deleted path appears likely KB-referenced; fetch trees
        try:
            fetch(repo,base); fetch(repo,head)
        except Exception as ex:
            print("  fetch fail",str(ex)[:160]); continue
        e={"repo":repo,"kb_file":kb,"base":base,"head":head,
           "title":"targeted drift introduction: "+msg,"files":[{"filename":f[0],"previous":f[1],"status":f[2]} for f in files],
           "kind":"targeted_drift","negative_control":False,
           "event_id":"%s@%s"%(slug(repo),head[:10])}
        if (repo,head) in have:
            print("  already present"); continue
        ev["events"].append(e); added.append(e)
        time.sleep(0.4)
    json.dump(ev,open(EV,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("added targeted events:",len(added),"total events:",len(ev["events"]))
if __name__=="__main__": main()
