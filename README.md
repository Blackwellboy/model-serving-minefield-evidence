# model-serving-minefield-evidence

Study artifacts for [model-serving-minefield](https://github.com/Blackwellboy/model-serving-minefield).

The registry stays readable: short entries, a symptom, a mechanism, a check you
can run. This repository holds the evidence those entries rest on, so a reader
who wants to check a number does not have to take it on trust.

## What is here

| Study | Registry entries | Verifier |
|---|---|---|
| [DSV4-Flash long soak](dsv4-flash-long-soak-20260728/) | traps 105, 106 | `python3 verify.py`, 16 checks |
| [Nemotron 3 Super 120B soak](nemotron-super-120b-soak-20260728/) | traps 107, 108, trap 12 addendum | `python3 verify.py`, 26 checks |

See [STUDY_INDEX.md](STUDY_INDEX.md) for model revisions, builds, topology and
limitations, and [REDACTIONS.md](REDACTIONS.md) for exactly what was removed
from the raw and why.

## Read this before citing anything here

**Both studies are single serves with no baseline arm.** They describe the
build, quantisation, hardware and workload mix they ran on. They are not
comparisons, and none of the absolute numbers transfer to stock checkpoints,
other runtimes or other prompt mixes. The registry entries say so; this repeats
it because raw data invites exactly that mistake.

**The raw is scrubbed, not synthetic.** Every record is present and every field
any published number is computed from is untouched. What was removed is
model-generated prose, private node identities and private network addresses.
The transformation is a committed script, the before/after record counts are
published, and nothing was dropped.

## Verifying

Each study ships a stdlib-only verifier that re-derives the published numbers
from the scrubbed data:

```bash
cd dsv4-flash-long-soak-20260728 && python3 verify.py
cd nemotron-super-120b-soak-20260728 && python3 verify.py
```

They exit non-zero if a source file is missing or a number moves beyond a
declared tolerance. CI runs both on every push, along with checksum
verification and the public-surface scanners.
