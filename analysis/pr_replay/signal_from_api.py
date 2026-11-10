#!/usr/bin/env python3
"""Add two real 'KB-referenced path deletion' events discovered via the GitHub REST API.

Runs after the unauthenticated API quota resets. For each target path it takes the most recent
commit that touched the path (the deletion/rename commit), resolves its first parent from the
commit detail, appends the (parent -> deletion) event to events.json, and fetches both tarballs.
"""
import json, os, subprocess, sys, time
HERE=os.path.dirname(os.path.abspath(__file__))
EV=os.path.join(HERE,"events.json")
SCRATCH="/tmp/pr_replay"; REPOS=os.path.join(SCRATCH,"repos"); TAR=os.path.join(SCRATCH,"tarballs")
TARGETS=[
 ("avelino/awesome-go", ".github/scripts/check-quality.js"),
 ("modelcontextprotocol/servers", ".github/dependabot.yml"),
]
def api(url):
    p=subprocess.run(["curl","-sS","--compressed","-m","60","-w","\n%{http_code}",url],capture_output=True,text=True)
    body,_,code=p.stdout.rpartition("\n")
    if code.strip()!="200": raise RuntimeError("%s -> %s %s"%(url,code.strip(),body[:200]))
    return json.loads(body)
def slug(r): return r.replace("/","__")
def fetch(repo,sha):
    dest=os.path.join(REPOS,slug(repo),sha)
    if os.path.isdir(dest) and os.listdir(dest): return dest
    os.makedirs(os.path.join(REPOS,slug(repo)),exist_ok=True); os.makedirs(TAR,exist_ok=True)
    tarp=os.path.join(TAR,"%s__%s.tar.gz"%(slug(repo),sha))
    url="https://codeload.github.com/%s/tar.gz/%s"%(repo,sha)
    p=subprocess.run(["curl","-sSL","-m","240","--max-filesize","20971520","-o",tarp,url],capture_output=True,text=True)
    if p.returncode!=0 or os.path.getsize(tarp)==0: raise RuntimeError("tarball fail "+url)
    os.makedirs(dest,exist_ok=True)
    subprocess.run(["tar","-xzf",tarp,"-C",dest,"--strip-components=1"],check=True)
    return dest
def main():
    ev=json.load(open(EV,encoding="utf-8"))
    have={(e["repo"],e["head"]) for e in ev["events"]}
    added=[]
    for repo,path in TARGETS:
        try:
            commits=api("https://api.github.com/repos/%s/commits?path=%s&per_page=5"%(repo,path))
        except Exception as ex:
            print("list fail",repo,str(ex)[:160]); continue
        if not commits: print("no commits",repo,path); continue
        head=commits[0]["sha"]
        try:
            detail=api("https://api.github.com/repos/%s/commits/%s"%(repo,head))
            base=detail["parents"][0]["sha"]
        except Exception as ex:
            print("detail fail",repo,head[:10],str(ex)[:160]); continue
        try:
            fetch(repo,base); fetch(repo,head)
        except Exception as ex:
            print("fetch fail",repo,str(ex)[:160]); continue
        if any(e["repo"]==repo and e["head"]==head for e in ev["events"]): continue
        e={"repo":repo,"kb_file":"AGENTS.md","base":base,"head":head,
           "title":"KB-referenced path deletion: "+"".join(commits[0]["commit"]["message"].splitlines()[:1])[:120],
           "files":[],"kind":"kb_referenced_move","negative_control":False,
           "event_id":"%s@%s"%(slug(repo),head[:10])}
        ev["events"].append(e); added.append(e)
        print("added event",repo,base[:10],"->",head[:10],e["title"][:80])
        time.sleep(0.5)
    json.dump(ev,open(EV,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("added",len(added),"events; total",len(ev["events"]))
if __name__=="__main__": main()
