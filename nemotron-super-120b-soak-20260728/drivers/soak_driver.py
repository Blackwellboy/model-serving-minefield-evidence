#!/usr/bin/env python3
"""
Nemotron Super 120B production soak driver.

Single serve, no baseline arm. Every number this produces is DESCRIPTIVE of one
process over time, not comparative against another configuration.

Design notes that matter for reading the output:
  * Sequential single-stream. max-num-seqs is 4 but we send one request at a
    time, so tok/s is a clean per-request decode rate, not an aggregate.
  * Task families are interleaved round-robin, so any monotone trend cannot be
    an artefact of task ordering.
  * A fixed temperature-0 canary runs on a wall-clock cadence with an identical
    prompt every time. That is the burn detector: identical input, so any change
    in length or content is the serve changing, not the workload.
  * Engine counters are cumulative. Acceptance DRIFT is computed from DELTAS
    between consecutive scrapes, never from the cumulative ratio, which by
    construction flattens toward its own average and would hide drift.
"""

import argparse, hashlib, json, os, re, signal, sys, time
import urllib.request, urllib.error

BASE = os.environ.get("SOAK_BASE", "http://REDACTED_IP:8000")
MODEL = os.environ.get("SOAK_MODEL", "nvidia/nemotron-3-super")

STOP = False


def _sig(*_):
    global STOP
    STOP = True
    sys.stderr.write("\n[driver] stop signal received, finishing current turn\n")


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


# --------------------------------------------------------------------------
# workload
# --------------------------------------------------------------------------
# Seven families. Deliberately different decode shapes: prose is high-entropy
# and should accept fewer drafts, code and structured output are low-entropy
# and should accept more. If acceptance sorts by family the same way all run,
# that is the content effect; a change in that sorting over time is drift.

FAMILIES = {
    "prose": [
        "Write three paragraphs about how tidal patterns shaped early coastal settlement.",
        "Describe the experience of walking through a city during a power outage.",
        "Explain, for a general audience, why old bridges are often over-engineered.",
        "Write a short reflective piece about learning a language as an adult.",
    ],
    "code": [
        "Write a Python function that merges overlapping intervals. Include docstring and three tests.",
        "Write a Go function that reads a CSV and returns column-wise summary statistics. Handle malformed rows.",
        "Write a SQL query and schema for tracking versioned document revisions with soft deletes.",
        "Write a Rust struct and impl for a fixed-capacity ring buffer with an iterator.",
    ],
    "math": [
        "A tank fills at 12 L/min and drains at 7 L/min. It starts at 40 L with capacity 300 L. When is it full? Show working.",
        "Prove that the sum of the first n odd numbers is n squared. Give both an algebraic and a visual argument.",
        "Three machines produce 40%, 35%, 25% of output with defect rates 2%, 3%, 5%. Given a defective item, what is the probability machine C made it?",
        "Find all integer solutions to 7x + 11y = 100 and explain the method.",
    ],
    "reasoning": [
        "Four people cross a bridge at night with one torch, taking 1, 2, 7 and 10 minutes. Two cross at a time at the slower pace. Find the minimum total time and justify optimality.",
        "You have 12 balls, one of which differs in weight. Using a balance three times, identify it and whether it is heavy or light.",
        "A says B lies. B says C lies. C says A and B both lie. Who tells the truth? Show the case analysis.",
        "Plan the order of five dependent tasks given constraints, and state which constraint is binding.",
    ],
    "tool": [
        "What is the current weather in Oslo, and what time is sunset there today?",
        "Look up the population of Bergen and convert it to a percentage of Norway's total.",
        "Search for the latest release version of PostgreSQL and report the release date.",
        "Get the exchange rate from NOK to JPY and convert 4500 NOK.",
    ],
    "summarize": [
        "Summarise in five bullet points: " + (
            "Speculative decoding proposes several tokens with a cheap draft model and verifies them "
            "in a single forward pass of the target model. Accepted tokens are emitted without their "
            "own pass, so throughput rises when acceptance is high. Acceptance depends on how "
            "predictable the text is, which is why structured output accepts more than open prose. "
            "The draft model itself costs time, so at low acceptance speculative decoding is a net "
            "loss. Multi-token prediction reuses one shared layer for several draft positions, which "
            "lowers acceptance at deeper positions relative to independent drafters. " * 3),
        "Summarise the tradeoffs between fp8 and fp4 KV cache in three sentences.",
        "Condense the following into a single paragraph: " + (
            "Unified memory on this class of hardware means the model weights, the KV cache and the "
            "host working set all draw on one pool. A configuration that fits at startup can still "
            "fail later if fragmentation grows or a co-tenant appears. Monitoring free memory over "
            "time is therefore not optional. " * 4),
        "Give a three-sentence summary of why prefill and decode have different performance characteristics.",
    ],
    "structured": [
        "Return a JSON object describing a library book: title, author, isbn, year, subjects (array), available (bool). Use plausible values. JSON only.",
        "Return a JSON array of five server health records with fields host, cpu_pct, mem_gb, status. JSON only.",
        "Produce a YAML config for a reverse proxy with two upstreams, health checks and TLS. YAML only.",
        "Return a markdown table of six programming languages with columns: name, year, paradigm, typing.",
    ],
}

FAMILY_ORDER = ["prose", "code", "math", "reasoning", "tool", "summarize", "structured"]

TOOLS = [{
    "type": "function",
    "function": {
        "name": "web_lookup",
        "description": "Look up a fact on the web.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "the search query"},
                "unit": {"type": "string", "description": "optional unit hint"},
            },
            "required": ["query"],
        },
    },
}]

# The burn canary. Identical every time, temperature 0, fixed seed, fixed
# max_tokens. Deterministic-in-intent; this fleet has documented temp-0
# non-determinism, so we measure the spread rather than assume byte equality.
CANARY_PROMPT = (
    "List the first eight prime numbers, then explain in exactly three sentences "
    "why there are infinitely many primes."
)


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

def _post_stream(path, payload, timeout=1800):
    """POST with stream=true. Returns (status, ttft_s, total_s, chunks, err)."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    ttft = None
    pieces = {"content": [], "reasoning": []}
    finish = None
    usage = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except Exception:
                    continue
                if ev.get("usage"):
                    usage = ev["usage"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    # which field carries reasoning is a serving-stack property,
                    # so accept every spelling rather than assuming one.
                    for k, dest in (("content", "content"),
                                    ("reasoning_content", "reasoning"),
                                    ("reasoning", "reasoning")):
                        v = d.get(k)
                        if v:
                            if ttft is None:
                                ttft = time.time() - t0
                            pieces[dest].append(v)
                    if d.get("tool_calls"):
                        if ttft is None:
                            ttft = time.time() - t0
                        pieces["content"].append(json.dumps(d["tool_calls"]))
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        return status, ttft, time.time() - t0, pieces, finish, usage, None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:600]
        except Exception:
            detail = ""
        return e.code, ttft, time.time() - t0, pieces, None, None, detail
    except Exception as e:
        return 0, ttft, time.time() - t0, pieces, None, None, f"{type(e).__name__}: {e}"


def scrape_metrics():
    """Cumulative engine counters. Deltas are taken by the caller."""
    out = {}
    try:
        with urllib.request.urlopen(BASE + "/metrics", timeout=30) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                m = re.match(r"^([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+([-\d.eE+]+)$", line)
                if not m:
                    continue
                name, labels, val = m.group(1), m.group(2) or "", m.group(3)
                if "spec_decode" not in name and "num_preemptions" not in name \
                        and "gpu_cache_usage" not in name and "request_success" not in name:
                    continue
                pos = ""
                pm = re.search(r'position="(\d+)"', labels)
                if pm:
                    pos = "_pos" + pm.group(1)
                fm = re.search(r'finished_reason="([^"]+)"', labels)
                if fm:
                    pos = "_" + fm.group(1)
                try:
                    out[name + pos] = float(val)
                except ValueError:
                    pass
    except Exception as e:
        out["_error"] = f"{type(e).__name__}: {e}"
    return out


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def turn_payload(family, prompt, thinking):
    p = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 1024,
        "temperature": 1.0,
        "top_p": 0.95,
        "chat_template_kwargs": {"enable_thinking": bool(thinking)},
    }
    if family == "tool":
        p["tools"] = TOOLS
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=13.0)
    ap.add_argument("--out", default="./soak/turns.jsonl")
    ap.add_argument("--metrics-every", type=int, default=14,
                    help="scrape engine counters every N turns")
    ap.add_argument("--canary-every-min", type=float, default=30.0)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    mout = args.out.replace("turns.jsonl", "metrics.jsonl")
    cout = args.out.replace("turns.jsonl", "canary.jsonl")

    t_start = time.time()
    deadline = t_start + args.hours * 3600
    turn = 0
    last_canary = 0.0
    prev_metrics = None

    def emit(path, obj):
        with open(path, "a") as f:
            f.write(json.dumps(obj) + "\n")
            f.flush()
            os.fsync(f.fileno())

    emit(mout, {"event": "soak_start", "ts": time.time(),
                "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "base": BASE, "model": MODEL, "planned_hours": args.hours})

    while not STOP and time.time() < deadline:
        elapsed = time.time() - t_start

        # ---- burn canary on a wall-clock cadence ----
        if elapsed - last_canary >= args.canary_every_min * 60:
            last_canary = elapsed
            cp = {
                "model": MODEL,
                "messages": [{"role": "user", "content": CANARY_PROMPT}],
                "stream": True, "stream_options": {"include_usage": True},
                "max_tokens": 512, "temperature": 0.0, "seed": 20260728,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            st, ttft, dur, pieces, fin, usage, err = _post_stream("/v1/chat/completions", cp)
            text = "".join(pieces["content"])
            emit(cout, {
                "ts": time.time(), "elapsed_h": round(elapsed / 3600, 4),
                "turn": turn, "status": st, "ttft_s": ttft, "dur_s": round(dur, 3),
                "finish": fin, "usage": usage, "err": err,
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "head": text[:300], "tail": text[-200:],
                "reasoning_chars": len("".join(pieces["reasoning"])),
            })

        # ---- workload turn ----
        family = FAMILY_ORDER[turn % len(FAMILY_ORDER)]
        bank = FAMILIES[family]
        prompt = bank[(turn // len(FAMILY_ORDER)) % len(bank)]
        # thinking alternates on a period coprime with the family cycle (7),
        # so every family sees both settings evenly across the run.
        thinking = (turn // len(FAMILY_ORDER)) % 2 == 0

        st, ttft, dur, pieces, fin, usage, err = _post_stream(
            "/v1/chat/completions", turn_payload(family, prompt, thinking))
        content = "".join(pieces["content"])
        reasoning = "".join(pieces["reasoning"])
        ct = (usage or {}).get("completion_tokens")
        rec = {
            "turn": turn, "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_h": round(elapsed / 3600, 4),
            "family": family, "thinking": thinking,
            "prompt_sha8": hashlib.sha256(prompt.encode()).hexdigest()[:8],
            "prompt_chars": len(prompt),
            "status": st, "err": err,
            "ttft_s": round(ttft, 4) if ttft else None,
            "dur_s": round(dur, 3),
            "finish": fin, "usage": usage,
            "content_chars": len(content), "reasoning_chars": len(reasoning),
            "content_sha8": hashlib.sha256(content.encode()).hexdigest()[:8],
            "empty_content": len(content.strip()) == 0,
            "tool_calls_in_content": "<tool_call>" in content,
        }
        if ct and dur > 0:
            decode = dur - (ttft or 0)
            rec["tok_s"] = round(ct / decode, 3) if decode > 0 else None
            rec["completion_tokens"] = ct
        if st != 200 or err:
            rec["excerpt"] = content[:400]
        emit(args.out, rec)

        # ---- periodic instrumentation ----
        if turn % args.metrics_every == 0:
            m = scrape_metrics()
            row = {"ts": time.time(), "turn": turn,
                   "elapsed_h": round(elapsed / 3600, 4),
                   "cumulative": m}
            # DELTA acceptance: the drift signal. Cumulative ratio cannot drift
            # by construction once the denominator is large.
            if prev_metrics:
                d = {}
                for k, v in m.items():
                    if k.startswith("_"):
                        continue
                    pv = prev_metrics.get(k)
                    if isinstance(pv, float):
                        d[k] = round(v - pv, 3)
                row["delta"] = d
                draft = d.get("vllm:spec_decode_num_draft_tokens_total")
                acc = d.get("vllm:spec_decode_num_accepted_tokens_total")
                if draft and draft > 0 and acc is not None:
                    row["window_acceptance"] = round(acc / draft, 5)
            prev_metrics = {k: v for k, v in m.items() if isinstance(v, float)}
            try:
                row["free"] = os.popen(
                    "free -m | awk '/^Mem:/{print $2\",\"$3\",\"$7}'").read().strip()
                row["docker"] = os.popen(
                    "docker stats --no-stream --format '{{.MemUsage}}' nemotron_super"
                ).read().strip()
            except Exception as e:
                row["hostinfo_err"] = str(e)
            emit(mout, row)

        turn += 1

    emit(mout, {"event": "soak_end", "ts": time.time(),
                "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "turns": turn, "hours": round((time.time() - t_start) / 3600, 3),
                "stopped_early": bool(STOP)})


if __name__ == "__main__":
    main()
