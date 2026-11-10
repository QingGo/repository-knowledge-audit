# Benchmark: 54 convention-sensitive tasks

`tasks/conventions.py` defines the 54 CPU-only tasks used in the paper (7 families: masked_mean,
shift_ce, topk, quantize, masked_softmax, ce_grad, stable_softmax). Each task dict contains the
function prompt, the useful / stale / neutral KB facts used by the conditions, and the **hidden pytest
suite** (`tests`).

`conditions/` documents the experimental conditions and the exact prompt builder
(`conditions.py`; the model runner is not included because it needs an API key). `results/` contains
the frozen per-run JSONL and summary JSON files used in the paper. `grader/grade_one.py` grades any
existing completion against a task's hidden suite, deterministically and offline.

**Post-hoc release note.** At experiment time the `tests` strings were hidden from the model. They are
released here for reproducibility; after this release they must not be described as a held-out set,
and any new model run on them is not a pre-registered held-out evaluation.
