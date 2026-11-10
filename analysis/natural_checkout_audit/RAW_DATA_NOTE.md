# Raw per-repository scan outputs withheld

`results/summary.json`, `adjudication.jsonl`, `PROTOCOL.md`, and the pipeline are included.
Per-repository raw scans under `raw/` are withheld from this anonymous bundle because they
embed public-repository KB text (including contact addresses); they can be regenerated with
`python3 run_pipeline.py select && fetch && scan && adjudicate && summarize`.