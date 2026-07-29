#!/usr/bin/env python3
"""
DSV4 abliterated long soak -- REQUEST-LEVEL ONLY.
Never restarts, reconfigures or touches the container. Pure HTTP client load.

Method (mandated):
  * FIXED REQUEST-COUNT WINDOWS -- all drift is per-window, never time-based.
  * Per-family reporting always; families interleaved round-robin.
  * Logs task_family, finish_reason, reasoning token count AND the token
    position of the reasoning-close marker (the reasoning->content switch).
  * Counter snapshots recorded at every window boundary (both edges).
"""
import json, os, ssl, sys, time, subprocess, urllib.request, urllib.error, re
from collections import deque

BASE = "http://REDACTED_IPHOST:PORT"
MODEL = "deepseek-v4-flash-dspark"
OUT = os.path.expanduser("~/staging/dsv4-long-soak-20260728")
RAW = os.path.join(OUT, "raw")
WINDOW = int(os.environ.get("SOAK_WINDOW", "60"))   # 10 per family x 6 families
BASE_GAP = float(os.environ.get("SOAK_GAP", "4.0"))  # background load, not a benchmark
MAX_WINDOWS = int(os.environ.get("SOAK_MAX_WINDOWS", "40"))
MEM_SAMPLE_EVERY = 20       # requests
NODES = ["node-a", "node-b"]

os.makedirs(RAW, exist_ok=True)
turns_f  = open(os.path.join(RAW, "turns.jsonl"), "a", buffering=1)
win_f    = open(os.path.join(RAW, "windows.jsonl"), "a", buffering=1)
ev_f     = open(os.path.join(RAW, "events.jsonl"), "a", buffering=1)
mem_f    = open(os.path.join(RAW, "memory.jsonl"), "a", buffering=1)

def now():
    return time.time()

def iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t or now()))

def ev(kind, **kw):
    rec = dict(ts=iso(), kind=kind, **kw)
    ev_f.write(json.dumps(rec) + "\n")
    print("EVENT", kind, kw, flush=True)

# ---------------------------------------------------------------- prompt pool
TOPICS = ["a tidal power station", "a municipal compost scheme", "an alpine rail tunnel",
          "a coral nursery", "a regional grain silo", "a satellite ground station",
          "a night bus network", "a hospital pharmacy robot", "a peat bog restoration",
          "a container port crane", "a rural fibre rollout", "a seed vault",
          "a desalination plant", "a wind farm substation", "a river lock"]

MATH = [
 "A tank fills at 12 L/min and drains at 7 L/min. It starts with 40 L and holds 300 L. When does it overflow?",
 "A train leaves A at 55 km/h. Three hours later a second leaves A at 88 km/h. How far from A do they meet?",
 "A rope loses one third of its length, then one quarter of what remains, leaving 9 m. What was the original length?",
 "Six machines make 240 parts in 8 hours. How long do 10 machines take for 500 parts at the same rate?",
 "A cyclist averages 24 km/h out and 16 km/h back. What is the average speed for the round trip?",
 "An alloy is 30% tin. How much pure tin must be added to 60 kg to make it 50% tin?",
 "A number is 4 more than three times its reciprocal's inverse-scaled double. Simplify: solve 3x + 4 = x^2 for x>0.",
 "Two pipes fill a pool in 6 and 9 hours. Both run for 2 hours, then only the slower. Total time to fill?",
 "A ladder 13 m long leans on a wall, base 5 m out. The base slides out 2 m. How far does the top drop?",
 "A shop marks up 40% then discounts 25%. What is the net percentage change on cost?",
]

CODE = [
 "Write a Python function that merges overlapping intervals. Include the edge cases you handle.",
 "Write a Python LRU cache using only a dict and a doubly linked list. No functools.",
 "Write a bash one-liner that finds the 10 largest files under a path, then explain each flag.",
 "Write a Python generator that yields a rolling median over a stream. Explain the data structure.",
 "Write a SQL query for the second-highest salary per department, and say why a naive LIMIT fails.",
 "Write a Python context manager that retries a block with exponential backoff and jitter.",
 "Write a function to detect a cycle in a linked list and return the node where it starts.",
 "Write a Python function that parses a semver string and compares two versions correctly.",
 "Write a regex to validate an IPv4 address and explain why the naive \\d{1,3} form is wrong.",
 "Write a Python function that flattens arbitrarily nested lists iteratively, not recursively.",
]

def summ_text(i):
    t = TOPICS[i % len(TOPICS)]
    return (f"Summarise the following operational note about {t} in exactly three sentences.\n\n"
            f"NOTE: The site logged {300+i*7} operating hours this quarter against a plan of "
            f"{320+i*5}. Two unplanned stoppages occurred, the first lasting {2+i%5} hours from a "
            f"sensor fault on the intake line, the second {1+i%3} hours during a scheduled grid "
            f"curtailment that overran. Maintenance closed {11+i%9} of {14+i%9} raised work orders. "
            f"Spare-part lead times rose from {3+i%4} to {6+i%6} weeks, and the team flagged that the "
            f"vibration monitoring threshold has not been recalibrated since commissioning. "
            f"Output was {88-i%12} percent of the modelled figure, with the shortfall attributed "
            f"mainly to the curtailment rather than to equipment availability.")

def longctx_text(i):
    # ~1.5k tokens of structured filler with a specific fact planted mid-document
    lines = []
    for j in range(60):
        lines.append(f"Record {j:03d}: asset={TOPICS[(i+j) % len(TOPICS)]}, "
                     f"status={'nominal' if j % 3 else 'watch'}, "
                     f"reading={(j*37 + i*11) % 900 / 10:.1f}, "
                     f"inspector=team-{(j % 7) + 1}, cycle={1900 + ((i + j) % 120)}")
    key = (i * 13) % 60
    lines[key] += f"  <-- ANOMALY CODE QX-{4000 + i}"
    body = "\n".join(lines)
    return (f"Below is an asset log. Find the single record carrying an ANOMALY CODE, "
            f"report the code and the record number, and state the inspector on that line.\n\n{body}")

def chat_text(i):
    t = TOPICS[i % len(TOPICS)]
    return f"In two or three sentences, what is the single biggest operational risk for {t}, and why that one?"

# family -> (builder, thinking_flag, max_tokens)
FAMILIES = [
    ("chat",         lambda i: chat_text(i),                False, 400),
    ("code",         lambda i: CODE[i % len(CODE)],         False, 1500),
    ("summarize",    lambda i: summ_text(i),                False, 500),
    ("math_think",   lambda i: MATH[i % len(MATH)],         True,  1600),
    ("math_nothink", lambda i: MATH[i % len(MATH)],         False, 1200),
    ("longctx",      lambda i: longctx_text(i),             False, 400),
]

# ------------------------------------------------------------------ scanners
# 5x repeated chunk. The repeated unit must itself contain a non-whitespace
# character: a lookahead is NOT enough (it matches a later non-space on the same
# line), which is why an earlier version still fired on code indentation.
# The whitespace rejection is therefore done on the captured group, below.
GARBLE_RE = re.compile(r"([^\n]{3,40}?)\1{4,}")
REGISTRY_RE = re.compile(
    r"(<\|[a-z_]+\|>|<\|tool|<function|◁|▷|\bskill_registry\b|\bregistry\b|"
    r"<\|im_start\|>|<\|im_end\|>|\btool_calls?\b|<｜begin|<｜end)", re.I)
CJK_RE = re.compile(r"[぀-ヿ一-鿿가-힯]")

def scan(text):
    if not text:
        return {}
    flags = {}
    for m in GARBLE_RE.finditer(text):
        unit = m.group(1)
        if unit.strip():                      # reject pure-whitespace runs
            flags["garble_repeat"] = unit[:40]
            flags["garble_at"] = m.start()
            break
    r = REGISTRY_RE.search(text)
    if r:
        flags["registry_symptom"] = r.group(0)[:40]
    cj = CJK_RE.findall(text)
    if len(cj) > 2:
        flags["cjk_chars"] = len(cj)
    na = sum(1 for c in text if ord(c) > 0x2000)
    if na > max(10, len(text) * 0.05):
        flags["nonascii_ratio"] = round(na / max(1, len(text)), 3)
    return flags

# ------------------------------------------------------------------- metrics
METRIC_KEYS = [
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:num_preemptions_total",
    "vllm:prompt_tokens_total",
    "vllm:generation_tokens_total",
    "vllm:request_success_total",
    "vllm:kv_cache_usage_perc",
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "http_requests_total",
    "http_request_duration_highr_seconds_count",
    "process_resident_memory_bytes",
    "vllm:gpu_prefix_cache_hits_total",
    "vllm:gpu_prefix_cache_queries_total",
]

def get_metrics():
    try:
        with urllib.request.urlopen(BASE + "/metrics", timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        ev("metrics_fail", err=repr(e)[:200])
        return None
    out, pos = {}, {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{")[0].split(" ")[0]
        try:
            val = float(line.rsplit(" ", 1)[1])
        except Exception:
            continue
        if name == "vllm:spec_decode_num_accepted_tokens_per_pos_total":
            mm = re.search(r'position="(\d+)"', line)
            if mm:
                pos[mm.group(1)] = val
            continue
        if name in METRIC_KEYS:
            out[name] = out.get(name, 0.0) + val
    out["_per_pos"] = pos
    return out

def node_mem():
    res = {}
    for n in NODES:
        try:
            p = subprocess.run(
                ["ssh", "-n", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", n,
                 "free -m | awk '/Mem:/{print $2,$3,$7} /Swap:/{print $3}'; "
                 "cat /proc/loadavg | cut -d' ' -f1"],
                capture_output=True, text=True, timeout=30)
            parts = p.stdout.split()
            if len(parts) >= 5:
                res[n] = dict(total_mb=int(parts[0]), used_mb=int(parts[1]),
                              avail_mb=int(parts[2]), swap_used_mb=int(parts[3]),
                              load1=float(parts[4]))
        except Exception as e:
            res[n] = {"err": repr(e)[:120]}
    return res

# ---------------------------------------------------------------- one request
def one(family, thinking, prompt, max_tok, req_id):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tok,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": f"soak-{req_id}-20260728",   # unique -> honest cold-prefill TTFT
    }
    if thinking:
        body["chat_template_kwargs"] = {"thinking": True}
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    rec = dict(req_id=req_id, ts=iso(), task_family=family, thinking=thinking,
               max_tokens=max_tok, prompt_chars=len(prompt))
    t0 = now()
    ttft = None
    # NOTE: one SSE delta == one DECODE STEP, not one token. Under MTP K=3 a
    # step emits 1..4 tokens (measured ratio 2.2-3.5 in the smoke run). These
    # are step counts; token counts are derived from usage, never from these.
    reasoning_deltas = 0
    content_deltas = 0
    close_pos_steps = None   # decode-step index at which reasoning -> content switched
    seen_content = False
    close_pos_chars = None
    r_chars = c_chars = 0
    reasoning_buf, content_buf = [], []
    finish = None
    usage = None
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            rec["http_status"] = resp.status
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ch = json.loads(payload)
                except Exception:
                    continue
                if ch.get("usage"):
                    usage = ch["usage"]
                for c in ch.get("choices") or []:
                    d = c.get("delta") or {}
                    if c.get("finish_reason"):
                        finish = c["finish_reason"]
                    rtxt = d.get("reasoning") or d.get("reasoning_content")
                    ctxt = d.get("content")
                    if rtxt:
                        if ttft is None:
                            ttft = now() - t0
                        reasoning_deltas += 1
                        r_chars += len(rtxt)
                        reasoning_buf.append(rtxt)
                    if ctxt:
                        if ttft is None:
                            ttft = now() - t0
                        if not seen_content:
                            seen_content = True
                            # The reasoning-close marker sits exactly here -- but
                            # only if reasoning was actually emitted. Without this
                            # guard every non-thinking turn records a spurious
                            # close position of 0 instead of "not applicable".
                            if reasoning_deltas > 0:
                                close_pos_steps = reasoning_deltas
                                close_pos_chars = r_chars
                        content_deltas += 1
                        c_chars += len(ctxt)
                        content_buf.append(ctxt)
    except urllib.error.HTTPError as e:
        rec.update(http_status=e.code, error_class="HTTPError",
                   error=e.read().decode("utf-8", "replace")[:300])
    except urllib.error.URLError as e:
        rec.update(http_status=0, error_class="URLError", error=repr(e.reason)[:200])
    except Exception as e:
        rec.update(http_status=0, error_class=type(e).__name__, error=repr(e)[:200])

    e2e = now() - t0
    content = "".join(content_buf)
    reasoning = "".join(reasoning_buf)
    ct = (usage or {}).get("completion_tokens")
    steps = reasoning_deltas + content_deltas
    total_chars = r_chars + c_chars
    # Per-request MTP observable. One decode step emits 1 target token plus any
    # accepted draft tokens, so tokens_per_step in [1, K+1] with K=3.
    # acceptance = (tokens_per_step - 1) / K. This is REQUEST-SCOPED and so is
    # immune to the fleet-wide contamination that /metrics acceptance carries.
    tps_step = (ct / steps) if (ct and steps) else None
    accept_est = ((tps_step - 1.0) / 3.0) if tps_step else None
    rec.update(
        e2e_s=round(e2e, 3),
        ttft_s=round(ttft, 3) if ttft is not None else None,
        finish_reason=finish,
        usage=usage,
        completion_tokens=ct,
        prompt_tokens=(usage or {}).get("prompt_tokens"),
        decode_steps=steps,
        reasoning_steps=reasoning_deltas,
        content_steps=content_deltas,
        reasoning_chars=r_chars,
        content_chars=c_chars,
        # exact character index of the reasoning-close marker in the generated
        # stream; None when the model never closed reasoning (or never opened it)
        close_marker_pos_chars=close_pos_chars,
        close_marker_pos_steps=close_pos_steps,
        close_marker_present=(close_pos_chars is not None) if thinking else None,
        close_marker_frac_chars=(round(close_pos_chars / total_chars, 4)
                                 if (close_pos_chars is not None and total_chars) else None),
        # token-scale reasoning length: exact total from usage, split by char share
        est_reasoning_tokens=(round(ct * r_chars / total_chars, 1)
                              if (ct and total_chars) else None),
        tokens_per_step=round(tps_step, 3) if tps_step else None,
        mtp_acceptance_est=round(accept_est, 4) if accept_est is not None else None,
        # assumption guard: tokens_per_step must not exceed K+1 = 4
        tps_over_ceiling=(bool(tps_step and tps_step > 4.0 + 1e-6)),
        empty_content=(c_chars == 0),
        output_tok_per_s=round(ct / e2e, 2) if (ct and e2e > 0) else None,
    )
    if rec["tps_over_ceiling"]:
        ev("ASSUMPTION_BREAK_tps_over_4", req_id=req_id, family=family,
           tokens_per_step=rec["tokens_per_step"], completion_tokens=ct, steps=steps)
    if thinking and close_pos_chars is None and r_chars > 0:
        ev("reasoning_never_closed", req_id=req_id, family=family,
           finish_reason=finish, reasoning_chars=r_chars)
    fl = scan(content + "\n" + reasoning)
    if fl:
        rec["flags"] = fl
        ev("scanner_flag", req_id=req_id, family=family, flags=fl)
    rec["content_head"] = content[:200]
    rec["reasoning_head"] = reasoning[:200]
    turns_f.write(json.dumps(rec) + "\n")
    return rec

# ------------------------------------------------------------------ main loop
def main():
    soak_start = now()
    m0 = get_metrics()
    mem0 = node_mem()
    ev("soak_start", soak_start=iso(soak_start), window_size=WINDOW,
       baseline_metrics={k: v for k, v in (m0 or {}).items() if k != "_per_pos"},
       baseline_per_pos=(m0 or {}).get("_per_pos"), baseline_mem=mem0)
    mem_f.write(json.dumps(dict(ts=iso(), req_i=0, mem=mem0)) + "\n")

    gap = BASE_GAP
    req_i = 0
    fam_i = 0
    recent_ttft = deque(maxlen=25)
    first_window_ttft = None
    consec_fail = 0
    halted = False

    for w in range(MAX_WINDOWS):
        w_start_req = req_i
        w_m0 = get_metrics()
        w_t0 = now()
        win_open = dict(window=w, edge="open", ts=iso(w_t0), req_index=req_i,
                        metrics={k: v for k, v in (w_m0 or {}).items() if k != "_per_pos"},
                        per_pos=(w_m0 or {}).get("_per_pos"))
        win_f.write(json.dumps(win_open) + "\n")

        for k in range(WINDOW):
            fam, builder, thinking, mt = (FAMILIES[fam_i % len(FAMILIES)][0],
                                          FAMILIES[fam_i % len(FAMILIES)][1],
                                          FAMILIES[fam_i % len(FAMILIES)][2],
                                          FAMILIES[fam_i % len(FAMILIES)][3])
            fam_i += 1
            prompt = builder(req_i)
            rec = one(fam, thinking, prompt, mt, req_i)
            rec_ok = rec.get("http_status") == 200 and not rec.get("error_class")
            if rec_ok:
                consec_fail = 0
                if rec.get("ttft_s"):
                    recent_ttft.append(rec["ttft_s"])
            else:
                consec_fail += 1
                ev("request_error", req_id=req_i, family=fam,
                   status=rec.get("http_status"), cls=rec.get("error_class"),
                   err=str(rec.get("error"))[:200])
                if consec_fail >= 3:
                    ev("backoff_errors", consec_fail=consec_fail, pause_s=60)
                    time.sleep(60)
            req_i += 1

            # ---- memory / burn sampling
            if req_i % MEM_SAMPLE_EVERY == 0:
                mm = node_mem()
                mem_f.write(json.dumps(dict(ts=iso(), req_i=req_i, mem=mm)) + "\n")
                worst = min([v.get("avail_mb", 999999) for v in mm.values()
                             if isinstance(v, dict) and "avail_mb" in v] or [999999])
                if worst < 2048:
                    ev("HALT_low_memory", avail_mb=worst, mem=mm)
                    halted = True
                    break
                if worst < 4096:
                    gap = max(gap, 30.0)
                    ev("backoff_memory", avail_mb=worst, new_gap=gap, mem=mm)

            # ---- latency burn detector
            if len(recent_ttft) == recent_ttft.maxlen:
                cur = sorted(recent_ttft)[len(recent_ttft) // 2]
                if first_window_ttft is None and w == 0:
                    first_window_ttft = cur
                    ev("ttft_baseline", p50=round(cur, 3))
                elif first_window_ttft and cur > 2.5 * first_window_ttft:
                    gap = min(gap * 2, 60.0)
                    ev("backoff_latency", p50_now=round(cur, 3),
                       p50_base=round(first_window_ttft, 3), new_gap=gap)
                    recent_ttft.clear()

            time.sleep(gap)

        w_m1 = get_metrics()
        win_close = dict(window=w, edge="close", ts=iso(), req_index=req_i,
                         requests_in_window=req_i - w_start_req,
                         wall_s=round(now() - w_t0, 1),
                         metrics={k: v for k, v in (w_m1 or {}).items() if k != "_per_pos"},
                         per_pos=(w_m1 or {}).get("_per_pos"))
        win_f.write(json.dumps(win_close) + "\n")
        ev("window_done", window=w, req_index=req_i,
           soak_elapsed_s=round(now() - soak_start, 1))
        if halted:
            break

    ev("soak_end", soak_start=iso(soak_start), soak_end=iso(),
       soak_elapsed_s=round(now() - soak_start, 1), requests=req_i, halted=halted,
       final_metrics={k: v for k, v in (get_metrics() or {}).items() if k != "_per_pos"},
       final_mem=node_mem())

if __name__ == "__main__":
    main()
