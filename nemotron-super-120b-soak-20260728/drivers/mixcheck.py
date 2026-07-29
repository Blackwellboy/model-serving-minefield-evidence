#!/usr/bin/env python3
"""Is the pooled acceptance series flat because nothing drifted, or because
offsetting mix changes cancelled? READ-ONLY over already-captured turns.jsonl.

The hazard, from the DSV4 re-analysis: pooled acceptance is DRAFT-TOKEN
weighted. Balanced REQUEST counts do not imply balanced draft-token weights,
because families differ in output length. If a low-acceptance family's token
share grows over the run, pooled acceptance falls with no server change; if it
shrinks, a real fall can be masked.

Round-robin fixes request share by construction. This checks whether it also
fixed token share, which it does NOT do automatically.
"""
import json
from collections import defaultdict

D = "./soak/"
turns = []
for l in open(D + "turns.jsonl"):
    l = l.strip()
    if l:
        try:
            turns.append(json.loads(l))
        except Exception:
            pass

ok = [t for t in turns if t.get("status") == 200 and t.get("completion_tokens")]
print("turns=%d usable=%d" % (len(turns), len(ok)))
print("""
Proxy note: the engine's per-family draft-token counts are not exposed (the
counters are process-wide). Completion tokens are used as the weight proxy.
Per decode step the engine emits accepted+1 tokens and drafts exactly 3, so
completion tokens are proportional to draft steps up to the acceptance rate
itself. That makes this a GOOD proxy for share drift and a POOR one for
absolute weights. It is sufficient for the question asked: does the mix move.
""")

Q = 4
n = len(ok)
bounds = [ok[i * n // Q]["turn"] for i in range(Q)] + [ok[-1]["turn"] + 1]
fams = sorted({t["family"] for t in ok})

req_share = defaultdict(dict)
tok_share = defaultdict(dict)
for q in range(Q):
    blk = [t for t in ok if bounds[q] <= t["turn"] < bounds[q + 1]]
    tot_r = len(blk)
    tot_t = sum(t["completion_tokens"] for t in blk)
    for f in fams:
        sub = [t for t in blk if t["family"] == f]
        req_share[f][q] = 100 * len(sub) / tot_r if tot_r else 0
        tok_share[f][q] = 100 * sum(x["completion_tokens"] for x in sub) / tot_t if tot_t else 0

print("Quartile turn boundaries:", ["[%d,%d)" % (bounds[i], bounds[i + 1]) for i in range(Q)])

print("\n=== REQUEST share per family per quartile (what round-robin controls) ===")
print("%-12s %7s %7s %7s %7s %8s" % ("family", "q1", "q2", "q3", "q4", "range"))
for f in fams:
    v = [req_share[f][q] for q in range(Q)]
    print("%-12s %6.1f%% %6.1f%% %6.1f%% %6.1f%% %7.2f" %
          (f, v[0], v[1], v[2], v[3], max(v) - min(v)))

print("\n=== COMPLETION-TOKEN share per family per quartile (the weight that matters) ===")
print("%-12s %7s %7s %7s %7s %8s" % ("family", "q1", "q2", "q3", "q4", "range"))
worst = 0.0
for f in fams:
    v = [tok_share[f][q] for q in range(Q)]
    r = max(v) - min(v)
    worst = max(worst, r)
    print("%-12s %6.1f%% %6.1f%% %6.1f%% %6.1f%% %7.2f" %
          (f, v[0], v[1], v[2], v[3], r))

print("\nLargest token-share swing across quartiles: %.2f points" % worst)
print("""
Reading: on the DSV4 run the destabilising family swung 16.5%% -> 61.6%%, a 45
point move, and that alone produced an 8.4 point fall in pooled acceptance. A
swing of a few points cannot produce a comparable artefact.""")

# how much pooled acceptance COULD move given observed share drift
print("\n=== BOUNDING THE ARTEFACT ===")
print("""Using per-family decode rate as an acceptance ordering (fastest family
accepts most), the worst case is that the entire observed share swing moved
between the highest- and lowest-acceptance families. Bounding that:""")
import statistics as st
rate = {}
for f in fams:
    v = [t["tok_s"] for t in ok if t["family"] == f and t.get("tok_s")]
    if v:
        rate[f] = st.median(v)
hi = max(rate, key=rate.get)
lo = min(rate, key=rate.get)
print("  fastest family: %-12s median %.2f tok/s" % (hi, rate[hi]))
print("  slowest family: %-12s median %.2f tok/s" % (lo, rate[lo]))
sw = max(abs(tok_share[hi][3] - tok_share[hi][0]), abs(tok_share[lo][3] - tok_share[lo][0]))
print("  share swing q1->q4 on those two families: %.2f points" % sw)
print("""
If the true per-family acceptance spread is comparable to the DSV4 spread
(0.43 to 0.82, i.e. ~39 points), a share swing of S points can move pooled
acceptance by at most roughly S x 0.39 points.""")
print("  => worst-case artefact from observed drift: %.2f points" % (sw * 0.39))
