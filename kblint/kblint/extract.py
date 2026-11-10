"""Deterministic markdown -> claim records.

Extraction unit: heading (rule/number-bearing only), bullet / numbered item,
blockquote, table row (header used as key context), or prose sentence.
No semantics, no LLM: markdown structure + deterministic regex features.

Skips: YAML frontmatter, fenced code blocks, link-only lines/images.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .config import Config
from .model import Claim, stable_id

# --- feature regexes --------------------------------------------------------
UNIT_RE = re.compile(
    r"(?<![\w.])(?P<num>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE]-?\d+)?)\s*"
    r"(?P<unit>%|pp|ms|us|µs|ns|s\b|TFLOPS|TFLOP/s|TF/s|TF|GiB|MiB|GB|MB|KB|"
    r"GB/s|tokens?/s|tok/s|tokens?|kernels?|variants?|lines?|params?|steps?|"
    r"rounds?|files?|runs?|items?|rows?|hours?|days?|minutes?|minutes?|"
    r"×|x\b)",
    re.IGNORECASE,
)
NUM_RE = re.compile(r"(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE]-?\d+)?(?![\w])")
DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
ARTIFACT_RE = re.compile(
    r"(?<![\w])(?:\.\./)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:jsonl|json|csv)\b")
PATH_RE = re.compile(
    r"(?<![\w])(?:\.\./)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:md|py|log|txt|yaml|yml)\b")
FLAG_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?:=[A-Za-z0-9_.,-]+)?)\b")
COUNT_RE = re.compile(
    r"\b(\d[\d,]*)\s+(kernels?|variants?|files?|rounds?|steps?|runs?|rows?|claims?|"
    r"docs?|items?|lines?|jobs?)\b", re.IGNORECASE)

SUPERSEDE_MARKERS = re.compile(
    r"supersed|replaced by|replaces\b|deprecat|obsolete|historical|no longer|"
    r"not the (?:project )?(?:target|goal)|not (?:the )?target|retract|"
    r"diagnostic, not|已.*取代|历史|过期|outdated", re.IGNORECASE)
NEGATIVE_MARKERS = re.compile(
    r"negative result|no gain|not faster|slower|fails?\b|failed\b|FAIL\b|OOM|"
    r"not reachable|cannot be reproduced|breaks parity|regress|no improvement|"
    r"did not (?:pay off|help|improve)|none beats|no detectable|暂缓|no change|"
    r"rejected?\b|not a drop-in|exhausted", re.IGNORECASE)
EXPIRY_MARKERS = re.compile(
    r"expir|valid until|revalidat|as of\b|ttl\b|stale|out of date|review by|"
    r"last verified|last updated", re.IGNORECASE)
CONTRACT_MARKERS = re.compile(
    r"\btarget\b|\bgate\b|must pass|acceptance|tolerance|protocol|contract|"
    r"invariant|convention|denominator|parity|opt-in|default off|口径|定义", re.IGNORECASE)
RULE_MARKERS = re.compile(
    r"\bdo not\b|\bnever\b|\bmust\b|\bonly\b|\brequire|\bcompare\b|\brecord\b|"
    r"\bkeep\b|\buse\b|\bprefer\b|\bavoid\b", re.IGNORECASE)

STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "at", "by", "for", "with", "and",
    "or", "is", "are", "was", "were", "be", "been", "this", "that", "these",
    "those", "it", "its", "as", "from", "into", "than", "vs", "versus", "per",
    "we", "our", "their", "his", "her", "also", "only", "can", "may", "will",
    "should", "would", "not", "no", "but", "if", "then", "when", "where", "which",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def strip_md(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = s.replace("**", "").replace("__", "").replace("*", "")
    return norm_ws(s)


def norm_key(s: str) -> str:
    s = strip_md(s).lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return norm_ws(s)


def _context_words(text: str, pos: int, max_words: int = 4) -> str:
    """Up to `max_words` non-stopword-ish tokens immediately before `pos`."""
    head = text[:pos]
    toks = re.findall(r"[A-Za-z][A-Za-z0-9_.\-]*", head)
    picked: List[str] = []
    for tok in reversed(toks):
        if len(picked) >= max_words + 2:
            break
        low = tok.lower().strip(".")
        if not low or low in STOPWORDS:
            continue
        picked.append(low)
        if len(picked) >= max_words:
            break
    return " ".join(reversed(picked))


def extract_features(text: str, cfg: Config, segments: Optional[List[Tuple[int, int, str]]] = None,
                     table_header: Optional[List[str]] = None) -> Dict[str, Any]:
    """Deterministic feature dict for one claim text."""
    segments = segments or []
    bold_spans = [(m.start(), m.end()) for m in re.finditer(r"\*\*([^*]+)\*\*", text)]

    def is_bold(pos: int) -> bool:
        return any(a <= pos < b for a, b in bold_spans)

    def segment_context(pos: int) -> Optional[str]:
        for a, b, ctx in segments:
            if a <= pos < b:
                return ctx
        return None

    numbers: List[Dict[str, Any]] = []
    seen_spans: List[Tuple[int, int]] = []
    for m in UNIT_RE.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        numbers.append({
            "value": val,
            "unit": m.group("unit").lower(),
            "raw": m.group("num").replace(",", ""),
            "bold": is_bold(m.start()),
            "context": segment_context(m.start()) or _context_words(text, m.start()),
        })
        seen_spans.append((m.start(), m.end()))
    for m in NUM_RE.finditer(text):
        if any(a <= m.start() < b for a, b in seen_spans):
            continue
        raw = m.group(0).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        numbers.append({
            "value": val,
            "unit": None,
            "raw": m.group(0).replace(",", ""),
            "bold": is_bold(m.start()),
            "context": segment_context(m.start()) or _context_words(text, m.start()),
        })

    paths = sorted({m.group(0).lstrip("./") for m in PATH_RE.finditer(text)})
    artifact_refs = sorted({m.group(0).lstrip("./") for m in ARTIFACT_RE.finditer(text)})
    dates = sorted({m.group(1) for m in DATE_RE.finditer(text)})
    flags = sorted({m.group(1) for m in FLAG_RE.finditer(text)})
    counts = [{"n": int(m.group(1).replace(",", "")), "noun": m.group(2).lower()}
              for m in COUNT_RE.finditer(text)]

    pins: Dict[str, List[str]] = {}
    for name, pat in cfg.effective_pin_patterns.items():
        try:
            found = sorted({m.group(1) for m in re.finditer(pat, text, re.IGNORECASE)})
        except re.error:
            found = []
        if found:
            pins[name] = found
    versions = sorted(set(re.findall(r"\bv?(\d+\.\d+\.\d+(?:\+[A-Za-z0-9]+)?)\b", text)))

    markers = {
        "supersedes": bool(SUPERSEDE_MARKERS.search(text)),
        "negative": bool(NEGATIVE_MARKERS.search(text)),
        "expiry": bool(EXPIRY_MARKERS.search(text)),
        "contract": bool(CONTRACT_MARKERS.search(text)),
        "rule": bool(RULE_MARKERS.search(text)),
    }
    kinds: List[str] = []
    if pins or versions:
        kinds.append("version")
    if markers["contract"]:
        kinds.append("contract")
    if markers["rule"]:
        kinds.append("rule")
    if markers["negative"]:
        kinds.append("failure")
    if numbers:
        kinds.append("numeric")
    if artifact_refs or paths:
        kinds.append("path")
    if not kinds:
        kinds.append("other")
    return {
        "numbers": numbers,
        "pins": pins,
        "versions": versions,
        "paths": paths,
        "artifact_refs": artifact_refs,
        "dates": dates,
        "flags": flags,
        "counts": counts,
        "markers": markers,
        "kinds": kinds,
        "has_number": bool(numbers),
        "table_header": list(table_header or []),
    }


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text)[:30].strip("-") or "root"


def parse_doc(rel: str, raw: str, cfg: Config) -> Tuple[List[Claim], Dict[str, Any]]:
    """Parse one markdown document into claims (deterministic order)."""
    lines = raw.splitlines()
    claims: List[Claim] = []
    frontmatter: Dict[str, str] = {}
    i = 0
    if lines and lines[0].strip() == "---":
        j = 1
        while j < len(lines) and lines[j].strip() != "---":
            if ":" in lines[j]:
                k, _, v = lines[j].partition(":")
                frontmatter[k.strip().lower()] = v.strip()
            j += 1
        i = min(j + 1, len(lines))

    stack: List[Tuple[int, str]] = []
    fence = False
    table_header: Optional[List[str]] = None
    block: List[str] = []
    block_start = 0
    doc_sha = sha256_text(raw)[:16]

    def section_path() -> str:
        return " / ".join(t for _, t in stack) if stack else "(root)"

    def emit(text: str, l0: int, l1: int, form: str,
             segments: Optional[List[Tuple[int, int, str]]] = None) -> None:
        text = norm_ws(text)
        plain = strip_md(text)
        if len(plain) < 12 or not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", plain):
            return
        if re.fullmatch(r"[-|: ]+", plain):
            return
        feats = extract_features(text, cfg, segments=segments,
                                  table_header=table_header)
        loc = f"{rel}#L{l0}" if l0 == l1 else f"{rel}#L{l0}-L{l1}"
        cid = stable_id("c_", doc_sha, loc, text)
        claims.append(Claim(
            claim_id=cid, doc=rel, locator=loc, line_start=l0, line_end=l1,
            section=section_path(), text=text, features=feats, form=form,
        ))

    def flush_block() -> None:
        nonlocal block
        if not block:
            return
        para = " ".join(block)
        for sent in split_sentences(para):
            emit(sent, block_start, block_start + len(block) - 1, "sentence")
        block = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_block()
            fence = not fence
            table_header = None
            i += 1
            continue
        if fence:
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_block()
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            if len(strip_md(title)) >= 12 and (
                    re.search(r"\d", title) or CONTRACT_MARKERS.search(title)
                    or RULE_MARKERS.search(title)):
                emit(title, i + 1, i + 1, "heading")
            table_header = None
            i += 1
            continue
        if not stripped:
            flush_block()
            table_header = None
            i += 1
            continue
        if stripped.startswith(">"):
            flush_block()
            q = stripped.lstrip(">").strip()
            j = i
            while j + 1 < len(lines) and lines[j + 1].strip().startswith(">"):
                j += 1
                q += " " + lines[j].strip().lstrip(">").strip()
            emit(q, i + 1, j + 1, "blockquote")
            i = j + 1
            continue
        if stripped.startswith("|"):
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in header_cells):
                i += 1
                continue
            if table_header is None:
                table_header = header_cells
                i += 1
                continue
            # build key-context text plus per-cell segments
            parts: List[str] = []
            segments: List[Tuple[int, int, str]] = []
            pos = 0
            for h, cell in zip(table_header, header_cells):
                if not cell:
                    continue
                ctx = strip_md(h) or "value"
                piece = f"{ctx}: {cell}"
                segments.append((pos, pos + len(piece), ctx))
                parts.append(piece)
                pos += len(piece) + 3
            emit(" | ".join(parts), i + 1, i + 1, "table_row", segments=segments)
            i += 1
            continue
        m = re.match(r"^(\s*)(?:[-*+]|\d+\.)\s+(.*)$", line)
        if m:
            flush_block()
            indent = len(m.group(1))
            buf = [m.group(2)]
            j = i
            while j + 1 < len(lines):
                nxt = lines[j + 1]
                if not nxt.strip():
                    break
                nm = re.match(r"^(\s*)(?:[-*+]|\d+\.)\s+(.*)$", nxt)
                if nm and len(nm.group(1)) <= indent:
                    break
                if nxt.strip().startswith(("|", "#", ">", "```")):
                    break
                if nm and len(nm.group(1)) > indent:
                    j += 1
                    buf.append(nm.group(2))
                    continue
                j += 1
                buf.append(nxt.strip())
            joined = " ".join(buf)
            if not re.fullmatch(r"(?:\[[^\]]*\]\([^)]*\)\s*)+", joined):
                emit(joined, i + 1, j + 1, "bullet")
            i = j + 1
            continue
        if re.fullmatch(r"(?:!?\[[^\]]*\]\([^)]*\)\s*)+", stripped):
            i += 1
            continue
        if not block:
            block_start = i + 1
        block.append(stripped)
        i += 1
    flush_block()
    meta = {"sha256": sha256_text(raw), "lines": len(lines), "frontmatter": frontmatter}
    claims.sort(key=lambda c: (c.line_start, c.line_end, c.text))
    return claims, meta


def split_sentences(block: str) -> List[str]:
    prot = block
    for a, b in (("e.g.", "eg"), ("i.e.", "ie"), ("vs.", "vs"), ("Fig.", "Fig"),
                 ("approx.", "approx"), ("No.", "No"), ("cf.", "cf"), ("etc.", "etc")):
        prot = prot.replace(a, b)
    parts = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z0-9\u4e00-\u9fff(\[*`])", prot)
    return [p.strip() for p in parts if p.strip()]


def extract_repo(repo: str, cfg: Config) -> Tuple[List[Claim], Dict[str, Any]]:
    """Extract all configured docs; returns sorted claims and per-doc metadata."""
    from .config import discover_paths
    docs = discover_paths(repo, cfg.docs, exclude=cfg.exclude)
    claims: List[Claim] = []
    doc_meta: Dict[str, Any] = {}
    for rel in docs:
        abspath = os.path.join(repo, rel)
        try:
            with open(abspath, encoding="utf-8") as f:
                raw = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        doc_claims, meta = parse_doc(rel, raw, cfg)
        # paragraph-level provenance inheritance: sentences cut from one paragraph
        # share its locator; a run-artifact pointer in a sibling sentence applies.
        blocks = {}
        for c in doc_claims:
            blocks.setdefault((c.line_start, c.line_end), []).append(c)
        for group in blocks.values():
            if len(group) < 2:
                continue
            refs = sorted({r for c in group for r in c.features.get("artifact_refs", [])})
            paths = sorted({p for c in group for p in c.features.get("paths", [])})
            for c in group:
                c.features["artifact_refs"] = refs
                c.features["paths"] = sorted(set(c.features.get("paths", [])) | set(paths))
        claims.extend(doc_claims)
        meta["abspath"] = abspath
        doc_meta[rel] = meta
    claims.sort(key=lambda c: (c.doc, c.line_start, c.line_end, c.text))
    return claims, doc_meta
