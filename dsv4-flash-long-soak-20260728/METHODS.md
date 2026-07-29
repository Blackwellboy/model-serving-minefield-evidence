# Methods: DSV4-Flash long soak

## Design

Request-level only. Nothing was restarted, stopped, started, reconfigured,
parked or unparked on the serving pair for the duration; the study had no
container or host access to the lane and did not need any.

2,400 requests over 10.20 h, issued in 40 fixed **request-count** windows of 60.
Windows are request-counted rather than time-counted so that occupancy and
counter deltas are comparable across windows regardless of how long each took.

Six task families, **n=400 each, interleaved**, so the workload mix is constant
by construction and the pooled acceptance figure cannot drift because the mix
drifted:

`chat`, `code`, `longctx`, `summarize`, and `math` under both thinking states.

## Instrumentation

- per request: TTFT, end-to-end latency, prompt/completion tokens, decode steps,
  finish reason, thinking state, close-marker position, derived
  `tokens_per_step` and `mtp_acceptance_est`
- per window: a full `/metrics` scrape including
  `vllm:kv_cache_usage_perc`, `vllm:num_preemptions_total`,
  `vllm:spec_decode_num_accepted_tokens_total`,
  `vllm:spec_decode_num_draft_tokens_total`, `vllm:request_success_total`
- a node memory sampler on both nodes
- a positive control and a set of cross-model cold/warm arms carrying
  `prefix_cache_hits_total` / `prefix_cache_queries_total` deltas

## Acceptance, both ways

Token-weighted is computed **scoped to this run's own requests**, from summed
completion tokens and decode steps, not from a single `/metrics` scrape:

```
token_weighted = (sum(completion_tokens) - sum(decode_steps)) / (sum(decode_steps) * K)
```

Request-weighted is the mean of the per-request value, each request counting
once:

```
tokens_per_step     = completion_tokens / decode_steps      # in [1, K+1]
request_acceptance  = (tokens_per_step - 1) / K
```

The distinction between these two, and the third unscoped process-wide value
that `/metrics` hands you, **is the subject of trap 105** rather than an
incidental detail of the method.

## Cold prefill

Every request carried a unique `cache_salt` to force a cold prefill and an
honest TTFT. This is a deliberate choice with a known consequence for trap 106
and it is stated wherever the occupancy curve appears.

## Known limits

Single serve, no baseline arm. One checkpoint, one runtime build, one topology,
one prompt mix. Absolute acceptance values are a property of that combination
and of the mix in particular.
