"""Config loading/validation for kblint.

A config is a JSON object; every key is optional. Unknown keys are rejected so a
typo cannot silently disable a rule. Defaults are safe on a docs-only repo:
no artifacts / pins / source_of_truth -> R1/R2/R4/R6 self-skip, and only R8
(audit queue) can emit output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import __version__

DEFAULT_NOW = "2026-11-05"
KNOWN_KEYS = {
    "repo", "docs", "artifacts", "run_index", "pins", "source_of_truth",
    "expiry", "tolerance", "waivers", "git", "rules", "now", "owner", "exclude",
    "config_version", "references",
}

# R9 defaults: safe on a docs-only repo. Every checker self-skips when the repo has no
# matching surface (no root Makefile / package.json / local references), so defaults never
# produce findings just because the config key is present.
DEFAULT_REFERENCES = {
    "enabled": True,
    "check_paths": True,
    "check_links": True,
    "check_make": True,
    "check_npm": True,
    "allow_missing": [],   # regex list; matching targets are suppressed (external/generated refs)
    "inventory": [],       # repo-relative paths/globs treated as present even if not on disk
}
REFERENCE_CHECK_KEYS = {"check_paths", "check_links", "check_make", "check_npm"}
DEFAULT_PIN_PATTERNS = {
    "torch": r"\btorch[^0-9\n]{0,16}(\d+\.\d+\.\d+(?:\+[A-Za-z0-9]+)?)",
    "python": r"\bPython\s*(\d+\.\d+\.\d+)",
    "cuda": r"\bcuda\s*(\d+\.\d+(?:\.\d+)?)",
    "triton": r"\btriton[^0-9\n]{0,16}(\d+\.\d+\.\d+)",
    "xformers": r"\bxformers[^0-9\n]{0,16}(\d+\.\d+\.\d+)",
    "numpy": r"\bnumpy[^0-9\n]{0,16}(\d+\.\d+\.\d+)",
    "transformers": r"\btransformers[^0-9\n]{0,16}(\d+\.\d+\.\d+)",
    "driver": r"\bdriver[^0-9\n]{0,16}(\d+(?:\.\d+){1,3})",
    "cudnn": r"\bcudnn[^0-9\n]{0,16}(\d+\.\d+(?:\.\d+)?)",
}


class ConfigError(Exception):
    """Invalid configuration (CLI exit code 2)."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _as_list_of_str(cfg: Dict[str, Any], key: str) -> List[str]:
    val = cfg.get(key, [])
    _require(isinstance(val, list) and all(isinstance(x, str) for x in val),
             f"config.{key} must be a list of strings")
    return val


@dataclass
class Config:
    repo: str = "."
    docs: List[str] = field(default_factory=lambda: ["**/*.md"])
    artifacts: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    run_index: Optional[Dict[str, Any]] = None
    pins: List[Dict[str, Any]] = field(default_factory=list)
    source_of_truth: List[Dict[str, Any]] = field(default_factory=list)
    expiry: Dict[str, Any] = field(default_factory=lambda: {
        "env_change_date": None, "negative_flag_regex": []})
    tolerance: Dict[str, Any] = field(default_factory=lambda: {"relative": 5e-4})
    waivers: List[Dict[str, Any]] = field(default_factory=list)
    git: Dict[str, Any] = field(default_factory=lambda: {"enabled": True})
    owner: Dict[str, Any] = field(default_factory=lambda: {"frontmatter_keys": []})
    rules: Dict[str, bool] = field(default_factory=dict)
    now: Optional[str] = None
    config_version: int = 1
    pin_patterns: Dict[str, str] = field(default_factory=dict)
    references: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_REFERENCES))
    base_dir: str = ""

    # -- derived ------------------------------------------------------------
    @property
    def references_cfg(self) -> Dict[str, Any]:
        """R9 settings merged over safe defaults (unknown sub-keys rejected at load time)."""
        merged = dict(DEFAULT_REFERENCES)
        merged.update(self.references or {})
        return merged

    @property
    def relative_tolerance(self) -> float:
        try:
            return float(self.tolerance.get("relative", 5e-4))
        except (TypeError, ValueError):
            raise ConfigError("config.tolerance.relative must be a number")

    @property
    def effective_pin_patterns(self) -> Dict[str, str]:
        pats = dict(DEFAULT_PIN_PATTERNS)
        pats.update(self.pin_patterns)
        return pats

    def rule_enabled(self, name: str) -> bool:
        """Per-rule enable flag. R4 is experimental and OFF unless explicitly enabled."""
        val = self.rules.get(name, self.rules.get(name.lower()))
        default = name not in ("R4",)
        if isinstance(val, dict):
            return bool(val.get("enabled", default))
        if val is None:
            return default
        return bool(val)

    def now_date(self) -> str:
        return self.now or os.environ.get("KBLINT_NOW") or DEFAULT_NOW

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], base_dir: Optional[str] = None) -> "Config":
        _require(isinstance(raw, dict), "config must be a JSON object")
        unknown = set(raw) - KNOWN_KEYS
        _require(not unknown, f"unknown config keys: {sorted(unknown)}")
        cfg = cls()
        if "repo" in raw:
            _require(isinstance(raw["repo"], str), "config.repo must be a string")
            repo = raw["repo"]
            if base_dir and not os.path.isabs(repo):
                repo = os.path.normpath(os.path.join(base_dir, repo))
            cfg.repo = repo
        cfg.docs = _as_list_of_str(raw, "docs") if "docs" in raw else cfg.docs
        cfg.artifacts = _as_list_of_str(raw, "artifacts") if "artifacts" in raw else []
        cfg.exclude = _as_list_of_str(raw, "exclude") if "exclude" in raw else []
        if "run_index" in raw and raw["run_index"] is not None:
            _require(isinstance(raw["run_index"], dict), "config.run_index must be an object")
            ri = dict(raw["run_index"])
            for k in ("path", "format", "file_field", "id_field"):
                if k in ri:
                    _require(isinstance(ri[k], str), f"config.run_index.{k} must be a string")
            cfg.run_index = ri
        if "pins" in raw:
            _require(isinstance(raw["pins"], list), "config.pins must be a list")
            for p in raw["pins"]:
                _require(isinstance(p, dict), "config.pins entries must be objects")
                for k in p:
                    _require(k in ("doc_glob", "artifact_glob", "artifact_keys",
                                   "doc_patterns", "names", "severity"),
                             f"unknown pins key: {k}")
            cfg.pins = list(raw["pins"])
        if "source_of_truth" in raw:
            _require(isinstance(raw["source_of_truth"], list),
                     "config.source_of_truth must be a list")
            for s in raw["source_of_truth"]:
                _require(isinstance(s, dict), "source_of_truth entries must be objects")
                _require(bool(s.get("topic")) and bool(s.get("canonical_doc")),
                         "source_of_truth entries need topic + canonical_doc")
            cfg.source_of_truth = list(raw["source_of_truth"])
        if "expiry" in raw:
            _require(isinstance(raw["expiry"], dict), "config.expiry must be an object")
            exp = dict(raw["expiry"])
            _require(exp.get("env_change_date") is None or
                     isinstance(exp.get("env_change_date"), str),
                     "config.expiry.env_change_date must be a string (ISO date) or null")
            nf = exp.get("negative_flag_regex", [])
            _require(isinstance(nf, list) and all(isinstance(x, str) for x in nf),
                     "config.expiry.negative_flag_regex must be a list of regex strings")
            cfg.expiry = {"env_change_date": exp.get("env_change_date"),
                          "negative_flag_regex": nf}
        if "tolerance" in raw:
            _require(isinstance(raw["tolerance"], dict), "config.tolerance must be an object")
            cfg.tolerance = dict(raw["tolerance"])
        if "waivers" in raw:
            _require(isinstance(raw["waivers"], list), "config.waivers must be a list")
            for w in raw["waivers"]:
                _require(isinstance(w, dict), "waivers entries must be objects")
                _require(any(k in w for k in ("finding_id", "rule", "claim_id", "doc", "path")),
                         "waiver needs one of finding_id/rule/claim_id/doc/path")
            cfg.waivers = list(raw["waivers"])
        if "git" in raw:
            _require(isinstance(raw["git"], dict), "config.git must be an object")
            cfg.git = {"enabled": bool(raw["git"].get("enabled", True))}
        if "owner" in raw:
            _require(isinstance(raw["owner"], dict), "config.owner must be an object")
            keys = raw["owner"].get("frontmatter_keys", [])
            _require(isinstance(keys, list) and all(isinstance(k, str) for k in keys),
                     "config.owner.frontmatter_keys must be a list of strings")
            cfg.owner = {"frontmatter_keys": list(keys)}
        if "rules" in raw:
            _require(isinstance(raw["rules"], dict), "config.rules must be an object")
            for k, v in raw["rules"].items():
                if isinstance(v, dict):
                    _require(isinstance(v.get("enabled"), bool),
                             f"config.rules.{k}.enabled must be boolean")
                else:
                    _require(isinstance(v, bool), f"config.rules.{k} must be boolean or "
                                                  f'{{"enabled": boolean}}')
            cfg.rules = dict(raw["rules"])
        if "now" in raw and raw["now"] is not None:
            _require(isinstance(raw["now"], str), "config.now must be an ISO date string")
            cfg.now = raw["now"]
        if "references" in raw:
            ref = raw["references"]
            _require(isinstance(ref, dict), "config.references must be an object")
            allowed = set(DEFAULT_REFERENCES)
            unknown_ref = set(ref) - allowed
            _require(not unknown_ref,
                     f"unknown config.references keys: {sorted(unknown_ref)} "
                     f"(allowed: {sorted(allowed)})")
            for k in ["enabled"] + sorted(REFERENCE_CHECK_KEYS):
                if k in ref:
                    _require(isinstance(ref[k], bool),
                             f"config.references.{k} must be boolean")
            am = ref.get("allow_missing", [])
            _require(isinstance(am, list) and all(isinstance(x, str) for x in am),
                     "config.references.allow_missing must be a list of regex strings")
            for pat in am:
                try:
                    __import__("re").compile(pat)
                except Exception as exc:  # noqa: BLE001
                    raise ConfigError(
                        f"config.references.allow_missing regex {pat!r} is invalid: {exc}")
            inv = ref.get("inventory", [])
            _require(isinstance(inv, list) and all(isinstance(x, str) for x in inv),
                     "config.references.inventory must be a list of repo-relative paths/globs")
            cfg.references = {**DEFAULT_REFERENCES, **dict(ref)}
        if "pin_patterns" in raw:
            _require(isinstance(raw["pin_patterns"], dict), "config.pin_patterns must be an object")
            for k, v in raw["pin_patterns"].items():
                _require(isinstance(v, str), f"config.pin_patterns.{k} must be a regex string")
            cfg.pin_patterns = dict(raw["pin_patterns"])
        return cfg

    @classmethod
    def load(cls, path: str) -> "Config":
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            raise ConfigError(f"config not found: {path}")
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config is not valid JSON: {path}: {exc}")
        base_dir = os.path.dirname(os.path.abspath(path))
        cfg = cls.from_dict(raw, base_dir=base_dir)
        cfg.base_dir = base_dir
        return cfg


def glob_match(path: str, pattern: str) -> bool:
    """Match a POSIX-style relative path against a glob supporting `**`."""
    path = path.replace(os.sep, "/").lstrip("./")
    pattern = pattern.replace(os.sep, "/").lstrip("./")
    if "**" not in pattern:
        return __import__("fnmatch").fnmatch(path, pattern)
    prefix, _, suffix = pattern.partition("**")
    prefix = prefix.rstrip("/")
    suffix = suffix.lstrip("/")
    if prefix and not (path == prefix or path.startswith(prefix + "/")):
        return False
    rest = path[len(prefix):].lstrip("/") if prefix else path
    if not suffix:
        return True
    return __import__("fnmatch").fnmatch(rest, suffix)


def discover_paths(repo: str, patterns: List[str], exclude: Optional[List[str]] = None,
                   skip_dirs: Optional[List[str]] = None) -> List[str]:
    """Sorted repo-relative POSIX paths matching any pattern (deterministic walk)."""
    skip_dirs = set(skip_dirs or [".git", "__pycache__", ".venv", "node_modules",
                                  ".pytest_cache", "build", "dist", ".mypy_cache"])
    exclude = exclude or []
    out = []
    repo = os.path.abspath(repo)
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith("."))
        for name in sorted(files):
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, repo).replace(os.sep, "/")
            if any(glob_match(rel, ex) for ex in exclude):
                continue
            if any(glob_match(rel, pat) for pat in patterns):
                out.append(rel)
    return sorted(set(out))
