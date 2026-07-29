# Nemotron Super 120B - 13-hour production soak

**2,045 turns over 13.009 hours. Single serve, no baseline arm.**

Everything below describes one process as it aged. Nothing here is a comparison
against another configuration, model or machine. Where a previously published
Super figure is quoted it is for orientation only, and the workloads differ.

What a single arm *can* establish is internal drift, because the run is its own
control across time. That is the question this soak was built to answer.

---

## 1. Stability

| | |
|---|---|
| turns | 2,045 |
| HTTP status | **200 on all 2,045** |
| transport errors | 0 |
| engine errors / tracebacks | 0 |
| container restarts | 0 (`RestartCount=0`) |
| preemptions (`vllm:num_preemptions_total`) | **0** |
| tool XML leaked into `content` | 0 |
| driver exit | clean, `stopped_early: false` |

`finish_reason`: 1,046 stop, 707 length, 292 tool_calls.

Thirteen hours of continuous sequential load produced no failed request of any
kind. There is nothing to report under instability because nothing happened.

## 2. MTP acceptance drift - the headline

**Acceptance does not drift.** This is the axis the soak existed to measure and
the result is a clean negative.

Fixed request-count windows of 200 requests, boundaries recorded:

| window (turn) | drafts | accepted | accept% | pos0 | pos1 | pos2 |
|---|---|---|---|---|---|---|
| [0, 196) | 118,143 | 76,287 | 64.57% | 81.8% | 63.9% | 48.0% |
| [196, 392) | 120,060 | 76,614 | 63.81% | 81.3% | 63.0% | 47.2% |
| [392, 588) | 115,527 | 74,231 | 64.25% | 81.5% | 63.6% | 47.7% |
| [588, 798) | 125,010 | 80,238 | 64.19% | 81.8% | 63.5% | 47.3% |
| [798, 994) | 115,473 | 74,314 | 64.36% | 81.7% | 63.7% | 47.6% |
| [994, 1190) | 119,745 | 76,786 | 64.12% | 81.5% | 63.3% | 47.5% |
| [1190, 1400) | 123,090 | 79,747 | 64.79% | 81.9% | 64.1% | 48.3% |
| [1400, 1596) | 117,066 | 75,424 | 64.43% | 81.8% | 63.7% | 47.7% |
| [1596, 1792) | 116,253 | 74,879 | 64.41% | 81.7% | 63.8% | 47.8% |
| [1792, 1988) | 112,365 | 72,849 | 64.83% | 82.0% | 64.1% | 48.4% |
| [1988, 2044) | 33,294 | 21,310 | 64.01% | 81.0% | 63.6% | 47.5% |

**Spread across the entire run: 1.02 points (63.81 - 64.83).** No slope. The
last full window (64.83%) is *higher* than the first (64.57%).

Cumulative tracked across checkpoints: 64.20% at 1.7h, 64.13% at 2.4h, 64.22%
at 5.4h, 64.22% at 9.2h. Mean accepted per draft step 1.926 -> 1.927.

**Acceptance on a fresh serve and acceptance thirteen hours in are the same
number.** Per-position decay (~82 / 64 / 48) is likewise fixed; the shape of the
decay does not change as the serve ages.

No counter reset occurred: all 6 spec_decode counters strictly non-decreasing
across 147 scrapes, checked explicitly.

## 3. Throughput and TTFT

Quartile medians: tok/s **27.578 / 27.621 / 27.691 / 27.459**; TTFT **0.366 /
0.365 / 0.364 / 0.363 s**.

Per-family, first half vs second half, all seven within **+/-0.10 tok/s**:

| family | 1st half | 2nd half | delta |
|---|---|---|---|
| code | 27.75 | 27.84 | +0.10 |
| math | 29.92 | 30.02 | +0.10 |
| prose | 20.87 | 20.79 | -0.08 |
| reasoning | 26.31 | 26.37 | +0.06 |

Decode rate sorts by content type exactly as expected of speculative decoding:
tool ~30.8, math ~30.0, structured ~29.8, code ~27.8, reasoning ~26.4,
summarize ~22.8, prose ~20.8 tok/s.

**A mid-run reading that did not survive.** At the 8-hour checkpoint the tok/s
quartiles were monotone decreasing (27.666 -> 27.434) and were reported as a
possible -0.86% decline. At full length the series is not monotone (Q3 is the
maximum) and the effect is gone. It was noise sampled at an unlucky moment.

## 4. Memory - a bounded transient, not a leak

Container memory across the run:

```
0.00h 3.217 -> 4.32h 3.389 -> 5.38h 3.448 -> 6.45h 3.511
 -> 7.54h 3.537 (peak) -> 9.66h 3.529 -> 10.73h 3.380 -> 12.82h 3.354 GiB
```

Total excursion +0.32 GiB, **fully recovered**; the final value is below the
1.09h value (3.378). Host available memory ended *higher* than it started
(3,990 -> 4,578 MB). Zero preemptions throughout.

**This series was misread twice before the run was long enough to settle it**,
and the sequence is worth recording because it is the argument for long soaks:

| observed at | reading given | status |
|---|---|---|
| 5.4h | monotone creep ~0.043 GiB/h; flagged that a 30-day extrapolation would be +31 GiB | wrong |
| 9.2h | plateaued; extrapolation withdrawn | closer |
| 13.0h | bounded transient, fully reverted, no net growth | correct |

A 5-hour soak would have published a memory-leak concern that does not exist.
The reason it was caught is that the extrapolation was flagged as the weakest
claim rather than acted on.

## 5. X-02 empty content - the operator-relevant finding

92 of 2,045 turns (**4.50%**) returned HTTP 200 with a populated reasoning
block, zero `content`, and `finish_reason: length`. Every one is thinking-on.

| family | turns | empty | rate (all) | **rate (thinking-on)** |
|---|---|---|---|---|
| reasoning | 292 | 45 | 15.41% | **30.82%** |
| code | 292 | 28 | 9.59% | **19.18%** |
| structured | 292 | 16 | 5.48% | **10.96%** |
| math | 292 | 3 | 1.03% | 2.05% |
| prose | 293 | 0 | 0% | **0%** |
| tool | 292 | 0 | 0% | **0%** |
| summarize | 292 | 0 | 0% | **0%** |

**Thinking-off: 0 empty completions across 1,022 turns.**

This reproduces registry item X-02 spontaneously, under an organic workload at a
routine 1024-token budget, rather than in a deliberate ceiling sweep. The
concentration is the useful part: with thinking on, **nearly a third of
reasoning-family requests return a blank answer**, while three families never do
it at all. Operator advice is therefore not "raise the budget" but "raise it for
reasoning, code and structured output".

Rate by quartile of thinking-on turns: 10.20 / 9.02 / 7.84 / 8.91%. Slightly
declining, not rising - a configuration property, not burn.

**Scope limit:** this rate is the rate *at max_tokens 1024*. It does not
transfer to other budgets, and the run does not establish where the safe floor
is for any family.

## 6. Burn detector - bistable, not degrading

**Corrected 2026-07-29.** This table previously read 22 and 3 while listing
**four** timestamps for the variant it called 3, and pooled the out-of-band
t~0 reference into the distinct-output count. Both are fixed below and the
counts now match `verify.py` and trap 108. Re-derived from `raw/canary.jsonl`.

**25 in-band canaries**, identical prompt, temperature 0, fixed seed, thinking
off. Exactly **2 distinct outputs**:

| sha256[:12] | chars | occurrences |
|---|---|---|
| `7e776e9bd5e2` | 356 | **21** |
| `81a6298f36c3` | 346 | **4** (at 2.02h, 2.53h, 4.55h, 7.09h) |

A **third** output, `2f97d795fd1d` (426 chars), came from the out-of-band t~0
reference fired before the series. It is recorded separately rather than
merged: a first request on a freshly warmed engine is not the same condition
as the rest, and pooling it inflates the distinct-output count from 2 to 3,
which is exactly the error trap 108 warns against.

The two in-band variants **alternate in both directions** with no ordering, then
`81a6298f` stops appearing after 7.09h. A burn signature would be monotone - 
progressive shortening, or a one-way transition. This is neither.

**A naive burn detector comparing consecutive canaries would have fired six
false alarms in this run.** The correct reading requires the whole series.

Canary TTFT is locked at 0.35-0.37 s for all 25 in-band samples. The t~0
reference's 1.72 s TTFT and differing output are consistent with first-request
warmup; it is kept separate rather than merged into the series.

This fleet's documented temperature-0 non-determinism is confirmed here on a
serve with `enable_prefix_caching=False`, so the prefix cache is excluded as the
mechanism for this instance.

## 7. Cold start

Launched 07:43:26Z, `Application startup complete` 07:53:47Z - **10m40s**,
against ~11m14s recorded previously for the same line. Weights read three times
(7m29s, then 1m09s, 1m09s). Engine reported GPU KV cache 1,188,064 tokens and
6.56x max concurrency for 1M-token requests.

Readiness was a completed generation. `/v1/models` returned HTTP 200 while the
model was still loading, recorded deliberately as the contrast case.

## 8. What this run does not establish

- **No baseline arm.** Descriptive only.
- **Per-family acceptance is not measurable from this log.** The engine's
 spec_decode counters are process-wide, and the round-robin workload puts all
 seven families in equal counts in every scrape window. The design choice that
 makes the drift result strong is the one that destroys family attribution.
 This is why the 64.22% vs the previously published 67.33% is left **open and
 unexplained** rather than attributed to workload mix - see section 9.
- **Sequential single-stream.** Nothing here characterises concurrency, which is
 where preemption and KV pressure would appear. tok/s is a per-request decode
 rate, not a serving-capacity figure.
- **One budget** (1024) for workload turns, **one node, one serve, one day.** No
 run-to-run variance.

## 9. The 64.22% vs 67.33% gap, stated honestly

The previously published Super figure is **pooled** (`67,987 / 100,977`,
draft-weighted). The soak figure is **also pooled**, computed as
`sum(accepted)/sum(drafts)` from the same class of engine counters. The
comparison is like-for-like, so the 3.1-point gap is **not an estimator
artefact**.

Workload mix is the obvious candidate, and it was **tested rather than
assumed**. Pooled acceptance is draft-token weighted, and balanced request
counts do not imply balanced token weights - here they differ sharply (code 24.7%
of completion tokens on 14.3% of requests; tool 1.4% on 14.3%). But the weights
do not *move*: the largest per-family token-share swing across quartiles is
**0.75 points**, bounding the worst-case mix artefact at **0.12 points**. For
comparison, the DSV4 case where mix genuinely dominated required a 45-point
share swing.

So mix drift cannot explain the gap either. **The gap is real, unexplained, and
requires a per-request acceptance measurement to close.** It is recorded as open.

---

## Method credit

The fixed request-count windowing and the insistence on per-family rather than
pooled acceptance reporting come from @Hikari_07_jp's published measurement
methodology, adopted here after a mid-run methodology review.

Two adaptations are recorded honestly:

1. The soak's scrape cadence was **already** request-triggered (every 14 turns,
 verified: the turn-index gap between all 147 scrapes is exactly 14, while
 wall-clock spacing varies 5.0-6.1 min). Aggregating to 200-request windows is
 a coarsening of an already request-count series, not a correction of a
 time-based one. It costs time resolution and gains comparability of window
 size.
2. Fixed request-count windows are **not** reset-immune. A reset corrupts
 `c1 - c0` regardless of how the boundary is chosen. Reset-safety comes from
 detecting the monotonicity violation, which is now an explicit check and
 which reported cleanly here.

The per-family reporting requirement is correct and could not be satisfied - see
section 8. That is a limitation of this run's design, recorded rather than papered over
with a derived estimate.
