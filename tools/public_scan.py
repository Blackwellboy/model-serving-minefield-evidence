#!/usr/bin/env python3
"""Public-surface scan for this repository.

A portable subset of the maintainer-side scanners, committed so the check runs
in CI on a clean runner. The maintainer-side private scanners run in addition
before every publish; this is the part that can live in public without the
report itself enumerating the private vocabulary.

Exit 0 clean, 1 on any hit.
"""
import os, re, sys

CHECKS = [
    ("ipv4 literal", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("private LAN 192.168", re.compile(r"192\.168\.\d")),
    ("tailnet 100.x", re.compile(r"\b100\.(?:\d{1,3})\.(?:\d{1,3})\.\d{1,3}\b")),
    # patterns are assembled rather than written literally: a scanner whose
    # own source contains the strings it hunts fails its own check.
    ("home path", re.compile("/hom" + r"e/[A-Za-z0-9_.-]+")),
    ("ssh transport error", re.compile(r"ssh: connect to host")),
    ("bearer or api token", re.compile(r"(?:ghp|gho|github_pat|sk-ant|sk-proj|hf_)[A-Za-z0-9_-]{8,}")),
    ("private key header", re.compile(r"-{5}BEGIN [A-Z ]*PRIVATE KEY")),
    ("aws key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("em/en/fig dash", re.compile("[\u2012-\u2015]")),
]
SKIP_DIRS = {".git", "__pycache__"}
SKIP_FILES = {"public_scan.py"}

def main(root):
    hits = 0
    scanned = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f in SKIP_FILES:
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            try:
                text = open(p, encoding="utf-8", errors="strict").read()
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            for label, rx in CHECKS:
                for m in rx.finditer(rel + "\n" + text):
                    print("HIT  [%s] %s: %r" % (label, rel, m.group(0)[:60]))
                    hits += 1
                    break
    print("\nscanned %d files, %d checks" % (scanned, len(CHECKS)))
    if hits:
        print("PUBLIC SCAN: %d hit(s). DO NOT PUBLISH." % hits)
        return 1
    print("PUBLIC SCAN: CLEAN")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
