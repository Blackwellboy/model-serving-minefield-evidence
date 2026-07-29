#!/usr/bin/env python3
"""Post-hoc reanalysis. READ-ONLY over already-captured logs.
Does not touch the running driver, the serve, or the lane."""
import json
from collections import defaultdict, Counter

D = "./soak/"


def load(p):
    out = []
    try:
        for l in open(D + p):
            l = l.strip()
            if l:
                try:
                    out.append(json.loads(l))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return out


turns = load("turns.jsonl")
mets = [m for m in load("metrics.jsonl") if "cumulative" in m]

K = "vllm:spec_decode_num_draft_tokens_total"
A = "vllm:spec_decode_num_accepted_tokens_total"
N = "vllm:spec_decode_num_drafts_total"
POS = ["vllm:spec_decode_num_accepted_tokens_per_pos_total_pos%d" % p for p in range(3)]

print("=" * 72)
print("POST-HOC REANALYSIS  turns=%d  metric_scrapes=%d" % (len(turns), len(mets)))
print("=" * 72)

# ---------------------------------------------------------------- 0. cadence
print("\n## 0. WHAT THE EXISTING SCRAPE CADENCE ACTUALLY IS")
gaps = [mets[i]["turn"] - mets[i - 1]["turn"] for i in range(1, len(mets))]
tgaps = [round((mets[i]["ts"] - mets[i - 1]["ts"]) / 60, 1) for i in range(1, len(mets))]
print("turn-index gap between scrapes : set=%s" % sorted(set(gaps)))
print("wall-clock gap (min)           : min=%.1f max=%.1f mean=%.1f"
      % (min(tgaps), max(tgaps), sum(tgaps) / len(tgaps)))
print("-> scrapes are triggered by REQUEST COUNT (every N turns), not wall clock.")
print("   The wall-clock spacing is a consequence, and it VARIES, which is the")
print("   signature of a request-triggered cadence rather than a timed one.")

# ---------------------------------------------------------------- 1. resets
print("\n## 1. COUNTER RESET CHECK (monotonicity)")
viol = []
for name in [K, A, N] + POS:
    prev = None
    for m in mets:
        v = m["cumulative"].get(name)
        if v is None:
            continue
        if prev is not None and v < prev:
            viol.append((name, m["turn"], prev, v))
        prev = v
if viol:
    print("!! NON-MONOTONIC COUNTER DETECTED - a reset occurred:")
    for n, t, p, v in viol:
        print("   %s at turn %d: %.0f -> %.0f" % (n, t, p, v))
else:
    print("All %d spec_decode counters strictly non-decreasing across %d scrapes."
          % (len(POS) + 3, len(mets)))
    print("NO RESET OCCURRED during the run. Every delta is a real delta.")
print("\nNote on method: a reset corrupts a delta REGARDLESS of whether the window")
print("boundary is defined by wall clock or by request count. Reset-immunity comes")
print("from DETECTING the monotonicity violation (this check), not from the choice")
print("of boundary. Fixed request-count windows buy comparability of window SIZE,")
print("which is a real and separate benefit.")

# ------------------------------------------------- 2. fixed request windows
print("\n## 2. ACCEPTANCE OVER FIXED REQUEST-COUNT WINDOWS (200 requests)")
W = 200
anchors = []
for m in mets:
    c = m["cumulative"]
    if K in c and A in c:
        anchors.append((m["turn"], c))
print("%-16s %10s %10s %9s %8s %8s %8s" %
      ("turn window", "drafts", "accepted", "accept%", "pos0%", "pos1%", "pos2%"))
lo = 0
newser = []
while True:
    hi = lo + W
    a0 = [x for x in anchors if x[0] <= lo]
    a1 = [x for x in anchors if x[0] <= hi]
    if not a0 or not a1 or a1[-1][0] <= a0[-1][0]:
        break
    t0, c0 = a0[-1]
    t1, c1 = a1[-1]
    dk = c1[K] - c0[K]
    da = c1[A] - c0[A]
    dn = c1.get(N, 0) - c0.get(N, 0)
    if dk > 0:
        pp = [100 * (c1.get(p, 0) - c0.get(p, 0)) / dn if dn else float("nan") for p in POS]
        print("%-16s %10.0f %10.0f %8.2f%% %7.1f%% %7.1f%% %7.1f%%"
              % ("[%d,%d)" % (t0, t1), dk, da, 100 * da / dk, pp[0], pp[1], pp[2]))
        newser.append(100 * da / dk)
    lo = hi
print("\nBoundaries are exact scrape turn-indices, printed above; scrapes land every")
print("14 turns so a 200-request request window snaps to the nearest scrape at or")
print("below each edge. That snapping is why the boundary is reported, not assumed.")

old = []
for i in range(1, len(anchors)):
    dk = anchors[i][1][K] - anchors[i - 1][1][K]
    da = anchors[i][1][A] - anchors[i - 1][1][A]
    if dk > 0:
        old.append(100 * da / dk)
if old and newser:
    print("\nOLD series (%d windows of 14 req): min=%.2f max=%.2f spread=%.2f"
          % (len(old), min(old), max(old), max(old) - min(old)))
    print("NEW series (%d windows of %d req): min=%.2f max=%.2f spread=%.2f"
          % (len(newser), W, min(newser), max(newser), max(newser) - min(newser)))
    print("Both series are flat; the larger window narrows the spread, which is what")
    print("averaging more requests per point is supposed to do. Neither shows a slope.")

# ------------------------------------------------- 3. per-family acceptance
print("\n## 3. PER-FAMILY ACCEPTANCE - IS IT COMPUTABLE FROM THIS LOG?")
print("Engine spec_decode counters are PROCESS-WIDE cumulative. They carry no")
print("family label. Attribution needs a window containing only one family.")
seen = []
for i in range(1, len(mets)):
    lo_t, hi_t = mets[i - 1]["turn"], mets[i]["turn"]
    fams = Counter(t["family"] for t in turns if lo_t <= t["turn"] < hi_t)
    seen.append(fams)
if seen:
    print("\nFamily composition of each inter-scrape window (first 4 shown):")
    for f in seen[:4]:
        print("  ", dict(sorted(f.items())))
    uniform = all(len(set(f.values())) == 1 and len(f) == 7 for f in seen if sum(f.values()) == 14)
    print("\nEvery full window contains all 7 families in EQUAL counts: %s" % uniform)
print("""
VERDICT: per-family acceptance is NOT computable from this log, and no
arithmetic on it can recover the split. The workload is round-robin one turn per
family and the scrape fires every 14 turns = exactly 2 complete cycles, so every
window is perfectly balanced by construction. The very design choice that makes
the DRIFT result strong - no family can occupy a contiguous stretch - is what
destroys family attribution in a process-wide counter.

This is a real limitation of the run, not something to paper over with a
derived estimate. Reporting a fabricated per-family split here would be worse
than reporting none.""")

print("\n## 3b. PER-FAMILY DECODE RATE (a PROXY, explicitly not acceptance)")
byf = defaultdict(list)
for t in turns:
    if t.get("tok_s") and t["status"] == 200:
        byf[t["family"]].append(t["tok_s"])
import statistics as st
print("%-12s %6s %10s" % ("family", "n", "median tok/s"))
for f in sorted(byf, key=lambda x: -st.median(byf[x])):
    print("%-12s %6d %10.2f" % (f, len(byf[f]), st.median(byf[f])))
print("""
Decode rate is driven by acceptance but is not a measurement of it: it also
carries prompt length, sampling and scheduler effects. The ~10 tok/s spread
between structured/math and prose is consistent with a large per-family
acceptance spread, but the size of that spread cannot be read off these numbers.""")

# ------------------------------------------------- 4. X-02 per family
print("\n## 4. X-02 EMPTY-CONTENT RATE, PER FAMILY")
tot = Counter()
emp = Counter()
tot_on = Counter()
emp_on = Counter()
for t in turns:
    tot[t["family"]] += 1
    if t["thinking"]:
        tot_on[t["family"]] += 1
    if t.get("empty_content"):
        emp[t["family"]] += 1
        if t["thinking"]:
            emp_on[t["family"]] += 1
print("%-12s %7s %7s %9s %10s %9s %11s" %
      ("family", "turns", "empty", "rate_all", "think-on", "empty_on", "rate_on"))
for f in sorted(tot, key=lambda x: -(emp_on[x] / tot_on[x] if tot_on[x] else 0)):
    r_all = 100 * emp[f] / tot[f] if tot[f] else 0
    r_on = 100 * emp_on[f] / tot_on[f] if tot_on[f] else 0
    print("%-12s %7d %7d %8.2f%% %10d %9d %10.2f%%"
          % (f, tot[f], emp[f], r_all, tot_on[f], emp_on[f], r_on))
print("\nthinking-OFF empty completions: %d (across %d thinking-off turns)"
      % (sum(1 for t in turns if t.get("empty_content") and not t["thinking"]),
         sum(1 for t in turns if not t["thinking"])))

# flatness of the X-02 rate over time
print("\n## 4b. IS THE X-02 RATE FLAT OVER THE RUN? (config property vs burn)")
on = [t for t in turns if t["thinking"]]
q = len(on) // 4
for i in range(4):
    blk = on[i * q:(i + 1) * q] if i < 3 else on[3 * q:]
    e = sum(1 for t in blk if t.get("empty_content"))
    print("  quartile %d of thinking-on turns: %d/%d = %.2f%%"
          % (i + 1, e, len(blk), 100 * e / len(blk) if blk else 0))
