"""R1 — version/pin consistency: doc-declared env pin vs configured artifact field.

Config: pins[] with doc_glob, artifact_glob, artifact_keys[] (field suffixes),
doc_patterns[] (regexes with capture group 1 = declared version).
- artifact has a different pin -> confirmed
- artifact exists but has no configured pin field -> provenance_gap (queued)
"""

from __future__ import annotations

import re
from typing import Dict, List

from ..config import glob_match
from .base import ScanContext, finding

VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:\+[A-Za-z0-9]+)?|\d+(?:\.\d+){1,3})")


def _artifact_pin(art, keys: List[str]) -> Dict[str, str]:
    """Return key->pin strings for configured artifact_keys (suffix match)."""
    out: Dict[str, str] = {}
    for key in keys:
        k = key.lower()
        for full, val in getattr(art, "strings", {}).items():
            low = full.lower()
            if low == k or low.endswith("." + k) or low.endswith("[" + k + "]"):
                out[full] = val
    return out


def run(ctx: ScanContext) -> List:
    findings = []
    if not ctx.cfg.pins:
        return findings
    for spec in ctx.cfg.pins:
        doc_glob = spec.get("doc_glob", "**/*.md")
        art_glob = spec.get("artifact_glob")
        keys = spec.get("artifact_keys") or []
        patterns = spec.get("doc_patterns") or []
        names = spec.get("names")
        if not keys or not patterns:
            continue
        arts = []
        for art in ctx.artifacts.artifacts:
            rel = art.path or art.ref
            if art_glob and not any(glob_match(rel, g) for g in _as_globs(art_glob)):
                continue
            arts.append(art)
        if not arts:
            continue
        # configured artifact pin pool: per key -> Counter(version string)
        from collections import Counter
        pool: Dict[str, Counter] = {k: Counter() for k in keys}
        for art in arts:
            pins = _artifact_pin(art, keys)
            for key, val in pins.items():
                ver = _version_of(val)
                if ver:
                    pool[_base_key(key, keys)][_version_key(ver)] += 1
        seen = set()
        for claim in ctx.claims:
            if not glob_match(claim.doc, doc_glob):
                continue
            for pat in patterns:
                try:
                    m = re.search(pat, claim.text, re.IGNORECASE)
                except re.error:
                    continue
                if not m:
                    continue
                declared = m.group(1) if m.groups() else m.group(0)
                decl_key = _version_key(declared)
                dedupe_key = (claim.doc, decl_key)
                if dedupe_key in seen:
                    continue
                for key in keys:
                    counts = pool.get(key, Counter())
                    distinct = sorted(counts)
                    if not distinct:
                        continue
                    if len(distinct) >= 2:
                        # mixed environment: the doc pin necessarily conflicts with some
                        # artifacts; this is an unresolved scope conflict, not a defect.
                        seen.add(dedupe_key)
                        counts_str = ", ".join(f"{v}×{counts[v]}" for v in distinct)
                        findings.append(finding(
                            "R1", "low", claim,
                            subject=f"mixed artifact environments for pin {decl_key!r}: "
                                    f"doc declares {declared}; pool contains {counts_str}",
                            observed=f"doc declares {declared}; matching artifacts record "
                                     f"{counts_str}",
                            expected="a doc pin is only verifiable when the governed artifact "
                                     "pool has a single environment, or the pin is scoped per "
                                     "round/device; mixed pools are an unresolved scope conflict",
                            evidence=[claim.locator,
                                      f"artifact pool values: {counts_str}"],
                            verification_method="artifact pool pin-value distribution",
                            disposition="unresolved",
                            confidence="medium",
                            suggested_action="scope the pin to the round/device environment, "
                                             "or record both environments explicitly",
                            tags=["pin", "version", "mixed-environment"],
                        ))
                        break
                    if len(distinct) == 1 and distinct[0] != decl_key:
                        seen.add(dedupe_key)
                        findings.append(finding(
                            "R1", "high", claim,
                            subject=f"env pin {declared!r} vs single artifact environment "
                                    f"{distinct[0]!r}",
                            observed=f"doc declares {declared}; all matching artifacts record "
                                     f"{distinct[0]}",
                            expected="a doc-declared environment pin must match every configured "
                                     "artifact it governs",
                            evidence=[claim.locator,
                                      f"artifact pool values: {distinct[0]}×{counts[distinct[0]]}"],
                            verification_method="single-environment artifact pin field match",
                            suggested_action="fix the artifact/doc pin",
                            tags=["pin", "version"],
                        ))
                        break
    return findings


def _base_key(key: str, keys: List[str]) -> str:
    low = key.lower()
    for k in keys:
        if low == k or low.endswith("." + k):
            return k
    return key


def _as_globs(g) -> List[str]:
    return g if isinstance(g, list) else [g]


def _version_of(s: str) -> str:
    m = VERSION_RE.search(str(s))
    return m.group(1) if m else ""


def _version_key(v: str) -> str:
    return v.split("+", 1)[0]
