"""R8 — audit queue: claims that cannot be deterministically checked.

This rule NEVER emits defects. It writes one queue item per uncovered
checkable-looking claim (numbers/pins/flags/contracts without a deterministic
witness) so a human can review them. The queue is explicitly not a defect list.
"""

from __future__ import annotations

from typing import List

from ..model import AuditItem, stable_id
from .base import ScanContext


def _reason(claim) -> str:
    feats = claim.features
    if feats.get("numbers"):
        return ("numeric claim without a matching artifact value or artifact pointer "
                "(number provenance unverified)")
    if feats.get("pins") or feats.get("flags"):
        return "version/flag claim with no configured artifact pin or runtime witness"
    if feats.get("markers", {}).get("contract"):
        return "contract/acceptance statement with no configured source-of-truth mapping"
    if feats.get("markers", {}).get("rule"):
        return "procedural rule with no deterministic witness"
    return "claim is not deterministically checkable"


def run(ctx: ScanContext) -> List:
    covered = {f.claim_id for f in ctx.findings if f.claim_id}
    covered |= set(ctx.matched_claims)
    canonical_docs = {str(s.get("canonical_doc")) for s in ctx.cfg.source_of_truth}
    queued = set()
    for claim in ctx.claims:
        if claim.claim_id in covered or claim.claim_id in queued:
            continue
        if claim.doc in canonical_docs:
            continue  # canonical declaration docs are the configured reference, not risk
        feats = claim.features
        checkable_looking = bool(
            feats.get("numbers") or feats.get("pins") or feats.get("flags")
            or feats.get("markers", {}).get("contract")
            or feats.get("markers", {}).get("rule"))
        if not checkable_looking:
            continue
        reason = _reason(claim)
        queued.add(claim.claim_id)
        ctx.audit.append(AuditItem(
            audit_id=stable_id("a_", claim.claim_id, reason),
            claim_id=claim.claim_id,
            doc=claim.doc,
            locator=claim.locator,
            reason=reason,
            subject=claim.text[:140],
            observed=f"section={claim.section!r}; kinds={','.join(feats.get('kinds', []))}",
            tags=["audit-queue", "not-a-defect"],
        ).to_dict())
    return []
