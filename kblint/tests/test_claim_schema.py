"""Claim-schema and example-entry tests (stdlib only; no network)."""

from __future__ import annotations

import json
import os

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(PKG, rel), encoding="utf-8") as fh:
        return json.load(fh)


def test_claim_schema_required_fields_and_status_enum():
    schema = load("schema/claim.schema.json")
    assert schema["$schema"].startswith("https://json-schema.org/draft/2020-12/")
    assert set(schema["required"]) == {"claim_id", "claim", "scope", "evidence",
                                       "invalidation", "status", "last_checked"}
    assert schema["properties"]["status"]["enum"] == ["verified", "stale", "unknown", "removed"]
    assert set(schema["properties"]["scope"]["required"]) == {"repository", "version"}
    assert set(schema["properties"]["evidence"]["required"]) == {"type"}
    assert schema["properties"]["evidence"]["properties"]["type"]["enum"] == ["test", "path", "artifact",
                                                                "command", "doc"]
    # evidence type -> required witness fields (via allOf if/then)
    conds = schema["properties"]["evidence"]["allOf"]
    assert len(conds) == 3


def test_claims_examples_cover_verified_stale_unknown_and_match_schema_shape():
    claims = load("examples/claims.example.json")
    assert isinstance(claims, list) and len(claims) >= 3
    statuses = {c["status"] for c in claims}
    assert {"verified", "stale", "unknown"} <= statuses
    for c in claims:
        for key in ("claim_id", "claim", "scope", "evidence", "invalidation",
                    "status", "last_checked"):
            assert key in c, (c.get("claim_id"), key)
        assert c["status"] in ("verified", "stale", "unknown", "removed")
        assert c["scope"]["repository"] and c["scope"]["version"]
        ev = c["evidence"]
        assert ev["type"] in ("test", "path", "artifact", "command", "doc")
        if ev["type"] in ("path", "artifact", "doc"):
            assert ev.get("path"), c["claim_id"]
        if ev["type"] == "test":
            assert ev.get("test")
        if ev["type"] == "command":
            assert ev.get("command")
    # no absolute local paths in the released examples
    blob = json.dumps(claims)
    assert "/Users/" not in blob and "/home/" not in blob


def test_markdown_claim_example_maps_to_schema_fields():
    text = open(os.path.join(PKG, "examples", "claim-audit.example.md"), encoding="utf-8").read()
    for field in ("claim_id:", "claim:", "scope:", "evidence:", "invalidation:",
                  "status:", "last_checked:"):
        assert field in text, field
    assert "produced by the audit" in text
    assert "not a verification result" in text or "not** a" in text
