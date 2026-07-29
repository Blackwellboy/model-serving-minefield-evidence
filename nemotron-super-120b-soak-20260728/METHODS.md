# Nemotron Super 120B production soak - methods

Session `super-soak`, 2026-07-28, a GB10 test node (121 GiB unified memory).

## The single most important limitation

**This is one serve with no baseline arm.** Every number here describes one
process over time. Nothing here is a comparison against another configuration,
another model, or another machine, and no claim of the form "X is faster/better
than Y" can be supported by this run. Where a published Super figure is quoted
alongside a soak figure, it is quoted for orientation only - the workloads
differ, so the two are not a controlled pair.

What a single arm *can* establish is **internal drift**: whether a quantity
measured on this serve changes as the serve ages. That is the question this
session exists to answer, and it is answerable without a second arm because the
run is its own control across time.

## Configuration

Vendor DGX Spark serve line, `vllm/vllm-openai:v0.20.0`, digest
`sha256:04563c302537a91aa49ebdfbceda96111c5712275999b7e8804fa598f0b5641d`
(digest verified on the node against the recipe, not assumed from the tag).

- `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4`, revision pinned
 `4f0cf9daaeb7a4d5e23f80a00e7ed15f0e03caf6`
- TP=1, PP=1, DP=1, single node
- `--speculative_config {"method":"mtp","num_speculative_tokens":3,"moe_backend":"triton"}`
- `--kv-cache-dtype fp8`, `--quantization fp4`, `--moe-backend marlin`
- `--gpu-memory-utilization 0.90`, `--max-num-seqs 4`, `--max-model-len 1000000`
- `--reasoning-parser super_v3` via plugin, `--tool-call-parser qwen3_coder`
- **`enable_prefix_caching=False`** (engine-reported). No prefix-cache confound
 on repeated prompts - relevant because repeated-prompt reuse has produced
 false stability readings elsewhere on this fleet.

Engine-reported at startup: GPU KV cache 1,188,064 tokens; max concurrency 6.56x
for 1M-token requests; graph capture 0.41 GiB.

**Note on the MTP config key.** `num_nextn_predict_layers: 1` is a property of
the *checkpoint*, not a serve-line flag, and is never passed at launch. Three
tokens are drafted from that one shared layer via `num_speculative_tokens: 3`.
The engine warns at startup that `num_speculative_tokens > 1` reruns the same
shared layer and "may result in lower acceptance rate"; the per-position decay
measured here is what that warning looks like.

**Note on max_model_len.** The main model resolves 1,000,000; the MTP draft
model resolves 262,144 in the same startup sequence. The soak ran nowhere near
either, so this is recorded as an observation, not a tested boundary.

## Readiness

Readiness was a **completed generation**, never `/v1/models`. Recorded for
contrast: `/v1/models` returned HTTP 200 while the model was still loading. The
same trap has produced a false pass twice on this fleet.

Cold start: launched 07:43:26Z, `Application startup complete` 07:53:47Z - 
**10m40s**, against ~11m14s recorded previously for the same line. Weights are
read three times (main + draft init); only the first pass is slow (7m29s, then
1m09s, 1m09s).

## Workload

Seven task families - prose, code, math, reasoning, tool, summarize, structured
 - cycled **round-robin, one turn each**, so no family occupies a contiguous
stretch of wall-clock. This is the design point that stops drift masquerading as
a task effect and vice versa: any monotone trend in a per-family series cannot be
an artefact of when that family happened to run.

`enable_thinking` alternates on a period of 2 family-cycles, coprime with
nothing but chosen so that every family sees both settings evenly across the run.

Sampling: `temperature=1.0`, `top_p=0.95`, `max_tokens=1024` (the card's
sampling). Requests are issued **sequentially, one at a time**, despite
`max-num-seqs 4`. Therefore reported tok/s is a clean per-request decode rate,
not an aggregate throughput figure, and must not be read as a serving-capacity
number.

TTFT is measured from request send to the first streamed token-bearing delta.
Reasoning text is accepted from `content`, `reasoning_content` **and**
`reasoning`, because which field carries it is a serving-stack property rather
than a model property.

## Acceptance measurement - why deltas, not cumulative

Engine counters (`vllm:spec_decode_num_draft_tokens_total`,
`..._num_accepted_tokens_total`, and the per-position
`..._num_accepted_tokens_per_pos_total_pos{0,1,2}`) are **cumulative since
process start**. A cumulative ratio cannot show drift once its denominator is
large: it is an average over the whole history and converges by construction,
so a genuine late-run change would be invisible.

Acceptance here is therefore computed as **deltas between consecutive scrapes**,
each window covering roughly 8,000 drafts. Per-position rates are expressed
against the number of *drafts* in the window, not against draft tokens, so
pos0/pos1/pos2 read directly as "what fraction of draft steps got at least this
many tokens accepted".

These are engine counters over all traffic, not a sampled estimate.

## Burn detector

A fixed canary - identical prompt, `temperature=0`, fixed seed, fixed
`max_tokens=512`, thinking off - runs on a **wall-clock cadence** (every 30 min),
independent of the turn counter. Identical input means any change in output
length or content is the serve changing, not the workload.

The t~0 canary was run **out-of-band** and is labelled
`OUT_OF_BAND_T0_REFERENCE` in the raw, because the in-band cadence places the
first scheduled canary at t+30min and a burn detector with no early reference is
weaker. It is kept separate rather than silently merged into the in-band series.

This fleet has documented temperature-0 non-determinism that is general and not
attributable to prefix caching, so canary output equality is *measured*, not
assumed.

## Instrumentation

Per turn, logged to JSONL with fsync: turn index, UTC timestamp, elapsed hours,
family, thinking setting, prompt hash and length, HTTP status, transport error,
TTFT, wall duration, finish reason, full usage block, content and reasoning
character counts, content hash, empty-content flag, and a flag for `<tool_call>`
XML leaking into `content`.

Every ~14 turns: full engine counter scrape, host `free`, container memory.

## Known gaps in this run

- Single arm, so descriptive only (stated above, and it is the main one).
- Sequential single-stream, so nothing here characterises behaviour under
 concurrency, which is where preemption and KV pressure would appear.
- One fixed `max_tokens` (1024) for workload turns, so the empty-content rate
 measured here is the rate *at that budget* and does not transfer to others.
- One node, one serve, one day. No claim about run-to-run variance.
