# Security and secret check

Checked every bundled file for credentials and identifying paths. **Result: 0 hits.**

| check | hits |
|---|---|
| secret-like key | 0 |
| inline API key | 0 |
| bearer header | 0 |
| AWS key | 0 |
| GitHub token | 0 |
| private key block | 0 |
| private repository name | 0 |
| absolute home path | 0 |
| author identity | 0 |
| personal email | 0 |
| other local absolute path | 0 |
| private KB text (analysis) | 0 |
| private KB text (regression) | 0 |

- `kblint` and the grader are stdlib-only/offline; no API key is included or read by the quickstart.
- The model runner used `DEEPSEEK_API_KEY` from the environment during the study; no credential is
  written to any result file, and no model runner is included in this artifact.
- Private repositories are anonymized (R1–R5; R0 for linter samples); see `ANONYMIZATION.md`.
- Personal e-mail addresses are counted excluding synthetic test/fixture addresses
  (example.com/example.invalid); author-identity strings and local absolute paths are counted as hits.
- `.env`, `__pycache__`, `.pytest_cache`, `.DS_Store`, raw scan dumps, private KB text, and private
  repository working trees are excluded by the packager; the "private KB text (analysis)" row above
  is a hard gate (the build fails if it is non-zero).
