# Anonymization note

This artifact is prepared for **double-blind review** of an AGENTVERIFY 2027 submission.

- Five private repositories used in the repository-derived analyses (repair replay, coding
  counterfactual, real-repository audit workflow, linter mutation natural sample) are anonymized as
  **R1, R2, R3, R4, R5**; one further private sample used by linter examples/regression is **R0**.
- Fixed git commit SHAs (parent/fix) are retained in `analysis/replay/cases.json` and report tables so
  the snapshots remain checkable; repository names and URLs are withheld.
- No author names, affiliations, e-mail addresses, local absolute paths, credentials, environment
  files, or private repository names are included. Generated figures were regenerated from
  sanitized data so no private name appears in rendered labels.
- **Private KB text is withheld or redacted:** raw model prompts/completions, per-repository scan
  dumps, and the private KB repair diff embed private repository text and are not shipped; frozen
  per-run outcome metrics, rule/locator information, reports, and analysis scripts are retained, and
  redacted fields are replaced by length-only placeholders.
- The artifact is public so reviewers and readers can run it, but it is not a de-anonymization: the
  private repositories themselves are not shipped (their frozen outputs are).
- A camera-ready / arXiv release may restore repository names and link the public repositories; this
  bundle does not invent URLs or DOIs and does not claim a DOI.
