#!/usr/bin/env python3
"""Generate golden Piece conformance fixtures — the top-level integration test.

Piece is where raga context ORIGINATES: on load it extracts
(raga.stratifiedRatios, raga.fundamental) and threads them down
phraseGrid -> phrase -> trajectoryGrid -> trajectory -> pitch. The whole Yaman
bug chain starts here (Python Piece.from_json threads nothing).

Fixtures pin: full Piece JSON -> the flat list of every pitch frequency on the
main track (phraseGrid[0][*].trajectoryGrid[0][*].pitches[*]) — the same set
`all_pitches()` returns. If any level drops context, some frequency is wrong.

Run: python3 tools/generate_piece_fixtures.py
"""
import json, os, copy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fixtures", "piece")

SARGAM = ["sa", "re", "ga", "ma", "pa", "dha", "ni"]
TWELVE_TET = [1, [2 ** (1 / 12), 2 ** (2 / 12)], [2 ** (3 / 12), 2 ** (4 / 12)],
              [2 ** (5 / 12), 2 ** (6 / 12)], 2 ** (7 / 12),
              [2 ** (8 / 12), 2 ** (9 / 12)], [2 ** (10 / 12), 2 ** (11 / 12)]]
JUST = [1, [16 / 15, 9 / 8], [6 / 5, 5 / 4], [4 / 3, 45 / 32], 3 / 2,
        [8 / 5, 5 / 3], [16 / 9, 15 / 8]]
ET_TUNING = {"sa": 1.0, "re": {"lowered": 2 ** (1 / 12), "raised": 2 ** (2 / 12)},
             "ga": {"lowered": 2 ** (3 / 12), "raised": 2 ** (4 / 12)},
             "ma": {"lowered": 2 ** (5 / 12), "raised": 2 ** (6 / 12)}, "pa": 2 ** (7 / 12),
             "dha": {"lowered": 2 ** (8 / 12), "raised": 2 ** (9 / 12)},
             "ni": {"lowered": 2 ** (10 / 12), "raised": 2 ** (11 / 12)}}
YAMAN_12TET_RATIOS = [1, 2 ** (2 / 12), 2 ** (4 / 12), 2 ** (6 / 12),
                      2 ** (7 / 12), 2 ** (9 / 12), 2 ** (11 / 12)]
YAMAN_JUST_RATIOS = [1, 9 / 8, 5 / 4, 45 / 32, 3 / 2, 27 / 16, 15 / 8]


def pitch_freq(p, ratios, fundamental):
    s, r, o = p["swara"], p["raised"], p["oct"]
    ratio = ratios[s] if s in (0, 4) else ratios[s][int(r)]
    return fundamental * ratio * (2 ** o) * (2 ** p.get("logOffset", 0))


def stratified_from_flat(flat):
    """Yaman-structure stratified array from a flat present-pitch ratio list."""
    out, ct = [], 0
    for s in SARGAM:
        if s in ("sa", "pa"):
            out.append(flat[ct]); ct += 1
        else:
            out.append([ET_TUNING[s]["lowered"], flat[ct]]); ct += 1
    return out


def raga_json(fundamental, flat_ratios):
    tuning = copy.deepcopy(ET_TUNING)
    # overwrite present (raised/sa/pa) values from flat ratios
    ct = 0
    for s in SARGAM:
        if s in ("sa", "pa"):
            tuning[s] = flat_ratios[ct]; ct += 1
        else:
            tuning[s]["raised"] = flat_ratios[ct]; ct += 1
    return {"name": "Yaman", "fundamental": fundamental,
            "ratios": flat_ratios, "tuning": tuning}


def pj(swara, raised, oct, log_offset=0.0, embed=None):
    d = {"swara": swara, "raised": raised, "oct": oct, "logOffset": log_offset}
    if embed:
        d["ratios"], d["fundamental"] = embed
    return d


def traj(tid, pitches):
    n = len(pitches)
    return {"id": tid, "pitches": pitches, "durTot": 1.0,
            "durArray": [1.0 / n] * n if n > 1 else [1.0],
            "slope": 2.0, "num": 0, "uniqueId": f"t{tid}"}


def phrase(trajs, section_start=False):
    return {"durTot": float(len(trajs)), "durArray": [1.0] * len(trajs),
            "chikaris": {}, "startTime": 0.0, "trajectoryGrid": [trajs],
            "instrumentation": ["Sitar"], "groupsGrid": [[]],
            "categorizationGrid": [], "uniqueId": "phr",
            "adHocCategorizationGrid": [], "isSectionStart": section_start}


def piece_json(rj, phrases, embed_legacy=False):
    p = {
        "raga": rj,
        "phraseGrid": [phrases],
        "instrumentation": ["Sitar"],
        "durTot": float(sum(ph["durTot"] for ph in phrases)),
        "durArrayGrid": [[ph["durTot"] for ph in phrases]],
        "sectionCatGrid": [[]],
        "meters": [],
        "title": "Contract Fixture",
        "_id": "fixture000000000000000000",
        "explicitPermissions": {"edit": [], "view": [], "publicView": True},
        "excerptRange": None,
        "adHocSectionCatGrid": [[]],
        "assemblageDescriptors": [],
    }
    if embed_legacy:
        # legacy: embed raga on each phrase + durArray/sectionCategorization on piece
        p["durArray"] = p["durArrayGrid"][0]
        p["sectionCategorization"] = [[]]
        for ph in p["phraseGrid"][0]:
            ph["raga"] = copy.deepcopy(rj)
    return p


def all_pitch_freqs(phrases, ratios, fundamental):
    """Traverse EVERY string of the trajectory grid (polyphonic / dual-string),
    not just the main string [0]."""
    freqs = []
    for ph in phrases:
        for string in ph["trajectoryGrid"]:
            for t in string:
                for p in t["pitches"]:
                    freqs.append(pitch_freq(p, ratios, fundamental))
    return freqs


def phrase_dual(string0, string1, section_start=False):
    """A phrase whose trajectory grid has TWO strings (sitar main + jor, or
    sarangi main + second string)."""
    ph = phrase(string0, section_start)
    ph["trajectoryGrid"] = [string0, string1]
    return ph


def make(name, description, scenario, fundamental, flat_ratios, phrases,
         embed_legacy=False):
    rj = raga_json(fundamental, flat_ratios)
    pj_obj = piece_json(rj, copy.deepcopy(phrases), embed_legacy=embed_legacy)
    # Expected uses the raga's ACTUAL stratified ratios (absent lowered variants
    # fall back to ET tuning), not a standalone full-JI array — because a komal
    # pitch of a swara Yaman only has raised uses the ET-tuned lowered slot.
    ratios = stratified_from_flat(flat_ratios)
    freqs = all_pitch_freqs(phrases, ratios, fundamental)
    return {"name": name, "description": description, "scenario": scenario,
            "pieceJson": pj_obj,
            "expected": {"allPitchFrequencies": freqs, "fundamental": fundamental},
            "tolerance": {"rel": 1e-9}}


def demo_phrases():
    return [
        phrase([traj(0, [pj(0, True, 0)]),
                traj(1, [pj(2, False, 0), pj(4, True, 0)])], section_start=True),
        phrase([traj(6, [pj(6, True, -1), pj(1, True, 0)]),
                traj(0, [pj(0, True, 1)])]),
    ]


FIXTURES = [
    make("stripped-full-piece-nondefault-fundamental",
         "Full stripped Piece, Yaman 12-TET, fundamental 246Hz. Every pitch "
         "frequency must reflect 246Hz threaded from the piece raga — not the "
         "261.63 default. This is the end-to-end integration test for the bug.",
         "stripped", 246.0, YAMAN_12TET_RATIOS, demo_phrases()),
    make("stripped-full-piece-just-intonation",
         "Full stripped Piece, Yaman just-intonation ratios, fundamental 240Hz.",
         "stripped", 240.0, YAMAN_JUST_RATIOS, demo_phrases()),
    make("legacy-full-embedded",
         "Legacy Piece: raga embedded on each phrase, durArray + "
         "sectionCategorization present at piece level. Must still reconstruct "
         "all frequencies (fundamental 246Hz) via backward-compat paths.",
         "legacy", 246.0, YAMAN_12TET_RATIOS, demo_phrases(),
         embed_legacy=True),
    make("stripped-dual-string-polyphonic",
         "DUAL-STRING (polyphonic): one phrase with a main string (melody) and a "
         "second string (jor/drone), each with its own trajectories. Context must "
         "thread to BOTH strings. Yaman just-intonation, fundamental 240Hz.",
         "stripped", 240.0, YAMAN_JUST_RATIOS,
         [phrase_dual(
             [traj(0, [pj(0, True, 0)]), traj(1, [pj(2, False, 0), pj(4, True, 0)])],
             [traj(0, [pj(0, True, 1)]), traj(0, [pj(4, True, 1)])],
             section_start=True)]),
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
        n = len(fx["expected"]["allPitchFrequencies"])
        print(f"wrote {fx['name']}.json  {n} pitches, fund={fx['expected']['fundamental']}Hz")
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump({"entity": "piece", "fixtures": index}, f, indent=2)
        f.write("\n")
    print(f"\n{len(FIXTURES)} piece fixtures written")


if __name__ == "__main__":
    main()
