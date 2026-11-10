#!/usr/bin/env python3
"""Behavioral / recovery-cost analysis of the 18 existing agentic-CF tool-loop runs (task-80).

ZERO model calls. Reads results/runs.jsonl + results/transcripts/*.json and writes
results/recovery_cost.json.

## Transcript JSON structure (parsed and documented before analysis)

`results/transcripts/<run_id>.json` is a list of chat messages, truncated by the harness:

  [ {"role":"system","content": <tool-protocol>},
    {"role":"user","content": <task prompt>},
    {"role":"assistant","content": <raw model reply, max 1800 chars>},
    {"role":"user","content": "tool output:\\n<result, max 1800 chars>" | "<invalid-JSON nudge>"},
    ... ]

`results/runs.jsonl` is the authoritative per-run record (steps, tool_calls incl invalid_json,
kb_read, kb_seen_in_tool_output, stale_inspections, stale_edit_actions, wrong_path_final_edits,
usage, cost, latency, auto_submit, hidden_pass). Transcript analysis is used only for ordering and
for path/pattern-level flags; aggregate counts are cross-checked against runs.jsonl.

An action is executed iff the following user message starts with "tool output:"; otherwise the reply
was rejected (invalid JSON) and nudged. Action type/path are recovered with the harness's
first-complete-JSON parser, falling back to a regex on the raw (truncated) reply when a long
write_file payload was cut at 1800 chars.
"""
from __future__ import annotations

import json
import pathlib
import posixpath
import re
import statistics
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import CASES, STALE_TOKENS, parse_action, kb_signatures  # noqa: E402 (no API at import)

RUNS = HERE / "results" / "runs.jsonl"
TRANSCRIPTS = HERE / "results" / "transcripts"
OUT = HERE / "results" / "recovery_cost.json"
ARMS = ("no_kb", "stale_kb", "corrected_kb")
EXPECTED_PREFIX = {"R4": "docs/layouts/_partials/layouts/icons.html",
                   "R5": "miniprogram/pages/stats/",
                   "R3": ".agents/skills/short-term-memory/"}
ACTION_RE = re.compile(r'"action"\s*:\s*"([a-zA-Z_]+)"')
DIFF_PATH_RE = re.compile(r"diff --git a/(\S+) b/")


def stale_path_target(target: str, case_id: str) -> bool:
    """True iff an edit/write target is (one of) the stale reference path(s)."""
    t = (target or "").strip().lstrip("./")
    if not t:
        return False
    if case_id == "R4":
        return t == "docs/layouts/_partials/icons.html"
    if case_id == "R5":
        return t == "app.json" or t.startswith(("pages/", "static/", "user/", "pay/"))
    if case_id == "R3":
        return t.startswith(".agents/skills/memory-update/")
    return False


def _same_kb_path(path: str, kb_path: str) -> bool:
    """True iff a tool path targets the designated KB file (exact) or its directory (ls)."""
    try:
        paths = [p for p in (path, kb_path)]
        norm = [posixpath.normpath(x.strip().lstrip("./")) for x in paths]
    except Exception:  # noqa: BLE001
        return False
    if norm[0] == norm[1]:
        return True
    if norm[1] in norm[0] or norm[0] in norm[1]:
        # e.g. 'CODEMAP.md' vs 'docs/CODEMAP.md' from a nested doc; only accept exact basename
        # matches when the tool path has no directory component or the KB path ends with it
        return posixpath.basename(norm[0]) == posixpath.basename(norm[1])
    return False
PATH_RE = re.compile(r'"path"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"')


def stale_touch(blob: str, case_id: str) -> bool:
    for tok in STALE_TOKENS.get(case_id, []):
        if tok not in blob:
            continue
        if case_id == "R5" and tok == "pages/":
            if re.search(r"(?<!miniprogram/)pages/", blob):
                return True
        else:
            return True
    return False


def parse_run(run: dict) -> dict:
    case_id = run["case"]
    msgs = json.loads((TRANSCRIPTS / f"{run['run_id']}.json").read_text())
    kb_sigs = kb_signatures(CASES[case_id], run["arm"])
    actions: list[dict] = []
    pending = None
    for i, m in enumerate(msgs):
        role, content = m.get("role"), (m.get("content") or "")
        if role == "assistant":
            pending = content
        elif role == "user" and pending is not None:
            raw = pending
            pending = None
            submitted_ack = content.strip() == "state submitted"
            valid = content.startswith("tool output:") or submitted_ack
            body = (content[len("tool output:"):].strip() if content.startswith("tool output:")
                    else "state submitted")
            act = parse_action(raw) if valid else {}
            typ = str(act.get("action", "")).lower() if act else ""
            if not typ:
                m2 = ACTION_RE.search(raw)
                typ = m2.group(1).lower() if m2 else ""
            pm = PATH_RE.search(raw)
            path = pm.group(1) if pm else ""
            if not valid:
                kind = "invalid_json"
            elif body == "state submitted":
                kind = "ok"
            elif body.startswith("command not allowed") or body.startswith("unknown action"):
                kind = "rejected"
            elif body.startswith("error:") or body.startswith("rc=1") or body.startswith("rc=2"):
                kind = "error"
            elif body in ("(no matches)", "(empty)"):
                kind = "no_match"
            else:
                kind = "ok"
            entry = {
                "idx": len(actions) + 1, "type": typ or ("invalid_json" if not valid else "unknown"),
                "reply_parsed": bool(act), "executed": valid,
                "output_kind": kind, "output": body[:300],
                "path": path,
                "stale_touch": stale_touch(raw, case_id),
                "kb_path_touch": (run["arm"] in ("stale_kb", "corrected_kb")
                                  and bool(path) and _same_kb_path(path, run["kb_path"])
                                  and kind == "ok"),
                "kb_exposed": bool(kb_sigs) and any(sig in body for sig in kb_sigs),
                "expected_edit": typ in ("write_file", "write", "create", "apply_patch", "patch")
                                 and EXPECTED_PREFIX.get(case_id, "") in raw,
                "lookup": typ in ("read_file", "read", "cat", "ls", "list", "grep", "search"),
            }
            entry["invalid_lookup"] = entry["lookup"] and kind in ("error", "no_match")
            edit_target = path
            if typ in ("apply_patch", "patch") and not edit_target:
                dm = DIFF_PATH_RE.search(raw)
                edit_target = dm.group(1) if dm else ""
            entry["edit_target"] = edit_target
            entry["stale_path_edit"] = (typ in ("write_file", "write", "create", "apply_patch",
                                                "patch") and stale_path_target(edit_target, case_id))
            actions.append(entry)
    # a trailing assistant message without a following user message = unexecuted final reply
    if pending is not None:
        actions.append({"idx": len(actions) + 1, "type": "unanswered", "executed": False,
                        "output_kind": "none", "stale_touch": stale_touch(pending, case_id),
                        "kb_path_touch": False, "kb_exposed": False, "expected_edit": False,
                        "lookup": False, "invalid_lookup": False, "path": ""})
    executed = [a for a in actions if a["executed"]]
    invalid = [a for a in actions if not a["executed"]]
    stale = [a for a in actions if a["stale_touch"]]
    stale_exec = [a for a in stale if a["executed"]]
    first_stale = stale_exec[0]["idx"] if stale_exec else None
    first_edit = next((a["idx"] for a in actions if a["expected_edit"]), None)
    first_kb = next((a["idx"] for a in actions if a["kb_exposed"] or a["kb_path_touch"]), None)
    stale_after_kb = [a for a in stale_exec if first_kb is not None and a["idx"] > first_kb]
    # recovery: from KB exposure (stale/corrected arms) or first stale action (any arm) to the
    # first edit at the expected location
    anchor = first_kb if first_kb is not None else first_stale
    recovery = (first_edit - anchor) if (anchor is not None and first_edit is not None
                                         and first_edit >= anchor) else None
    steps_after_kb = (len(actions) - first_kb + 1) if first_kb is not None else None
    rec = {
        "run_id": run["run_id"], "case": case_id, "arm": run["arm"], "seed": run["seed"],
        "hidden_pass": bool(run["hidden_pass"]), "auto_submit": bool(run["auto_submit"]),
        "steps_record": int(run["steps"]), "assistant_turns_transcript": len(actions),
        "invalid_json_transcript": len(invalid),
        "invalid_json_record": int((run.get("tool_calls") or {}).get("invalid_json") or 0),
        "executed_tool_actions": len(executed),
        "tool_calls_executed": len([a for a in executed if a["type"] != "submit"]),
        "submit_actions": len([a for a in executed if a["type"] == "submit"]),
        "executed_by_type": dict(sorted(Counter(a["type"] for a in executed).items())),
        "invalid_lookups": sum(1 for a in executed if a["invalid_lookup"]),
        "stale_touch_actions": len(stale_exec),
        "stale_inspections_record": int((run.get("stale_inspections") or 0)),
        "stale_edit_actions_record": int((run.get("stale_edit_actions") or 0)),
        "stale_path_edit_attempts": sum(1 for a in actions if a.get("stale_path_edit")),
        "stale_touches_after_kb_exposure": len(stale_after_kb),
        "steps_after_kb_exposure": steps_after_kb,
        "stale_touch_invalid": len([a for a in stale_exec if a["invalid_lookup"]]),
        "stale_path_reads": len([a for a in stale_exec if a["lookup"]]),
        "kb_read": bool(run.get("kb_read")),
        "kb_seen_in_tool_output": bool(run.get("kb_seen_in_tool_output")),
        "kb_exposed_transcript": bool(first_kb),
        "first_kb_exposure_idx": first_kb,
        "first_stale_touch_idx": first_stale,
        "first_expected_edit_idx": first_edit,
        "recovery_steps_anchor_to_expected_edit": recovery,
        "steps_after_kb_exposure": steps_after_kb,
        "actions_after_first_stale": (len(actions) - first_stale + 1) if first_stale else None,
        "steps": int(run["steps"]),
        "tokens_prompt": int((run.get("usage") or {}).get("prompt_tokens") or 0),
        "tokens_completion": int((run.get("usage") or {}).get("completion_tokens") or 0),
        "cost_cny": float(run.get("cost_cny") or 0.0),
        "latency_s": float(run.get("latency_s") or 0.0),
        "wrong_path_final_edits": list(run.get("wrong_path_final_edits") or []),
        "repo_test_status": run.get("repo_test_status"),
        "tool_calls_record": run.get("tool_calls") or {},
    }
    return rec


def agg(rows: list[dict]) -> dict:
    def med(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(statistics.median(vals), 2) if vals else None
    def mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    n = len(rows)
    return {
        "n": n, "hidden_pass": sum(r["hidden_pass"] for r in rows),
        "kb_read": sum(r["kb_read"] for r in rows),
        "kb_seen_in_tool_output": sum(r["kb_seen_in_tool_output"] for r in rows),
        "kb_exposed_transcript": sum(r["kb_exposed_transcript"] for r in rows),
        "stale_touch_actions_total": sum(r["stale_touch_actions"] for r in rows),
        "stale_inspections_record_total": sum(r["stale_inspections_record"] for r in rows),
        "stale_edit_actions_record_total": sum(r["stale_edit_actions_record"] for r in rows),
        "stale_path_edit_attempts_total": sum(r["stale_path_edit_attempts"] for r in rows),
        "stale_touches_after_kb_exposure_total": sum(r["stale_touches_after_kb_exposure"] for r in rows),
        "kb_exposed_runs": sum(1 for r in rows if r["first_kb_exposure_idx"] is not None),
        "stale_touch_actions_median": med("stale_touch_actions"),
        "stale_path_reads_total": sum(r["stale_path_reads"] for r in rows),
        "stale_invalid_lookups_total": sum(r["stale_touch_invalid"] for r in rows),
        "invalid_lookups_total": sum(r["invalid_lookups"] for r in rows),
        "invalid_json_record_total": sum(r["invalid_json_record"] for r in rows),
        "invalid_json_transcript_total": sum(r["invalid_json_transcript"] for r in rows),
        "executed_tool_actions_total": sum(r["executed_tool_actions"] for r in rows),
        "tool_calls_executed_total": sum(r["tool_calls_executed"] for r in rows),
        "tool_calls_median": med("tool_calls_executed"),
        "submit_total": sum(r["submit_actions"] for r in rows),
        "auto_submit": sum(r["auto_submit"] for r in rows),
        "steps_median": med("steps"), "steps_mean": mean("steps"),
        "tokens_prompt_total": sum(r["tokens_prompt"] for r in rows),
        "tokens_completion_total": sum(r["tokens_completion"] for r in rows),
        "cost_cny_total": round(sum(r["cost_cny"] for r in rows), 6),
        "cost_cny_median": med("cost_cny"), "latency_s_median": med("latency_s"),
        "wrong_path_final_edits": sum(len(r["wrong_path_final_edits"]) for r in rows),
        "repo_test_pass": sum(1 for r in rows if r["repo_test_status"] == "pass"),
    }


def main() -> int:
    runs = [json.loads(x) for x in RUNS.read_text().splitlines() if x.strip()]
    per_run = [parse_run(r) for r in runs]
    by_arm = {a: agg([r for r in per_run if r["arm"] == a]) for a in ARMS}
    by_repo = {cid: {a: agg([r for r in per_run if r["case"] == cid and r["arm"] == a])
                     for a in ARMS} for cid in CASES}
    by_repo_compact = {
        cid: {a: {"n": by_repo[cid][a]["n"],
                  "hidden_pass": by_repo[cid][a]["hidden_pass"],
                  "kb_read": by_repo[cid][a]["kb_read"],
                  "kb_seen": by_repo[cid][a]["kb_seen_in_tool_output"],
                  "stale_touch_actions_total": by_repo[cid][a]["stale_touch_actions_total"],
                  "steps_mean": by_repo[cid][a]["steps_mean"]} for a in ARMS}
        for cid in CASES}
    stale_rows = [r for r in per_run if r["arm"] == "stale_kb"]
    def kb_recovery(rows_arm):
        xs = [r for r in rows_arm if r["first_kb_exposure_idx"] is not None]
        return {
            "kb_exposed_runs": len(xs),
            "steps_after_kb_exposure": [r["steps_after_kb_exposure"] for r in xs],
            "recovery_steps_anchor_to_expected_edit": [r["recovery_steps_anchor_to_expected_edit"]
                                                        for r in xs],
            "median_steps_after_kb": (round(statistics.median(
                [r["steps_after_kb_exposure"] for r in xs]), 2) if xs else None),
            "median_recovery_steps": (round(statistics.median(
                [r["recovery_steps_anchor_to_expected_edit"] for r in xs
                 if r["recovery_steps_anchor_to_expected_edit"] is not None]), 2)
                if any(r["recovery_steps_anchor_to_expected_edit"] is not None for r in xs) else None),
            "stale_touches_after_kb_exposure_total": sum(r["stale_touches_after_kb_exposure"] for r in xs),
        }
    recovery = {
        "definition": ("For every run, anchor = first tool action that exposed the KB "
                       "(kb_seen/kb_path) or, if the KB was never exposed, the first stale-token "
                       "action; recovery_steps_anchor_to_expected_edit = index(first edit at the "
                       "expected location) - anchor. steps_after_kb_exposure = transcript actions "
                       "from the first KB exposure through submit/cap. stale_touches_after_kb_exposure "
                       "= stale-targeting actions made AFTER the KB was seen, i.e. plausibly "
                       "KB-induced detours. stale_invalid_lookups = stale-targeting read/ls/grep "
                       "calls whose output was an error or '(no matches)'."),
        "by_arm_kb_exposed": {a: kb_recovery([r for r in per_run if r["arm"] == a]) for a in ARMS},
        "per_stale_run": [{k: r[k] for k in (
            "run_id", "hidden_pass", "steps", "kb_seen_in_tool_output", "kb_exposed_transcript",
            "first_kb_exposure_idx", "first_stale_touch_idx", "first_expected_edit_idx",
            "recovery_steps_anchor_to_expected_edit", "steps_after_kb_exposure",
            "actions_after_first_stale", "stale_touch_actions", "stale_touches_after_kb_exposure",
            "stale_path_reads", "stale_touch_invalid", "stale_path_edit_attempts",
            "stale_edit_actions_record", "invalid_json_record")}
            for r in stale_rows],
        "median_recovery_steps": (round(statistics.median(
            [r["recovery_steps_anchor_to_expected_edit"] for r in stale_rows
             if r["recovery_steps_anchor_to_expected_edit"] is not None]), 2)
            if any(r["recovery_steps_anchor_to_expected_edit"] is not None for r in stale_rows) else None),
        "median_steps": round(statistics.median([r["steps"] for r in stale_rows]), 2),
        "stale_invalid_lookups_total": sum(r["stale_touch_invalid"] for r in stale_rows),
    }
    hugo_runs = [r for r in per_run if r["case"] == "R4"]
    hugo_actions = {}
    for r in hugo_runs:
        msgs = json.loads((TRANSCRIPTS / f"{r['run_id']}.json").read_text())
        first_tool = next((a for a in per_run if a["run_id"] == r["run_id"]), None)
        hugo_actions[r["run_id"]] = {"steps": r["steps"], "kb_read": r["kb_read"],
                                     "kb_seen": r["kb_seen_in_tool_output"],
                                     "hidden_pass": r["hidden_pass"]}
    R4 = {
        "kb_read": {a: sum(r["kb_read"] for r in hugo_runs if r["arm"] == a) for a in ARMS},
        "kb_seen": {a: sum(r["kb_seen_in_tool_output"] for r in hugo_runs if r["arm"] == a)
                    for a in ARMS},
        "n_by_arm": {a: sum(1 for r in hugo_runs if r["arm"] == a) for a in ARMS},
        "all_pass": sum(r["hidden_pass"] for r in hugo_runs),
        "note": ("no arm read the R4 KB (0/6 kb_read, 0/6 kb_seen across all arms): the icon "
                 "sprite is one grep/ls from the repo root, so the KB is never consulted and all "
                 "6 R4 runs pass; any KB-condition behavioral difference is mechanically absent "
                 "in this repo"),
        "runs": hugo_actions,
    }
    consistency = {r["run_id"]: {"record": r["invalid_json_record"],
                                 "transcript": r["invalid_json_transcript"]}
                   for r in per_run if r["invalid_json_record"] != r["invalid_json_transcript"]}
    out = {
        "schema": "agentic-cf/recovery-cost/1",
        "source": "kb-health/analysis/agentic_cf/results (18 v2 runs, deepseek-chat, max 25 steps; 0 new model calls)",
        "definitions": {
            "kb_read": "explicit read/ls/grep of the designated KB file (runs.jsonl field)",
            "kb_seen_in_tool_output": "a distinctive KB line appeared in a tool output (runs.jsonl field)",
            "stale_touch_actions": "transcript tool actions mentioning the stale reference token "
                                   "(C5 'pages/' counts only when not preceded by 'miniprogram/')",
            "invalid_json": "assistant replies with no parseable action (nudged; no tool call)",
            "invalid_lookups": "read/ls/grep calls whose output was an error or '(no matches)'",
            "stale_edit_actions_record": "runs.jsonl field: write/patch payload CONTAINS the stale token (including correct-path writes whose file text mentions it) — an over-count, kept for comparison; see stale_path_edit_attempts",
            "stale_path_edit_attempts": "strict transcript metric: write/apply_patch whose TARGET PATH is the stale reference path (0 in all 18 runs)",
            "recovery_overhead": "see recovery.definition",
            "transcript_structure": "list of chat messages; assistant reply truncated 1800 chars; "
                                   "executed iff following user message starts with 'tool output:'",
        },
        "by_arm": by_arm, "by_repo": by_repo_compact, "recovery": recovery, "R4": R4,
        "invalid_json_consistency": consistency,
        "external_evidence": {
            "citation": "T. Mehtiyev, B. Tadesse, L. Arkoh, W. Assuncao. When Instruction Files Go Stale: Documentation Debt and Hidden Cost in Coding Agents. arXiv:2611.09802 (6 Nov 2026).",
            "url": "https://arxiv.org/abs/2611.09802",
            "summary": ("22 maintenance tasks x 3 instruction versions (left stale / corrected / removed), "
                        "732 trajectories, two models, per-tool-call analysis. Stale test command: Claude "
                        "Sonnet 5.5 needed ~2 extra tool calls per run (~1/3 more than corrected); the other "
                        "two stale-guidance kinds showed no detectable difference; agents recovered from "
                        "immediate failures but repaired no instruction file."),
            "relation": ("independent concurrent evidence that stale instructions can add tool calls. Our "
                        "in-harness result is consistent in direction (stale KB adds stale-path inspection "
                        "actions: 6 post-KB stale touches vs 3 with the corrected KB) but small and fully "
                        "recoverable in these three real-repo location cases (no wrong-path edits, no outcome "
                        "effect), which calibrates how much of the 'hidden cost' translates to agentic harm."),
        },
        "per_run": per_run,
        "caveats": [
            "custom JSON-action harness (not native tool calling); KB is a workspace file the agent must discover, not auto-injected",
            "n=6 per arm (3 engineered repos x 2 prompt seeds); not a random sample; one model family",
            "transcript-derived counts; assistant replies are truncated at 1800 chars, so very long write payloads can under-count content-level flags",
            "behavioral cost within this harness, not native-agent behavior",
        ],
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print("by_arm:")
    for a in ARMS:
        print(" ", a, json.dumps(by_arm[a]))
    print("\nby_repo:", json.dumps(by_repo_compact, indent=1))
    print("\nrecovery:", json.dumps({k: v for k, v in recovery.items() if k != "per_stale_run"}, indent=1))
    print("\nstale per-run:", json.dumps(recovery["per_stale_run"], indent=1))
    print("\nhugo:", json.dumps(R4, indent=1))
    print("\nrecord/transcript invalid_json mismatches (reconciled by truncation):",
          json.dumps(consistency, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
