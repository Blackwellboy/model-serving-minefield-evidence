# DSV4 abliterated long soak - 2026-07-28

Session `dsv4-long-soak`. **Request-level only.** `HOST:PORT` was never restarted,
reconfigured, stopped, or subjected to any container operation. Nothing was run
on test-node-1, test-node-2 or test-node-3 as part of the soak.

**Single serve, no baseline arm. Every number below is DESCRIPTIVE, not
comparative.** There is no control serve, no A/B, and no second build. Nothing
here supports a claim that DSV4 is better or worse than anything else.

**Scope: the abliterated build only** (`dsv4_ablit_mida`, community abliterated
DeepSeek-V4-Flash + the local garble fix). None of it generalises to stock
DeepSeek-V4.

---

## 1. The two clocks, stated separately

A prior return reported 16 hours for a 6h39m run by reading container uptime.
Keeping them apart:

| clock | value |
|---|---|
| **SOAK elapsed** | **10.20 h** (36,720 s), 11:21:21Z → 21:33:22Z |
| **CONTAINER uptime at soak start** | **9.84 h** (started 2026-07-28T01:33:13Z) |
| CONTAINER uptime at soak end | ~20.0 h |
| host boot, node-a | 2026-07-28 01:30:16 |
| host boot, node-b | 2026-07-09 12:28:19 (**19 days - not container uptime**) |

The brief's "served for six days" describes the lane/build era. **This process
was ~10 h old when the soak began**, restarted by the power-cycle recorded in
`lanes.json`. node-b's 19-day host uptime is unrelated: its container restarted
at 01:32:34Z alongside node-a's, because TP=2 pairs them. `RestartCount` was
**0** on both nodes at start and still 0 at end - the serve never restarted
during the soak.

## 2. Lane health timeline

| | result |
|---|---|
| HTTP status | **2400 / 2400 = 200.** No other status, ever. |
| Error classes | **none** |
| Preemptions | **0** across all 40 windows |
| Container restarts | 0 on both nodes |
| `/health` (independent sampler) | **291 / 291 = 200** |
| Backoffs triggered | 0 (no latency or memory movement met threshold) |

**Memory did not move.** node-a available 7569 MB → 7503 MB over 2400 requests
(full range 7469-7574); node-b 9121 → 9090. Swap: node-a 2769 → 2768 MB,
node-b 2630 → 2622 MB - i.e. slightly *less* swap in use at the end. On nodes
sitting at ~113/121 GB this is the outcome that matters: **no burn, no creep,
across 10.2 hours.**

**KV cache: rose then plateaued, and it was self-inflicted.** 65.1% → 96.4% over
the first 12 windows, then pinned at 96.4% for the remaining 28 windows with
preemptions still 0. The climb is an artifact of my own instrumentation - a
unique `cache_salt` per request (chosen for honest cold-prefill TTFT) means
every turn allocates prefix blocks that are never reused, so occupancy only
grows until LRU eviction balances it. Eviction engaged and held. **This curve
should not be read as lane behaviour under normal shared-prefix traffic.**

**One real finding on the management plane.** The independent sampler recorded
**5 failed samples out of 291, all on node-b, all SSH timeouts** ("connection
timed out during banner exchange"), spread across the run - while the serving
lane was 2400/2400 healthy throughout. Management-plane reachability to node-b
is intermittently flaky in a way the serving path is not. This is only visible
because the sampler was changed mid-run to *record* failed samples; the original
version dropped them silently, which would have degraded the burn detector to
single-node coverage while still looking healthy.

## 3. Per-family acceptance - never a pooled number alone

n = 400 per family, interleaved round-robin so the mix is constant by
construction.

| family | acceptance | tok/step | TTFT p50 | e2e p50 | out tok/s | stop% | length% |
|---|---|---|---|---|---|---|---|
| math_nothink | **78.14%** | 3.344 | 0.42 s | 8.0 s | 33.3 | 100% | 0% |
| code | 75.74% | 3.272 | 0.41 s | 36.4 s | 33.1 | 62% | **38%** |
| math_think | 74.80% | 3.244 | 0.41 s | 11.6 s | 32.8 | 100% | 0% |
| longctx | 66.18% | 2.985 | 2.35 s | 3.8 s | 12.8 | 100% | 0% |
| summarize | 60.10% | 2.803 | 0.53 s | 4.3 s | 25.8 | 100% | 0% |
| chat | **43.37%** | 2.301 | 0.41 s | 3.9 s | 22.8 | 100% | 0% |

**Spread: 34.78 points.** The pooled figure is 66.39% - reported here only as
context, and it describes no family. Citing it alone would hide a 35-point range
and would misdescribe every one of the six.

**Two estimators, 6.31 points apart, both defensible.** Both computed over the
**same 2,400 requests**, which is the only comparison that means anything:

| estimator | value |
|---|---|
| token-weighted, my turns only | **72.70%** |
| request-weighted (each request one vote) | **66.39%** |

**CORRECTED 2026-07-29.** An earlier version of this table printed **73.4%** for
the token-weighted figure. That number is `fleet_tw` - the process-wide value
straight off `/metrics`, which includes traffic outside my request set (the
pre-soak baseline and the 2 positive-control requests). Pairing a process-wide
numerator with a request-scoped one is not like-for-like and inflated the gap to
7.0 points. The like-for-like token-weighted value over my own 2,400 turns is
**72.70%**, and the honest gap is **6.31 points**. The prose figure of "6 points"
was right; the tabulated 73.4% was the wrong number to put beside it.

Token-weighting lets long high-acceptance `code` turns dominate; request-
weighting gives a 40-token chat turn the same vote as a 1,500-token code turn.
Same data. **Report which one you mean.**

**The thinking flag is not the driver.** `math_think` and `math_nothink` run
*identical prompts*, differing only in the flag: **−3.34 pts** (74.80 vs 78.14),
against a 34.78-pt family spread. On this build the *task* moves acceptance, not
the reasoning toggle. This comparison only exists because the two arms share
prompts.

**CORRECTED 2026-07-29.** An earlier version of this section claimed the result
"points the opposite way from the Super result, where reasoning was the worst
family." **That comparison does not exist and the sentence is withdrawn.** The
Nemotron Super soak produced **no per-family acceptance figures at all** - its
own `SOAK_RESULTS.md` records that its spec_decode counters are process-wide and
its round-robin workload put all seven families in equal counts in every scrape
window, which destroys family attribution. What that run established about the
reasoning family was **empty content at a token ceiling** (30.82% of thinking-on
reasoning turns returned blank) and a **decode rate** of 26.4 tok/s. Neither is
acceptance. The "45.4%" figure originated in a session brief, was repeated here
without being checked against the source, and is not supported by it.

## 4. Drift across fixed request-count windows

40 windows × 60 requests. Every boundary recorded at both edges. **No time-based
deltas anywhere** - a counter reset mid-window would fabricate a delta silently.

**Fleet token-weighted acceptance ranged 73.03% - 73.76% across all 2,400
requests. Total spread: 0.73 points.**

First 300 requests vs last 300, per family:

| family | first 300 | last 300 | delta |
|---|---|---|---|
| chat | 43.32% | 43.47% | +0.15 |
| code | 75.52% | 76.00% | +0.48 |
| longctx | 66.28% | 66.53% | +0.25 |
| math_nothink | 77.75% | 78.25% | +0.50 |
| math_think | 74.81% | 74.43% | −0.38 |
| summarize | 59.65% | 59.45% | −0.20 |

**There is no drift at this resolution.** Every family moves less than 0.5 pts
across 10.2 hours. Because families are interleaved evenly, drift could not
masquerade as a task effect and a task effect could not masquerade as drift.

**Attribution is measured, not assumed.** Foreign inference was **0 in 39 of 40
windows**. Window 9 shows exactly **2** - my own positive-control requests, and
I fired exactly 2. That the counter can read non-zero is what makes the 39 zeros
meaningful rather than a silent detector. The `/health`-class poll traffic
(~44/window from watchdog, board renderer and ModelOps dashboard) is counted
separately and never enters the acceptance figures. **No unattributed fraction.**

## 5. Reasoning close-marker - position, not just count

400 thinking turns:

- **400/400 closed reasoning** (100%)
- **0 empty-content completions**
- close position p50 **727 chars**, p95 1,048
- close position as a fraction of generation: p50 **0.659**, p95 0.733
- estimated reasoning tokens p50 256, p95 315

On Super, close *position* separated empty from successful completions at
p=6.5e-46 while token *count* did not. **Here that mechanism has nothing to
separate**: there were no empty completions and no unclosed reasoning in 400
turns. The instrument was in place and the phenomenon did not occur - which is
a different and stronger statement than not having looked.

## 6. Spontaneous symptoms

**Zero.** Across 2,400 turns: no garble, no registry/template-token leakage, no
CJK intrusion, no non-ASCII bloom, no unclosed reasoning, no empty content, no
`tokens_per_step` above the K+1 ceiling. The scanners were mutation-tested
against planted positives, so this zero is a measured zero.

The only truncation is `code` at 38% `finish_reason: length`, which is my
`max_tokens` 1500 cap meeting long code answers - a harness choice, not a lane
symptom.

## 7. Instrumentation defects found in my own harness

Recorded because a green result from an unvalidated instrument is worthless.

1. **Delta ≠ token.** One SSE delta carries 2.2-3.5 tokens under MTP K=3.
   Counting deltas as "reasoning tokens" would have been wrong by ~3×. Caught in
   smoke by cross-checking against `usage`. Turned into the run's best
   instrument: `completion_tokens / decode_steps` is a per-request acceptance
   proxy, request-scoped and immune to fleet-wide contamination.
2. **Garble scanner false positive** on ordinary code indentation. First fix
   passed a unit test and still failed live - the lookahead matched a later
   non-space on the same line rather than inside the repeated unit.
3. **Spurious close-marker at position 0** on every non-thinking turn,
   conflating "no reasoning" with "closed immediately".
4. **9 negative TTFT values out of 2,400** (−0.012 to −0.802 s) from
   `time.time()` under a syncing NTP clock. **TTFT p50 is ~0.41 s, so the clock
   step is larger than the signal: my sub-second TTFT figures are not reliable
   below ~1 s.** e2e (multi-second) is unaffected, as are token counts, memory,
   HTTP status and all acceptance figures. Fix is `time.monotonic()`, carried
   forward into the cross-model probe.
5. **Memory sampler dropped failed samples silently**, so the burn detector
   could have degraded to one node while still looking healthy. Fixed mid-run by
   an independent sampler that records failures explicitly - which is how the 5
   node-b SSH timeouts in §2 were seen at all.
6. **A readiness loop whose memory guard was silently broken** by nested
   quoting: it evaluated empty strings and "checked" nothing for 30 polls.

Items 5 and 6 are the false-healthy class appearing *inside the tooling built to
detect it*.

## 8. What this soak cannot say

- Nothing comparative. Single serve, no baseline arm.
- Nothing about stock DeepSeek-V4. Abliterated build only.
- Nothing about long-context behaviour: **max prompt was 1,954 tokens = 1
  prefill chunk.** The entire soak sits inside the clean regime of the
  `dsv4-idle-work` cold-prefill entry. The 2400/2400 clean result is therefore
  *corroboration* of that entry's 1-2 chunk arm at n=400 per family, and is
  **not** evidence against the >2-chunk failure.
- Nothing about drift beyond ~0.7 pts resolution over 10.2 h at this request rate.
- TTFT below ~1 s (see §7 item 4).
