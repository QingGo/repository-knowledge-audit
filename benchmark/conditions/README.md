# Conditions

`conditions.py` holds the condition header map and the exact prompt builder used by the paper's
`run_bench.py` (prompt construction only; the API runner is not shipped). The frozen results in
`../results/` were produced with this prompt builder, one completion per (task, condition, seed), and
the hidden pytest suites in `../tasks/conventions.py`. Conditions: c0 no KB, c1 useful KB, c2 stale KB,
c3 neutral note, c2v/c2f stale + one/full visible test, c1v/c1f useful + one/full visible test,
c2a appended correction, c2ar correction order reversed, c2an correction after a neutral distractor.
