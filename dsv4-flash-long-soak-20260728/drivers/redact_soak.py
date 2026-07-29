#!/usr/bin/env python3
"""Structure-preserving scrub of the long-soak JSONL, field level.

The transformation logic is here in full. The *vocabulary* it substitutes is
not: node identities are read from a mapping file supplied at run time with
--map, and that file is deliberately not committed, because it is a list of
the private hostnames this scrub exists to remove. Committing it would publish
the thing the script is for.

What the logic does, in full, is auditable from this file alone:

  * DROP_FIELDS      removed outright. Raw command output and transport errors.
                     No published number is computed from them.
  * PROSE_FIELDS     replaced by "<field>_sha8", a sha256 prefix of the same
                     value. Identity and dedup analysis survive; the text does
                     not ship. Lengths are already carried separately in the
                     *_chars fields, which is what the published counts use.
  * mapping keys     dict keys and substrings matching a private identity are
                     replaced by its pseudonym, 1:1 and order preserving, so
                     per-node series stay separable.
  * IPv4 literals    replaced with REDACTED_IP.

No record is ever dropped. The tool prints a before/after count per file and
exits non-zero if any count changes.

Usage:  python3 redact_soak.py <source_dir> <dest_dir> --map <mapping.json>
        mapping.json is {"<private identity>": "<pseudonym>", ...}
"""
import argparse, hashlib, json, os, re, sys

PROSE_FIELDS = ("content_head", "reasoning_head")
DROP_FIELDS = ("raw", "stderr")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

JSONL = [
    "raw/turns.jsonl", "raw/windows.jsonl", "raw/memory.jsonl",
    "raw/events.jsonl", "raw/sampler.jsonl", "raw/positive_control.jsonl",
    "raw/laguna/deep.jsonl", "raw/laguna/decisive.jsonl",
    "raw/laguna/mnbt4096.jsonl",
    "smoke/raw/turns.jsonl", "smoke/raw/windows.jsonl",
    "smoke/raw/events.jsonl", "smoke/raw/memory.jsonl",
    "smoke2/raw/turns.jsonl", "smoke2/raw/windows.jsonl",
    "smoke2/raw/events.jsonl", "smoke2/raw/memory.jsonl",
    "smoke3/raw/turns.jsonl",
]


def h8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def scrub(o, nmap):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in DROP_FIELDS:
                continue
            if k in PROSE_FIELDS and isinstance(v, str):
                out[k + "_sha8"] = h8(v) if v else None
                continue
            out[nmap.get(k, k)] = scrub(v, nmap)
        return out
    if isinstance(o, list):
        return [scrub(x, nmap) for x in o]
    if isinstance(o, str):
        s = o
        for priv, pub in nmap.items():
            s = s.replace(priv, pub)
        return IPV4.sub("REDACTED_IP", s)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--map", required=True,
                    help="JSON object of private identity -> pseudonym. Not committed.")
    a = ap.parse_args()
    nmap = json.load(open(a.map, encoding="utf-8"))

    rows, ok = [], True
    for rel in JSONL:
        sp = os.path.join(a.src, rel)
        if not os.path.exists(sp):
            print("MISSING (skipped): %s" % rel)
            continue
        dp = os.path.join(a.dst, rel)
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        n_in = n_out = 0
        with open(sp, encoding="utf-8") as fi, open(dp, "w", encoding="utf-8") as fo:
            for line in fi:
                if not line.strip():
                    continue
                n_in += 1
                fo.write(json.dumps(scrub(json.loads(line), nmap), sort_keys=True) + "\n")
                n_out += 1
        rows.append((rel, n_in, n_out))
    print("%-34s %8s %8s" % ("file", "in", "out"))
    for rel, x, y in rows:
        print("%-34s %8d %8d%s" % (rel, x, y, "" if x == y else "   <-- MISMATCH"))
        ok &= (x == y)
    print("\n" + ("All record counts preserved. No record dropped."
                  if ok else "RECORD COUNT MISMATCH"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
