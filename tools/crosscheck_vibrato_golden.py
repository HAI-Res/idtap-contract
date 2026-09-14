#!/usr/bin/env python3
"""Cross-check the contract's vibrato fixtures against the TS reference golden.

The TS implementation (idtap-platform `Trajectory.id13`) is the reference; its
golden file pins 21- and 201-point renders per case. This script matches contract
fixtures to golden cases by input and reports the max relative error, so the
contract's hand-implemented formula and the reference cannot drift apart.

Run: python3 tools/crosscheck_vibrato_golden.py path/to/vibrato-v2-golden.json
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures", "trajectory")


def main(golden_path):
    g = json.load(open(golden_path))
    cases = g["cases"]
    fails = 0
    for fn in sorted(os.listdir(FIX)):
        if not fn.startswith("vib-"):
            continue
        fx = json.load(open(os.path.join(FIX, fn)))
        tj, exp = fx["trajectoryJson"], fx["expected"]
        match = None
        for c in cases:
            same = (c["durTot"] == tj["durTot"]
                    and c["input"]["pitches"][0]["swara"] == tj["pitches"][0]["swara"]
                    and c["input"]["pitches"][0]["oct"] == tj["pitches"][0]["oct"]
                    and all(math.isclose(c["vibObj"][k], exp["vibObj"][k], rel_tol=1e-12)
                            for k in c["vibObj"]))
            if same:
                match = c
                break
        if match is None:
            print(f"  ----  {fx['name']}: no golden case with the same inputs")
            continue
        assert g["xs21"] == exp["curveX"], "sample points differ"
        err = max(abs(a - b) / b for a, b in zip(exp["curveFrequencies"], match["values21"]))
        ok = err <= fx["tolerance"]["rel"]
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {fx['name']:40s} == {match['name']:28s} maxRelErr={err:.2e}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
