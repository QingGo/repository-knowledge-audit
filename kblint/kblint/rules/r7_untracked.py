"""R7 — untracked / no-owner knowledge docs (git optional).

- docs under the configured globs that `git ls-files` does not track -> low finding
- tracked docs with uncommitted changes vs HEAD (git status) -> low finding
  (this is the committed-vs-worktree drift surface: a knowledge edit that exists
  only in the working tree)
- docs missing a configured owner frontmatter key -> low finding

If the repo is not a git repository (or git is disabled), the rule self-skips.
"""

from __future__ import annotations

import os
import subprocess
from typing import Dict, List

from .base import ScanContext, finding


def _git(repo: str, *args: str) -> str:
    # core.quotepath=false: without it git C-escapes non-ASCII paths (e.g. docs/商业计划.md ->
    # "docs/\\345\\225..."), so tracked non-ASCII docs never match the raw doc paths and are
    # misreported as untracked. Special-character paths (spaces/quotes) may still be quoted; those
    # are decoded by _unquote_git_path.
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=false", "-C", repo, *args],
                             capture_output=True, text=True, timeout=30)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


_GIT_SIMPLE_ESCAPES = {"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11,
                       '"': 34, "\\": 92}


def _unquote_git_path(path: str) -> str:
    """Decode git's C-style quoted path form (only special characters are quoted once
    core.quotepath=false is set; quoted names may still appear for spaces/quotes/control chars)."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    body = path[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.extend(ch.encode("utf-8", "replace"))
            i += 1
            continue
        i += 1
        if i >= len(body):
            break
        esc = body[i]
        if esc in _GIT_SIMPLE_ESCAPES:
            out.append(_GIT_SIMPLE_ESCAPES[esc])
            i += 1
        elif esc in "01234567":
            digits = ""
            while i < len(body) and len(digits) < 3 and body[i] in "01234567":
                digits += body[i]
                i += 1
            out.append(int(digits, 8) & 0xFF)
        else:
            out.extend(esc.encode("utf-8", "replace"))
            i += 1
    return out.decode("utf-8", "replace")


def _first_claim(ctx: ScanContext, doc: str):
    claims = ctx.claims_of(doc)
    return claims[0] if claims else None


def run(ctx: ScanContext) -> List:
    findings = []
    if not ctx.cfg.git.get("enabled", True):
        return findings
    repo = ctx.repo
    if not os.path.isdir(os.path.join(repo, ".git")):
        return findings
    tracked = {_unquote_git_path(x) for x in _git(repo, "ls-files").splitlines() if x}
    if not tracked:
        return findings
    status: Dict[str, str] = {}
    for line in _git(repo, "status", "--porcelain").splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = _unquote_git_path(path)
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        status[path.replace(os.sep, "/")] = code
    owner_keys = (ctx.cfg.owner or {}).get("frontmatter_keys") or []
    for doc in sorted(ctx.doc_meta):
        claim = _first_claim(ctx, doc)
        if doc not in tracked:
            findings.append(finding(
                "R7", "low", claim,
                subject=f"knowledge doc not tracked in git: {doc}",
                observed=f"{doc} matches the configured docs globs but is absent from "
                         f"`git ls-files`",
                expected="knowledge docs should be version-controlled so claims have provenance",
                evidence=[doc, "git -C <repo> ls-files: absent", "git status: ?? (untracked)"],
                verification_method="git ls-files / git status",
                disposition="provenance_gap",
                suggested_action="commit the doc (or add it to .gitignore and declare it non-knowledge)",
                tags=["git", "untracked"],
            ))
            continue
        code = status.get(doc)
        if code and code != "??":
            findings.append(finding(
                "R7", "low", claim,
                subject=f"uncommitted change to tracked knowledge doc: {doc}",
                observed=f"git status --porcelain reports {code!r} for {doc}; the working-tree "
                         f"version differs from HEAD",
                expected="knowledge edits that change contracts should be committed (or explicitly "
                         "scoped) so readers see a stable claim/provenance boundary",
                evidence=[doc, f"git status --porcelain: {code} {doc}"],
                verification_method="git status working-tree vs HEAD comparison (doc level)",
                suggested_action="commit the doc change, or revert it if it was a probe",
                tags=["git", "committed-vs-worktree"],
            ))
        if owner_keys:
            fm = ctx.doc_meta[doc].get("frontmatter", {})
            if not any(k in fm for k in owner_keys):
                findings.append(finding(
                    "R7", "low", claim,
                    subject=f"missing owner metadata in {doc}",
                    observed=f"no frontmatter key among {owner_keys} in {doc}",
                    expected="configured owner keys must be present where the convention is declared",
                    evidence=[doc, f"frontmatter keys: {sorted(fm)}"],
                    verification_method="frontmatter key lookup",
                    disposition="unresolved",
                    suggested_action="add the configured owner key to the frontmatter",
                    tags=["owner"],
                ))
    return findings
