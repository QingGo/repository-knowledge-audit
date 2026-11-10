"""R2 — number provenance against the configured artifact index.

For every claim number with a unit (or with an artifact pointer):
  1. exact/threshold match anywhere in the index -> verified (claim recorded as checked)
  2. a same-unit / same-key-context artifact field disagrees beyond tolerance:
       - claim cites that artifact -> confirmed artifact_mismatch
       - claim cites nothing -> revalidation_due (queue; never a confirmed defect)
  3. nothing plausible found -> revalidation_due (queue)
"""

from __future__ import annotations

import os
import re
from typing import List, Optional

from .base import (ArtifactEntry, ScanContext, _context_overlap, best_artifact_match,
                   context_tokens, finding, rel_diff, unit_tokens)

TARGET_LANGUAGE = re.compile(
    r"\b(target|targets|reaching|reach|budget|goal|goals|ceiling|required|requires|"
    r"away|headroom|theoretical|extrapolat\w*|what-if|projection)\b", re.IGNORECASE)


def display_half_unit(raw: Optional[str]) -> Optional[float]:
    """Half of the last displayed place: 655->0.5, 358.8->0.05, 1.02->0.005."""
    if not raw:
        return None
    s = str(raw).strip()
    if "e" in s.lower():
        return None
    if "." in s:
        return 0.5 * (10 ** -len(s.split(".", 1)[1]))
    return 0.5


def within_display_precision(doc_value: float, artifact_value: float, raw: Optional[str],
                             rel_tol: float) -> bool:
    if rel_diff(artifact_value, doc_value) <= rel_tol:
        return True
    half = display_half_unit(raw)
    if half is None:
        return False
    return abs(artifact_value - doc_value) <= half + 1e-12


def _target_language_near(claim_text: str, raw: Optional[str]) -> bool:
    if not raw:
        return bool(TARGET_LANGUAGE.search(claim_text))
    idx = claim_text.find(str(raw))
    if idx < 0:
        return bool(TARGET_LANGUAGE.search(claim_text))
    window = claim_text[max(0, idx - 90): idx + len(str(raw)) + 40]
    return bool(TARGET_LANGUAGE.search(window))


GENERIC_CONTEXT = {"raw", "ms", "step", "steps", "base", "config", "configs", "run", "runs",
                   "head", "path", "host", "gave", "pushed", "measured", "rounds", "round",
                   "interleaved", "session", "stack", "tools", "setup", "another", "moved",
                   "value", "values", "more", "less", "small", "large", "true", "false",
                   "best", "current", "latest", "new", "old", "with", "from", "into"}


def _context_match_count(number, entry: ArtifactEntry) -> int:
    """Number of non-generic context tokens that match the artifact key path."""
    key_toks = set(t for t in re.split(r"[^A-Za-z0-9]+", entry.key.lower()) if len(t) >= 2)
    ctx = [t for t in context_tokens(number.get("context"))
           if len(t) >= 3 and t not in GENERIC_CONTEXT]
    n = 0
    for t in ctx:
        if t in key_toks or any(t in k for k in key_toks if len(k) >= 3):
            n += 1
    return n


def _best_candidate_ok(claim, number, entry: ArtifactEntry) -> bool:
    """The located field must be the best candidate for this claim's unit/context.

    Requires >=2 matching non-generic context tokens (e.g. the 358.8 case matches
    `dw13` + `tile(s)` in `results.dw13_tiles...triton_fp8_tflops`); a single generic
    token match (e.g. `raw` vs `raw_bf16_mfu_pct`) is queued, not confirmed.
    """
    key_toks = set(t for t in re.split(r"[^A-Za-z0-9]+", entry.key.lower()) if len(t) >= 2)
    unit_ok = number.get("unit") is None or any(
        t in key_toks for t in unit_tokens(number.get("unit")))
    if not unit_ok:
        return False
    return _context_match_count(number, entry) >= 2


def _checkable(number) -> bool:
    return number.get("unit") is not None


def run(ctx: ScanContext) -> List:
    findings = []
    if not ctx.artifacts:
        return findings
    for claim in ctx.claims:
        numbers = [n for n in claim.features.get("numbers", []) if _checkable(n)]
        if not numbers:
            continue
        refs = claim.features.get("artifact_refs") or []
        mismatch = None
        unmatched = None
        verified = 0
        for number in numbers:
            entry = None
            # prefer a context-matched field inside the cited artifacts (FIX-2 best
            # candidate); only fall back to a blind value search when none exists
            if refs:
                pool = []
                for ref in refs:
                    for art in ctx.artifacts.artifacts_of(ref):
                        pool.extend(art.entries)
                toks = unit_tokens(number.get("unit"))
                strong = [e for e in pool
                          if _context_match_count(number, e) >= 2
                          and (number.get("unit") is None or
                               any(t in set(re.split(r"[^A-Za-z0-9]+", e.key.lower()))
                                   for t in toks))]
                if strong:
                    entry = sorted(strong, key=lambda e: (rel_diff(e.value, float(number["value"])),
                                                          e.artifact, e.key))[0]
                    if within_display_precision(float(number["value"]), entry.value,
                                                number.get("raw"), ctx.rel_tol()):
                        verified += 1
                        ctx.matched_claims[claim.claim_id] = (
                            f"{entry.artifact} :: {entry.key} = {entry.value}")
                        continue
                    if _target_language_near(claim.text, number.get("raw")) or \
                            not _best_candidate_ok(claim, number, entry):
                        if unmatched is None:
                            unmatched = number
                        continue
                    if mismatch is None:
                        mismatch = (number, entry,
                                    rel_diff(entry.value, float(number["value"])))
                    continue
            match = best_artifact_match(ctx, claim, number)
            if match is None:
                if unmatched is None:
                    unmatched = number
                continue
            inherited_only = bool(refs) and not any(
                os.path.basename(r) in claim.text for r in refs) if False else False
            if match.exact or within_display_precision(
                    float(number["value"]), match.entry.value, number.get("raw"),
                    ctx.rel_tol()):
                verified += 1
                ctx.matched_claims[claim.claim_id] = (
                    f"{match.entry.artifact} :: {match.entry.key} = {match.entry.value}")
                continue
            # FIX-2: a confirmed mismatch needs a direct pointer, a best-candidate
            # field, and no threshold/target language around the number.
            if not refs or _target_language_near(claim.text, number.get("raw")):
                if unmatched is None:
                    unmatched = number
                continue
            # a table row that does not itself name the artifact relies on paragraph-
            # inherited pointers: require strong (>=2 token) context before confirming
            names_artifact = any(os.path.basename(r) in claim.text
                                 for r in refs)
            if claim.form == "table_row" and not names_artifact:
                if unmatched is None:
                    unmatched = number
                continue
            if not _best_candidate_ok(claim, number, match.entry):
                if unmatched is None:
                    unmatched = number
                continue
            if mismatch is None:
                mismatch = (number, match.entry,
                            rel_diff(match.entry.value, float(number["value"])))
        if mismatch is not None:
            number, entry, diff = mismatch
            severity = "high" if diff > 0.01 else "medium"
            findings.append(finding(
                "R2", severity, claim,
                subject=f"artifact_mismatch: {number['value']:g}{number.get('unit') or ''} vs "
                        f"{entry.key} = {entry.value:g}",
                observed=f"claim states {number['value']:g}{number.get('unit') or ''} "
                         f"({number.get('context') or 'no context'}); "
                         f"{entry.artifact} :: {entry.key} = {entry.value:g}",
                expected=f"the cited artifact field must agree within display precision "
                         f"(half last place {display_half_unit(number.get('raw'))}) or relative "
                         f"tolerance {ctx.rel_tol():g} (observed relative difference {diff:.2e})",
                evidence=[claim.locator, f"{entry.artifact} :: {entry.key}",
                          f"relative difference = {diff:.4%}"],
                verification_method="cited artifact field lookup + display-precision / relative tolerance",
                confidence=("high" if any(os.path.basename(r) in claim.text for r in refs)
                            else "medium"),
                suggested_action="fix the doc number or cite the artifact that actually produced it",
                tags=["number", "provenance", "artifact-mismatch"]
                     + ([] if any(os.path.basename(r) in claim.text for r in refs)
                        else ["inherited-pointer"]),
            ))
        elif unmatched is not None and verified == 0:
            findings.append(finding(
                "R2", "low", claim,
                subject=f"number not located in artifact index: "
                        f"{unmatched['value']:g}{unmatched.get('unit') or ''}",
                observed=f"claim number {unmatched['value']:g}{unmatched.get('unit') or ''} "
                         f"({unmatched.get('context') or 'no context'}) has no matching artifact "
                         f"value (displaying {unmatched.get('raw')!r})",
                expected="a measured number should be reproducible from a configured artifact",
                evidence=[claim.locator],
                verification_method="artifact index search (no display-precision match)",
                disposition="revalidation_due",
                suggested_action="attach an artifact pointer or revalidate the number",
                tags=["number", "revalidation"],
            ))
    return findings
