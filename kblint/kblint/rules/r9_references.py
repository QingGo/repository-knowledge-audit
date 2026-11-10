"""R9 — reference check: KB claims that point at repository artifacts which do not exist.

Deterministic, stdlib-only, no network, no clock. Covers four reference surfaces:

  (a) local markdown links ``[text](relpath)``;
  (b) backticked repo-relative file paths (``docs/foo.md``, ``compiler/pipeline/__init__.py``);
  (c) ``make <target>`` when the repo has a root ``Makefile``;
  (d) ``npm|pnpm|yarn run <script>`` when the repo has a root ``package.json``.

Conservative by construction (false positives are worse than missed findings for a contract
linter):

- only *relative* references are checked; URLs, mailto/anchor links, absolute paths, globs,
  placeholders (``{}`` ``<>`` ``$``), shell variables, URL-encoded targets and paths that escape
  the repo root are ignored;
- backticked paths must contain a ``/`` and a recognised file extension (bare filenames and
  directory names are not checked);
- markdown *links* and backticked *paths* are checked only outside fenced code blocks (fences
  often contain tree diagrams / pasted output); ``make``/package-manager invocations are checked
  in fenced code too, because that is where run commands normally live, but lines containing
  box-drawing tree characters are skipped;
- a reference is only flagged when it is absent from **both** the doc-relative and the repo-root
  resolution (so a repo-root path written from a nested doc is not a false positive);
- ``references.allow_missing`` regexes and ``references.inventory`` globs suppress known
  external/generated references; configured ``exclude`` globs are never checked;
- make/npm checks self-skip unless the repo actually ships a root ``Makefile``/``package.json``;
- lines carrying illustrative markers (``e.g.``, ``for example``, ``such as`` …) are skipped for
  path/link checks, and markdown links must look path-like (a slash or an extension), because
  convention docs often cite *other projects'* paths as examples — the dominant FP class measured
  on real repositories (see R9_REPORT.md).

Finding attribution: one confirmed finding per (doc, target) occurrence, with the doc path and a
line locator. R9 findings are not defects of the *content* — they are broken evidence pointers.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import glob_match
from ..model import Finding
from .base import ScanContext, finding

TREE_CHARS = re.compile(r"[│├└┬┼┴┌┐┘┏┓┗┛━┃]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MD_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]*)\)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
MAKE_RE = re.compile(r"(?<![\w./-])make\s+([A-Za-z0-9][A-Za-z0-9_.:-]*)")
NPM_RUN_RE = re.compile(r"\b(?:npm|pnpm|yarn)\s+run\s+([A-Za-z0-9][A-Za-z0-9_:.-]*)")
PATH_CANDIDATE_RE = re.compile(
    r"^(?:\.\.?/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8}$")
PHONY_RE = re.compile(r"^\.PHONY\s*:\s*(.+)$")
# "e.g. `layouts/page.html`" style lines describe an illustrative/other-project artifact, not a
# claim about THIS repo; they are the dominant false-positive class on convention-heavy AGENTS.md.
ILLUSTRATIVE_MARKERS = re.compile(
    r"\b(e\.g\.|for example|for instance|such as|example[s]?[:\s])|例如|示例|比如|举例",
    re.IGNORECASE)

# conservative delimiter set: any of these means "not a concrete repo path"
BAD_TARGET_CHARS = set("*?{}<>$|[]~\\\"'")

ALLOWED_EXTS = {
    "md", "markdown", "rst", "txt", "py", "pyi", "ipynb", "json", "jsonl", "csv", "tsv",
    "yaml", "yml", "toml", "ini", "cfg", "conf", "sh", "bash", "zsh", "fish", "ps1",
    "log", "js", "mjs", "cjs", "ts", "tsx", "jsx", "css", "scss", "html", "vue", "svelte",
    "rs", "go", "java", "kt", "kts", "c", "h", "cc", "cpp", "hpp", "rb", "php", "sql",
    "proto", "lock", "txt", "tex", "bib", "pdf", "png", "svg", "jpg", "jpeg", "gif",
    "webp", "npy", "npz", "pt", "pth", "onnx", "safetensors", "bin", "patch", "diff",
}

KIND_SEVERITY = {"link": "medium", "path": "medium", "make": "low", "npm": "low"}
KIND_LABEL = {"link": "markdown link", "path": "file path", "make": "make target",
              "npm": "package script"}
KIND_ACTION = {
    "link": "fix the link target (or update it to a repo-relative path that exists)",
    "path": "fix the path or add the referenced artifact (or allow_missing it if external)",
    "make": "fix the target name, add the target to the root Makefile, or allow_missing it",
    "npm": "fix the script name or add it to package.json scripts",
}


# --------------------------------------------------------------------------- manifests
def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _make_targets(repo: str) -> Optional[set]:
    """Root-Makefile targets; None when the repo has no root Makefile."""
    path = os.path.join(repo, "Makefile")
    if not os.path.isfile(path):
        return None
    text = _read_text(path) or ""
    targets = set()
    for line in text.splitlines():
        if not line or line[0] in "\t#" or line.lstrip().startswith("#"):
            continue
        m = PHONY_RE.match(line.strip())
        if m:
            for tok in m.group(1).split():
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tok):
                    targets.add(tok)
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s+[A-Za-z0-9_.-]+)*\s*::?(?!=)(?:\s|$)", line)
        if m:
            targets.add(m.group(1))
    return targets


def _npm_scripts(repo: str) -> Optional[set]:
    """Root package.json script names; None when the repo has no root package.json."""
    path = os.path.join(repo, "package.json")
    if not os.path.isfile(path):
        return None
    text = _read_text(path) or ""
    try:
        data = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return set(scripts) if isinstance(scripts, dict) else None


# --------------------------------------------------------------------------- extraction
def _iter_lines(text: str) -> Iterable[Tuple[int, bool, str]]:
    """(1-based line number, inside-fence, line) — deterministic fence tracking."""
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            yield i, in_fence, line
            continue
        yield i, in_fence, line


def _clean_link_target(raw: str) -> Optional[str]:
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<"):
        end = target.find(">")
        if end < 0:
            return None
        target = target[1:end]
    else:
        target = target.split()[0]  # drop an optional markdown title
    if not target:
        return None
    low = target.lower()
    if low.startswith(("http://", "https://", "mailto:", "ftp://", "ftps://", "tel:",
                       "sms:", "irc:", "data:", "javascript:", "file:")):
        return None
    if target.startswith(("/", "#", "//")) or "%" in target:
        return None
    # anchors/queries are not part of the path; strip them before the placeholder guard so a
    # normal `#L10` fragment or `?raw=1` query is not mistaken for a glob/placeholder.
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or target in (".", ".."):
        return None
    if any(ch in BAD_TARGET_CHARS for ch in target):
        return None
    # Require a path shape: a slash or an extension. Bare-word link stubs (`(g)` in generated
    # docs) are not repo-path claims and are ignored (documented conservative choice).
    if "/" not in target and "." not in target:
        return None
    return target


def _code_paths(line: str) -> List[str]:
    out: List[str] = []
    for m in INLINE_CODE_RE.finditer(line):
        tok = m.group(1).strip()
        if not tok or any(ch in BAD_TARGET_CHARS for ch in tok):
            continue
        if tok.startswith(("/", "~", "-")) or "://" in tok or "=" in tok:
            continue
        tok = tok.rstrip(".,;:)")
        if not PATH_CANDIDATE_RE.match(tok):
            continue
        ext = tok.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTS:
            continue
        out.append(tok)
    return out


# --------------------------------------------------------------------------- resolution
def _candidates(doc: str, target: str) -> List[str]:
    """Doc-relative then repo-root-relative resolution; drop paths escaping the repo."""
    if target.startswith("/"):
        return []
    doc_dir = posixpath.dirname(doc)
    out: List[str] = []
    for base in (doc_dir, ""):
        p = posixpath.normpath(posixpath.join(base, target)) if base else posixpath.normpath(target)
        if not p or p in (".", "..") or p.startswith("../") or p.startswith("/"):
            continue
        if p not in out:
            out.append(p)
    return out


def _exists(repo: str, rel: str) -> bool:
    if not rel or rel.startswith("../"):
        return False
    return os.path.exists(os.path.join(repo, rel))


def _suppressed(ctx: ScanContext, cfg: Dict[str, Any], target: str,
                cands: List[str]) -> bool:
    for pat in cfg.get("allow_missing") or []:
        try:
            rx = re.compile(pat)
        except re.error:  # pragma: no cover - validated at config load
            continue
        if rx.search(target) or any(rx.search(c) for c in cands):
            return True
    inventory = cfg.get("inventory") or []
    if inventory:
        for c in [target] + cands:
            if any(glob_match(c, pat) for pat in inventory):
                return True
    for ex in ctx.cfg.exclude:
        if any(glob_match(c, ex) for c in cands):
            return True
    return False


def _add(findings: List[Finding], ctx: ScanContext, doc: str, line: int, kind: str,
         target: str, cands: List[str], evidence_extra: Optional[List[str]] = None) -> None:
    repo = ctx.repo
    evidence = [f"{doc}#L{line}", "checked: " + ", ".join(cands)]
    if evidence_extra:
        evidence.extend(evidence_extra)
    f = finding(
        "R9", KIND_SEVERITY.get(kind, "medium"), None,
        subject=f"{KIND_LABEL.get(kind, 'reference')} does not exist: {target}",
        observed=f"{doc}#L{line}: {KIND_LABEL.get(kind, 'reference')} `{target}` "
                 f"not found (checked: {', '.join(cands)})",
        expected="references in a knowledge artifact must resolve to repository artifacts "
                 "that exist in the scanned repository state",
        evidence=evidence,
        verification_method="deterministic filesystem existence check "
                            "(doc-relative then repo-root-relative dispatch)",
        suggested_action=KIND_ACTION.get(kind, "fix or remove the stale reference"),
        tags=["references", kind],
    )
    if f.doc is None:
        f.doc = doc
    if f.locator is None:
        f.locator = f"{doc}#L{line}"
    findings.append(f)


def _add_manifest(findings: List[Finding], ctx: ScanContext, doc: str, line: int,
                  kind: str, target: str, known: set, manifest: str) -> None:
    where = "root Makefile" if kind == "make" else "root package.json scripts"
    f = finding(
        "R9", KIND_SEVERITY.get(kind, "low"), None,
        subject=f"{KIND_LABEL.get(kind, 'reference')} does not exist: {target}",
        observed=f"{doc}#L{line}: `{kind} {target}` was not found in the {where} "
                 f"({len(known)} entries parsed)",
        expected="run targets/scripts referenced by a knowledge artifact must exist in the "
                 "repository manifest they belong to",
        evidence=[f"{doc}#L{line}", f"{manifest} entries parsed: {len(known)}",
                  f"known entries: {', '.join(sorted(known)) if len(known) <= 40 else '<many>'}",
                  f"looked up: {target}"],
        verification_method=("deterministic root-Makefile target parse" if kind == "make"
                             else "deterministic root package.json scripts key parse"),
        suggested_action=KIND_ACTION.get(kind, "fix the reference"),
        tags=["references", kind],
    )
    if f.doc is None:
        f.doc = doc
    if f.locator is None:
        f.locator = f"{doc}#L{line}"
    findings.append(f)


# --------------------------------------------------------------------------- rule entry
def run(ctx: ScanContext) -> List[Finding]:
    cfg = ctx.cfg.references_cfg
    if not cfg.get("enabled", True):
        return []
    repo = ctx.repo
    findings: List[Finding] = []
    targets = _make_targets(repo) if cfg.get("check_make", True) else None
    scripts = _npm_scripts(repo) if cfg.get("check_npm", True) else None
    make_evidence = [f"root Makefile targets parsed: {len(targets)}"] if targets is not None else []
    npm_evidence = [f"package.json scripts parsed: {len(scripts)}"] if scripts is not None else []

    for doc in sorted(ctx.doc_meta):
        meta = ctx.doc_meta[doc]
        abspath = meta.get("abspath")
        if not abspath:
            continue
        text = _read_text(abspath)
        if text is None:
            continue
        seen = set()  # one finding per (doc, target): first occurrence wins

        def handle_path(kind: str, target: str) -> None:
            if (kind, target) in seen:
                return
            cands = _candidates(doc, target)
            if not cands:
                return
            if any(_exists(repo, c) for c in cands):
                return
            if _suppressed(ctx, cfg, target, cands):
                return
            seen.add((kind, target))
            _add(findings, ctx, doc, line_no, kind, target, cands)

        def handle_manifest(kind: str, target: str) -> None:
            known = targets if kind == "make" else scripts
            manifest = "root Makefile" if kind == "make" else "root package.json"
            if known is None or (kind, target) in seen or target in known:
                return
            if _suppressed(ctx, cfg, target, [target]):
                return
            seen.add((kind, target))
            _add_manifest(findings, ctx, doc, line_no, kind, target, known, manifest)

        for line_no, in_fence, line in _iter_lines(text):
            tree = bool(TREE_CHARS.search(line))
            if not tree:
                if targets is not None and cfg.get("check_make", True):
                    for m in MAKE_RE.finditer(line):
                        handle_manifest("make", m.group(1))
                if scripts is not None and cfg.get("check_npm", True):
                    for m in NPM_RUN_RE.finditer(line):
                        handle_manifest("npm", m.group(1))
            if in_fence:
                # Fenced blocks are only trusted for run commands; paths inside fences are
                # often tree diagrams / pasted output => never checked (documented).
                continue
            if ILLUSTRATIVE_MARKERS.search(line):
                continue  # illustrative/other-project example, not an assertion about this repo
            if cfg.get("check_links", True):
                for m in MD_LINK_RE.finditer(line):
                    target = _clean_link_target(m.group(1))
                    if target:
                        handle_path("link", target)
            if cfg.get("check_paths", True):
                for target in _code_paths(line):
                    handle_path("path", target)
    return findings
