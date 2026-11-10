"""kblint CLI: `scan`, `diff`, `rules`. Exit codes 0/1/2 (clean / findings / error)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

from . import __version__
from .config import Config, ConfigError, discover_paths, glob_match
from .extract import extract_repo
from .model import SEVERITY_RANK, Finding
from .report import RULE_META, counts, write_all
from .rules import RULES
from .rules.base import ScanContext, build_artifact_index

FORMATS = ("json", "md", "sarif")


def _load_run_index(repo: str, cfg: Config) -> List[Dict]:
    ri = cfg.run_index
    if not ri or not ri.get("path"):
        return []
    path = ri["path"]
    if not os.path.isabs(path):
        base = cfg.base_dir or os.getcwd()
        path = os.path.normpath(os.path.join(base, path))
    if not os.path.exists(path):
        raise ConfigError(f"run_index path not found: {path}")
    rows: List[Dict] = []
    try:
        if ri.get("format", "jsonl") == "json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("rows", data.get("runs", list(data.values())))
            rows = list(data)
        else:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read run_index {path}: {exc}")
    return rows


def _dedupe(findings: List[Finding]) -> List[Finding]:
    seen = set()
    out = []
    for f in findings:
        # Claim-attached findings dedupe per claim (R1-R8 contract). Claimless findings (R9
        # reference checks attach doc+locator directly) must dedupe per occurrence, otherwise the
        # same missing target cited in two docs would be silently collapsed into one finding.
        key = (f.rule, f.claim_id) if f.claim_id else (
            f.rule, f.doc, f.locator, f.subject)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return sorted(out, key=lambda f: (f.rule, f.claim_id or "", f.doc or "", f.finding_id))


def _waived(f: Finding, waivers: List[Dict]) -> bool:
    for w in waivers:
        if "finding_id" in w and w["finding_id"] != f.finding_id:
            continue
        if "rule" in w and w["rule"] != f.rule:
            continue
        if "claim_id" in w and w["claim_id"] != f.claim_id:
            continue
        if "doc" in w and not glob_match(f.doc or "", w["doc"]):
            continue
        if "path" in w and not glob_match(f.doc or "", w["path"]):
            continue
        return True
    return False


def _parse_formats(raw: str, allowed=FORMATS) -> List[str]:
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    bad = [p for p in parts if p not in allowed]
    if bad or not parts:
        raise ConfigError(f"--format must be a comma list of {allowed}, got {raw!r}")
    return parts


def _scan(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config)
    repo = os.path.abspath(args.repo or cfg.repo)
    if not os.path.isdir(repo):
        raise ConfigError(f"repo directory not found: {repo}")
    now = args.now or cfg.now_date()
    out_dir = os.path.abspath(args.out or os.path.join(os.getcwd(), ".kblint-out"))
    formats = _parse_formats(args.format)
    claims, doc_meta = extract_repo(repo, cfg)
    run_rows = _load_run_index(repo, cfg)
    artifacts = build_artifact_index(repo, cfg, run_rows)
    ctx = ScanContext(repo=repo, cfg=cfg, claims=claims, doc_meta=doc_meta,
                      artifacts=artifacts, run_index_rows=run_rows, now=now)
    stats: Dict[str, int] = {}
    for rule_id, run in RULES:
        if not cfg.rule_enabled(rule_id):
            continue
        produced = run(ctx) or []
        stats[rule_id] = len(produced)
        ctx.add(produced)
    findings = _dedupe(ctx.findings)
    waived = [f for f in findings if _waived(f, cfg.waivers)]
    findings = [f for f in findings if not _waived(f, cfg.waivers)]
    audit = list(ctx.audit)
    meta = {
        "repo": repo,
        "docs": len(doc_meta),
        "claims": len(claims),
        "artifacts": len(artifacts.artifacts),
        "waived": len(waived),
        "now": now,
        "stats": stats,
        "r4_enabled": cfg.rule_enabled("R4"),
    }
    written = write_all(out_dir, findings, audit, meta, formats)
    c = counts(findings)
    threshold = args.fail_on
    failed = False
    if threshold != "none":
        limit = SEVERITY_RANK[threshold]
        failed = any(SEVERITY_RANK.get(f.severity, 0) >= limit for f in findings)
    if not args.quiet:
        print(f"kblint {__version__}: {len(findings)} findings "
              f"(confirmed {c['confirmed']}, unresolved {c['unresolved']}, "
              f"provenance_gap {c['provenance_gap']}, revalidation_due {c['revalidation_due']}), "
              f"{len(audit)} audit items; out={out_dir}")
        if not args.quiet:
            for kind in sorted(written):
                print(f"  wrote {kind}: {os.path.relpath(written[kind], os.getcwd())}")
    return 1 if failed else 0


def _diff(args: argparse.Namespace) -> int:
    from .diff import FAIL_ON_NEW_CHOICES, FORMATS as DIFF_FORMATS, classify, load_findings, write_outputs

    before = load_findings(args.before)
    after = load_findings(args.after)
    formats = _parse_formats(args.format, DIFF_FORMATS)
    result = classify(before, after, fail_on_new=args.fail_on_new)
    out_dir = os.path.abspath(args.out or os.path.join(os.getcwd(), ".kblint-diff"))
    written = write_outputs(out_dir, result, args.before, args.after, formats)
    c = result["counts"]
    if not args.quiet:
        print(f"kblint diff {__version__}: {c['new']} new "
              f"({c['new_blocking']} blocking, {c['new_unknown_non_blocking']} new Unknown), "
              f"{c['persisting']} persisting, {c['fixed']} fixed "
              f"(before {c['before']} / after {c['after']}); out={out_dir}")
        for kind in sorted(written):
            print(f"  wrote {kind}: {os.path.relpath(written[kind], os.getcwd())}")
        if result["exit_code"]:
            print(f"  incremental check FAILS: {c['new_blocking']} new confirmed finding(s) at or "
                  f"above --fail-on-new {result['fail_on_new']}", file=sys.stderr)
    return int(result["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kblint",
        description="Deterministic contract linter for engineering-agent knowledge artifacts "
                    "(zero network; findings are verifiable defects, the audit queue is not a defect list).")
    p.add_argument("--version", action="version", version=f"kblint {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="scan a repo's docs against configured artifacts")
    scan.add_argument("--repo", default=None, help="repo root (default: config.repo or '.')")
    scan.add_argument("--config", required=True, help="path to kblint JSON config")
    scan.add_argument("--out", default=None,
                      help="output directory (default: ./.kblint-out)")
    scan.add_argument("--format", default="json,md,sarif",
                      help="comma list of json,md,sarif (default: all)")
    scan.add_argument("--fail-on", default="high", choices=["none", "low", "medium", "high"],
                      help="exit 1 if any finding has this severity or higher (default: high)")
    scan.add_argument("--now", default=None, help="ISO date used for expiry checks (deterministic tests)")
    scan.add_argument("--quiet", action="store_true", help="suppress stdout summary")

    diff = sub.add_parser(
        "diff", help="compare a current scan to a stored baseline; classify NEW/PERSISTING/FIXED")
    diff.add_argument("--before", required=True,
                      help="baseline report directory (containing findings.jsonl) or JSON/JSONL file")
    diff.add_argument("--after", required=True,
                      help="current report directory (containing findings.jsonl) or JSON/JSONL file")
    diff.add_argument("--out", default=None,
                      help="output directory for diff.json/diff.md (default: ./.kblint-diff)")
    diff.add_argument("--format", default="md,json", help="comma list of json,md (default: both)")
    diff.add_argument("--fail-on-new", default="medium", choices=["none", "low", "medium", "high"],
                      help="fail on NEW confirmed findings at this severity or higher "
                           "(default: medium; 'none' never fails)")
    diff.add_argument("--quiet", action="store_true", help="suppress stdout summary")

    sub.add_parser("rules", help="list rules and exit")
    return p


def _print_rules() -> int:
    print(f"kblint {__version__} — rules")
    for rule_id in sorted(RULE_META):
        name, desc = RULE_META[rule_id]
        print(f"  {rule_id}  {name:34s} {desc}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "rules":
            return _print_rules()
        if args.cmd == "diff":
            return _diff(args)
        return _scan(args)
    except ConfigError as exc:
        print(f"kblint error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"kblint error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:  # pragma: no cover - defensive
        print(f"kblint error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
