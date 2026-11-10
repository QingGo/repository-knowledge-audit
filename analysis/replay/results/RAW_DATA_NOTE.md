# Raw repair-replay prompts and completions withheld

The raw per-run records embed the private KB text sent in the prompts. `replay.jsonl` keeps the
case/arm/seed, check results, usage and cost per run, with the private `file` and `raw` fields
replaced by length-only placeholders. Regenerate from `cases.json` and the private snapshots.
