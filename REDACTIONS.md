# Redaction record

What was removed from the source bundles before publication, why, and what it
does and does not change. The transformation is a committed script, not a
manual pass.

## Principle

**Fields, not records.** No record was dropped from either study. Where a field
carried something unpublishable, that field was removed or replaced with a
structure-preserving equivalent, and the record kept every other field. Every
input to every published number is present and untouched.

**Prose does not ship because a scanner did not flag it.** The response text in
these runs is mostly innocuous (tidal power stations, a `ZEPHYR-4417` recall
sentinel). It is removed anyway. A vocabulary scanner cannot certify
model-generated text, and the standard here is that raw prose is published
deliberately or not at all.

## Scripts

| Script | Applies to | What it does |
|---|---|---|
| `redact_soak.py` (in `dsv4-flash-long-soak-20260728/drivers/`) | all DSV4 JSONL | recursive field-level scrub: hashes prose, pseudonymises node keys, redacts IPv4 |
| a text-substitution pass | drivers, analysis text, prose docs | regex substitution over text surfaces |

## Transformations

| Field / surface | Action | Reason | Changes a published number? |
|---|---|---|---|
| `content_head`, `reasoning_head` (DSV4 `turns.jsonl`, `positive_control.jsonl`, `laguna/*.jsonl`) | replaced by `content_head_sha8`, `reasoning_head_sha8` | model-generated prose | **No.** Lengths were already carried separately in `content_chars` / `reasoning_chars`, which are the fields the published counts use. The hash preserves identity and dedup analysis. |
| `raw` (DSV4 `sampler.jsonl`) | dropped | raw shell output from a memory sampler; carries hostnames | **No.** The parsed numeric fields (`total_mb`, `used_mb`, `avail_mb`, `swap_used_mb`, `container_status`, `restart_count`) are retained. |
| `stderr` (DSV4 `sampler.jsonl`) | dropped | ssh transport errors containing private addresses | **No.** `sample_ok`, `reason` and `rc` are retained, so failed samples remain visible and countable. |
| the two private node identities | renamed `node-a`, `node-b` | private node identity | **No.** The mapping is 1:1 and order-preserving, so per-node series stay separable. |
| any IPv4 literal | replaced with `REDACTED_IP` | LAN and tailnet addresses | **No.** |
| the serving port literal, alone or with a loopback host | replaced with `HOST:PORT` | identifies private infrastructure | **No.** |
| user home-directory paths | replaced with a shell variable | usernames and home paths | **No.** |
| internal orchestrator names, control-plane document paths, owner name | replaced with neutral terms | private orchestration vocabulary | **No.** |
| scanner proof reports | **not published**; replaced by `proofs/README.md` | a clean scan report enumerates the entire private pattern vocabulary line by line, so publishing one would publish the list of things that must never be published | **No.** The CI job reproduces the verdict. |

## Files present in the source and deliberately not published

Internal operating documents with no bearing on any published number:
`next-actions.md`, `risks-and-guardrails.md`, `changed-paths.md`,
`CORRECTIONS_FOR_RECONCILE.md`, `SUPERSEDED.md`, `entries/` (superseded trap
drafts numbered 98/99, rebased to 105/106 before landing), a source-side redaction script that embeds the private vocabulary itself, `soak.console.log`,
`CROSSMODEL_RESULT.md` and `DESIGN_mnbt_boundary.md` (a different open
question, carried as a registry mining note instead).

## Record counts, source to public

Produced by `redact_dsv4.py`. **No record was dropped.**

| File | source | public |
|---|---|---|
| `raw/turns.jsonl` | 2400 | 2400 |
| `raw/windows.jsonl` | 80 | 80 |
| `raw/memory.jsonl` | 121 | 121 |
| `raw/events.jsonl` | 43 | 43 |
| `raw/sampler.jsonl` | 451 | 451 |
| `raw/positive_control.jsonl` | 2 | 2 |
| `raw/laguna/deep.jsonl` | 6 | 6 |
| `raw/laguna/decisive.jsonl` | 2 | 2 |
| `raw/laguna/mnbt4096.jsonl` | 6 | 6 |
| smoke passes (7 files) | 25 | 25 |

Nemotron: `turns.jsonl` 2045 / 2045, `metrics.jsonl` 149 / 149 (147 with
`elapsed_h` plus a start and an end event), `canary.jsonl` 25 / 25,
`canary_t0.jsonl` 1 / 1. That bundle hashed response content at capture time,
so it carried no prose bodies to remove.

## Checksum relationship

The source bundles carry their own `SHA256SUMS`, generated before any scrub and
preserved unchanged in the private archive. The public bundles carry their own
`SHA256SUMS` over the scrubbed files. **These do not and must not match**: the
scrub changes file bytes by design. The private archive is what proves the
source was not altered; the public checksums prove the public tree is intact.

## What the scrub does not claim

It does not certify that no model-generated string anywhere in these runs could
identify anything. It certifies that prose bodies were removed rather than
scanned and passed, which is a stronger and more checkable claim.

## Why the substitution vocabulary is not committed

`redact_soak.py` ships its full transformation logic and reads its identity
mapping from a file supplied at run time, which is **not** in this repository.

That is not evasion, it is the finding. The first version of this bundle
committed the scrub scripts verbatim, and the maintainer-side scanners refused
them: the scripts contain, as string literals, every private hostname, path and
control-plane term they exist to remove. **A scrub script is a machine-readable
copy of the vocabulary it scrubs.** Publishing it would have leaked precisely
what the scrub was for, through the artifact that proves the scrub happened.

The same shape caught the committed scanner proof reports, which enumerate
every pattern with an `OK ... 0 hits` beside it, and a line in this very
document that spelled out the node mapping it was describing. Three instances,
one class, all in one publication pass.

What is auditable without the vocabulary: which fields are dropped, which are
hashed, which are renamed, that the rename is 1:1, that no record is dropped,
and the before/after counts. That is the part a reader needs to judge whether
the published numbers survived the transformation. The list of private
hostnames is not.
