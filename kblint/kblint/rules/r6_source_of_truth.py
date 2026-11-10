"""R6 — source-of-truth declaration missing.

Config lists topics and their canonical doc/locator. For claims that talk about a
configured topic but live outside the canonical doc and do not reference the
canonical locator, emit a "missing declaration" finding. The rule NEVER guesses
which value is true — it only reports that the declaration is absent.
"""

from __future__ import annotations

import re
from typing import List

from ..extract import norm_key
from .base import ScanContext, finding


def run(ctx: ScanContext) -> List:
    findings = []
    if not ctx.cfg.source_of_truth:
        return findings
    for sot in ctx.cfg.source_of_truth:
        topic = str(sot.get("topic", "")).strip()
        canonical_doc = str(sot.get("canonical_doc", "")).strip()
        canonical_locator = str(sot.get("canonical_locator", "") or "").strip()
        if not topic or not canonical_doc:
            continue
        topic_tokens = [t for t in re.split(r"[^a-z0-9]+", topic.lower()) if len(t) >= 3]
        if not topic_tokens:
            continue
        flagged_docs = set()
        for claim in ctx.claims:
            if claim.doc == canonical_doc:
                continue
            hay = (claim.text + " " + (claim.section or "")).lower()
            if not all(t in hay for t in topic_tokens):
                continue
            if canonical_doc in claim.text or (canonical_locator and
                                               canonical_locator in claim.text):
                continue
            if claim.doc in flagged_docs:
                continue
            flagged_docs.add(claim.doc)
            findings.append(finding(
                "R6", "low", claim,
                subject=f"missing canonical declaration for topic {topic!r}",
                observed=f"{claim.doc} discusses '{topic}' without referencing the canonical "
                         f"{canonical_doc}{(' ' + canonical_locator) if canonical_locator else ''}",
                expected=f"claims about {topic!r} should declare the canonical source "
                         f"({canonical_doc}) or link its locator",
                evidence=[claim.locator,
                          f"configured canonical: {canonical_doc}"
                          + (f" {canonical_locator}" if canonical_locator else "")],
                verification_method="configured topic matching + canonical declaration absence",
                disposition="unresolved",
                confidence="medium",
                suggested_action="point the claim at the canonical source or declare the canonical doc",
                tags=["source-of-truth", "declaration"],
            ))
    return findings
