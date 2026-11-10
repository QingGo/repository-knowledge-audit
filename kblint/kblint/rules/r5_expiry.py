"""R5 — negative-result / flag expiry.

Config: expiry.env_change_date + expiry.negative_flag_regex[].
Negative or flag-matched claims dated before the environment-change date are
confirmed expired; undated ones are revalidation_due (queue, not defects).
"""

from __future__ import annotations

import re
from typing import List

from ..extract import NEGATIVE_MARKERS
from .base import ScanContext, finding


def run(ctx: ScanContext) -> List:
    findings = []
    env_date = (ctx.cfg.expiry or {}).get("env_change_date")
    patterns = (ctx.cfg.expiry or {}).get("negative_flag_regex") or []
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error:
            continue
    if not env_date and not compiled:
        return findings
    for claim in ctx.claims:
        text = claim.text
        markers = claim.features.get("markers", {})
        matched_re = None
        if markers.get("negative") or NEGATIVE_MARKERS.search(text):
            matched_re = "negative_marker"
        for rx in compiled:
            if rx.search(text):
                matched_re = f"flag_regex:{rx.pattern}"
                break
        if not matched_re:
            continue
        # explicit expiry/negative-result retirement markers exempt the claim
        if markers.get("supersedes") and re.search(r"expir|retract|supersed|no longer", text, re.I):
            continue
        dates = claim.features.get("dates") or []
        claim_date = max(dates) if dates else None
        if claim_date and env_date:
            if claim_date >= env_date:
                continue
            findings.append(finding(
                "R5", "medium", claim,
                subject=f"negative/flag claim predates environment change {env_date}",
                observed=f"claim dated {claim_date} ({matched_re}) is older than "
                         f"environment-change date {env_date}",
                expected="negative results and flags must be revalidated after an environment change "
                         "or carry a date/expiry",
                evidence=[claim.locator, f"claim date {claim_date}",
                          f"env_change_date {env_date}"],
                verification_method="config expiry date comparison + negative/flag marker scan",
                suggested_action="revalidate under the current environment or mark the claim expired",
                tags=["expiry", "negative-result"],
            ))
        else:
            findings.append(finding(
                "R5", "low", claim,
                subject="undated negative/flag claim (expiry unknown)",
                observed=f"claim matches {matched_re} but has no ISO date/expiry marker",
                expected="negative results and flags should carry a date or explicit expiry",
                evidence=[claim.locator],
                verification_method="date/expiry marker scan",
                disposition="revalidation_due",
                suggested_action="add a date/expiry or revalidate",
                tags=["expiry", "revalidation"],
            ))
    return findings
