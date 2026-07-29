# Study index

## dsv4-flash-long-soak-20260728

| Field | Value |
|---|---|
| Model | community abliterated DeepSeek-V4-Flash, `dsv4_ablit_mida`, NVFP4 |
| Immutable revision | community re-upload; no upstream revision pin is published for this checkpoint |
| Runtime | vLLM `0.21.1rc1.dev339+g1967a5627bc3` |
| KV | dtype `nvfp4_ds_mla`, block size 256, 20,139 GPU blocks |
| Speculative | MTP `dspark`, 3 draft tokens (K=3) |
| Serve flags | `--max-num-seqs 4`, `--max-model-len 1048576`, `--enable-prefix-caching` |
| Hardware / topology | two GB10-class nodes, tensor parallel 2, request-level access only |
| Duration | 10.20 h, 2026-07-28 |
| Requests | 2,400, all HTTP 200, 40 windows of 60 |
| Minefield entries | [105](https://github.com/Blackwellboy/model-serving-minefield/blob/main/traps/evaluation/105-acceptance-estimator-unnamed.md), [106](https://github.com/Blackwellboy/model-serving-minefield/blob/main/traps/memory/106-kv-occupancy-ceiling-is-not-a-leak.md) |
| Raw publication | **scrubbed raw published**; prose replaced by hashes and lengths, node identities pseudonymised |
| Limitations | single serve, no baseline arm; per-request `cache_salt` forced cache misses by design, so the occupancy curve does not describe normal traffic |

## nemotron-super-120b-soak-20260728

| Field | Value |
|---|---|
| Model | NVIDIA Nemotron 3 Super 120B A12B NVFP4 |
| Immutable revision | `4f0cf9daaeb7a4d5e23f80a00e7ed15f0e03caf6` |
| Runtime | vLLM 0.20.0, image digest `sha256:04563c302537a91aa49ebdfbceda96111c5712275999b7e8804fa598f0b5641d` |
| Speculative | MTP `num_speculative_tokens=3` |
| Serve flags | `--gpu-memory-utilization 0.90` |
| Generation | `max_tokens=1024`, `temperature=1.0`, `top_p=0.95` |
| Hardware / topology | single GB10-class node, TP=1 |
| Duration | 13.009 h, 2026-07-28 |
| Turns | 2,045 (1,023 thinking-on / 1,022 thinking-off), all HTTP 200, 147 scrapes |
| Minefield entries | [107](https://github.com/Blackwellboy/model-serving-minefield/blob/main/traps/memory/107-soak-duration-changes-the-verdict.md), [108](https://github.com/Blackwellboy/model-serving-minefield/blob/main/traps/evaluation/108-burn-canary-is-bistable-not-degrading.md), [trap 12 addendum](https://github.com/Blackwellboy/model-serving-minefield/blob/main/traps/evaluation/12-empty-content-at-token-ceiling.md) |
| Raw publication | **scrubbed raw published**; this bundle carried no prose bodies to begin with (content was hashed at capture) |
| Limitations | single serve, no baseline arm; every rate is at `max_tokens=1024` on this task mix and does not transfer to another budget |
| Known open | a 64.22 vs 67.33 per-family acceptance gap survives both the estimator check and a 0.12-point mix bound and is not explained |

## Immutable evidence commit

Cite this repository at a commit, not at `main`. The registry entries link to
commit-pinned paths for exactly that reason.
