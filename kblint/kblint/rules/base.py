"""Rule base: scan context, artifact index, matching helpers, finding factory."""

from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config, discover_paths, glob_match
from ..extract import norm_key
from ..model import Claim, Finding, make_finding

# unit family -> tokens that identify the same measured quantity inside artifact keys
UNIT_TOKENS: Dict[str, Tuple[str, ...]] = {
    "%": ("pct", "percent", "share", "mfu", "util"),
    "ms": ("ms", "_ms", "millisecond", "step_ms", "latency"),
    "s": ("sec", "_s", "second"),
    "tflops": ("tflops", "tflop/s", "tf/s", "flops"),
    "tflop/s": ("tflops", "tflop/s", "tf/s", "flops"),
    "tf/s": ("tflops", "tflop/s", "tf/s", "flops"),
    "tokens": ("tokens", "tok"),
    "tok/s": ("tokens_per_s", "tok", "tokens"),
    "gib": ("gib", "memory", "mem"),
    "mib": ("mib", "memory"),
    "gb": ("gb", "memory", "mem"),
    "mb": ("mb", "memory"),
    "kernels": ("kernels", "kernel"),
    "variants": ("variants", "variant"),
    "params": ("params", "param"),
    "pp": ("pp", "pct_point", "diff_pp"),
}

SKIP_SECTION_MARKERS = re.compile(
    r"historical|deprecated|superseded|obsolete|old plan|previous|legacy", re.I)


def unit_tokens(unit: Optional[str]) -> Tuple[str, ...]:
    if not unit:
        return ()
    u = unit.lower()
    if u in UNIT_TOKENS:
        return UNIT_TOKENS[u]
    return (u.replace("%", "pct"),)


def context_tokens(context: Optional[str]) -> List[str]:
    if not context:
        return []
    toks = [t for t in re.split(r"[^a-z0-9]+", context.lower())
            if len(t) >= 2 and not t.isdigit()]
    from ..extract import STOPWORDS
    return [t for t in toks if t not in STOPWORDS][-4:]


@dataclass
class ArtifactEntry:
    artifact: str          # repo-relative path or configured artifact id
    key: str               # dotted/bracket key path inside the artifact
    value: float
    mtime: Optional[str] = None
    row: Optional[int] = None


@dataclass
class Artifact:
    ref: str               # canonical id used in evidence (file field or path)
    path: Optional[str]    # repo-relative path if known
    entries: List[ArtifactEntry] = field(default_factory=list)
    mtime: Optional[str] = None
    strings: Dict[str, str] = field(default_factory=dict)


class ArtifactIndex:
    """Flattened numeric index over configured artifacts / run-index rows."""

    def __init__(self, artifacts: Optional[List[Artifact]] = None,
                 unit_index: Optional[Dict[str, List[ArtifactEntry]]] = None):
        self.artifacts = artifacts or []
        self.unit_index = unit_index or {}
        self._all: List[ArtifactEntry] = [e for a in self.artifacts for e in a.entries]

    def __bool__(self) -> bool:
        return bool(self._all) or bool(self.artifacts)

    @property
    def entries(self) -> List[ArtifactEntry]:
        return self._all

    def entries_for_unit(self, unit: Optional[str]) -> List[ArtifactEntry]:
        toks = unit_tokens(unit)
        if not toks:
            return self._all
        out: List[ArtifactEntry] = []
        for tok in toks:
            out.extend(self.unit_index.get(tok, []))
        seen = set()
        uniq = []
        for e in out:
            key = (e.artifact, e.key, e.value)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)
        return uniq

    def artifacts_of(self, ref: str) -> List[Artifact]:
        base = os.path.basename(ref)
        return [a for a in self.artifacts if a.ref == ref or (a.path and
                (a.path == ref or os.path.basename(a.path) == base))]

    def newer_entries(self, entry: ArtifactEntry, unit: Optional[str]) -> List[ArtifactEntry]:
        """Entries with the same unit family from artifacts newer than `entry`."""
        if not entry.mtime:
            return []
        out = []
        for e in self.entries_for_unit(unit):
            if e.artifact == entry.artifact or not e.mtime:
                continue
            if e.mtime > entry.mtime:
                out.append(e)
        return out


def _add_numeric(entries: List[ArtifactEntry], artifact: str, key: str, value: float,
                 mtime: Optional[str], row: Optional[int]) -> None:
    entries.append(ArtifactEntry(artifact=artifact, key=key, value=value,
                                 mtime=mtime, row=row))


def flatten_numeric(obj: Any, prefix: str, artifact: str, mtime: Optional[str],
                    out: List[ArtifactEntry], row: Optional[int] = None,
                    depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(obj, dict):
        for k in obj:
            flatten_numeric(obj[k], f"{prefix}.{k}" if prefix else str(k),
                            artifact, mtime, out, row, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten_numeric(v, f"{prefix}[{i}]", artifact, mtime, out, row, depth + 1)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        _add_numeric(out, artifact, prefix or "value", float(obj), mtime, row)
    elif isinstance(obj, str) and re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", obj.strip()):
        _add_numeric(out, artifact, prefix or "value", float(obj.strip()), mtime, row)


def flatten_strings(obj: Any, prefix: str, out: Dict[str, str], depth: int = 0) -> None:
    """Collect leaf string fields (env pins etc.) with dotted key paths."""
    if depth > 12:
        return
    if isinstance(obj, dict):
        for k in obj:
            flatten_strings(obj[k], f"{prefix}.{k}" if prefix else str(k), out, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten_strings(v, f"{prefix}[{i}]", out, depth + 1)
    elif isinstance(obj, str):
        val = obj.strip()
        if val and len(val) <= 200:
            out[prefix or "value"] = val


def _load_artifact_file(repo: str, rel: str) -> Any:
    path = os.path.join(repo, rel)
    try:
        if rel.endswith(".jsonl"):
            rows = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            return rows
        if rel.endswith(".csv"):
            with open(path, encoding="utf-8", newline="") as f:
                return [dict(r) for r in csv.DictReader(f)]
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _mtime_str(repo: str, rel: str) -> Optional[str]:
    try:
        import datetime
        ts = os.path.getmtime(os.path.join(repo, rel))
        return datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return None


def build_artifact_index(repo: str, cfg: Config, run_index_rows: Optional[List[Dict[str, Any]]] = None) -> ArtifactIndex:
    """Build flattened artifact index from configured artifacts and/or run index."""
    artifacts: List[Artifact] = []
    unit_index: Dict[str, List[ArtifactEntry]] = {}

    def add_artifact(art: Artifact) -> None:
        artifacts.append(art)
        for e in art.entries:
            low = e.key.lower()
            for tok in set([t for t in re.split(r"[^a-z0-9/]+", low) if t]):
                unit_index.setdefault(tok, []).append(e)
            for tok in re.findall(r"[a-z][a-z0-9_/]*", low):
                unit_index.setdefault(tok, []).append(e)
        # also index the numeric string form: "mfu" etc.

    # 1) explicit artifact globs
    if cfg.artifacts:
        for rel in discover_paths(repo, cfg.artifacts, exclude=cfg.exclude):
            data = _load_artifact_file(repo, rel)
            if data is None:
                continue
            entries: List[ArtifactEntry] = []
            strings: Dict[str, str] = {}
            flatten_numeric(data, "", rel, _mtime_str(repo, rel), entries)
            flatten_strings(data, "", strings)
            if entries or strings:
                add_artifact(Artifact(ref=rel, path=rel, entries=entries,
                                      mtime=_mtime_str(repo, rel), strings=strings))

    # 2) run index rows (each row may point at a file; load it lazily/eagerly)
    if cfg.run_index and run_index_rows:
        ri = cfg.run_index
        file_field = ri.get("file_field", "file")
        id_field = ri.get("id_field", "run_id")
        for row in run_index_rows:
            rel = row.get(file_field)
            ref = str(row.get(id_field) or rel or "?")
            mtime = row.get("mtime") or row.get("date")
            entries: List[ArtifactEntry] = []
            strings: Dict[str, str] = {}
            flatten_numeric(row, "", ref, mtime, entries)
            flatten_strings(row, "", strings)
            path = None
            if isinstance(rel, str) and rel.endswith((".json", ".jsonl", ".csv")):
                if os.path.exists(os.path.join(repo, rel)):
                    loader = _load_artifact_file(repo, rel)
                    if loader is not None:
                        flatten_numeric(loader, "", ref, mtime, entries)
                        flatten_strings(loader, "", strings)
                    path = rel
            if entries or strings:
                add_artifact(Artifact(ref=ref, path=path, entries=entries, mtime=mtime,
                                      strings=strings))

    # dedupe artifact refs (e.g. run-index row and explicit glob for same file)
    by_ref: Dict[str, Artifact] = {}
    for art in artifacts:
        key = art.path or art.ref
        if key in by_ref:
            for e in art.entries:
                if not any((x.key, x.value) == (e.key, e.value) for x in by_ref[key].entries):
                    by_ref[key].entries.append(e)
        else:
            by_ref[key] = art
    artifacts = [by_ref[k] for k in sorted(by_ref)]
    return ArtifactIndex(artifacts=artifacts, unit_index=unit_index)


@dataclass
class Match:
    entry: ArtifactEntry
    exact: bool
    unique_near: bool = False


@dataclass
class ScanContext:
    repo: str
    cfg: Config
    claims: List[Claim]
    doc_meta: Dict[str, Any]
    artifacts: ArtifactIndex
    run_index_rows: List[Dict[str, Any]] = field(default_factory=list)
    now: str = ""
    findings: List[Finding] = field(default_factory=list)
    audit: List[Dict[str, Any]] = field(default_factory=list)
    matched_claims: Dict[str, str] = field(default_factory=dict)  # claim_id -> evidence
    stats: Dict[str, int] = field(default_factory=dict)

    def add(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def rel_tol(self) -> float:
        return self.cfg.relative_tolerance

    def claims_of(self, doc: str) -> List[Claim]:
        return [c for c in self.claims if c.doc == doc]


def rel_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def _key_tokens(key: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", key.lower()) if len(t) >= 2]


SPECIFIC_UNITS = {"tflops", "tflop/s", "tf/s", "tokens", "tok/s", "variants",
                  "kernels", "params", "gib", "mib", "gb/s", "pp"}


def _context_overlap(number: Dict[str, Any], entry: ArtifactEntry) -> bool:
    """Strict key-context overlap: a non-generic context token appears in the key."""
    from ..extract import STOPWORDS
    tokens = [t for t in context_tokens(number.get("context"))
              if len(t) >= 3 and t not in STOPWORDS]
    if not tokens:
        return False
    key_toks = set(_key_tokens(entry.key))
    for tok in tokens:
        if tok in key_toks:
            return True
        if any(tok in k for k in key_toks if len(k) >= 3):
            return True
    return False


def best_artifact_match(ctx: ScanContext, claim: Claim, number: Dict[str, Any]) -> Optional[Match]:
    """Find the artifact entry the claim number most likely refers to.

    Deterministic preference: (1) exact value within tolerance (any unit-compatible
    entry; all entries when the number has no unit), (2) cited artifacts with a
    strict key-context match (candidate for artifact_mismatch), (3) for specific
    units only, a unique near-value (+/-5%) elsewhere in the index (candidate for a
    pointer-less mismatch). Otherwise None -> revalidation queue.
    """
    value = float(number["value"])
    unit = number.get("unit")
    tol = ctx.rel_tol()
    refs = claim.features.get("artifact_refs") or []
    unit_entries = ctx.artifacts.entries_for_unit(unit) if unit else []
    cited: List[ArtifactEntry] = []
    for ref in refs:
        for art in ctx.artifacts.artifacts_of(ref):
            cited.extend(art.entries)
    search_pool = cited or unit_entries or (ctx.artifacts.entries if unit is None else [])
    if not search_pool:
        return None

    # (1) exact / within-tolerance value anywhere plausible
    value_hits = [e for e in search_pool if rel_diff(e.value, value) <= tol]
    if value_hits:
        hit = sorted(value_hits, key=lambda e: (e.artifact, e.key))[0]
        return Match(entry=hit, exact=True)

    # (2) cited artifacts: strict key-context match -> mismatch candidate
    if cited:
        strict = [e for e in cited if _context_overlap(number, e)]
        if not strict and unit in SPECIFIC_UNITS:
            toks = unit_tokens(unit)
            strict = [e for e in cited if any(t in _key_tokens(e.key) for t in toks)]
        if strict:
            nearest = sorted(strict, key=lambda e: (rel_diff(e.value, value),
                                                    e.artifact, e.key))[0]
            return Match(entry=nearest, exact=False)

    # (3) pointer-less claim: unique near-value on a specific unit -> mismatch candidate
    if not refs and unit in SPECIFIC_UNITS and unit_entries:
        near = [e for e in unit_entries if rel_diff(e.value, value) <= 0.05]
        arts = {e.artifact for e in near}
        if len(arts) == 1 and near:
            nearest = sorted(near, key=lambda e: (rel_diff(e.value, value),
                                                  e.artifact, e.key))[0]
            return Match(entry=nearest, exact=False, unique_near=True)
    return None


def context_anchor(number: Dict[str, Any]) -> Tuple[str, str]:
    unit = (number.get("unit") or "").lower()
    toks = context_tokens(number.get("context"))
    return unit, " ".join(toks[-4:])


def section_has_supersede_marker(ctx: ScanContext, claim: Claim) -> bool:
    if claim.features.get("markers", {}).get("supersedes"):
        return True
    return bool(SKIP_SECTION_MARKERS.search(claim.section or ""))


def finding(rule: str, severity: str, claim: Claim, subject: str, observed: str,
            expected: str, evidence: List[str], verification_method: str,
            disposition: str = "confirmed", confidence: str = "high",
            suggested_action: str = "", tags: Optional[List[str]] = None) -> Finding:
    return make_finding(rule, severity, subject, observed, expected,
                        disposition=disposition, claim=claim, evidence=evidence,
                        verification_method=verification_method, confidence=confidence,
                        suggested_action=suggested_action, tags=tags)
