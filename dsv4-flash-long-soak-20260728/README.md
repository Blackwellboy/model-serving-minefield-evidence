# DSV4-Flash long soak, 2026-07-28

Backs Minefield traps **105** (acceptance rate without a named estimator) and
**106** (KV occupancy climbing to a ceiling is not a leak).

**Single serve, no baseline arm.** This describes one community abliterated
checkpoint on one runtime build on one two-node pair under one workload mix. It
is not a comparison and none of the absolute numbers transfer.

| | |
|---|---|
| Model | community abliterated DeepSeek-V4-Flash, `dsv4_ablit_mida`, NVFP4 |
| Runtime | vLLM `0.21.1rc1.dev339+g1967a5627bc3`, TP=2, two GB10-class nodes |
| Speculative | MTP `dspark`, K=3 |
| Run | 10.20 h, 2,400 requests, all HTTP 200, 40 windows of 60 |

## Headline numbers, all reproduced by `verify.py`

| Quantity | Value |
|---|---|
| token-weighted acceptance (scoped to these 2,400) | **72.6991%** |
| request-weighted acceptance | **66.3888%** |
| estimator gap | **6.3102 points** |
| per-family range | 43.37% (chat) to 78.14% (math, thinking off) |
| family spread | 34.78 points |
| KV occupancy | 65.1% first window, **96.4% ceiling**, held 28+ windows |
| preemptions | **0** across the run |
| cold-arm prefix-cache hit fraction | **0.0000** |

```bash
python3 verify.py      # 17 checks, exits non-zero on any drift
```

## Layout

- `raw-scrubbed/raw/` per-request, per-window, memory, event, sampler and
  cross-model JSONL. See [REDACTIONS.md](../REDACTIONS.md).
- `drivers/` the soak driver, analysis script, probe, and the two scrub scripts
  that produced this bundle
- `analysis/FULL_ANALYSIS.txt` the original analysis output
- `FINDINGS.md` the study write-up
- `MANIFEST.md`, `SHA256SUMS`

## Caveat that matters most

The occupancy curve in trap 106 is **an artifact of the harness by design**: a
unique `cache_salt` on every request forced a cold prefill for honest TTFT, so
no request could reuse another's blocks. That is why the climb is so linear, and
it is why the curve does not describe this lane under normal traffic. The
`0.0000` hit fraction above is the measurement proving it.
