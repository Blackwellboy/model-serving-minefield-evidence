# Evidence manifest: Nemotron 3 Super 120B long soak, 2026-07-28

Durable manifest created 2026-07-29 by session `LAND_RECONCILED_SOAK_TRAPS_20260729`.
This bundle is the evidence behind public traps **107** and **108** in
`Blackwellboy/model-serving-minefield`, the primary source for the 2026-07-29
addendum to trap 12, and the counter-example grafted into trap 105.

**LOCAL ONLY. Not published.** Public entries carry `measured here, raw not published`.

| Field | Value |
|---|---|
| Source node | single GB10-class node, TP=1 |
| Model | NVIDIA Nemotron 3 Super 120B A12B NVFP4 |
| Immutable revision | `4f0cf9daaeb7a4d5e23f80a00e7ed15f0e03caf6` |
| Serving engine | vLLM 0.20.0, image digest `sha256:04563c302537a91aa49ebdfbceda96111c5712275999b7e8804fa598f0b5641d` |
| Speculative | MTP `num_speculative_tokens=3` |
| Serve flags | `--gpu-memory-utilization 0.90` |
| Generation | `max_tokens=1024`, `temperature=1.0`, `top_p=0.95` |
| Run window | 2026-07-28, 13.009 h |
| Turns | 2,045 (1,023 thinking-on / 1,022 thinking-off), all HTTP 200 |
| Task families | 7, round-robin, `enable_thinking` alternating |
| Instrumented scrapes | 147 |
| Failures / retries | none; 0 preemptions at every scrape |

## Re-derived 2026-07-29 directly from raw

| Quantity | Value | Source file |
|---|---|---|
| container memory peak | **3.538 GiB at h=7.36** (tied at h=7.89) | `raw/metrics.jsonl` |
| memory at h=13.00 | 3.354 GiB, **below** its own h=1.09 value of 3.378 GiB | `raw/metrics.jsonl` |
| burn-canary in-band samples | 25, all status 200 | `raw/canary.jsonl` |
| distinct canary outputs | **exactly 2**: `7e776e9bd5e2` (356 chars) x21, `81a6298f36c3` (346 chars) x4 | `raw/canary.jsonl` |
| canary TTFT, in-band | 0.35 to 0.37 s | `raw/canary.jsonl` |
| out-of-band t0 sample | `2f97d795fd1d`, 426 chars, TTFT 1.717 s | `raw/canary_t0.jsonl` |
| empty-content 200s | **92 of 2,045 = 4.50%**, all thinking-on, all `finish_reason: length` | `raw/turns.jsonl` |
| thinking-off empties | **0 of 1,022** | `raw/turns.jsonl` |
| per-family empty rate (thinking-on) | reasoning 30.82%, code 19.18%, structured 10.96%, math 2.05%, prose/tool/summarize 0% | `raw/turns.jsonl` |
| empty rate by quartile | 10.20 / 9.02 / 7.84 / 8.91 % (flat, not climbing) | `raw/turns.jsonl` |

## Paths

- `raw/turns.jsonl`, `raw/metrics.jsonl`, `raw/canary.jsonl`,
  `raw/canary_t0.jsonl`, `raw/engine_log_startup.txt`, `raw/engine_log_tail.txt`
- `drivers/soak_driver.py`, `drivers/analyse.py`, `drivers/recompute.py`,
  `drivers/mixcheck.py`
- `analysis/ANALYSIS_FULL.txt`, `analysis/RECOMPUTE_FULL.txt`,
  `analysis/MIXCHECK_FULL.txt`
- `METHODS.md`, `SOAK_RESULTS.md`
- `_proofs/` sanitizer proofs
- `SHA256SUMS` (18 files, generated 2026-07-29)

## Known open

`64.22 vs 67.33` per-family acceptance gap survives both the estimator check and
a 0.12-point mix bound, and is NOT explained. Carried into trap 105 as a
counter-example where the per-family split was **not computable by design**
(process-wide counters plus a scrape period that is an exact multiple of the
round-robin cycle).
