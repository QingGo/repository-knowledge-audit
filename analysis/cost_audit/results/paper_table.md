**Table (paper-ready): inference cost per run and per successful task, expanded benchmark, chat model.**

| condition | pass rate | input tok | output tok | total ¥/run | cost/success |
|---|---:|---:|---:|---:|---:|
| c0 | 17/108 | 139 | 251 | 0.00114 | ¥0.00724 |
| c1 | 87/108 | 201 | 222 | 0.00109 | ¥0.00135 |
| c2 | 5/108 | 194 | 253 | 0.00120 | ¥0.02595 |
| c2v | 34/108 | 547 | 166 | 0.00094 | ¥0.00300 |
| c2f | 49/108 | 678 | 157 | 0.00100 | ¥0.00220 |
| c3 | 19/108 | 172 | 320 | 0.00145 | ¥0.00823 |

*Prompt tokens estimated from reconstructed prompt text (condition-specific token-audit ratio; leave-one-task-out MAPE 2.72%); completion tokens exact; costs use the paper's off-peak pricing.*