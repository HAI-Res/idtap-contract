#!/usr/bin/env python3
"""Generate golden Trajectory conformance fixtures.

Trajectory's contract-critical property: on load it threads (ratios, fundamental)
down to each Pitch, so every pitch frequency must be reconstructed correctly.
This is where the Yaman bug propagates (Python from_json currently drops context).
Fixtures also pin the stripped fields: `name` is DERIVED from `id`, `tags`
defaults to `[]`, `instrumentation` is inherited — none are in canonical output.

Run: python3 tools/generate_trajectory_fixtures.py
"""
import json, os

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
    return {
        "name": name,
        "description": description,
        "scenario": scenario,
        "trajectoryJson": traj,
        "context": ctx,
        "expected": {
            "id": traj_id,
            "durTot": dur_tot,
            "derivedName": NAMES[traj_id],
            "tagsDefault": [],
            "pitchFrequencies": freqs,
        },
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
]


def main():
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
