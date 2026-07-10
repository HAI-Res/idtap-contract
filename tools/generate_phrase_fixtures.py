#!/usr/bin/env python3
"""Generate golden Phrase conformance fixtures.

Phrase's contract-critical property: on load it threads (ratios, fundamental)
down through `trajectoryGrid` -> each Trajectory -> each Pitch. If no context is
passed but the phrase has an embedded `raga` (LEGACY), the phrase's own raga
supplies the fallback context (`r = ratios ?? phraseRaga.stratifiedRatios`).
Every reconstructed pitch frequency must match regardless.

Canonical form strips `raga`. Fixtures pin: Phrase JSON (+ context) -> the flat
list of all pitch frequencies across the trajectory grid.

Run: python3 tools/generate_phrase_fixtures.py
"""
import json, os, copy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fixtures", "phrase")

SARGAM = ["sa", "re", "ga", "ma", "pa", "dha", "ni"]
TWELVE_TET = [1, [2 ** (1 / 12), 2 ** (2 / 12)], [2 ** (3 / 12), 2 ** (4 / 12)],
              [2 ** (5 / 12), 2 ** (6 / 12)], 2 ** (7 / 12),
              [2 ** (8 / 12), 2 ** (9 / 12)], [2 ** (10 / 12), 2 ** (11 / 12)]]
JUST = [1, [16 / 15, 9 / 8], [6 / 5, 5 / 4], [4 / 3, 45 / 32], 3 / 2,
        [8 / 5, 5 / 3], [16 / 9, 15 / 8]]
YAMAN_RULESET = {"sa": True, "re": {"lowered": False, "raised": True},
                 "ga": {"lowered": False, "raised": True}, "ma": {"lowered": False, "raised": True},
                 "pa": True, "dha": {"lowered": False, "raised": True},
                 "ni": {"lowered": False, "raised": True}}
ET_TUNING = {"sa": 1.0, "re": {"lowered": 2 ** (1 / 12), "raised": 2 ** (2 / 12)},
             "ga": {"lowered": 2 ** (3 / 12), "raised": 2 ** (4 / 12)},
             "ma": {"lowered": 2 ** (5 / 12), "raised": 2 ** (6 / 12)}, "pa": 2 ** (7 / 12),
             "dha": {"lowered": 2 ** (8 / 12), "raised": 2 ** (9 / 12)},
             "ni": {"lowered": 2 ** (10 / 12), "raised": 2 ** (11 / 12)}}
YAMAN_12TET_RATIOS = [1, 2 ** (2 / 12), 2 ** (4 / 12), 2 ** (6 / 12),
                      2 ** (7 / 12), 2 ** (9 / 12), 2 ** (11 / 12)]


def pitch_freq(p, ratios, fundamental):
    s, r, o = p["swara"], p["raised"], p["oct"]
    ratio = ratios[s] if s in (0, 4) else ratios[s][int(r)]
    return fundamental * ratio * (2 ** o) * (2 ** p.get("logOffset", 0))


def stratified(ratios):
    """Yaman-structure stratified array from a flat 7-ratio list (present pitches
    are the 'raised' variants; absent lowered variants use ET tuning)."""
    out, ct = [], 0
    for s in SARGAM:
        val, base = YAMAN_RULESET[s], ET_TUNING[s]
        if isinstance(val, bool):
            out.append(ratios[ct]); ct += 1
        else:
            lowered = base["lowered"]  # not present in Yaman
            raised = ratios[ct]; ct += 1
            out.append([lowered, raised])
    return out


def pj(swara, raised, oct, log_offset=0.0, embed=None):
    d = {"swara": swara, "raised": raised, "oct": oct, "logOffset": log_offset}
    if embed:
        d["ratios"], d["fundamental"] = embed
    return d


def traj(tid, pitches, dur_tot=1.0):
    return {"id": tid, "pitches": pitches, "durTot": dur_tot,
            "durArray": [1.0 / len(pitches)] * len(pitches) if len(pitches) > 1 else [1.0],
            "slope": 2.0, "num": 0, "uniqueId": f"t{tid}"}


def phrase_base(grid):
    return {"durTot": 2.0, "durArray": [1.0, 1.0], "chikaris": {},
            "startTime": 0.0, "trajectoryGrid": grid, "instrumentation": ["Sitar"],
            "groupsGrid": [[]], "categorizationGrid": [], "uniqueId": "phr",
            "adHocCategorizationGrid": [], "isSectionStart": True}


def make(name, description, scenario, grid, ratios, fundamental, embed_raga=False):
    ph = phrase_base(copy.deepcopy(grid))
    ctx = None if embed_raga else {"ratios": ratios, "fundamental": fundamental}
    if embed_raga:
        ph["raga"] = {"name": "Yaman", "fundamental": fundamental,
                      "ratios": YAMAN_12TET_RATIOS, "tuning": copy.deepcopy(ET_TUNING)}
    freqs = []
    for row in grid:
        for t in row:
            for p in t["pitches"]:
                freqs.append(pitch_freq(p, ratios, fundamental))
    return {"name": name, "description": description, "scenario": scenario,
            "phraseJson": ph, "context": ctx,
            "expected": {"pitchFrequencies": freqs},
            "tolerance": {"rel": 1e-9}}


FIXTURES = [
    make("stripped-grid-context-threaded",
         "Stripped phrase; trajectoryGrid main string has two trajectories "
         "(Fixed sa, Bend ga->pa) at just intonation, fundamental 240Hz. All "
         "pitch freqs come from threaded context.",
         "stripped",
         [[traj(0, [pj(0, True, 0)]),
           traj(1, [pj(2, False, 0), pj(4, True, 0)])]],
         JUST, 240.0),
    make("legacy-embedded-raga-fallback",
         "Legacy phrase with an embedded raga (Yaman, 12-TET, fundamental 246Hz) "
         "and NO context passed. Pitch freqs must come from the phrase's own raga "
         "stratifiedRatios (the fallback path Python currently lacks).",
         "legacy",
         [[traj(0, [pj(0, True, 0)]),
           traj(2, [pj(6, True, -1), pj(1, True, 0)])]],
         TWELVE_TET, 246.0, embed_raga=True),
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
        json.dump({"entity": "phrase", "fixtures": index}, f, indent=2)
        f.write("\n")
    print(f"\n{len(FIXTURES)} phrase fixtures written")


if __name__ == "__main__":
    main()
