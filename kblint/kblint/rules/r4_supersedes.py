"""R4 — missing supersedes/deprecation marker.

If a claim cites an artifact and that artifact's value matches the claim, but a
NEWER artifact records a conflicting value for the same unit/key context, and
neither the claim nor its section carries a supersedes/deprecated marker, the
claim is a confirmed "missing supersedes" finding.
"""

from __future__ import annotations

from typing import List

from .base import (ScanContext, best_artifact_match, context_tokens, finding, rel_diff,
                   section_has_supersede_marker, unit_tokens)


def run(ctx: ScanContext) -> List:
    findings = []
    if not ctx.artifacts:
        return findings
    for claim in ctx.claims:
        refs = claim.features.get("artifact_refs") or []
        if not refs:
            continue
        if section_has_supersede_marker(ctx, claim):
            continue
        if not __import__("re").search(r"\b(best|current|latest|record|now|new)\b",
                                       claim.text, __import__("re").IGNORECASE):
            continue
        for number in claim.features.get("numbers", []):
            if number.get("unit") is None:
                continue
            match = best_artifact_match(ctx, claim, number)
            if match is None or not match.exact:
                continue
            unit = number.get("unit")
            anchor_tokens = set(context_tokens(number.get("context"))) | set(unit_tokens(unit))
            newer = []
            for entry in ctx.artifacts.newer_entries(match.entry, unit):
                low = entry.key.lower()
                if not any(t in low for t in anchor_tokens if len(t) >= 3):
                    continue
                old_v = float(number["value"])
                if old_v == 0 or entry.value == 0:
                    continue
                ratio = entry.value / old_v
                if ratio < 0.5 or ratio > 2.0:
                    continue  # different quantity scale, not a superseding measurement
                if rel_diff(entry.value, old_v) > max(ctx.rel_tol(), 5e-3):
                    newer.append(entry)
            if not newer:
                continue
            def family(ref: str) -> str:
                import os
                base = os.path.basename(ref or "")
                return base.split("_", 1)[0]

            same_family = [e for e in newer if family(e.artifact) ==
                           family(match.entry.artifact)]
            if not same_family:
                continue
            newest = sorted(same_family, key=lambda e: (e.mtime or "", e.artifact, e.key))[0]
            findings.append(finding(
                "R4", "medium", claim,
                subject=f"missing supersedes: newer artifact {newest.artifact} contradicts "
                        f"{match.entry.artifact} ({number['value']:g}{unit or ''} vs "
                        f"{newest.value:g}{unit or ''})",
                observed=f"claim cites {match.entry.artifact} ({match.entry.key} = "
                         f"{match.entry.value:g}) and states {number['value']:g}{unit or ''}; "
                         f"newer artifact {newest.artifact} records {newest.value:g} "
                         f"at {newest.key} (mtime {newest.mtime})",
                expected="a claim contradicted by a newer artifact must be marked superseded / "
                         "deprecated (or scoped to its artifact date)",
                evidence=[claim.locator,
                          f"{match.entry.artifact} :: {match.entry.key} (mtime {match.entry.mtime})",
                          f"{newest.artifact} :: {newest.key} (mtime {newest.mtime})"],
                verification_method="artifact chronology (mtime) + value comparison + marker scan",
                suggested_action="add a supersedes/deprecation note or update the claim",
                tags=["supersedes", "lineage", unit or "unit"],
            ))
            break
    return findings
