#!/usr/bin/env python3
"""Generate golden Pitch conformance fixtures for idtap-contract.

The fixtures are language-neutral: each carries an input Pitch JSON, the raga
CONTEXT (ratios + fundamental) that must be threaded in on load, and the exact
expected derived values. Any conforming implementation (TS or Python) must
reproduce `expected` from (pitch_json + context).

Run:  python3 tools/generate_pitch_fixtures.py
Writes: fixtures/pitch/*.json  and  fixtures/pitch/index.json

The frequency rule (identical in pitch.ts and pitch.py):
    ratio = ratios[swara]                 if swara in (0, 4)   # sa, pa
    ratio = ratios[swara][int(raised)]    otherwise
    frequency = fundamental * ratio * 2**oct * 2**logOffset
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fixtures", "pitch")

# 12-TET stratified ratios (the Pitch constructor default)
TWELVE_TET = [
    1,
    [2 ** (1 / 12), 2 ** (2 / 12)],
    [2 ** (3 / 12), 2 ** (4 / 12)],
    [2 ** (5 / 12), 2 ** (6 / 12)],
    2 ** (7 / 12),
    [2 ** (8 / 12), 2 ** (9 / 12)],
    [2 ** (10 / 12), 2 ** (11 / 12)],
]

# A just-intonation stratified set — deliberately NON-12-TET so a fixture can
# catch an implementation that ignores threaded ratios and uses the default.
JUST = [
    1,
    [16 / 15, 9 / 8],
    [6 / 5, 5 / 4],
    [4 / 3, 45 / 32],
    3 / 2,
    [8 / 5, 5 / 3],
    [16 / 9, 15 / 8],
]

SARGAM = ["sa", "re", "ga", "ma", "pa", "dha", "ni"]


def ratio_for(ratios, swara, raised):
    if swara in (0, 4):
        return ratios[swara]
    return ratios[swara][int(raised)]


def numbered_pitch(swara, raised, oct):
    base = {0: 0, 1: 1, 2: 3, 3: 5, 4: 7, 5: 8, 6: 10}[swara]
    if swara in (0, 4):
        return oct * 12 + base
    return oct * 12 + base + int(raised)


def derive(swara, raised, oct, log_offset, ratios, fundamental):
    ratio = ratio_for(ratios, swara, raised)
    freq = fundamental * ratio * (2 ** oct) * (2 ** log_offset)
    np = numbered_pitch(swara, raised, oct)
    chroma = np % 12
    while chroma < 0:
        chroma += 12
    letter = SARGAM[swara][0]
    if swara in (0, 4) or raised:
        letter = letter.upper()
    return {
        "frequency": freq,
        "logFreq": math.log2(freq),
        "numberedPitch": np,
        "chroma": chroma,
        "sargamLetter": letter,
    }


def make(name, description, scenario, swara, raised, oct, log_offset,
         ratios, fundamental, embed_context):
    """embed_context=True => legacy: ratios+fundamental live IN the pitch json,
    context is null. False => stripped: context supplied separately."""
    pitch_json = {"swara": swara, "raised": raised, "oct": oct,
                  "logOffset": log_offset}
    if embed_context:
        pitch_json["ratios"] = ratios
        pitch_json["fundamental"] = fundamental
        context = None
    else:
        context = {"ratios": ratios, "fundamental": fundamental}
    return {
        "name": name,
        "description": description,
        "scenario": scenario,
        "pitchJson": pitch_json,
        "context": context,
        "expected": derive(swara, raised, oct, log_offset, ratios, fundamental),
        "tolerance": {"rel": 1e-9},
    }


FIXTURES = [
    make("stripped-12tet-sa", "sa in 12-TET at default fundamental (baseline)",
         "stripped", 0, True, 0, 0.0, TWELVE_TET, 261.63, False),
    make("stripped-12tet-re-raised", "re raised, 12-TET, default fundamental",
         "stripped", 1, True, 0, 0.0, TWELVE_TET, 261.63, False),
    # --- THE BUG CASE: non-default fundamental, stripped ---
    make("stripped-nondefault-fundamental-ga-komal",
         "ga komal, oct+1, fundamental 246Hz (Yaman-like). If an impl fails to "
         "thread the fundamental it uses 261.63 and gets the WRONG frequency.",
         "stripped", 2, False, 1, 0.0, TWELVE_TET, 246.0, False),
    # --- non-12-TET ratios, stripped ---
    make("stripped-just-intonation-ga",
         "ga raised with JUST-INTONATION ratios (5/4), fundamental 246Hz. "
         "Catches an impl that ignores threaded ratios and uses 12-TET.",
         "stripped", 2, True, 0, 0.0, JUST, 246.0, False),
    make("stripped-just-intonation-pa",
         "pa (single-ratio swara) just-intonation 3/2, fundamental 220Hz",
         "stripped", 4, True, -1, 0.0, JUST, 220.0, False),
    # --- microtonal logOffset ---
    make("stripped-logoffset-ni",
         "ni raised, oct-1, logOffset 0.15 (microtonal bend), fundamental 246Hz",
         "stripped", 6, True, -1, 0.15, TWELVE_TET, 246.0, False),
    # --- legacy: ratios+fundamental embedded, no context threaded ---
    make("legacy-embedded-ga-komal",
         "Legacy JSON with ratios+fundamental embedded in the pitch (no context "
         "threaded). Must still compute the correct frequency (backward compat).",
         "legacy", 2, False, 1, 0.0, TWELVE_TET, 246.0, True),
    make("legacy-embedded-just-pa",
         "Legacy embedded just-intonation pa, fundamental 220Hz",
         "legacy", 4, True, 0, 0.0, JUST, 220.0, True),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for fx in FIXTURES:
        path = os.path.join(OUT, fx["name"] + ".json")
        with open(path, "w") as f:
            json.dump(fx, f, indent=2)
            f.write("\n")
        index.append({"name": fx["name"], "scenario": fx["scenario"],
                      "description": fx["description"]})
        print(f"wrote {fx['name']}.json  freq={fx['expected']['frequency']:.4f}Hz")
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump({"entity": "pitch", "fixtures": index}, f, indent=2)
        f.write("\n")
    print(f"\n{len(FIXTURES)} fixtures + index written to fixtures/pitch/")


if __name__ == "__main__":
    main()
