"""Data model: claims, findings, audit-queue items. Stable hash-based ids.

Determinism contract: ids are derived only from content (doc, locator, rule,
text/value fields) — never from wall clock, environment, or iteration order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# finding dispositions -------------------------------------------------------
CONFIRMED = "confirmed"
UNRESOLVED = "unresolved"
PROVENANCE_GAP = "provenance_gap"
REVALIDATION_DUE = "revalidation_due"
DISPOSITIONS = (CONFIRMED, UNRESOLVED, PROVENANCE_GAP, REVALIDATION_DUE)

SEVERITIES = ("high", "medium", "low")
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    """Deterministic short id from a tuple of content parts."""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return prefix + h.hexdigest()[:length]


@dataclass
class Claim:
    """One minimal checkable statement extracted from a doc."""

    claim_id: str
    doc: str
    locator: str
    line_start: int
    line_end: int
    section: str
    text: str
    features: Dict[str, Any]
    form: str = "sentence"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "doc": self.doc,
            "locator": self.locator,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "section": self.section,
            "form": self.form,
            "text": self.text,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Claim":
        return cls(**d)


@dataclass
class Finding:
    """A verifiable contract defect (or an explicitly non-defect queue item)."""

    finding_id: str
    rule: str
    severity: str
    disposition: str = CONFIRMED
    claim_id: Optional[str] = None
    doc: Optional[str] = None
    locator: Optional[str] = None
    subject: str = ""
    observed: str = ""
    expected: str = ""
    evidence: List[str] = field(default_factory=list)
    verification_method: str = ""
    confidence: str = "high"
    suggested_action: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule": self.rule,
            "severity": self.severity,
            "disposition": self.disposition,
            "claim_id": self.claim_id,
            "doc": self.doc,
            "locator": self.locator,
            "subject": self.subject,
            "observed": self.observed,
            "expected": self.expected,
            "evidence": list(self.evidence),
            "verification_method": self.verification_method,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "tags": list(self.tags),
        }


@dataclass
class AuditItem:
    """R8: a claim that cannot be deterministically checked -> review queue."""

    audit_id: str
    rule: str = "R8"
    claim_id: Optional[str] = None
    doc: Optional[str] = None
    locator: Optional[str] = None
    reason: str = ""
    subject: str = ""
    observed: str = ""
    suggested_action: str = "human review"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "rule": self.rule,
            "claim_id": self.claim_id,
            "doc": self.doc,
            "locator": self.locator,
            "reason": self.reason,
            "subject": self.subject,
            "observed": self.observed,
            "suggested_action": self.suggested_action,
            "tags": list(self.tags),
        }


def make_finding(rule: str, severity: str, subject: str, observed: str, expected: str,
                 disposition: str = CONFIRMED, claim: Optional[Claim] = None,
                 evidence: Optional[List[str]] = None, verification_method: str = "",
                 confidence: str = "high", suggested_action: str = "",
                 tags: Optional[List[str]] = None) -> Finding:
    """Build a Finding with a content-addressed id (dedupe key is rule+claim)."""
    if disposition not in DISPOSITIONS:
        raise ValueError(f"bad disposition: {disposition}")
    if severity not in SEVERITIES:
        raise ValueError(f"bad severity: {severity}")
    claim_id = claim.claim_id if claim is not None else None
    fid = stable_id(
        "F-",
        rule,
        claim_id or "",
        claim.doc if claim is not None else "",
        subject,
        observed,
        expected,
        disposition,
    )
    return Finding(
        finding_id=fid,
        rule=rule,
        severity=severity,
        disposition=disposition,
        claim_id=claim_id,
        doc=claim.doc if claim is not None else None,
        locator=claim.locator if claim is not None else None,
        subject=subject,
        observed=observed,
        expected=expected,
        evidence=list(evidence or []),
        verification_method=verification_method,
        confidence=confidence,
        suggested_action=suggested_action,
        tags=list(tags or []),
    )
