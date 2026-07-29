# Evidence manifest: DSV4-Flash long soak, 2026-07-28

Durable manifest created 2026-07-29 by session `LAND_RECONCILED_SOAK_TRAPS_20260729`.
This bundle is the evidence behind public traps **105** and **106** in
`Blackwellboy/model-serving-minefield`, and the corroborating negative in the
2026-07-29 addendum to trap 12.

**LOCAL ONLY. Not published.** The public entries carry the status
`measured here, raw not published` for exactly this reason. Their checks are
written so a reader settles the same question on their own lane from counters
they can read, which is the substitute for raw we can actually offer.

| Field | Value |
|---|---|
| Source node | the two-node serving pair, two DGX Spark GB10 nodes, TP=2 (request-level only) |
| Model | community abliterated DeepSeek-V4-Flash, `dsv4_ablit_mida`, NVFP4 |
| KV dtype | `nvfp4_ds_mla`, block size 256, 20,139 GPU blocks |
| Serving engine | vLLM `0.21.1rc1.dev339+g1967a5627bc3` |
| Speculative | MTP `dspark`, 3 draft tokens (K=3) |
| Serve flags | `--max-num-seqs 4`, `--max-model-len 1048576`, `--enable-prefix-caching` |
| Run window | 2026-07-28, 10.20 h |
| Requests | 2,400, all HTTP 200 |
| Windows | 40 fixed request-count windows, 60 requests each |
| Task families | 6, n=400 each, interleaved so the mix is constant |
| Failures / retries | none; 0 preemptions across the run |
| Exclusions | pre-soak baseline and 2 positive-control requests are OUTSIDE the 2,400 and must not be pooled with them (this is the trap-105 finding) |

## Re-derived 2026-07-29 directly from `raw/turns.jsonl`

| Quantity | Value |
|---|---|
| token-weighted acceptance, scoped to the 2,400 | **72.6991%** |
| request-weighted acceptance (mean of per-request) | **66.3888%** |
| estimator gap | **6.3102 points** |
| unscoped process-wide `/metrics` value | 73.4% (NOT like-for-like) |
| per-family spread | 43.37% (chat) to 78.14% (math, thinking off) = **34.78 points** |
| thinking turns closing their reasoning block | 400/400 |
| empty completions | 0 |

## Paths

- `raw/turns.jsonl` (2,400 per-request rows), `raw/windows.jsonl`,
  `raw/memory.jsonl`, `raw/events.jsonl`, `raw/sampler.jsonl`,
  `raw/positive_control.jsonl`, `raw/laguna/` (cross-model arms)
- `analyze.py`, `pc_probe.py` (analysis + probe drivers)
- `smoke/`, `smoke2/`, `smoke3/` (pre-run smoke passes)
- `entries/` SUPERSEDED drafts numbered 98/99, rebased to 105/106 before landing
- `_proofs/` sanitizer proofs
- `SHA256SUMS` (46 files, generated 2026-07-29)
