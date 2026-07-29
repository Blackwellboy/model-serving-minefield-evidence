# Nemotron 3 Super 120B A12B NVFP4 soak, 2026-07-28

Backs Minefield traps **107** (a short soak changes the verdict) and **108**
(a burn canary is bistable, not degrading), and the 2026-07-29 addendum to
**trap 12**.

**Single serve, no baseline arm.** Every rate below is at `max_tokens=1024` on
this task mix and does not transfer to another budget.

| | |
|---|---|
| Model | NVIDIA Nemotron 3 Super 120B A12B NVFP4, rev `4f0cf9daaeb7a4d5e23f80a00e7ed15f0e03caf6` |
| Runtime | vLLM 0.20.0, image `sha256:04563c302537a91aa49ebdfbceda96111c5712275999b7e8804fa598f0b5641d` |
| Speculative | MTP `num_speculative_tokens=3` |
| Run | 13.009 h, 2,045 turns, all HTTP 200, 147 scrapes |

## Headline numbers, all reproduced by `verify.py`

| Quantity | Value |
|---|---|
| container memory peak | **3.538 GiB at h=7.36** |
| final memory | 3.354 GiB at h=13.0, **below** its own h=1.09 value of 3.378 |
| total excursion | 0.32 GiB against a 121 GiB pool |
| burn canary | 25 samples, **exactly 2 distinct outputs**, split **21 / 4** |
| out-of-band t0 sample | a third output, TTFT 1.72 s against 0.35 to 0.37 s in band |
| empty-content responses | **92 of 2,045 = 4.50%**, all thinking-on, all `finish_reason: length` |
| thinking-off empties | **0 of 1,022** |
| worst family (reasoning, thinking-on) | **30.82%** |
| families never affected | 3 of 7 |
| quartile rates | 10.20 / 9.02 / 7.84 / 8.91 %, flat |

```bash
python3 verify.py      # 26 checks, exits non-zero on any drift
```

## Layout

- `raw-scrubbed/raw/` turns, metrics scrapes, canary samples, engine logs
- `drivers/` soak driver, analysis, recompute and mix-check scripts
- `analysis/` the original analysis, recompute and mix-check output
- `FINDINGS.md`, `METHODS.md`, `MANIFEST.md`, `SHA256SUMS`

## Open, and not claimed as resolved

A **64.22 vs 67.33** per-family acceptance gap survives both the estimator check
and a 0.12-point mix bound. It is not explained. It is carried into trap 105 as
a counter-example where the per-family split was not computable by design,
because the counters are process-wide and the scrape period is an exact multiple
of the round-robin cycle.
