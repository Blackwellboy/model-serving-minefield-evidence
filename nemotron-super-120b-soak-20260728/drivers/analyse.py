#!/usr/bin/env python3
"""Soak analysis. Descriptive only - single serve, no baseline arm."""
import json, sys, statistics as st
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
can = load("canary_t0.jsonl") + load("canary.jsonl")

if not turns:
    print("no turns yet")
    sys.exit()

span = (turns[-1]["ts"] - turns[0]["ts"]) / 3600
print("=" * 68)
print("SOAK ANALYSIS  turns=%d  elapsed=%.2fh  (single serve, no baseline arm)"
      % (len(turns), span))
print("=" * 68)

# ---- stability -------------------------------------------------------
print("\n-- STABILITY --")
print("HTTP status distribution:", dict(Counter(t["status"] for t in turns)))
print("finish_reason           :", dict(Counter(t.get("finish") for t in turns)))
errs = [t for t in turns if t.get("err")]
print("turns with transport err:", len(errs))
for e in errs[:5]:
    print("   turn", e["turn"], e["family"], str(e["err"])[:120])
empt = [t for t in turns if t.get("empty_content")]
print("empty-content turns     : %d (%.2f%%)" % (len(empt), 100 * len(empt) / len(turns)))
if empt:
    bt = Counter((t["family"], t["thinking"]) for t in empt)
    print("   by (family, thinking):", dict(bt))
    print("   all hit length cap   :", all(t.get("finish") == "length" for t in empt))
    print("   all had reasoning    :", all(t.get("reasoning_chars", 0) > 0 for t in empt))
xml = [t for t in turns if t.get("tool_calls_in_content")]
print("tool XML leaked to content:", len(xml))

# ---- quartile drift --------------------------------------------------
def quartiles(rows, key):
    n = len(rows)
    if n < 8:
        return None
    q = [rows[i * n // 4:(i + 1) * n // 4] for i in range(4)]
    out = []
    for blk in q:
        vals = [r[key] for r in blk if isinstance(r.get(key), (int, float))]
        out.append(round(st.median(vals), 3) if vals else None)
    return out


print("\n-- DRIFT BY QUARTILE OF RUN (median) --")
ok = [t for t in turns if t["status"] == 200 and t.get("tok_s")]
print("tok/s      :", quartiles(ok, "tok_s"))
print("ttft_s     :", quartiles([t for t in turns if t.get("ttft_s")], "ttft_s"))
print("content_chars:", quartiles(turns, "content_chars"))

print("\n-- tok/s BY FAMILY, first half vs second half --")
half = turns[len(turns) // 2]["ts"]
byf = defaultdict(lambda: ([], []))
for t in ok:
    byf[t["family"]][0 if t["ts"] < half else 1].append(t["tok_s"])
print("%-12s %8s %8s %8s %6s" % ("family", "n1", "1st-half", "2nd-half", "delta"))
for f in sorted(byf):
    a, b = byf[f]
    if a and b:
        ma, mb = st.median(a), st.median(b)
        print("%-12s %8d %8.2f %8.2f %+6.2f" % (f, len(a), ma, mb, mb - ma))

# ---- MTP acceptance drift -------------------------------------------
print("\n-- MTP ACCEPTANCE (windowed deltas, NOT cumulative) --")
K = "vllm:spec_decode_num_draft_tokens_total"
A = "vllm:spec_decode_num_accepted_tokens_total"
rows = []
for m in mets:
    c = m["cumulative"]
    if K in c and A in c:
        rows.append((m.get("elapsed_h", 0), c[K], c[A], c))
if len(rows) >= 2:
    print("%6s %10s %10s %9s %8s %8s %8s" %
          ("h", "drafts", "accepted", "window%", "pos0%", "pos1%", "pos2%"))
    for i in range(1, len(rows)):
        h, k0, a0, c0 = rows[i - 1]
        h1, k1, a1, c1 = rows[i]
        dk, da = k1 - k0, a1 - a0
        if dk <= 0:
            continue
        nd = c1.get("vllm:spec_decode_num_drafts_total", 0) - \
             c0.get("vllm:spec_decode_num_drafts_total", 0)
        pp = []
        for p in range(3):
            kk = "vllm:spec_decode_num_accepted_tokens_per_pos_total_pos%d" % p
            d = c1.get(kk, 0) - c0.get(kk, 0)
            pp.append(100 * d / nd if nd else float("nan"))
        print("%6.2f %10.0f %10.0f %8.2f%% %7.1f%% %7.1f%% %7.1f%%"
              % (h1, dk, da, 100 * da / dk, pp[0], pp[1], pp[2]))
    fk, fa = rows[-1][1], rows[-1][2]
    print("cumulative over run: %.0f/%.0f = %.2f%%" % (fa, fk, 100 * fa / fk))
    fd = rows[-1][3].get("vllm:spec_decode_num_drafts_total", 0)
    if fd:
        print("mean accepted per draft step: %.3f of 3" % (fa / fd))

# ---- preemption / memory --------------------------------------------
print("\n-- PREEMPTION + MEMORY OVER TIME --")
print("%6s %8s %-26s %s" % ("h", "preempt", "free MB tot,used,avail", "container mem"))
for m in mets[::max(1, len(mets) // 12)]:
    print("%6.2f %8s %-26s %s" % (
        m.get("elapsed_h", 0),
        m["cumulative"].get("vllm:num_preemptions_total"),
        m.get("free", ""), m.get("docker", "")))

# ---- burn detector ---------------------------------------------------
print("\n-- BURN CANARY (identical prompt, temp 0, seed fixed) --")
if can:
    print("%6s %7s %8s %8s %s" % ("h", "chars", "ttft", "finish", "sha256[:12]"))
    for c in can:
        print("%6.2f %7d %8.2f %8s %s" % (
            c.get("elapsed_h", 0), c.get("chars", 0), c.get("ttft_s") or 0,
            c.get("finish"), c.get("sha256", "")[:12]))
    ch = [c["chars"] for c in can]
    u = len({c.get("sha256") for c in can})
    print("chars: min=%d max=%d spread=%d ; distinct outputs %d of %d"
          % (min(ch), max(ch), max(ch) - min(ch), u, len(can)))
