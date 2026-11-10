"""Output writers: findings.jsonl, audit_queue.jsonl, summary.md, report.sarif."""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from . import __version__
from .model import SEVERITY_RANK, Finding

RULE_META = {
    "R1": ("pin/version consistency", "doc-declared env pin vs configured artifact field"),
    "R2": ("number provenance", "claim number resolved against the artifact index"),
    "R3": ("cross-doc conflict", "same subject, conflicting values across docs"),
    "R4": ("missing supersedes/deprecation", "newer artifact contradicts an unmarked claim"),
    "R5": ("negative-result/flag expiry", "stale or undated negative results and flags"),
    "R6": ("source-of-truth declaration", "topic claim without a canonical declaration"),
    "R7": ("untracked/no-owner knowledge file", "git tracking and owner metadata"),
    "R8": ("audit queue", "claims that are not deterministically checkable (not defects)"),
    "R9": ("reference check", "links/paths/make targets/npm scripts that do not exist in the repo"),
}


def _sorted_findings(findings: List[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda f: (f.rule, f.claim_id or "", f.doc or "",
                                           f.locator or "", f.finding_id))


def _sorted_audit(audit: List[Dict]) -> List[Dict]:
    return sorted(audit, key=lambda a: (a.get("doc") or "", a.get("locator") or "",
                                        a.get("claim_id") or "", a.get("audit_id") or ""))


def _line_of(locator: Optional[str]) -> Optional[int]:
    if not locator:
        return None
    m = re.search(r"#L(\d+)", locator)
    return int(m.group(1)) if m else None


def _doc_of(f: Finding) -> Optional[str]:
    if f.doc:
        return f.doc
    for ev in f.evidence:
        if isinstance(ev, str) and "#L" in ev:
            return ev.split("#L", 1)[0]
    for ev in f.evidence:
        if isinstance(ev, str) and "." in ev and " " not in ev and "=" not in ev:
            return ev
    return None


def write_findings(path: str, findings: List[Finding]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for finding in _sorted_findings(findings):
            f.write(json.dumps(finding.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def write_audit(path: str, audit: List[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in _sorted_audit(audit):
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def counts(findings: List[Finding]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key in ("confirmed", "unresolved", "provenance_gap", "revalidation_due"):
        out[key] = sum(1 for f in findings if f.disposition == key)
    return out


def build_summary(findings: List[Finding], audit: List[Dict], meta: Dict) -> str:
    by_rule: Dict[str, int] = {r: 0 for r in RULE_META}
    by_sev: Dict[str, int] = {s: 0 for s in SEVERITY_RANK}
    for f in findings:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    c = counts(findings)
    lines = [
        "# kblint summary",
        "",
        f"- tool: `kblint {__version__}` (deterministic, stdlib only, zero network)",
        f"- repo: `{meta.get('repo', '?')}`",
        f"- docs scanned: {meta.get('docs', 0)}; claims extracted: {meta.get('claims', 0)}; "
        f"artifacts indexed: {meta.get('artifacts', 0)}",
        f"- findings: **{len(findings)}** "
        f"(confirmed {c['confirmed']}, unresolved {c['unresolved']}, "
        f"provenance_gap {c['provenance_gap']}, revalidation_due {c['revalidation_due']})",
        f"- waivers applied: {meta.get('waived', 0)}",
        f"- audit queue (not defects): **{len(audit)}** claims",
        ("- **R4 (missing supersedes) is ENABLED but still experimental**: artifact-chronology "
         "flags can be cross-shape false positives; treat R4 findings as review candidates "
         "(see README honest limits)." if meta.get("r4_enabled") else
         "- R4 (missing supersedes) is disabled by default (experimental; enable with "
         '`"rules": {"R4": true}`).'),
        "",
        "## Findings by rule",
        "",
        "| rule | name | findings |",
        "|---|---|---:|",
    ]
    for rule in sorted(by_rule):
        name = RULE_META.get(rule, ("?", "?"))[0]
        lines.append(f"| {rule} | {name} | {by_rule[rule]} |")
    lines += ["", "## Severity", ""]
    for sev in ("high", "medium", "low"):
        lines.append(f"- {sev}: {by_sev.get(sev, 0)}")
    lines += ["", "## Confirmed / unresolved findings (evidence, not usefulness)", ""]
    shown = [f for f in _sorted_findings(findings) if f.disposition in ("confirmed", "unresolved")]
    if not shown:
        lines.append("_none_")
    for f in shown:
        lines.append(f"- **{f.rule} {f.severity} {f.disposition}** `{f.doc or '?'}"
                     f"{('#' + (f.locator.split('#', 1)[1]) if f.locator and '#' in f.locator else '')}` — "
                     f"{f.subject}")
        lines.append(f"  - observed: {f.observed}")
        lines.append(f"  - expected: {f.expected}")
    queue_only = [f for f in _sorted_findings(findings)
                  if f.disposition in ("provenance_gap", "revalidation_due")]
    lines += ["", "## Queued (provenance gaps / revalidation due — not defects)", ""]
    if not queue_only:
        lines.append("_none_")
    else:
        for f in queue_only[:50]:
            lines.append(f"- {f.rule} {f.disposition}: `{f.doc or '?'}` — {f.subject}")
        if len(queue_only) > 50:
            lines.append(f"- … {len(queue_only) - 50} more in findings.jsonl")
    lines += [
        "",
        "## Honest limits",
        "",
        "- kblint reports **verifiable contract defects** and an **unverifiable-risk queue**. "
        "It does not judge whether knowledge is useful, correct as a route, or harmful; the audit "
        "queue is not a defect list; findings are not a population measurement.",
        "- The doc surface is markdown only; artifact-internal, git-history, and session-history "
        "defects are out of scope unless they reach a configured doc/artifact field.",
        "- Each finding carries a claim locator, evidence locators, a verification method and a "
        "disposition; `revalidation_due` and `provenance_gap` are queue dispositions, not defects.",
        f"- Generated deterministically; no wall-clock or network input (now={meta.get('now', '?')}).",
        "",
    ]
    return "\n".join(lines)


def build_sarif(findings: List[Finding]) -> Dict:
    rules = []
    for rule in sorted(RULE_META):
        rules.append({
            "id": rule,
            "name": RULE_META[rule][0],
            "shortDescription": {"text": RULE_META[rule][1]},
        })
    results = []
    level_map = {"high": "error", "medium": "warning", "low": "note"}
    for f in _sorted_findings(findings):
        doc = _doc_of(f) or "unknown"
        line = _line_of(f.locator)
        region = {"startLine": line} if line else {"startLine": 1}
        results.append({
            "ruleId": f.rule,
            "level": level_map.get(f.severity, "note"),
            "message": {
                "text": f"[{f.disposition}] {f.subject}. observed: {f.observed} "
                        f"expected: {f.expected}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": doc},
                    "region": region,
                }
            }],
            "properties": {
                "finding_id": f.finding_id,
                "claim_id": f.claim_id,
                "disposition": f.disposition,
                "verification_method": f.verification_method,
                "confidence": f.confidence,
            },
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "kblint",
                "version": __version__,
                "rules": rules,
            }},
            "results": results,
        }],
    }


def write_sarif(path: str, findings: List[Finding]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_sarif(findings), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def write_all(out_dir: str, findings: List[Finding], audit: List[Dict],
              meta: Dict, formats: List[str]) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    written = {}
    if "json" in formats:
        p = os.path.join(out_dir, "findings.jsonl")
        write_findings(p, findings)
        written["findings"] = p
        p = os.path.join(out_dir, "audit_queue.jsonl")
        write_audit(p, audit)
        written["audit_queue"] = p
    if "md" in formats:
        p = os.path.join(out_dir, "summary.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_summary(findings, audit, meta))
        written["summary"] = p
    if "sarif" in formats:
        p = os.path.join(out_dir, "report.sarif")
        write_sarif(p, findings)
        written["sarif"] = p
    return written
