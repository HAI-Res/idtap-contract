#!/usr/bin/env python3
"""Generate golden Trajectory conformance fixtures.

Trajectory's contract-critical property: on load it threads (ratios, fundamental)
down to each Pitch, so every pitch frequency must be reconstructed correctly.
This is where the Yaman bug propagates (Python from_json currently drops context).
Fixtures also pin the stripped fields: `name` is DERIVED from `id`, `tags`
defaults to `[]`, `instrumentation` is inherited — none are in canonical output.

Vibrato (PROP-6): the `vib-*` fixtures pin the v2 `vibObj` semantics — the
lossless v1 -> v2 heal, the normative v2 curve (rate in Hz, linear extent ramp,
continuous phase, attach-at-extreme end rule), and PROP-6b (canonical form emits
`vibObj` only when id == 13). `vibrato_v1` below is a port of the pre-PROP-6 TS
`Trajectory.id13`; `vibrato_v2` hand-implements the PROP-6 rule. The generator
asserts the two agree on the `vib-v2-equals-v1-golden` sample points.

Run: python3 tools/generate_trajectory_fixtures.py
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fixtures", "trajectory")

TWELVE_TET = [
    1, [2 ** (1 / 12), 2 ** (2 / 12)], [2 ** (3 / 12), 2 ** (4 / 12)],
    [2 ** (5 / 12), 2 ** (6 / 12)], 2 ** (7 / 12),
    [2 ** (8 / 12), 2 ** (9 / 12)], [2 ** (10 / 12), 2 ** (11 / 12)],
]
JUST = [1, [16 / 15, 9 / 8], [6 / 5, 5 / 4], [4 / 3, 45 / 32], 3 / 2,
        [8 / 5, 5 / 3], [16 / 9, 15 / 8]]

# id -> name (derived, not serialized in canonical form)
NAMES = ['Fixed', 'Bend: Simple', 'Bend: Sloped Start', 'Bend: Sloped End',
         'Bend: Ladle', 'Bend: Reverse Ladle', 'Bend: Simple Multiple',
         'Krintin', 'Krintin Slide', 'Krintin Slide Hammer',
         'Dense Krintin Slide Hammer', 'Slide', 'Silent', 'Vibrato']


def pitch_freq(pj, ratios, fundamental):
    s, r, o = pj["swara"], pj["raised"], pj["oct"]
    lo = pj.get("logOffset", 0)
    ratio = ratios[s] if s in (0, 4) else ratios[s][int(r)]
    return fundamental * ratio * (2 ** o) * (2 ** lo)


# --------------------------------------------------------------------------- vibrato
CURVE_X = [round(i / 20, 2) for i in range(21)]   # 21 sample points, x in [0, 1]


def clamp_offset(vert_offset, half_extent):
    if abs(vert_offset) > half_extent:
        return math.copysign(half_extent, vert_offset)
    return vert_offset


def vibrato_v1(x, lf0, vib):
    """Pre-PROP-6 TS `Trajectory.id13` (v1: periods, vertOffset, initUp, extent).
    Kept only to prove the v2 formula reproduces it; not a contract rule."""
    periods = float(vib["periods"])
    extent = float(vib["extent"])
    vo = clamp_offset(float(vib["vertOffset"]), extent / 2)
    init_up = 1 if vib["initUp"] else 0

    def raw(xx):
        return math.cos(xx * 2 * math.pi * periods + init_up * math.pi)

    def middle(xx):
        return 2 ** (raw(xx) * extent / 2 + vo + lf0)

    half = 1 / (2 * periods)
    out = raw(x)
    if x < half:
        start, end = lf0, math.log2(middle(half))
    elif x > 1 - half:
        start, end = math.log2(middle(1 - half)), lf0
    else:
        return middle(x)
    mid = (end + start) / 2
    ext = abs(end - start) / 2
    return 2 ** (out * ext + mid)


def vibrato_v2_attach(vib, dur_tot):
    """(P, x1, x2) per PROP-6: P = rate*durTot (>= 1); x1 = first extreme of
    cos(2*pi*P*x + phase) at least a quarter period in; x2 = the last extreme at
    least a quarter period before the end. Extremes sit at x = (k - phase/pi)/(2P)."""
    P = vib["rate"] * dur_tot
    if not (P >= 1):
        P = 1.0
    ph = vib["phase"] / math.pi
    k1 = math.ceil(0.5 + ph)
    k2 = math.floor(2 * P - 0.5 + ph)
    x1 = (k1 - ph) / (2 * P)
    x2 = (k2 - ph) / (2 * P)
    if x2 < x1:
        x2 = x1
    return P, x1, x2


def vibrato_v2(x, lf0, vib, dur_tot):
    """PROP-6 normative curve. Returns frequency in Hz (2 ** y(x))."""
    P, x1, x2 = vibrato_v2_attach(vib, dur_tot)

    def core(xx):
        A = (vib["extentStart"] + (vib["extentEnd"] - vib["extentStart"]) * xx) / 2
        return lf0 + clamp_offset(vib["vertOffset"], A) + A * math.cos(2 * math.pi * P * xx + vib["phase"])

    if x <= x1:
        end = core(x1)
        y = lf0 + (end - lf0) * (1 - math.cos(math.pi * x / x1)) / 2
    elif x >= x2:
        start = core(x2)
        y = start + (lf0 - start) * (1 - math.cos(math.pi * (x - x2) / (1 - x2))) / 2
    else:
        y = core(x)
    return 2 ** y


def heal_vib_obj(vib, dur_tot):
    """PROP-6 lossless v1 -> v2 heal. v1 is detected by the presence of `periods`.
    All four v1 fields are coerced with Number() (old sliders stored strings) and
    `periods` is used as stored — no truncation."""
    if "periods" not in vib:
        return dict(vib)
    extent = float(vib["extent"])
    return {
        "rate": float(vib["periods"]) / dur_tot,
        "extentStart": extent,
        "extentEnd": extent,
        "vertOffset": float(vib["vertOffset"]),
        "phase": math.pi if vib["initUp"] else 0.0,
    }


def pj(swara, raised, oct, log_offset=0.0, embed=None):
    d = {"swara": swara, "raised": raised, "oct": oct, "logOffset": log_offset}
    if embed:
        d["ratios"], d["fundamental"] = embed
    return d


def make(name, description, scenario, traj_id, pitches, dur_tot, dur_array,
         ratios, fundamental, extra=None):
    embedded = scenario == "legacy"
    ctx = None if embedded else {"ratios": ratios, "fundamental": fundamental}
    traj = {
        "id": traj_id,
        "pitches": [pj(**{**p, "embed": (ratios, fundamental) if embedded else None})
                    for p in pitches],
        "durTot": dur_tot,
        "durArray": dur_array,
        "slope": 2.0,
        "num": 0,
        "uniqueId": f"fixture-{name}",
    }
    if extra:
        traj.update(extra)
    freqs = [pitch_freq(t, ratios, fundamental) for t in traj["pitches"]]
    expected = {
        "id": traj_id,
        "durTot": dur_tot,
        "derivedName": NAMES[traj_id],
        "tagsDefault": [],
        "pitchFrequencies": freqs,
    }
    if "vibObj" in traj:
        # PROP-6b: canonical output carries vibObj only on id 13.
        expected["vibObjInCanonical"] = traj_id == 13
        if traj_id == 13:
            vib = heal_vib_obj(traj["vibObj"], dur_tot)
            lf0 = math.log2(freqs[0])
            P, x1, x2 = vibrato_v2_attach(vib, dur_tot)
            expected["vibObj"] = vib
            expected["curveX"] = CURVE_X
            expected["curveFrequencies"] = [vibrato_v2(x, lf0, vib, dur_tot) for x in CURVE_X]
            expected["attach"] = {"P": P, "x1": x1, "x2": x2}
    return {
        "name": name,
        "description": description,
        "scenario": scenario,
        "trajectoryJson": traj,
        "context": ctx,
        "expected": expected,
        "tolerance": {"rel": 1e-9},
    }


FIXTURES = [
    make("stripped-fixed-single-pitch",
         "id=0 (Fixed), single sa pitch, Yaman fundamental 246Hz. Pitch freq must "
         "be reconstructed from threaded context (not the 261.63 default).",
         "stripped", 0, [dict(swara=0, raised=True, oct=0)], 1.0, [1.0],
         TWELVE_TET, 246.0),
    make("stripped-bend-two-pitches-just",
         "id=1 (Bend), ga-komal -> pa, just-intonation, fundamental 240Hz. Both "
         "pitch frequencies must reflect threaded JUST ratios, not 12-TET.",
         "stripped", 1, [dict(swara=2, raised=False, oct=0),
                         dict(swara=4, raised=True, oct=0)],
         2.0, [0.5, 0.5], JUST, 240.0),
    make("stripped-logoffset-pitch",
         "id=6 with a microtonal logOffset pitch, fundamental 246Hz",
         "stripped", 6, [dict(swara=6, raised=True, oct=-1, log_offset=0.1),
                         dict(swara=0, raised=True, oct=0)],
         1.5, [0.7, 0.3], TWELVE_TET, 246.0),
    make("legacy-embedded-with-stripped-fields",
         "Legacy trajectory: name/instrumentation/tags present AND ratios/"
         "fundamental embedded in pitches, no context threaded. Must still "
         "reconstruct correct frequencies; stripped fields ignored on canonical out.",
         "legacy", 3, [dict(swara=2, raised=True, oct=0),
                       dict(swara=5, raised=False, oct=1)],
         2.0, [0.5, 0.5], TWELVE_TET, 246.0,
         extra={"name": "Bend: Sloped End", "instrumentation": "Sitar",
                "tags": ["legacy-annotation"]}),
    make("sub-objects-articulations-automation",
         "Trajectory carrying articulations (pluck w/ stroke at 0.00) AND an "
         "automation envelope. Both sub-objects must round-trip through from_json "
         "(idtap-contract E).",
         "stripped", 0, [dict(swara=0, raised=True, oct=0)], 1.0, [1.0],
         TWELVE_TET, 246.0,
         extra={"articulations": {"0.00": {"name": "pluck", "stroke": "d"}},
                "automation": {"values": [{"normTime": 0.0, "value": 1.0},
                                          {"normTime": 0.5, "value": 0.6},
                                          {"normTime": 1.0, "value": 0.9}]}}),
    make("hygiene-null-durarray",
         "durArray explicitly null (hygiene F): must load without error and "
         "reconstruct pitch frequencies from context.",
         "stripped", 0, [dict(swara=0, raised=True, oct=0)], 1.0, None,
         TWELVE_TET, 246.0),
]

# D: enumerate every trajectory id 0-13 (skip 11 == 7). Bend ids 4-10 take 2
# pitches; others take 1. 12=Silent, 13=Vibrato are the special ones.
# Minimum pitch count per id (derived from the constructor's starts[N] usage):
# krintin-slide variants need more segments — id 8→3, id 9→4, id 10→6.
_ID_MIN_PITCHES = {8: 3, 9: 4, 10: 6}
for _tid in range(14):
    if _tid == 11:
        continue
    _n = _ID_MIN_PITCHES.get(_tid, 2 if 4 <= _tid <= 10 else 1)
    _pitches = [dict(swara=s, raised=True, oct=0) for s in range(_n)]
    _durarr = [1.0 / _n] * _n if _n > 1 else [1.0]
    FIXTURES.append(make(
        f"enum-id-{_tid:02d}-{NAMES[_tid].split(':')[0].replace(' ', '-').lower()}",
        f"Trajectory id={_tid} ({NAMES[_tid]}), {_n} pitch(es), 12-TET 246Hz.",
        "stripped", _tid, _pitches, 1.0, _durarr, TWELVE_TET, 246.0))


# PROP-6 vibrato fixtures. Inputs mirror idtap-platform's TS golden
# (src/ts/tests/fixtures/vibrato-v2-golden.json) so the two can be cross-checked.
_GA = [dict(swara=2, raised=True, oct=0)]
_V2_DEFAULT = {"rate": 5.5, "extentStart": 0.05, "extentEnd": 0.05,
               "vertOffset": 0.0, "phase": math.pi}

FIXTURES += [
    make("vib-v1-legacy-heals",
         "LEGACY v1 vibObj {periods, vertOffset, initUp, extent} on a legacy "
         "(embedded-ratios) id-13 trajectory. Must heal losslessly to v2: rate = "
         "periods/durTot (8/2 = 4 Hz), extentStart = extentEnd = extent, phase = pi "
         "for initUp true; the curve must equal the v1 render (PROP-6).",
         "legacy", 13, _GA, 2.0, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"periods": 8, "vertOffset": 0.0, "initUp": True, "extent": 0.05}}),
    make("vib-v1-legacy-string-fields-heals",
         "Real stored shape (Babul Mora, post-#887: stripped pitches + v1 vibObj): the "
         "old sliders stored periods/extent as STRINGS and periods is non-integer "
         "(3.5). The heal coerces with Number() and uses periods as-is (no "
         "truncation): rate = 3.5/0.474 Hz (PROP-6).",
         "stripped", 13, _GA, 0.474, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"periods": "3.5", "vertOffset": 0.0209, "initUp": True, "extent": "0.055"}}),
    make("vib-v2-equals-v1-golden",
         "THE LOSSLESS PROOF: a v2 vibObj with equal extents, integer cycle count "
         "(P = 4 Hz * 2 s = 8) and phase pi is rendered at 21 sample points; the "
         "values equal the v1 formula for {periods: 8, initUp: true, extent: 0.05, "
         "vertOffset: 0} term for term (PROP-6).",
         "stripped", 13, _GA, 2.0, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"rate": 4.0, "extentStart": 0.05, "extentEnd": 0.05,
                           "vertOffset": 0.0, "phase": math.pi}}),
    make("vib-v2-equals-v1-golden-phase0-offset",
         "Second lossless proof: phase 0 (v1 initUp false), non-zero vertOffset "
         "(0.01), P = 1.5 Hz * 2 s = 3. Equals v1 {periods: 3, initUp: false, "
         "extent: 0.08, vertOffset: 0.01} (PROP-6).",
         "stripped", 13, _GA, 2.0, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"rate": 1.5, "extentStart": 0.08, "extentEnd": 0.08,
                           "vertOffset": 0.01, "phase": 0.0}}),
    make("vib-v2-ramp",
         "v2 extent ramp: extentStart 0 -> extentEnd 0.08 (0 -> 96 c) over 2 s at "
         "5.5 Hz, phase pi; vertOffset 0.01 is clamped to +-A(x) so it fades in with "
         "the ramp (PROP-6).",
         "stripped", 13, _GA, 2.0, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"rate": 5.5, "extentStart": 0.0, "extentEnd": 0.08,
                           "vertOffset": 0.01, "phase": math.pi}}),
    make("vib-v2-noninteger-cycles",
         "v2 with a non-integer cycle count (P = 3.7 Hz * 0.55 s = 2.035) and an "
         "arbitrary phase (1.3 rad): x1 is the first cosine extreme >= 1/(4P), x2 the "
         "last <= 1 - 1/(4P); raised-cosine tapers on [0, x1] and [x2, 1] attach the "
         "curve to logFreqs[0]. Sample points cover both tapers (PROP-6).",
         "stripped", 13, [dict(swara=4, raised=True, oct=-1)], 0.55, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"rate": 3.7, "extentStart": 0.06, "extentEnd": 0.03,
                           "vertOffset": -0.005, "phase": 1.3}}),
    make("vib-v2-subcycle",
         "v2 with fewer than one cycle (P = 1 Hz * 0.3 s = 0.3 < 1): computed with "
         "P = 1, the stored rate is untouched (PROP-6).",
         "stripped", 13, [dict(swara=0, raised=True, oct=0)], 0.3, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": {"rate": 1.0, "extentStart": 0.05, "extentEnd": 0.05,
                           "vertOffset": 0.0, "phase": math.pi / 2}}),
    make("canonical-omits-vibobj-for-non-13",
         "PROP-6b: a non-13 trajectory (id 0) carrying a vibObj must load (the "
         "field is ignored) and its CANONICAL output must NOT contain vibObj — "
         "vibObj is emitted only when id == 13.",
         "stripped", 0, [dict(swara=0, raised=True, oct=0)], 1.0, [1.0], TWELVE_TET, 246.0,
         extra={"vibObj": dict(_V2_DEFAULT)}),
]


def _assert_lossless():
    """The generator's own proof that v2 reproduces v1 where the spec says it must."""
    pairs = {
        "vib-v2-equals-v1-golden": {"periods": 8, "vertOffset": 0.0, "initUp": True, "extent": 0.05},
        "vib-v2-equals-v1-golden-phase0-offset": {"periods": 3, "vertOffset": 0.01, "initUp": False, "extent": 0.08},
        "vib-v1-legacy-heals": {"periods": 8, "vertOffset": 0.0, "initUp": True, "extent": 0.05},
        "vib-v1-legacy-string-fields-heals": {"periods": "3.5", "vertOffset": 0.0209, "initUp": True, "extent": "0.055"},
    }
    by_name = {fx["name"]: fx for fx in FIXTURES}
    for name, v1 in pairs.items():
        fx = by_name[name]
        lf0 = math.log2(fx["expected"]["pitchFrequencies"][0])
        fx["expected"]["v1Equivalent"] = v1
        if float(v1["periods"]) != int(float(v1["periods"])):
            continue  # non-integer periods: v1 end taper is not an extreme; no equality claim
        for x, want in zip(CURVE_X, fx["expected"]["curveFrequencies"]):
            got = vibrato_v1(x, lf0, v1)
            assert abs(got - want) <= 1e-9 * want, (name, x, got, want)
    print("lossless check: v2 == v1 on integer-P, phase in {0, pi} fixtures")


def main():
    _assert_lossless()
    os.makedirs(OUT, exist_ok=True)
    index = []
    for fx in FIXTURES:
        with open(os.path.join(OUT, fx["name"] + ".json"), "w") as f:
            json.dump(fx, f, indent=2)
            f.write("\n")
        index.append({"name": fx["name"], "scenario": fx["scenario"],
                      "description": fx["description"]})
        print(f"wrote {fx['name']}.json  freqs={[round(x,2) for x in fx['expected']['pitchFrequencies']]}")
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump({"entity": "trajectory", "fixtures": index}, f, indent=2)
        f.write("\n")
    print(f"\n{len(FIXTURES)} trajectory fixtures written")


if __name__ == "__main__":
    main()
