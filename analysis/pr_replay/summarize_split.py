#!/usr/bin/env python3
"""Split the replay metrics into ordinary (null) vs targeted drift-introduction events."""
import json, os, statistics
from run_pr_replay import clopper_pearson, load_json, EVENTS, RAW, RESULTS, HERE

def metrics(event_ids):
    rows=[json.loads(l) for l in open(os.path.join(HERE,"adjudication.jsonl"),encoding="utf-8") if l.strip()]
    metas=[]
    for eid in event_ids:
        m=os.path.join(RAW,eid,"meta.json")
        if os.path.exists(m): metas.append(json.load(open(m,encoding="utf-8")))
    evset=set(event_ids)
    new=[r for r in rows if r["type"]=="NEW" and r["event_id"] in evset]
    fix=[r for r in rows if r["type"]=="FIXED" and r["event_id"] in evset]
    tp=sum(1 for r in new if r["class"]=="true_stale")
    fp=sum(1 for r in new if r["class"]=="false_positive")
    rt=sum(1 for r in new if r["class"]=="runtime_unavailable")
    unk=len(new)-tp-fp-rt
    lo,hi=clopper_pearson(tp,tp+fp)
    blocked=[m for m in metas if m["diff"]["counts"]["new_blocking"]>0]
    block_rows=[r for r in new if r.get("blocking")]
    false_block=sum(1 for m in blocked
                    if all(r["class"]!="true_stale" for r in block_rows if r["event_id"]==m["event_id"]))
    negs=[m for m in metas if m["negative_control"]]
    lat=[m["total_runtime_s"] for m in metas]
    return {
        "events": len(metas),
        "event_ids": event_ids,
        "events_with_any_new": sum(1 for m in metas if m["diff"]["counts"]["new"]>0),
        "signal_rate": round(sum(1 for m in metas if m["diff"]["counts"]["new"]>0)/len(metas),4) if metas else None,
        "new_total": len(new), "new_true_stale": tp, "new_false_positive": fp,
        "new_runtime_unavailable": rt, "new_unknown": unk,
        "new_precision": round(tp/(tp+fp),4) if tp+fp else None,
        "new_precision_clopper_pearson_95ci": [lo,hi],
        "blocking_new_total": len(block_rows), "events_blocked": len(blocked),
        "false_block_events": false_block,
        "false_block_rate": round(false_block/len(blocked),4) if blocked else None,
        "fixed_rows": len(fix), "fixed_real_repairs": sum(1 for r in fix if r["class"]=="real_repair"),
        "fixed_not_a_repair": sum(1 for r in fix if r["class"]!="real_repair"),
        "negative_control_events": len(negs),
        "negative_control_quiet": sum(1 for m in negs if m["diff"]["counts"]["new_blocking"]==0),
        "negative_control_quiet_rate": round(sum(1 for m in negs if m["diff"]["counts"]["new_blocking"]==0)/len(negs),4) if negs else None,
        "latency_s": {"min":min(lat),"median":statistics.median(lat),"max":max(lat),"total":round(sum(lat),2)} if lat else None,
        "events_detail": [{"event_id":m["event_id"],"repo":m["repo"],"kind":m["kind"],
                           "new":m["diff"]["counts"]["new"],"new_blocking":m["diff"]["counts"]["new_blocking"],
                           "persisting":m["diff"]["counts"]["persisting"],"fixed":m["diff"]["counts"]["fixed"],
                           "exit_code":m["diff"]["exit_code"],"runtime_s":m["total_runtime_s"]} for m in metas],
    }

def main():
    ev=load_json(EVENTS)["events"]
    ordinary=[e["event_id"] for e in ev if e["kind"]!="targeted_drift"]
    targeted=[e["event_id"] for e in ev if e["kind"]=="targeted_drift"]
    out={
      "task":"task-87 historical replay of the kblint incremental PR gate",
      "kblint_version":"0.3.0","now":"2026-11-09","fail_on_new":"medium",
      "sampling_rule":load_json(EVENTS)["sampling_rule"],
      "ordinary_events":metrics(ordinary),
      "targeted_events":metrics(targeted),
      "annotator":"single annotator (rule-assisted pass + manual review of every NEW and FIXED row)",
      "limitations":[
        "small convenience sample: 18 ordinary events + 3 targeted drift-introduction events; not a false-alarm rate over all PRs",
        "targeted events were selected for known/potential drift, so their signal rate and precision are not comparable to unselected PRs",
        "tarballs have no .git: R7 unavailable; events are commit-parent pairs/historical windows, not PR merge bases",
        "single annotator; no inter-annotator agreement",
        "FIXED: 2 rows in the restructure window, both reference removals/doc moves, not real repairs of the named target",
      ],
    }
    os.makedirs(RESULTS,exist_ok=True)
    json.dump(out,open(os.path.join(RESULTS,"summary.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print(json.dumps({k:out[k] for k in ("ordinary_events","targeted_events")},indent=1)[:4000])
if __name__=="__main__":
    import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    main()
