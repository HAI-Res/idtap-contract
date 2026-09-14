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
CONTRACT = os.path.join(HERE, "..", "contract.json")

# The contract version this runner was written against. Each implementation
# repo keeps the same kind of constant (see README "Versioning") and asserts it
# against contract.json in its conformance suite, so a bump that changes wire
# semantics fails CI in every client until the client is updated.
CONTRACT_VERSION = "0.2.0"

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
    # PROP-1: ruleSet is serialized; legacy fixtures fall back to Yaman.
    rule_set = rj.get("ruleSet", YAMAN_RULESET)
    got = stratified_ratios(rule_set, rj["ratios"], rj["tuning"])
    want = fx["expected"]["stratifiedRatios"]
    gflat, wflat = list(flatten(got)), list(flatten(want))
    ok = len(gflat) == len(wflat) and all(close(a, b, rel) for a, b in zip(gflat, wflat))
    ok = ok and fx["expected"]["fundamental"] == rj["fundamental"]
    return ok, f"fund={rj['fundamental']}Hz"


# --------------------------------------------------------------------------- trajectory
def clamp_offset(vert_offset, half_extent):
    if abs(vert_offset) > half_extent:
        return math.copysign(half_extent, vert_offset)
    return vert_offset


def heal_vib_obj(vib, dur_tot):
    """PROP-6 lossless v1 -> v2 heal: v1 is detected by `periods`; the four v1
    fields are coerced with Number() (stored strings are common) and `periods` is
    used as stored, no truncation."""
    if "periods" not in vib:
        return dict(vib)
    extent = float(vib["extent"])
    return {"rate": float(vib["periods"]) / dur_tot,
            "extentStart": extent, "extentEnd": extent,
            "vertOffset": float(vib["vertOffset"]),
            "phase": math.pi if vib["initUp"] else 0.0}


def vibrato_v2_attach(vib, dur_tot):
    """PROP-6 attach-at-extreme rule: P = rate*durTot (P = 1 when P < 1);
    extremes of cos(2 pi P x + phase) sit at x = (k - phase/pi) / (2P); x1 is the
    first with x1 >= 1/(4P), x2 the last with x2 <= 1 - 1/(4P); if x2 < x1 the two
    tapers meet at x1."""
    P = vib["rate"] * dur_tot
    if not (P >= 1):
        P = 1.0
    ph = vib["phase"] / math.pi
    x1 = (math.ceil(0.5 + ph) - ph) / (2 * P)
    x2 = (math.floor(2 * P - 0.5 + ph) - ph) / (2 * P)
    return P, x1, max(x1, x2)


def vibrato_v2(x, lf0, vib, dur_tot):
    """PROP-6 normative vibrato curve; returns Hz."""
    P, x1, x2 = vibrato_v2_attach(vib, dur_tot)

    def core(xx):
        A = (vib["extentStart"] + (vib["extentEnd"] - vib["extentStart"]) * xx) / 2
        return lf0 + clamp_offset(vib["vertOffset"], A) + A * math.cos(2 * math.pi * P * xx + vib["phase"])

    if x <= x1:
        y = lf0 + (core(x1) - lf0) * (1 - math.cos(math.pi * x / x1)) / 2
    elif x >= x2:
        s = core(x2)
        y = s + (lf0 - s) * (1 - math.cos(math.pi * (x - x2) / (1 - x2))) / 2
    else:
        y = core(x)
    return 2 ** y


def check_trajectory(fx):
    ctx = fx.get("context") or {}
    tj = fx["trajectoryJson"]
    exp = fx["expected"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    got = []
    for p in tj["pitches"]:
        ratios = ctx.get("ratios", p.get("ratios"))
        fundamental = ctx.get("fundamental", p.get("fundamental"))
        got.append(pitch_frequency(p, ratios, fundamental))
    want = exp["pitchFrequencies"]
    ok = len(got) == len(want) and all(close(a, b, rel) for a, b in zip(got, want))
    ok = ok and tj["id"] == exp["id"]
    info = f"freqs={[round(x, 2) for x in got]}"
    if "vibObj" not in tj:
        return ok, info
    # PROP-6b: canonical output carries vibObj only on id 13.
    ok = ok and exp["vibObjInCanonical"] == (tj["id"] == 13)
    if tj["id"] != 13:
        return ok, info + " vibObj ignored (id != 13)"
    # PROP-6: heal to v2, then re-derive the curve at the fixture's sample points.
    vib = heal_vib_obj(tj["vibObj"], tj["durTot"])
    ok = ok and set(vib) == {"rate", "extentStart", "extentEnd", "vertOffset", "phase"}
    ok = ok and all(close(vib[k], exp["vibObj"][k], rel) for k in vib)
    lf0 = math.log2(got[0])
    curve = [vibrato_v2(x, lf0, vib, tj["durTot"]) for x in exp["curveX"]]
    ok = ok and len(curve) == len(exp["curveFrequencies"]) and all(
        close(a, b, rel) for a, b in zip(curve, exp["curveFrequencies"]))
    P, x1, x2 = vibrato_v2_attach(vib, tj["durTot"])
    att = exp.get("attach", {})
    ok = ok and all(close(a, att[k], rel) for k, a in (("P", P), ("x1", x1), ("x2", x2)))
    return ok, info + f" rate={vib['rate']:.3f}Hz P={P:.3f} x1={x1:.3f} x2={x2:.3f} curve[{len(curve)}] ok"


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
        ratios = stratified_ratios(rg.get("ruleSet", YAMAN_RULESET), rg["ratios"], rg["tuning"])
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
    ratios = stratified_ratios(rg.get("ruleSet", YAMAN_RULESET), rg["ratios"], rg["tuning"])
    fundamental = rg["fundamental"]
    got = []
    for track in pc["phraseGrid"]:
        for ph in track:
            for string in ph["trajectoryGrid"]:  # ALL strings (polyphonic)
                for t in string:
                    if t.get("id") == 12:  # skip Silent trajs (string-sync)
                        continue
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


# --------------------------------------------------------------------------- meter
def check_meter(fx):
    """behavioral: derive each PulseStructure's proportional offsets from its
    pulses' realTimes (offset[i] = (realTime[i]-startTime-i*pulseDur)/pulseDur)
    and compare to expected. structural: fall back to the required-keys check."""
    if fx.get("scenario") != "behavioral":
        return check_structural(fx)
    mj = fx["meterJson"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    got = []
    for layer in mj["pulseStructures"]:
        for ps in layer:
            st, pd = ps["startTime"], ps["pulseDur"]
            got.append([(ps["pulses"][i]["realTime"] - st - i * pd) / pd
                        for i in range(ps["size"])])
    want = fx["expected"]["pulseStructureOffsets"]
    ok = len(got) == len(want) and all(
        len(g) == len(w) and all(close(a, b, rel) for a, b in zip(g, w))
        for g, w in zip(got, want))
    return ok, f"offsets={[[round(x, 3) for x in g] for g in got]}"


CHECKERS = {"pitch": check_pitch, "raga": check_raga,
            "trajectory": check_trajectory, "phrase": check_phrase,
            "piece": check_piece,
            "articulation": check_structural, "automation": check_structural,
            "chikari": check_structural, "group": check_structural,
            "meter": check_meter}


def check_contract_version():
    """The version assertion every client must mirror: contract.json `version`
    must equal the constant this runner was written against."""
    version = json.load(open(CONTRACT))["version"]
    ok = version == CONTRACT_VERSION
    print(f"== contract ==\n  {'PASS' if ok else 'FAIL'}  version {version} (expected {CONTRACT_VERSION})")
    return ok


def main():
    total = fails = 0
    version_ok = check_contract_version()
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
    print(f"\n{total - fails}/{total} fixtures consistent; contract version "
          f"{'OK' if version_ok else 'MISMATCH'}")
    sys.exit(1 if fails or not version_ok else 0)


if __name__ == "__main__":
    main()
