"""R3 — cross-doc numeric conflict on the same subject anchor.

Anchor = (unit family, normalized key/noun context). A group with >= 2 docs,
conflicting values beyond tolerance, and no supersedes/deprecation marker on any
member yields ONE confirmed finding for the group (subject-level, not per-doc).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from .base import ScanContext, context_anchor, finding, rel_diff, section_has_supersede_marker

GENERIC_TOKENS = {"value", "values", "step", "steps", "token", "tokens", "mfu", "pct",
                  "percent", "percentage", "best", "run", "runs", "row", "rows",
                  "batch", "seq", "b", "model", "head", "rest"}


def run(ctx: ScanContext) -> List:
    findings = []
    groups: Dict[Tuple[str, str], List] = defaultdict(list)
    for claim in ctx.claims:
        for number in claim.features.get("numbers", []):
            unit, anchor = context_anchor(number)
            if not unit or not anchor:
                continue
            groups[(unit, anchor)].append((claim, number))
    for (unit, anchor), members in sorted(groups.items()):
        docs = {c.doc for c, _ in members}
        if len(docs) < 2:
            continue
        if any(section_has_supersede_marker(ctx, c) for c, _ in members):
            continue
        anchor_tokens = [t for t in anchor.split() if len(t) >= 2 and t not in GENERIC_TOKENS]
        if len(anchor_tokens) < 2:
            continue
        values = [float(n["value"]) for _, n in members]
        # conflicting if max pairwise relative difference exceeds tolerance
        conflict = False
        lo, hi = min(values), max(values)
        if hi != lo and rel_diff(hi, lo) > max(ctx.rel_tol(), 0.01):
            conflict = True
        if not conflict:
            continue
        # pick deterministic representative claim (earliest locator)
        rep_claim, rep_number = sorted(members, key=lambda m: (m[0].doc, m[0].line_start))[0]
        evidence = [f"{c.locator} = {n['value']:g}{n.get('unit') or ''}" for c, n in
                    sorted(members, key=lambda m: (m[0].doc, m[0].line_start))]
        findings.append(finding(
            "R3", "medium", rep_claim,
            subject=f"cross-doc conflict on '{anchor}' ({unit}): "
                    f"{lo:g} vs {hi:g}",
            observed=f"{rep_claim.doc} states {rep_number['value']:g}{unit}; "
                     f"other doc(s) state different values: " +
                     ", ".join(f"{c.doc}:{n['value']:g}" for c, n in members
                               if c.doc != rep_claim.doc),
            expected="the same subject must have one value across docs unless a claim/section is "
                     "explicitly marked superseded/deprecated",
            evidence=evidence,
            verification_method="normalized (unit, key-context) anchor grouping + relative tolerance",
            confidence="medium",
            suggested_action="mark the older claim superseded or align the values",
            tags=["conflict", "cross-doc", unit],
        ))
    return findings
