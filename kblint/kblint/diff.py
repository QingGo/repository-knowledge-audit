"""Incremental (baseline) audit diff: classify findings as NEW / PERSISTING / FIXED.

The finding key is *content-based* and deliberately excludes line numbers: two scans of the same
knowledge file after unrelated edits that shift lines still match as PERSISTING. The key is
``(rule, doc, target/observed, expected, subject)``; the locator is used only with its ``#L<number>``
suffix stripped, as a last-resort tiebreaker.

Exit policy: only **NEW** findings with ``disposition == "confirmed"`` and severity at/above
``--fail-on-new`` fail the check. Pre-existing Unknown-class findings (``unresolved``,
``provenance_gap``, ``revalidation_due``) are listed but never block; NEW Unknown-class findings are
listed as non-blocking too.

This module is stdlib-only and never touches the network. CLI:

    python3 -m kblint diff --before <report-dir-or-file> --after <report-dir-or-file> \\
        --out .kblint-diff --format md,json --fail-on-new medium
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import __version__
from .model import SEVERITY_RANK

FORMATS = ("json", "md")
DISPOSITIONS = ("confirmed", "unresolved", "provenance_gap", "revalidation_due")
FAIL_ON_NEW_CHOICES = ("none", "low", "medium", "high")
_LINE_SUFFIX = re.compile(r"#L\d+(?:-L?\d+)?\s*$")


def finding_key(f: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    """Stable content key for a finding (a JSON object) across line shifts.

    Primary fields: rule, doc, observed (which carries the target for R9/R1), expected, subject.
    ``locator`` is included with any ``#L<n>`` suffix removed only as a tiebreaker, so editing
    unrelated lines above a finding does not turn it into NEW/FIXED.
    """
    rule = str(f.get("rule") or "")
    doc = str(f.get("doc") or "")
    observed = str(f.get("observed") or "").strip()
    expected = str(f.get("expected") or "").strip()
    subject = str(f.get("subject") or "").strip()
    locator = _LINE_SUFFIX.sub("", str(f.get("locator") or "")).strip()
    return (rule, doc, observed, expected, subject, locator)


def _finding_sort_key(item: Dict[str, Any]) -> Tuple:
    f = item["finding"]
    return (str(f.get("rule") or ""), str(f.get("doc") or ""),
            str(f.get("locator") or ""), str(f.get("subject") or ""), item["key"])


def load_findings(path: str) -> List[Dict[str, Any]]:
    """Load findings from a scan directory (findings.jsonl) or a JSON/JSONL file.

    An existing empty directory or empty findings file is a valid **empty baseline** (all current
    findings are then NEW). A missing path raises FileNotFoundError so a typo is not mistaken for an
    empty baseline.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"report path not found: {path}")
    if p.is_dir():
        candidate = p / "findings.jsonl"
        if not candidate.exists():
            # an empty report directory is an explicit empty baseline
            return []
        p = candidate
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return []
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("findings", data.get("new", [])) or []
        return [dict(x) for x in data]
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _index(findings: Iterable[Dict[str, Any]]) -> Dict[Tuple, Dict[str, Any]]:
    out: Dict[Tuple, Dict[str, Any]] = {}
    for f in findings:
        if not isinstance(f, dict) or not f.get("rule"):
            continue
        key = finding_key(f)
        # keep the first occurrence per key; duplicate keys are counted as one identity
        out.setdefault(key, f)
    return out


def _is_confirmed(f: Dict[str, Any]) -> bool:
    return str(f.get("disposition") or "confirmed") == "confirmed"


def classify(before: Sequence[Dict[str, Any]], after: Sequence[Dict[str, Any]],
             fail_on_new: str = "medium") -> Dict[str, Any]:
    """Classify findings into NEW / PERSISTING / FIXED and compute the CI blocking set."""
    if fail_on_new not in FAIL_ON_NEW_CHOICES:
        raise ValueError(f"fail_on_new must be one of {FAIL_ON_NEW_CHOICES}, got {fail_on_new!r}")
    b = _index(before)
    a = _index(after)
    rank = SEVERITY_RANK
    threshold = None if fail_on_new == "none" else rank[fail_on_new]

    def blocking(f: Dict[str, Any]) -> bool:
        if threshold is None:
            return False
        return _is_confirmed(f) and rank.get(str(f.get("severity") or "low"), 0) >= threshold

    new_items = [{"key": list(k), "finding": a[k], "blocking": blocking(a[k])}
                 for k in a.keys() - b.keys()]
    fixed_items = [{"key": list(k), "finding": b[k]} for k in b.keys() - a.keys()]
    persisting_items = [{"key": list(k), "finding": a[k], "blocking": False}
                        for k in a.keys() & b.keys()]
    new_items.sort(key=_finding_sort_key)
    fixed_items.sort(key=_finding_sort_key)
    persisting_items.sort(key=_finding_sort_key)

    def disposition_counts(items):
        out = {d: 0 for d in DISPOSITIONS}
        for item in items:
            d = str(item["finding"].get("disposition") or "confirmed")
            out[d] = out.get(d, 0) + 1
        return out

    blocking_n = sum(1 for item in new_items if item["blocking"])
    return {
        "tool": "kblint diff",
        "version": __version__,
        "fail_on_new": fail_on_new,
        "policy": {
            "blocking": "NEW findings with disposition=confirmed and severity >= fail-on-new",
            "unknown_non_blocking": "unresolved / provenance_gap / revalidation_due findings "
                                    "(pre-existing and new) are listed but never block",
        },
        "counts": {
            "before": len(b),
            "after": len(a),
            "new": len(new_items),
            "new_blocking": blocking_n,
            "new_unknown_non_blocking": sum(1 for i in new_items if not _is_confirmed(i["finding"])),
            "persisting": len(persisting_items),
            "fixed": len(fixed_items),
        },
        "dispositions": {
            "new": disposition_counts(new_items),
            "persisting": disposition_counts(persisting_items),
            "fixed": disposition_counts(fixed_items),
        },
        "exit_code": 1 if blocking_n else 0,
        "new": new_items,
        "persisting": persisting_items,
        "fixed": fixed_items,
    }


def _sev(f: Dict[str, Any]) -> str:
    return str(f.get("severity") or "low")


def build_markdown(result: Dict[str, Any], before_path: str, after_path: str) -> str:
    c = result["counts"]
    lines = [
        "# kblint incremental audit",
        "",
        f"- tool: `{result['tool']} {result['version']}`",
        f"- baseline: `{before_path}`",
        f"- current: `{after_path}`",
        f"- fail-on-new: **{result['fail_on_new']}** (only NEW confirmed findings at/above this "
        f"severity block; pre-existing Unknowns never block)",
        "",
        "| classification | findings |",
        "|---|---:|",
        f"| NEW (blocking) | {c['new_blocking']} |",
        f"| NEW (Unknown-class, listed, non-blocking) | {c['new_unknown_non_blocking']} |",
        f"| PERSISTING (pre-existing; non-blocking) | {c['persisting']} |",
        f"| FIXED | {c['fixed']} |",
        f"| before / after totals | {c['before']} / {c['after']} |",
        "",
        "## NEW findings",
        "",
    ]
    if not result["new"]:
        lines.append("_none_")
    else:
        lines += ["| rule | severity | disposition | blocking | locator | subject |",
                  "|---|---|---|---|---|---|"]
        for item in result["new"]:
            f = item["finding"]
            lines.append(f"| {f.get('rule','?')} | {_sev(f)} | {f.get('disposition','?')} | "
                         f"{'**yes**' if item['blocking'] else 'no'} | "
                         f"`{f.get('locator') or '-'}` | {str(f.get('subject') or '')[:160]} |")
    lines += ["", "## PERSISTING findings (pre-existing; listed, never blocking)", ""]
    if not result["persisting"]:
        lines.append("_none_")
    else:
        lines += ["| rule | severity | disposition | locator | subject |",
                  "|---|---|---|---|---|"]
        for item in result["persisting"]:
            f = item["finding"]
            lines.append(f"| {f.get('rule','?')} | {_sev(f)} | {f.get('disposition','?')} | "
                         f"`{f.get('locator') or '-'}` | {str(f.get('subject') or '')[:160]} |")
    lines += ["", "## FIXED findings (present in baseline, absent now)", ""]
    if not result["fixed"]:
        lines.append("_none_")
    else:
        lines += ["| rule | severity | disposition | locator | subject |",
                  "|---|---|---|---|---|"]
        for item in result["fixed"]:
            f = item["finding"]
            lines.append(f"| {f.get('rule','?')} | {_sev(f)} | {f.get('disposition','?')} | "
                         f"`{f.get('locator') or '-'}` | {str(f.get('subject') or '')[:160]} |")
    lines += [
        "",
        "## Honest limits",
        "",
        "- Classification is content-based and line-shift tolerant; the same finding appearing in a "
        "**different doc** is NEW, by design.",
        "- Unknown-class findings (`unresolved`, `provenance_gap`, `revalidation_due`) are not "
        "verified defects and never block CI; they are carried for review.",
        "- `FIXED` means the finding is absent from the current scan (e.g. the reference was "
        "repaired); it does not by itself prove the underlying claim is true.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(out_dir: str, result: Dict[str, Any], before_path: str, after_path: str,
                  formats: Sequence[str]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: Dict[str, str] = {}
    if "json" in formats:
        payload = {
            "schema": "kblint-diff/1",
            "tool": result["tool"],
            "version": result["version"],
            "before": before_path,
            "after": after_path,
            "fail_on_new": result["fail_on_new"],
            "policy": result["policy"],
            "counts": result["counts"],
            "dispositions": result["dispositions"],
            "exit_code": result["exit_code"],
            "new": result["new"],
            "persisting": result["persisting"],
            "fixed": result["fixed"],
        }
        path = out / "diff.json"
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
                        encoding="utf-8")
        written["json"] = str(path)
    if "md" in formats:
        path = out / "diff.md"
        path.write_text(build_markdown(result, before_path, after_path), encoding="utf-8")
        written["md"] = str(path)
    return written
