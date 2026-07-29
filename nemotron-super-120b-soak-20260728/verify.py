#!/usr/bin/env python3
"""Independently re-derive every published number for the Nemotron 3 Super 120B soak.

stdlib only.  Run:  python3 verify.py
Exit 0 = every claim reproduced.  Exit 1 = missing source or a number moved.
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw-scrubbed", "raw")
TOL = 1e-3
fails, checks = [], 0


def load(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        print("FATAL: required source file missing: %s" % p)
        sys.exit(1)
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def eq(label, got, want, tol=0.0):
    global checks
    checks += 1
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print("  %-52s %-18s %s" % (label, got, "OK" if ok else "FAIL (want %s)" % want))
    if not ok:
        fails.append(label)


turns = load("turns.jsonl")
metrics = load("metrics.jsonl")
canary = load("canary.jsonl")
t0 = load("canary_t0.jsonl")

print("Nemotron 3 Super 120B A12B NVFP4 soak, 2026-07-28 - verification")
print("\n[turns]")
eq("turn records", len(turns), 2045)
eq("HTTP 200", len([t for t in turns if t.get("status") == 200]), 2045)
on = [t for t in turns if t.get("thinking")]
off = [t for t in turns if not t.get("thinking")]
eq("thinking-on turns", len(on), 1023)
eq("thinking-off turns", len(off), 1022)

print("\n[memory series]")
sc = [m for m in metrics if "elapsed_h" in m]
eq("instrumented scrapes", len(sc), 147)
gib = lambda s: float(re.search(r"([\d.]+)\s*GiB", s).group(1))
ser = [(m["elapsed_h"], gib(m["docker"])) for m in sc]
peak = max(ser, key=lambda p: p[1])
eq("peak container memory, GiB", round(peak[1], 3), 3.538, TOL)
eq("hour of peak", round(peak[0], 2), 7.36, 0.005)
eq("final memory, GiB", round(ser[-1][1], 3), 3.354, TOL)
eq("final hour", round(ser[-1][0], 2), 13.00, 0.005)
h109 = min(ser, key=lambda p: abs(p[0] - 1.09))
eq("memory at h=1.09, GiB", round(h109[1], 3), 3.378, TOL)
eq("final is BELOW the h=1.09 value", ser[-1][1] < h109[1], True)
eq("total excursion, GiB", round(peak[1] - ser[0][1], 2), 0.32, 0.011)

print("\n[burn canary]")
eq("in-band canary samples", len(canary), 25)
eq("all canary samples HTTP 200", len([c for c in canary if c.get("status") == 200]), 25)
h = collections.Counter(c["sha256"][:12] for c in canary)
eq("distinct canary outputs", len(h), 2)
freq = sorted(h.values(), reverse=True)
eq("canary frequency split", tuple(freq), (21, 4))
eq("out-of-band t0 reference is a THIRD output",
   t0[0]["sha256"][:12] not in h, True)

print("\n[empty content]")
empt = [t for t in turns if t.get("empty_content")]
eq("empty-content responses", len(empt), 92)
eq("empty-content rate %", round(100.0 * len(empt) / len(turns), 2), 4.50, 0.005)
eq("all empties were thinking-on", all(t.get("thinking") for t in empt), True)
eq("all empties finish_reason=length",
   set(t.get("finish") for t in empt) == {"length"}, True)
eq("thinking-off empties", len([t for t in off if t.get("empty_content")]), 0)

print("\n[family concentration, thinking-on]")
famon = collections.defaultdict(list)
for t in on:
    famon[t["family"]].append(bool(t.get("empty_content")))
rates = {k: 100.0 * sum(v) / len(v) for k, v in famon.items()}
for k in sorted(rates, key=lambda k: -rates[k]):
    print("    %-14s n=%-5d %.2f%%" % (k, len(famon[k]), rates[k]))
eq("worst family (reasoning) %", round(rates["reasoning"], 2), 30.82, 0.01)
eq("families with zero empties", len([k for k, v in rates.items() if v == 0]), 3)

print("\n[quartiles, thinking-on]")
srt = sorted(on, key=lambda t: t["turn"])
q = len(srt) // 4
qs = []
for i in range(4):
    seg = srt[i * q:(i + 1) * q] if i < 3 else srt[3 * q:]
    qs.append(round(100.0 * sum(1 for t in seg if t.get("empty_content")) / len(seg), 2))
print("    %s" % qs)
eq("quartile rates", tuple(qs), (10.20, 9.02, 7.84, 8.91))
eq("rate is flat, not climbing (last < first)", qs[-1] < qs[0], True)

print("\n%d checks, %d failed" % (checks, len(fails)))
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PUBLISHED NUMBERS REPRODUCED")
