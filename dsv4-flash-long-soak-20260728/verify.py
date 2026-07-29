#!/usr/bin/env python3
"""Independently re-derive every published number for the DSV4-Flash long soak.

stdlib only.  Run:  python3 verify.py
Exit 0 = every claim reproduced.  Exit 1 = a source file is missing or a
number moved beyond its declared tolerance.
"""
import collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw-scrubbed", "raw")
K_SPEC = 3
TOL = 1e-4          # percentage points, for float comparisons
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
wins = load("windows.jsonl")

print("DSV4-Flash long soak, 2026-07-28 - verification")
print("\n[requests]")
eq("total request records", len(turns), 2400)
ok200 = [t for t in turns if t["http_status"] == 200]
eq("HTTP 200 responses", len(ok200), 2400)

print("\n[acceptance estimators]")
ct = sum(t["completion_tokens"] for t in ok200)
ds = sum(t["decode_steps"] for t in ok200)
tw = 100.0 * (ct - ds) / (ds * K_SPEC)
rw = 100.0 * sum(t["mtp_acceptance_est"] for t in ok200) / len(ok200)
eq("token-weighted acceptance %", round(tw, 4), 72.6991, TOL)
eq("request-weighted acceptance %", round(rw, 4), 66.3888, TOL)
eq("estimator gap, points", round(tw - rw, 4), 6.3102, TOL)

print("\n[per-family acceptance]")
fam = collections.defaultdict(list)
for t in ok200:
    f = t["task_family"]
    if f == "math":
        f = "math_think" if t["thinking"] else "math_nothink"
    fam[f].append(t["mtp_acceptance_est"])
means = {k: 100.0 * sum(v) / len(v) for k, v in fam.items()}
for k in sorted(means, key=lambda k: -means[k]):
    print("    %-16s n=%-5d %.4f%%" % (k, len(fam[k]), means[k]))
eq("families", len(means), 6)
eq("min family n", min(len(v) for v in fam.values()), 400)
eq("lowest family %", round(min(means.values()), 4), 43.3653, TOL)
eq("highest family %", round(max(means.values()), 4), 78.1407, TOL)
eq("family spread, points", round(max(means.values()) - min(means.values()), 2), 34.78, 0.01)

print("\n[KV occupancy and preemptions]")
kv = [w["metrics"]["vllm:kv_cache_usage_perc"] for w in wins if "metrics" in w]
kv = [round(100.0 * v, 1) for v in kv]
eq("windows with metrics", len(kv), 80)
eq("first-window occupancy %", kv[0], 65.1, 0.11)
eq("peak occupancy %", max(kv), 96.4, 0.11)
ceiling = [v for v in kv if v >= 96.0]
eq("windows at/above 96.0%", len(ceiling) >= 28, True)
pre = [w["metrics"]["vllm:num_preemptions_total"] for w in wins if "metrics" in w]
eq("preemptions, max over run", max(pre), 0.0)

print("\n[prefix cache reuse]")
pc = [json.loads(l) for l in open(os.path.join(RAW, "positive_control.jsonl"), encoding="utf-8") if l.strip()]
lag = []
for n in ("deep.jsonl", "decisive.jsonl", "mnbt4096.jsonl"):
    lag += load(os.path.join("laguna", n))
cold = [r for r in lag if r.get("arm") == "cold" and r.get("hit_fraction") is not None]
# Absence is a failure, not a skip. Exiting 0 with "ALL PUBLISHED NUMBERS
# REPRODUCED" while quietly not checking a published headline number is the
# false-green these studies are partly about.
eq("cold-arm rows available", len(cold) > 0, True)
if cold:
    eq("cold-arm prefix hit fraction, max", max(r["hit_fraction"] for r in cold), 0.0)

print("\n%d checks, %d failed" % (checks, len(fails)))
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PUBLISHED NUMBERS REPRODUCED")
