#!/usr/bin/env python3
"""
Cross-model test of the cold-prefill / max-num-batched-tokens boundary.
Runs ON the serving node against REDACTED_IP:8201 (Laguna S 2.1 NVFP4).

Cold is MEASURED, never assumed: the prefix-cache hit fraction is read from the
engine counters immediately before and after every request and reported next to
every result. Requests landing between the cold and warm thresholds are
excluded from both groups and counted.

Durations use time.monotonic() -- time.time() under a syncing NTP clock gave
9 negative TTFTs in an earlier harness this session.
"""
import json, sys, time, urllib.request, re, os, argparse

BASE = "http://REDACTED_IPHOST:PORT"
MODEL = "deepseek-v4-flash-dspark"
COLD_MAX = 0.02
WARM_MIN = 0.95

def http(path, payload=None, timeout=1800):
    if payload is None:
        req = urllib.request.Request(BASE + path)
    else:
        req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

def metrics():
    _, body = http("/metrics")
    out = {}
    for line in body.splitlines():
        if line.startswith("#") or not line:
            continue
        name = line.split("{")[0].split(" ")[0]
        try:
            val = float(line.rsplit(" ", 1)[1])
        except Exception:
            continue
        out[name] = out.get(name, 0.0) + val
    return out

def hit_fraction(m0, m1):
    """Measured prefix-cache hit fraction for the work done between snapshots."""
    for hk, qk in (("vllm:gpu_prefix_cache_hits_total", "vllm:gpu_prefix_cache_queries_total"),
                   ("vllm:prefix_cache_hits_total", "vllm:prefix_cache_queries_total")):
        if hk in m1 and qk in m1:
            dh = m1[hk] - m0.get(hk, 0.0)
            dq = m1[qk] - m0.get(qk, 0.0)
            return (dh / dq) if dq > 0 else 0.0, dh, dq
    return None, None, None

def ntokens(text):
    st, body = http("/tokenize", {"model": MODEL, "prompt": text})
    return json.loads(body)["count"]

# --- prompt construction -----------------------------------------------------
SECRET = "ZEPHYR-4417"
PREAMBLE = (f"CLEARANCE CODE FOR THIS SESSION: {SECRET}\n"
            "Remember this code. You will be asked for it at the end.\n\n"
            "MANIFEST FOLLOWS.\n")
QUESTION = ("\n\nEND OF MANIFEST.\n\n"
            "Ignore the manifest. What is the CLEARANCE CODE for this session? "
            "Reply with the code and nothing else.")

def record(i):
    return (f"Record {i:06d}: crate UNIT-{i%997:03d} was sealed at bay "
            f"{i%53} on day {i%365}, mass {40+(i*7)%60}.{i%10} kg, "
            f"inspector team-{i%11}, seal {(i*31)%9973:04d}.\n")

def build(target_tokens):
    """Build a prompt of almost exactly target_tokens, fact early, question last."""
    body, i = [], 0
    # coarse fill
    while True:
        chunk = "".join(record(i + k) for k in range(200))
        cand = PREAMBLE + "".join(body) + chunk + QUESTION
        if ntokens(cand) > target_tokens:
            break
        body.append(chunk); i += 200
    # fine fill
    while True:
        cand = PREAMBLE + "".join(body) + record(i) + QUESTION
        if ntokens(cand) > target_tokens:
            break
        body.append(record(i)); i += 1
    text = PREAMBLE + "".join(body) + QUESTION
    return text, ntokens(text)

def classify(content, reasoning):
    c = (content or "").strip()
    r = (reasoning or "")
    if SECRET in c:
        return "clean_answered"
    if re.search(r"Record \d{6}:", c):
        return "continued_document"
    if not c and r:
        return "empty_content_reasoning_only"
    if not c:
        return "empty"
    return "other_wrong"

def fire(text, thinking, max_tokens, salt, label):
    body = {"model": MODEL,
            "messages": [{"role": "user", "content": text}],
            "max_tokens": max_tokens, "temperature": 0.0,
            "cache_salt": salt}
    if thinking is not None:
        body["chat_template_kwargs"] = {"thinking": bool(thinking)}
    m0 = metrics()
    t0 = time.monotonic()
    try:
        st, raw = http("/v1/chat/completions", body)
        e2e = time.monotonic() - t0
        d = json.loads(raw)
        ch = d["choices"][0]; msg = ch["message"]
        content = msg.get("content"); reasoning = msg.get("reasoning") or msg.get("reasoning_content")
        fin = ch.get("finish_reason"); usage = d.get("usage")
        err = None
    except Exception as e:
        e2e = time.monotonic() - t0
        st, content, reasoning, fin, usage, err = 0, None, None, None, None, repr(e)[:300]
    m1 = metrics()
    hf, dh, dq = hit_fraction(m0, m1)
    path = ("cold" if (hf is not None and hf <= COLD_MAX)
            else "warm" if (hf is not None and hf >= WARM_MIN) else "EXCLUDED")
    rec = dict(label=label, thinking=thinking, http=st, e2e_s=round(e2e, 2),
               finish_reason=fin, hit_fraction=(round(hf, 4) if hf is not None else None),
               hits_delta=dh, queries_delta=dq, path=path,
               usage=usage, outcome=classify(content, reasoning), error=err,
               content_head=(content or "")[:200], reasoning_head=(reasoning or "")[:200])
    return rec

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, nargs="+", required=True)
    ap.add_argument("--mnbt", type=int, required=True)
    ap.add_argument("--out", default=os.path.expanduser("~/mnbt_probe/results.jsonl"))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--warm", action="store_true", help="also fire an identical warm arm")
    ap.add_argument("--thinking", default="none", choices=["none", "off", "on", "both"])
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fh = open(a.out, "a", buffering=1)
    modes = {"none": [None], "off": [False], "on": [True], "both": [False, True]}[a.thinking]
    for tgt in a.tokens:
        text, actual = build(tgt)
        chunks = -(-actual // a.mnbt)
        for th in modes:
            for rep in range(a.reps):
                salt = f"mnbt{a.mnbt}-t{actual}-th{th}-r{rep}-{int(time.time()*1000)}"
                r = fire(text, th, 64, salt, f"mnbt{a.mnbt}_tok{actual}_th{th}_r{rep}")
                r.update(mnbt=a.mnbt, target_tokens=tgt, prompt_tokens=actual, chunks=chunks,
                         arm="cold", rep=rep)
                fh.write(json.dumps(r) + "\n")
                print(f"MNBT{a.mnbt} tok={actual:>7} chunks={chunks} th={th} rep={rep} "
                      f"path={r['path']} hit={r['hit_fraction']} fin={r['finish_reason']} "
                      f"-> {r['outcome']} ({r['e2e_s']}s)", flush=True)
                if a.warm:
                    r2 = fire(text, th, 64, salt, f"WARM_{r['label']}")
                    r2.update(mnbt=a.mnbt, target_tokens=tgt, prompt_tokens=actual,
                              chunks=chunks, arm="warm", rep=rep)
                    fh.write(json.dumps(r2) + "\n")
                    print(f"   WARM  hit={r2['hit_fraction']} fin={r2['finish_reason']} "
                          f"-> {r2['outcome']} ({r2['e2e_s']}s)", flush=True)
