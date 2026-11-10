# Grader

`grade_one.py` grades a saved completion against a benchmark task's hidden pytest suite,
deterministically and offline (no API, no network). It imports the task table from
`benchmark/tasks/conventions.py` and runs pytest in a temporary directory.

```bash
python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 --code benchmark/grader/examples/saved_pass.py
python3 benchmark/grader/grade_one.py --task M1_valid_zeros_f32 --code benchmark/grader/examples/saved_fail.py
```

Exit status 0 = pass, 1 = fail. `--json` prints a machine-readable record. The hidden tests were hidden
from the model at experiment time and are released here post hoc for reproducibility; they are not a
held-out set after this release.
