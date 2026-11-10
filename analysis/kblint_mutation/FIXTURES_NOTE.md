# Fixture corpus not shipped

The controlled-mutation fixtures are generated build artifacts (and the real-repo
cases need the private snapshots). They are excluded from this artifact so the zip
stays reproducible; the frozen evaluation results are included below. With the private
snapshots available, regenerate them with `python3 mutate.py build` (synthetic cases
need no private repository), then run `python3 run_eval.py --skip-natural`.
