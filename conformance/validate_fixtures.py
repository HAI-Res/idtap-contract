#!/usr/bin/env python3
"""Reference conformance runner + self-check for idtap-contract fixtures.

Two purposes:
  1. Self-check (run in this repo's CI): recompute every fixture's `expected`
     from the canonical rule and confirm the golden values are internally
     consistent — no real model involved.
  2. Template: each implementation repo copies these loops and swaps the
     reference computation for a call into ITS OWN model (see conformance/README.md).

Run:  python3 conformance/validate_fixtures.py
Exit 0 = all pass.
"""
import json, math, os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures")

SARGAM = ["sa", "re", "ga", "ma", "pa", "dha", "ni"]
YAMAN_RULESET = {
    "sa": True, "re": {"lowered": False, "raised": True},
    "ga": {"lowered": False, "raised": True}, "ma": {"lowered": False, "raised": True},
    "pa": True, "dha": {"lowered": False, "raised": True},
    "ni": {"lowered": False, "raised": True},
}


def close(a, b, rel):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


# --------------------------------------------------------------------------- pitch
def pitch_frequency(pj, ratios, fundamental):
    swara, raised, oct = pj["swara"], pj["raised"], pj["oct"]
    log_offset = pj.get("logOffset", 0)
    if swara in (0, 4):
        ratio = ratios[swara]
    else:
        ratio = ratios[swara][int(raised)]
    return fundamental * ratio * (2 ** oct) * (2 ** log_offset)


def check_pitch(fx):
    ctx = fx.get("context") or {}
    pj = fx["pitchJson"]
    ratios = ctx.get("ratios", pj.get("ratios"))
    fundamental = ctx.get("fundamental", pj.get("fundamental"))
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    got = pitch_frequency(pj, ratios, fundamental)
    want = fx["expected"]["frequency"]
    ok = close(got, want, rel) and close(math.log2(got), fx["expected"]["logFreq"], rel)
    return ok, f"{got:.4f}Hz"


# --------------------------------------------------------------------------- raga
def stratified_ratios(rule_set, ratios, tuning):
    out, ct = [], 0
    for s in SARGAM:
        val, base = rule_set[s], tuning[s]
        if isinstance(val, bool):
            out.append(ratios[ct] if val else base)
            ct += 1 if val else 0
        else:
            pair = []
            if val.get("lowered"):
                pair.append(ratios[ct]); ct += 1
            else:
                pair.append(base["lowered"])
            if val.get("raised"):
                pair.append(ratios[ct]); ct += 1
            else:
                pair.append(base["raised"])
            out.append(pair)
    return out


def flatten(x):
    for e in x:
        if isinstance(e, list):
            yield from e
        else:
            yield e


def check_raga(fx):
    rj = fx["ragaJson"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    got = stratified_ratios(YAMAN_RULESET, rj["ratios"], rj["tuning"])
    want = fx["expected"]["stratifiedRatios"]
    gflat, wflat = list(flatten(got)), list(flatten(want))
    ok = len(gflat) == len(wflat) and all(close(a, b, rel) for a, b in zip(gflat, wflat))
    ok = ok and fx["expected"]["fundamental"] == rj["fundamental"]
    return ok, f"fund={rj['fundamental']}Hz"


# --------------------------------------------------------------------------- trajectory
def check_trajectory(fx):
    ctx = fx.get("context") or {}
    tj = fx["trajectoryJson"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    got = []
    for p in tj["pitches"]:
        ratios = ctx.get("ratios", p.get("ratios"))
        fundamental = ctx.get("fundamental", p.get("fundamental"))
        got.append(pitch_frequency(p, ratios, fundamental))
    want = fx["expected"]["pitchFrequencies"]
    ok = len(got) == len(want) and all(close(a, b, rel) for a, b in zip(got, want))
    ok = ok and tj["id"] == fx["expected"]["id"]
    return ok, f"freqs={[round(x, 2) for x in got]}"


# --------------------------------------------------------------------------- phrase
def check_phrase(fx):
    ctx = fx.get("context")
    ph = fx["phraseJson"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    if ctx:
        ratios, fundamental = ctx["ratios"], ctx["fundamental"]
    else:
        # LEGACY fallback: derive context from the phrase's own embedded raga
        rg = ph["raga"]
        ratios = stratified_ratios(YAMAN_RULESET, rg["ratios"], rg["tuning"])
        fundamental = rg["fundamental"]
    got = []
    for row in ph["trajectoryGrid"]:
        for t in row:
            for p in t["pitches"]:
                got.append(pitch_frequency(p, ratios, fundamental))
    want = fx["expected"]["pitchFrequencies"]
    ok = len(got) == len(want) and all(close(a, b, rel) for a, b in zip(got, want))
    return ok, f"freqs={[round(x, 2) for x in got]}"


# --------------------------------------------------------------------------- piece
def check_piece(fx):
    pc = fx["pieceJson"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    rg = pc["raga"]
    # Piece is the ROOT: extract context from its raga and thread down.
    ratios = stratified_ratios(YAMAN_RULESET, rg["ratios"], rg["tuning"])
    fundamental = rg["fundamental"]
    got = []
    for track in pc["phraseGrid"]:
        for ph in track:
            for t in ph["trajectoryGrid"][0]:  # main string
                for p in t["pitches"]:
                    got.append(pitch_frequency(p, ratios, fundamental))
    want = fx["expected"]["allPitchFrequencies"]
    ok = len(got) == len(want) and all(close(a, b, rel) for a, b in zip(got, want))
    ok = ok and fundamental == fx["expected"]["fundamental"]
    return ok, f"{len(got)} pitches, fund={fundamental}Hz"


# --------------------------------------------------------------------------- structural
def check_structural(fx):
    """Supporting classes: no computation — verify the example instance has all
    required keys. Full shape validation is the JSON Schema's job."""
    inst = fx["instance"]
    req = fx["expected"]["requiredKeys"]
    missing = [k for k in req if k not in inst]
    ok = not missing
    return ok, ("ok" if ok else f"missing {missing}")


CHECKERS = {"pitch": check_pitch, "raga": check_raga,
            "trajectory": check_trajectory, "phrase": check_phrase,
            "piece": check_piece,
            "articulation": check_structural, "automation": check_structural,
            "chikari": check_structural, "group": check_structural,
            "meter": check_structural}


def main():
    total = fails = 0
    for entity, checker in CHECKERS.items():
        files = sorted(glob.glob(os.path.join(FIX, entity, "*.json")))
        files = [f for f in files if not f.endswith("index.json")]
        if not files:
            continue
        print(f"== {entity} ==")
        for path in files:
            fx = json.load(open(path))
            ok, info = checker(fx)
            total += 1
            fails += 0 if ok else 1
            print(f"  {'PASS' if ok else 'FAIL'}  {fx['name']}  {info}")
    print(f"\n{total - fails}/{total} fixtures consistent")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
