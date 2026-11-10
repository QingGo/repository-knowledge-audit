---
claim_id: ENV-003
claim: "torch 2.14.1+cu130 is the training environment pin"
scope:
  repository: sample_repo
  version: r49
  environment: GPU node group A
evidence:
  type: artifact
  path: artifacts/r50_v2.json
invalidation:
  condition: "artifact pool changes to a different torch build, or expiry env_change_date 2026-10-01 passes"
status: verified
last_checked: "2026-11-05T00:00:00+08:00"
---

# Environment pin — audit example

The training environment uses torch `2.14.1+cu130` (see `artifacts/r50_v2.json`).

How this maps to `schema/claim.schema.json`:

- `claim_id` / `claim` / `scope` — the checkable statement and where it applies.
- `evidence: {type: artifact, path: artifacts/r50_v2.json}` — the executable witness. The audit
  re-resolves the claim against this artifact (`python3 -m kblint scan ...`).
- `invalidation.condition` — what would make the claim stale; the maintainer records it up front.
- `status` — **produced by the audit**, not self-asserted: a matching artifact pin yields
  `verified`; a missing/mismatched artifact yields `stale`; a claim with no deterministic witness is
  `unknown`. `removed` marks a retired claim.
- `last_checked` — timestamp of the last audit run that inspected this claim. It is **not** a
  verification result: a claim can be `last_checked` recently and still `unknown` (or `stale`); only
  `status` reflects the evidence check.

The same entry is serialized in `examples/claims.example.json` (together with one `stale` and one
`unknown` example) and can be emitted/consumed by any KB tool that reads the JSON Schema.
