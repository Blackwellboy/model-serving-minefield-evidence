#!/usr/bin/env python3
"""Analyser for the DSV4 abliterated long soak. Read-only over raw/*.jsonl."""
import json, os, sys, statistics as st
from collections import defaultdict, Counter

OUT = os.path.expanduser("~/staging/dsv4-long-soak-20260728")
RAW = os.path.join(OUT, "raw")

def load(n):
    p = os.path.join(RAW, n)
    rows = []
    if not os.path.exists(p):
        return rows
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass          # tolerate a torn final line while the soak is running
    return rows

turns = load("turns.jsonl")
wins  = load("windows.jsonl")
evs   = load("events.jsonl")
mems  = load("memory.jsonl")

def pct(x, n):
    return f"{100.0*x/n:.1f}%" if n else "n/a"

def q(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return s[i]

print("=" * 78)
print("DSV4 ABLITERATED LONG SOAK -- ANALYSIS")
print("=" * 78)

# ------------------------------------------------------------ elapsed & scope
start_ev = next((e for e in evs if e["kind"] == "soak_start"), None)
end_ev   = next((e for e in evs if e["kind"] == "soak_end"), None)
if start_ev:
    print(f"SOAK start (UTC)      : {start_ev['soak_start']}")
last_ts = turns[-1]["ts"] if turns else "n/a"
print(f"last turn (UTC)       : {last_ts}")
if end_ev:
    el = end_ev["soak_elapsed_s"]
else:
    import time, calendar
    if start_ev and turns:
        t0 = calendar.timegm(time.strptime(start_ev["soak_start"], "%Y-%m-%dT%H:%M:%SZ"))
        t1 = calendar.timegm(time.strptime(last_ts, "%Y-%m-%dT%H:%M:%SZ"))
        el = t1 - t0
    else:
        el = 0
print(f"SOAK elapsed          : {el/3600:.2f} h ({int(el)} s)   <-- soak clock, NOT container uptime")
print(f"requests issued       : {len(turns)}")
print(f"windows closed        : {sum(1 for w in wins if w['edge']=='close')}")

# --------------------------------------------------------- HTTP / error classes
print("\n" + "-" * 78)
print("HTTP STATUS DISTRIBUTION / ERROR CLASSES")
print("-" * 78)
sc = Counter(t.get("http_status") for t in turns)
for k, v in sorted(sc.items(), key=lambda x: -x[1]):
    print(f"  status {k}: {v}  ({pct(v,len(turns))})")
ec = Counter(t.get("error_class") for t in turns if t.get("error_class"))
if ec:
    for k, v in ec.most_common():
        print(f"  error_class {k}: {v}")
else:
    print("  error classes: NONE")

ok = [t for t in turns if t.get("http_status") == 200 and not t.get("error_class")]
print(f"  successful turns: {len(ok)} / {len(turns)}  ({pct(len(ok),len(turns))})")

# ------------------------------------------------------------- per-family table
print("\n" + "-" * 78)
print("PER-FAMILY REPORT  (never a pooled number alone)")
print("-" * 78)
byf = defaultdict(list)
for t in ok:
    byf[t["task_family"]].append(t)

hdr = (f"{'family':13s} {'n':>4s} {'accept_est':>10s} {'tok/step':>8s} "
       f"{'TTFT p50':>9s} {'TTFT p95':>9s} {'e2e p50':>8s} {'out tok/s':>9s} {'stop%':>6s} {'len%':>6s}")
print(hdr)
print("-" * len(hdr))
fam_rows = {}
for f in sorted(byf):
    rs = byf[f]
    acc = [r["mtp_acceptance_est"] for r in rs if r.get("mtp_acceptance_est") is not None]
    tps = [r["tokens_per_step"] for r in rs if r.get("tokens_per_step")]
    ttft = [r["ttft_s"] for r in rs if r.get("ttft_s")]
    e2e = [r["e2e_s"] for r in rs if r.get("e2e_s")]
    ots = [r["output_tok_per_s"] for r in rs if r.get("output_tok_per_s")]
    fin = Counter(r.get("finish_reason") for r in rs)
    fam_rows[f] = dict(n=len(rs), acc=st.mean(acc) if acc else None,
                       acc_sd=st.pstdev(acc) if len(acc) > 1 else 0.0)
    print(f"{f:13s} {len(rs):4d} "
          f"{(f'{st.mean(acc)*100:.2f}%' if acc else 'n/a'):>10s} "
          f"{(f'{st.mean(tps):.3f}' if tps else 'n/a'):>8s} "
          f"{(f'{q(ttft,0.5):.2f}s' if ttft else 'n/a'):>9s} "
          f"{(f'{q(ttft,0.95):.2f}s' if ttft else 'n/a'):>9s} "
          f"{(f'{q(e2e,0.5):.1f}s' if e2e else 'n/a'):>8s} "
          f"{(f'{st.mean(ots):.1f}' if ots else 'n/a'):>9s} "
          f"{pct(fin.get('stop',0),len(rs)):>6s} {pct(fin.get('length',0),len(rs)):>6s}")

allacc = [r["mtp_acceptance_est"] for r in ok if r.get("mtp_acceptance_est") is not None]
if allacc:
    print(f"\n  POOLED (context only, never cite alone): {st.mean(allacc)*100:.2f}%  n={len(allacc)}")
    best = max(fam_rows.items(), key=lambda x: x[1]["acc"] or 0)
    worst = min(fam_rows.items(), key=lambda x: x[1]["acc"] if x[1]["acc"] is not None else 9)
    print(f"  best family : {best[0]} {best[1]['acc']*100:.2f}%")
    print(f"  worst family: {worst[0]} {worst[1]['acc']*100:.2f}%")
    print(f"  spread      : {(best[1]['acc']-worst[1]['acc'])*100:.2f} pts")

# --------------------------------------------------- finish_reason by family
print("\n" + "-" * 78)
print("FINISH_REASON BY FAMILY")
print("-" * 78)
for f in sorted(byf):
    print(f"  {f:13s} {dict(Counter(r.get('finish_reason') for r in byf[f]))}")

# ------------------------------------------------ reasoning close-marker stats
print("\n" + "-" * 78)
print("REASONING CLOSE-MARKER (position, not just count)")
print("-" * 78)
th = [r for r in ok if r.get("thinking")]
if th:
    closed = [r for r in th if r.get("close_marker_present")]
    unclosed = [r for r in th if not r.get("close_marker_present")]
    print(f"  thinking turns      : {len(th)}")
    print(f"  reasoning CLOSED    : {len(closed)}  ({pct(len(closed),len(th))})")
    print(f"  reasoning UNCLOSED  : {len(unclosed)}  ({pct(len(unclosed),len(th))})")
    if closed:
        cp = [r["close_marker_pos_chars"] for r in closed]
        cf = [r["close_marker_frac_chars"] for r in closed if r.get("close_marker_frac_chars")]
        rt = [r["est_reasoning_tokens"] for r in closed if r.get("est_reasoning_tokens")]
        print(f"  close pos (chars)   : p50={q(cp,0.5)} p95={q(cp,0.95)} max={max(cp)}")
        print(f"  close frac of gen   : p50={q(cf,0.5):.3f} p95={q(cf,0.95):.3f}")
        print(f"  est reasoning tokens: p50={q(rt,0.5):.0f} p95={q(rt,0.95):.0f}")
    empt = [r for r in th if r.get("empty_content")]
    print(f"  EMPTY content turns : {len(empt)}  ({pct(len(empt),len(th))})")
    if empt and closed:
        ce = [r["close_marker_pos_chars"] for r in empt if r.get("close_marker_pos_chars")]
        print(f"    empty-turn close pos p50 = {q(ce,0.5) if ce else 'n/a (never closed)'}")
        print(f"    non-empty close pos  p50 = {q([r['close_marker_pos_chars'] for r in closed if not r.get('empty_content')],0.5)}")
else:
    print("  no thinking turns yet")

# thinking flag effect, prompt held constant
mt = fam_rows.get("math_think"); mn = fam_rows.get("math_nothink")
if mt and mn and mt["acc"] and mn["acc"]:
    print(f"\n  SAME PROMPTS, thinking ON vs OFF (disentangles flag from task):")
    print(f"    math_think  {mt['acc']*100:.2f}%  n={mt['n']}")
    print(f"    math_nothink {mn['acc']*100:.2f}%  n={mn['n']}")
    print(f"    delta        {(mt['acc']-mn['acc'])*100:+.2f} pts")

# ------------------------------------------------------ per-window drift
print("\n" + "-" * 78)
print("DRIFT ACROSS FIXED REQUEST-COUNT WINDOWS (never time-based)")
print("-" * 78)
opens = {w["window"]: w for w in wins if w["edge"] == "open"}
closes = {w["window"]: w for w in wins if w["edge"] == "close"}
print("  fleet_tw = /metrics, token-weighted   mine_tw = same estimator on my turns only")
print("  mine_rw  = request-weighted mean (each request counts once)")
print(f"{'win':>3s} {'reqs':>5s} {'idx range':>12s} {'fleet_tw':>9s} {'mine_tw':>9s} {'mine_rw':>9s} "
      f"{'foreign':>8s} {'polls':>7s} {'preempt':>8s} {'kv%':>6s}")
for w in sorted(closes):
    o, c = opens.get(w), closes[w]
    if not o:
        continue
    dd = c["metrics"].get("vllm:spec_decode_num_draft_tokens_total", 0) - \
         o["metrics"].get("vllm:spec_decode_num_draft_tokens_total", 0)
    da = c["metrics"].get("vllm:spec_decode_num_accepted_tokens_total", 0) - \
         o["metrics"].get("vllm:spec_decode_num_accepted_tokens_total", 0)
    fleet = (da / dd) if dd else None
    lo, hi = o["req_index"], c["req_index"]
    mine = [t for t in ok if lo <= t["req_id"] < hi and t.get("mtp_acceptance_est") is not None]
    myacc = st.mean([t["mtp_acceptance_est"] for t in mine]) if mine else None
    # token-weighted, i.e. the SAME estimator /metrics uses:
    # accepted = completion_tokens - decode_steps ; drafts = decode_steps * K
    num = sum((t["completion_tokens"] - t["decode_steps"]) for t in mine)
    den = sum(t["decode_steps"] * 3 for t in mine)
    mytw = (num / den) if den else None
    http_d = c["metrics"].get("http_requests_total", 0) - o["metrics"].get("http_requests_total", 0)
    # http_requests_total counts EVERY endpoint, including /health and /metrics
    # polls from the watchdog, board renderer and ModelOps dashboard. For
    # "did other INFERENCE leak into the acceptance counters?" the only correct
    # attributor is vllm:request_success_total, which counts generations only.
    succ_d = c["metrics"].get("vllm:request_success_total", 0) - \
             o["metrics"].get("vllm:request_success_total", 0)
    unattrib = int(round(succ_d - (hi - lo)))          # foreign INFERENCE
    poll_d = int(round(http_d - succ_d))               # non-inference polls
    pre = c["metrics"].get("vllm:num_preemptions_total", 0) - \
          o["metrics"].get("vllm:num_preemptions_total", 0)
    print(f"{w:3d} {hi-lo:5d} {f'{lo}-{hi}':>12s} "
          f"{(f'{fleet*100:.2f}%' if fleet else 'n/a'):>9s} "
          f"{(f'{mytw*100:.2f}%' if mytw else 'n/a'):>9s} "
          f"{(f'{myacc*100:.2f}%' if myacc else 'n/a'):>9s} "
          f"{unattrib:>8d} {poll_d:>7d} {int(pre):>8d} "
          f"{c['metrics'].get('vllm:kv_cache_usage_perc',0)*100:5.1f}%")

# per-family drift across windows
print("\n  PER-FAMILY ACCEPTANCE BY WINDOW (drift cannot hide as a task effect):")
famset = sorted(byf)
print("    win  " + "".join(f"{f[:12]:>14s}" for f in famset))
for w in sorted(closes):
    o, c = opens.get(w), closes[w]
    if not o:
        continue
    lo, hi = o["req_index"], c["req_index"]
    cells = []
    for f in famset:
        v = [t["mtp_acceptance_est"] for t in byf[f]
             if lo <= t["req_id"] < hi and t.get("mtp_acceptance_est") is not None]
        cells.append(f"{st.mean(v)*100:.1f}% (n{len(v)})" if v else "n/a")
    print(f"    {w:3d}  " + "".join(f"{c2:>14s}" for c2 in cells))

# ------------------------------------------------------------------- memory
print("\n" + "-" * 78)
print("MEMORY / LANE HEALTH TIMELINE")
print("-" * 78)
print(f"{'req_i':>6s} {'ts':>21s}  " + "  ".join(f"{n[:9]:>9s} avail/swap" for n in ["node-a", "node-b"]))
for m in mems:
    cells = []
    for n in ["node-a", "node-b"]:
        d = m["mem"].get(n, {})
        cells.append(f"{d.get('avail_mb','?'):>6}MB/{d.get('swap_used_mb','?')}MB" if "avail_mb" in d else "   ERR   ")
    print(f"{m['req_i']:6d} {m['ts']:>21s}  " + "  ".join(f"{c:>20s}" for c in cells))

# ------------------------------------------------------------------- events
print("\n" + "-" * 78)
print("EVENTS (backoff / errors / scanner / assumption breaks)")
print("-" * 78)
kinds = Counter(e["kind"] for e in evs)
for k, v in kinds.most_common():
    print(f"  {k}: {v}")
notable = [e for e in evs if e["kind"] not in ("window_done", "soak_start", "soak_end")]
if notable:
    print("\n  detail:")
    for e in notable[:60]:
        print("   ", json.dumps(e)[:260])
else:
    print("  no backoffs, no errors, no scanner flags, no assumption breaks")

# ------------------------------------------------------------- scanner flags
print("\n" + "-" * 78)
print("SPONTANEOUS SYMPTOM SCAN")
print("-" * 78)
fl = [t for t in turns if t.get("flags")]
print(f"  turns with any flag: {len(fl)} / {len(turns)}  ({pct(len(fl),len(turns))})")
agg = Counter()
for t in fl:
    for k in t["flags"]:
        agg[k] += 1
for k, v in agg.most_common():
    print(f"    {k}: {v}")
for t in fl[:15]:
    print(f"    req {t['req_id']} [{t['task_family']}] {json.dumps(t['flags'])[:150]}")
over = [t for t in turns if t.get("tps_over_ceiling")]
print(f"  tokens/step > K+1 ceiling (assumption break): {len(over)}")
