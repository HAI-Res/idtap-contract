#!/usr/bin/env python3
"""Reference conformance runner for idtap-contract Pitch fixtures.

Two purposes:
  1. Self-check: proves every golden fixture is internally consistent with the
     canonical frequency rule (run in this repo's CI).
  2. Template: each implementation repo copies this loop and replaces
     `reference_frequency(...)` with a call into ITS OWN model, e.g.
         p = Pitch.from_json(fx["pitchJson"], ratios=ctx_ratios, fundamental=ctx_fund)
         got = p.frequency
     then asserts against fx["expected"] with the same tolerance. That is the
     test that fails RED until the implementation threads raga context correctly.

Run:  python3 conformance/validate_fixtures.py
Exit code 0 = all pass.
"""
import json, math, os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(HERE, "..", "fixtures", "pitch")


def resolve_context(fx):
    """The core contract rule: threaded context wins; embedded (legacy) values
    are fallback only. Returns (ratios, fundamental) or raises if neither."""
    ctx = fx.get("context")
    pj = fx["pitchJson"]
    ratios = (ctx or {}).get("ratios", pj.get("ratios"))
    fundamental = (ctx or {}).get("fundamental", pj.get("fundamental"))
    if ratios is None or fundamental is None:
        raise ValueError(f"{fx['name']}: no ratios/fundamental in context or json")
    return ratios, fundamental


def reference_frequency(pj, ratios, fundamental):
    swara, raised, oct = pj["swara"], pj["raised"], pj["oct"]
    log_offset = pj.get("logOffset", 0)
    if swara in (0, 4):
        raised = True
        ratio = ratios[swara]
    else:
        ratio = ratios[swara][int(raised)]
    return fundamental * ratio * (2 ** oct) * (2 ** log_offset)


def close(a, b, rel):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


def main():
    files = sorted(glob.glob(os.path.join(FIXDIR, "*.json")))
    files = [f for f in files if not f.endswith("index.json")]
    failures = 0
    for path in files:
        with open(path) as f:
            fx = json.load(f)
        ratios, fundamental = resolve_context(fx)
        got = reference_frequency(fx["pitchJson"], ratios, fundamental)
        want = fx["expected"]["frequency"]
        rel = fx.get("tolerance", {}).get("rel", 1e-9)
        ok = close(got, want, rel)
        # also verify logFreq consistency
        ok = ok and close(math.log2(got), fx["expected"]["logFreq"], rel)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
            print(f"  {status}  {fx['name']}: got {got:.6f} want {want:.6f}")
        else:
            print(f"  {status}  {fx['name']}  ({fx['scenario']})  {got:.4f}Hz")
    print(f"\n{len(files) - failures}/{len(files)} fixtures consistent")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
