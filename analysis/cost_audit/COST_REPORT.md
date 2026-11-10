# KB experiment cost audit: full input/output token and cost accounting

All numbers below are recomputed from the frozen result JSONLs (no benchmark re-runs). `cost_cny` in the logs is `usage_cost(usage)` under the paper's pricing constants; the input/output split is exact (`output = completion_tokens × ¥4/M`, `input = cost_cny − output`). Prompt-token counts are estimated from the exact reconstructed prompt text using a char→token ratio measured by a small API token audit (logged, capped at ¥0.30).

## Token-audit calibration

- Audit calls: 156 (chat, temperature 0, max_tokens=1), spend ¥0.03201 of the ¥0.30 cap.
- Tokens/char ratios (condition-specific): `bench` 0.318, `mixed` 0.272, `mitigation` 0.299, `natural` 0.267, `natural_prior` 0.257, `probe` 0.341; global 0.298.
- Leave-one-task-out MAPE: **2.72%** with the condition-specific ratio (the estimator used below); pooled per-kind ratio 8.62% (shows why per-condition calibration matters).

## Table 1. Expanded constructed benchmark, chat (54 tasks × 2 prompt-variant seeds; 108 runs/cond)

| condition | n | pass | prompt tok (est.) | completion tok | input ¥/run | output ¥/run | total ¥/run | effective input ¥/M | total cost | cost/success | Δtotal vs c0 | Δcost/success vs c0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| c0 | 108 | 17/108 | 139 | 251 | 0.00014 | 0.00100 | 0.00114 | 0.97 | ¥0.12301 | ¥0.00724 |  |  |
| c1 | 108 | 87/108 | 201 | 222 | 0.00020 | 0.00089 | 0.00109 | 0.99 | ¥0.11751 | ¥0.00135 | -4.5% | 5.36× cheaper |
| c2 | 108 | 5/108 | 194 | 253 | 0.00019 | 0.00101 | 0.00120 | 0.98 | ¥0.12977 | ¥0.02595 | +5.5% | 3.6× |
| c2v | 108 | 34/108 | 547 | 166 | 0.00028 | 0.00066 | 0.00094 | 0.51 | ¥0.10187 | ¥0.00300 | -17.2% | 2.41× cheaper |
| c2f | 108 | 49/108 | 678 | 157 | 0.00037 | 0.00063 | 0.00100 | 0.54 | ¥0.10766 | ¥0.00220 | -12.5% | 3.29× cheaper |
| c3 | 108 | 19/108 | 172 | 320 | 0.00017 | 0.00128 | 0.00145 | 0.98 | ¥0.15641 | ¥0.00823 | +27.1% | 1.1× |

*(c2v = stale + one visible test, c2f = stale + full visible suite, c3 = neutral note. Effective input ¥/M = mean input cost / mean estimated prompt tokens; the miss price is ¥1.0/M, values below 1.0 indicate some prompt-cache discount.)*

## Table 2. Other datasets / arms (per-condition detail in `results/cost_summary.json`)

| dataset | conditions | pass (best→worst) | cost/success range | notes |
|---|---|---|---|---|
| bench_pilot | 6 | c1 75/84, c2f 46/84, c2v 38/84, c0 23/84 | ¥0.00132–¥0.01247 | pilot 28 tasks, chat, 3 seeds |
| bench_reasoner | 6 | c2f 52/54, c2v 48/54, c1 41/54, c0 9/54 | ¥0.00849–¥0.20649 | 54 tasks, reasoner, 1 seed |
| authority_chat | 3 | c1v 95/108, c2a 94/108, c1f 92/108 | ¥0.00130–¥0.00153 | c1v/c1f/c2a arms |
| authority_order_chat | 1 | c2ar 79/108 | ¥0.00161–¥0.00161 | c2ar order control |
| authority_c2an_chat | 1 | c2an 87/108 | ¥0.00146–¥0.00146 | c2an distractor control |
| c0tests_chat | 2 | c0f 32/54, c0v 31/54 | ¥0.00180–¥0.00192 | c0v/c0f controls |
| c0tests_reasoner | 2 | c0f 51/54, c0v 50/54 | ¥0.00764–¥0.01094 | c0v/c0f controls |
| mixed_chat | 8 | h1 33/54, m5 25/54, m1 20/54, m6 7/54 | ¥0.00185–¥0.04004 | 8 mixed-KB conditions |
| mixed_reasoner | 8 | h1 19/26, m5 11/18, m1 13/24, m6 5/18 | ¥0.01533–¥0.33608 | reasoner mixed |
| mitigation_chat | 12 | v1 42/54, obs1 37/54, tag1 36/54, n1 35/54 | ¥0.00145–¥0.07351 | 12 writing variants |
| mitigation_reasoner | 12 | v1 19/21, n1 17/21, scope1 5/8, obs1 4/8 | ¥0.00832–¥0.28846 | reasoner writing variants |
| natural | 6 | c2f 20/20, c2v 19/20, c1 17/20, c3 8/20 | ¥0.00055–¥0.00274 | 10 tasks, real c1/c3/c4 packs |
| natural_prior_chat | 6 | c2f 48/48, c2v 47/48, c1 42/48, c3 30/48 | ¥0.00037–¥0.00171 | 24 prior-bearing tasks, chat |
| natural_prior_reasoner | 6 | c2f 21/24, c2v 21/24, c1 17/24, c3 9/24 | ¥0.00239–¥0.01910 | 24 prior-bearing tasks, reasoner |

## Does "correct entries are cheaper" survive?

- **bench_chat**: c1 vs c0 total cost 0.00109 vs 0.00114 (-4.5%); input cost 0.00014 → 0.00020; completion cost 0.00100 → 0.00089; cost per success ¥0.00724 → ¥0.00135.
- **bench_pilot**: c1 vs c0 total cost 0.00118 vs 0.00120 (-2.3%); input cost 0.00014 → 0.00020; completion cost 0.00107 → 0.00098; cost per success ¥0.00440 → ¥0.00132.
- **bench_reasoner**: c1 vs c0 total cost 0.01020 vs 0.01264 (-19.3%); input cost 0.00015 → 0.00022; completion cost 0.01249 → 0.00998; cost per success ¥0.07585 → ¥0.01343.

**Reading.** The KB condition raises prompt/input cost and lowers completion cost. In the expanded chat run the total-cost reduction is small (~4–5%) and input-cost is *higher* with the KB; the large, robust saving is **cost per successful task** (mostly a pass-rate effect). The old claim "correct entries are cheaper" is therefore only defensible as **cost per success** (and as completion-token savings), not as per-call inference cost in general; on the reasoner model the completion-token saving is large enough to also reduce total cost.

## Table 3. Agentic harness (multi-turn, 25 tasks × 4 conditions × 2 seeds; steps = model calls, loop cap 16)

| condition | n | pass | mean steps | completion tok | total ¥/run | input ¥/run | cost/success |
|---|---:|---:|---:|---:|---:|---:|---:|
| exec-c0 | 50 | 24/50 | 1.2 | 230 | 0.00118 | 0.00026 | ¥0.00250 |
| exec-c1 | 50 | 47/50 | 1.0 | 201 | 0.00099 | 0.00018 | ¥0.00100 |
| exec-c2 | 50 | 9/50 | 1.8 | 317 | 0.00165 | 0.00038 | ¥0.00920 |
| exec-c2full | 50 | 35/50 | 1.1 | 157 | 0.00082 | 0.00020 | ¥0.00120 |

Prompt tokens are not reconstructed for the agentic arm (multi-turn transcripts are truncated in the logs; cost_cny is exact, so input cost is exact and input tokens are not claimed).

## Table 4. Real-repo replay (our separate helper; exact usage fields)

| arm | n | success | prompt tok | completion tok | total ¥/run | cost/success |
|---|---:|---:|---:|---:|---:|---:|
| stale_only | 10 | 9/10 | 6394 | 2652 | 0.01397 | ¥0.01550 |
| stale_plus_report | 10 | 10/10 | 6767 | 2566 | 0.01072 | ¥0.01070 |
| no_kb | 10 | 1/10 | 3953 | 1281 | 0.00706 | ¥0.07060 |
| stale_no_hint | 10 | 5/10 | 6364 | 2817 | 0.01461 | ¥0.02920 |

## Appendix. All dataset × condition cells

| dataset | cond | n | pass | pass rate | prompt tok (est.) | completion tok | total ¥/run | total ¥ | cost/success |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bench_chat | c0 | 108 | 17 | 0.157 | 139 | 251 | 0.00114 | ¥0.12301 | ¥0.00724 |
| bench_chat | c1 | 108 | 87 | 0.806 | 201 | 222 | 0.00109 | ¥0.11751 | ¥0.00135 |
| bench_chat | c2 | 108 | 5 | 0.046 | 194 | 253 | 0.00120 | ¥0.12977 | ¥0.02595 |
| bench_chat | c2f | 108 | 49 | 0.454 | 678 | 157 | 0.00100 | ¥0.10766 | ¥0.00220 |
| bench_chat | c2v | 108 | 34 | 0.315 | 547 | 166 | 0.00094 | ¥0.10187 | ¥0.00300 |
| bench_chat | c3 | 108 | 19 | 0.176 | 172 | 320 | 0.00145 | ¥0.15641 | ¥0.00823 |
| bench_pilot | c0 | 84 | 23 | 0.274 | 144 | 267 | 0.00120 | ¥0.10112 | ¥0.00440 |
| bench_pilot | c1 | 84 | 75 | 0.893 | 205 | 244 | 0.00118 | ¥0.09878 | ¥0.00132 |
| bench_pilot | c2 | 84 | 9 | 0.107 | 197 | 286 | 0.00134 | ¥0.11219 | ¥0.01247 |
| bench_pilot | c2f | 84 | 46 | 0.548 | 677 | 160 | 0.00101 | ¥0.08516 | ¥0.00185 |
| bench_pilot | c2v | 84 | 38 | 0.452 | 549 | 175 | 0.00107 | ¥0.08984 | ¥0.00236 |
| bench_pilot | c3 | 84 | 23 | 0.274 | 175 | 341 | 0.00153 | ¥0.12866 | ¥0.00559 |
| bench_reasoner | c0 | 54 | 9 | 0.167 | 130 | 3122 | 0.01264 | ¥0.68266 | ¥0.07585 |
| bench_reasoner | c1 | 54 | 41 | 0.759 | 193 | 2496 | 0.01020 | ¥0.55081 | ¥0.01343 |
| bench_reasoner | c2 | 54 | 4 | 0.074 | 185 | 3772 | 0.01530 | ¥0.82596 | ¥0.20649 |
| bench_reasoner | c2f | 54 | 52 | 0.963 | 667 | 2003 | 0.00818 | ¥0.44165 | ¥0.00849 |
| bench_reasoner | c2v | 54 | 48 | 0.889 | 537 | 2991 | 0.01217 | ¥0.65696 | ¥0.01369 |
| bench_reasoner | c3 | 54 | 8 | 0.148 | 163 | 3037 | 0.01233 | ¥0.66604 | ¥0.08326 |
| authority_chat | c1f | 108 | 92 | 0.852 | 684 | 156 | 0.00130 | ¥0.14058 | ¥0.00153 |
| authority_chat | c1v | 108 | 95 | 0.88 | 554 | 162 | 0.00120 | ¥0.12927 | ¥0.00136 |
| authority_chat | c2a | 108 | 94 | 0.87 | 264 | 220 | 0.00113 | ¥0.12176 | ¥0.00130 |
| authority_order_chat | c2ar | 108 | 79 | 0.731 | 264 | 229 | 0.00118 | ¥0.12706 | ¥0.00161 |
| authority_c2an_chat | c2an | 108 | 87 | 0.806 | 297 | 223 | 0.00118 | ¥0.12742 | ¥0.00146 |
| c0tests_chat | c0f | 54 | 32 | 0.593 | 612 | 150 | 0.00114 | ¥0.06152 | ¥0.00192 |
| c0tests_chat | c0v | 54 | 31 | 0.574 | 481 | 154 | 0.00103 | ¥0.05578 | ¥0.00180 |
| c0tests_reasoner | c0f | 54 | 51 | 0.944 | 612 | 1671 | 0.00722 | ¥0.38985 | ¥0.00764 |
| c0tests_reasoner | c0v | 54 | 50 | 0.926 | 481 | 2428 | 0.01013 | ¥0.54683 | ¥0.01094 |
| mixed_chat | h1 | 54 | 33 | 0.611 | 195 | 234 | 0.00113 | ¥0.06117 | ¥0.00185 |
| mixed_chat | h2 | 54 | 3 | 0.056 | 190 | 254 | 0.00120 | ¥0.06496 | ¥0.02165 |
| mixed_chat | m1 | 54 | 20 | 0.37 | 470 | 260 | 0.00152 | ¥0.08201 | ¥0.00410 |
| mixed_chat | m2 | 54 | 3 | 0.056 | 465 | 277 | 0.00158 | ¥0.08510 | ¥0.02837 |
| mixed_chat | m3 | 54 | 3 | 0.056 | 426 | 250 | 0.00142 | ¥0.07688 | ¥0.02563 |
| mixed_chat | m4 | 54 | 2 | 0.037 | 315 | 293 | 0.00148 | ¥0.08009 | ¥0.04004 |
| mixed_chat | m5 | 54 | 25 | 0.463 | 320 | 256 | 0.00135 | ¥0.07265 | ¥0.00291 |
| mixed_chat | m6 | 54 | 7 | 0.13 | 296 | 266 | 0.00136 | ¥0.07341 | ¥0.01049 |
| mixed_reasoner | h1 | 26 | 19 | 0.731 | 195 | 2746 | 0.01121 | ¥0.29133 | ¥0.01533 |
| mixed_reasoner | h2 | 24 | 2 | 0.083 | 191 | 4309 | 0.01745 | ¥0.41870 | ¥0.20935 |
| mixed_reasoner | m1 | 24 | 13 | 0.542 | 476 | 2600 | 0.01087 | ¥0.26100 | ¥0.02008 |
| mixed_reasoner | m2 | 23 | 1 | 0.043 | 473 | 3536 | 0.01461 | ¥0.33608 | ¥0.33608 |
| mixed_reasoner | m3 | 24 | 3 | 0.125 | 426 | 4309 | 0.01765 | ¥0.42369 | ¥0.14123 |
| mixed_reasoner | m4 | 17 | 2 | 0.118 | 320 | 3607 | 0.01476 | ¥0.25085 | ¥0.12543 |
| mixed_reasoner | m5 | 18 | 11 | 0.611 | 326 | 2275 | 0.00944 | ¥0.16996 | ¥0.01545 |
| mixed_reasoner | m6 | 18 | 5 | 0.278 | 302 | 2319 | 0.00958 | ¥0.17252 | ¥0.03450 |
| mitigation_chat | n1 | 54 | 35 | 0.648 | 185 | 238 | 0.00114 | ¥0.06146 | ¥0.00176 |
| mitigation_chat | n2 | 54 | 0 | 0.0 | 180 | 266 | 0.00124 | ¥0.06688 | n/a |
| mitigation_chat | obs1 | 54 | 37 | 0.685 | 194 | 228 | 0.00111 | ¥0.05982 | ¥0.00162 |
| mitigation_chat | obs2 | 54 | 1 | 0.019 | 189 | 294 | 0.00136 | ¥0.07351 | ¥0.07351 |
| mitigation_chat | scope1 | 54 | 34 | 0.63 | 207 | 230 | 0.00113 | ¥0.06093 | ¥0.00179 |
| mitigation_chat | scope2 | 54 | 0 | 0.0 | 202 | 270 | 0.00128 | ¥0.06900 | n/a |
| mitigation_chat | tag1 | 54 | 36 | 0.667 | 198 | 244 | 0.00118 | ¥0.06350 | ¥0.00176 |
| mitigation_chat | tag2 | 54 | 0 | 0.0 | 193 | 303 | 0.00140 | ¥0.07552 | n/a |
| mitigation_chat | v1 | 54 | 42 | 0.778 | 192 | 234 | 0.00113 | ¥0.06096 | ¥0.00145 |
| mitigation_chat | v2 | 54 | 2 | 0.037 | 190 | 277 | 0.00129 | ¥0.06973 | ¥0.03487 |
| mitigation_chat | warn1 | 54 | 28 | 0.519 | 205 | 231 | 0.00113 | ¥0.06111 | ¥0.00218 |
| mitigation_chat | warn2 | 54 | 1 | 0.019 | 200 | 269 | 0.00127 | ¥0.06861 | ¥0.06861 |
| mitigation_reasoner | n1 | 21 | 17 | 0.81 | 186 | 2158 | 0.00884 | ¥0.18569 | ¥0.01092 |
| mitigation_reasoner | n2 | 20 | 0 | 0.0 | 182 | 4006 | 0.01622 | ¥0.32450 | n/a |
| mitigation_reasoner | obs1 | 8 | 4 | 0.5 | 197 | 1948 | 0.00801 | ¥0.06410 | ¥0.01603 |
| mitigation_reasoner | obs2 | 20 | 2 | 0.1 | 191 | 3284 | 0.01335 | ¥0.26692 | ¥0.13346 |
| mitigation_reasoner | scope1 | 8 | 5 | 0.625 | 210 | 1637 | 0.00678 | ¥0.05427 | ¥0.01085 |
| mitigation_reasoner | scope2 | 7 | 1 | 0.143 | 200 | 3556 | 0.01445 | ¥0.10114 | ¥0.10114 |
| mitigation_reasoner | tag1 | 8 | 4 | 0.5 | 201 | 2466 | 0.01009 | ¥0.08073 | ¥0.02018 |
| mitigation_reasoner | tag2 | 8 | 1 | 0.125 | 192 | 2842 | 0.01158 | ¥0.09266 | ¥0.09266 |
| mitigation_reasoner | v1 | 21 | 19 | 0.905 | 194 | 1828 | 0.00753 | ¥0.15817 | ¥0.00832 |
| mitigation_reasoner | v2 | 19 | 4 | 0.211 | 192 | 3686 | 0.01495 | ¥0.28414 | ¥0.07103 |
| mitigation_reasoner | warn1 | 8 | 4 | 0.5 | 208 | 1999 | 0.00823 | ¥0.06581 | ¥0.01645 |
| mitigation_reasoner | warn2 | 20 | 1 | 0.05 | 202 | 3551 | 0.01442 | ¥0.28846 | ¥0.28846 |
| natural | c0 | 20 | 6 | 0.3 | 148 | 151 | 0.00075 | ¥0.01493 | ¥0.00249 |
| natural | c1 | 20 | 17 | 0.85 | 1093 | 145 | 0.00147 | ¥0.02932 | ¥0.00172 |
| natural | c2 | 20 | 6 | 0.3 | 455 | 108 | 0.00082 | ¥0.01643 | ¥0.00274 |
| natural | c2f | 20 | 20 | 1.0 | 603 | 83 | 0.00055 | ¥0.01103 | ¥0.00055 |
| natural | c2v | 20 | 19 | 0.95 | 572 | 85 | 0.00056 | ¥0.01116 | ¥0.00059 |
| natural | c3 | 20 | 8 | 0.4 | 710 | 94 | 0.00102 | ¥0.02035 | ¥0.00254 |
| natural_prior_chat | c0 | 48 | 25 | 0.521 | 120 | 132 | 0.00065 | ¥0.03107 | ¥0.00124 |
| natural_prior_chat | c1 | 48 | 42 | 0.875 | 1065 | 121 | 0.00150 | ¥0.07179 | ¥0.00171 |
| natural_prior_chat | c2 | 48 | 29 | 0.604 | 427 | 84 | 0.00072 | ¥0.03458 | ¥0.00119 |
| natural_prior_chat | c2f | 48 | 48 | 1.0 | 472 | 40 | 0.00037 | ¥0.01765 | ¥0.00037 |
| natural_prior_chat | c2v | 48 | 47 | 0.979 | 480 | 55 | 0.00047 | ¥0.02263 | ¥0.00048 |
| natural_prior_chat | c3 | 48 | 30 | 0.625 | 681 | 90 | 0.00095 | ¥0.04559 | ¥0.00152 |
| natural_prior_reasoner | c0 | 24 | 8 | 0.333 | 113 | 1556 | 0.00637 | ¥0.15276 | ¥0.01910 |
| natural_prior_reasoner | c1 | 24 | 17 | 0.708 | 1060 | 914 | 0.00472 | ¥0.11329 | ¥0.00666 |
| natural_prior_reasoner | c2 | 24 | 8 | 0.333 | 421 | 1481 | 0.00635 | ¥0.15238 | ¥0.01905 |
| natural_prior_reasoner | c2f | 24 | 21 | 0.875 | 466 | 450 | 0.00209 | ¥0.05015 | ¥0.00239 |
| natural_prior_reasoner | c2v | 24 | 21 | 0.875 | 474 | 603 | 0.00277 | ¥0.06653 | ¥0.00317 |
| natural_prior_reasoner | c3 | 24 | 9 | 0.375 | 676 | 1552 | 0.00689 | ¥0.16537 | ¥0.01837 |

## Caveats

- Pricing constants are the paper's **off-peak** DEEPSEEK constants (cache hit ¥0.02/M, miss ¥1.0/M, output ¥4.0/M); if the runs were billed at peak prices, absolute ¥ values change, but the logged `cost_cny` uses the same constants, so the *relative* input/output split and deltas stay internally consistent.
- Prompt-token counts are char→token **estimates** (validation MAPE above), not tokenizer-exact for every row; completion tokens and the input/output cost split are exact from the logs.
- Cache-hit fractions are not directly observed per row; prompt-token estimates + exact input cost imply effective input pricing, and the audit shows the prompt-cache hit tokens for the audited calls. Effective input prices below ¥1.0/M (c2v/c2f in Table 1) indicate either prompt-cache discounts or prompt-token estimation error on code-heavy prompts; neither changes the exact cost split or the exact completion-token counts.
- Deltas compare conditions within the same task set/model; seeds are prompt variants, not independent samples; cost per success is sensitive to the small number of passes for low-pass conditions (e.g., c2).
- Only conditions/datasets listed above are included; `bench_reasoner_2400cap`, `bench_reasoner_cap16k`, agentic history variants (`agentic`, `agentic_v1`, `agentic_verify`) and `paired_probe_chat` are duplicates/diagnostics and are excluded from the tables to avoid double counting.

## Exact quotable sentences

> The expanded chat benchmark costs ¥0.00109–0.00120 per run (input + output); correct KB entries raise input cost by ~47% but lower completion cost enough that total cost is ~4.5% lower and cost per successful task is 5.4× lower (¥0.00724 → ¥0.00135).
> The cost advantage of correct entries is not a completion-token-only artifact: it survives as total cost (marginally: −4.5% in chat, −19.3% on the reasoner) and as cost per success (5.4× in chat, 5.6× on the reasoner), but the mechanism is dominated by fewer completion tokens and higher pass rates; KB prompts themselves cost more to send (+~47% input cost).
> For stale KBs, cost per success is 3.6× worse than no KB in the chat benchmark (¥0.0260 vs ¥0.0072), driven by the collapse in pass rate rather than by longer outputs.
