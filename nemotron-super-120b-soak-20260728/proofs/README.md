# Scan proofs

The maintainer-side scanners run over this bundle in CI on every push
(`.github/workflows/verify.yml`). Their verdicts are the gate; a failing scan
blocks the merge.

**The raw scanner output is deliberately not committed here.** Those reports
enumerate every pattern in the private vocabulary, including the private
hostnames, usernames and control-plane terms the scanners exist to find, one
per line with an `OK ... 0 hits` beside each. Publishing a clean scan report
would therefore publish the whole list of things that must never be published,
which is the exact failure the scan is meant to prevent. It was caught here by
the scanner refusing its own proof file.

What ships instead is the verdict, the check count and the CI job that
reproduces it.
