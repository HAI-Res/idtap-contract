#!/usr/bin/env python3
"""Generate golden Raga conformance fixtures for idtap-contract.

Raga is the SOURCE OF TRUTH for the (stratifiedRatios, fundamental) context that
gets threaded into every Pitch. These fixtures pin:  Raga JSON -> stratifiedRatios
+ fundamental. A conforming implementation must reproduce `expected` from the
serialized {name, fundamental, ratios, tuning}.

IMPORTANT: `ruleSet` is NOT serialized; both implementations default it to Yaman
on load. These fixtures therefore all use the Yaman rule set (the common case).
Non-Yaman ragas are affected by the divergences noted in DIVERGENCES.md and are
intentionally out of scope until those are resolved.

Run:  python3 tools/generate_raga_fixtures.py
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fixtures", "raga")

SARGAM = ["sa", "re", "ga", "ma", "pa", "dha", "ni"]

# Yaman rule set (the serialization default in both TS and Python)
YAMAN_RULESET = {
    "sa": True,
    "re": {"lowered": False, "raised": True},
    "ga": {"lowered": False, "raised": True},
    "ma": {"lowered": False, "raised": True},
    "pa": True,
    "dha": {"lowered": False, "raised": True},
    "ni": {"lowered": False, "raised": True},
}

ET_TUNING = {
    "sa": 2 ** (0 / 12),
    "re": {"lowered": 2 ** (1 / 12), "raised": 2 ** (2 / 12)},
    "ga": {"lowered": 2 ** (3 / 12), "raised": 2 ** (4 / 12)},
    "ma": {"lowered": 2 ** (5 / 12), "raised": 2 ** (6 / 12)},
    "pa": 2 ** (7 / 12),
    "dha": {"lowered": 2 ** (8 / 12), "raised": 2 ** (9 / 12)},
    "ni": {"lowered": 2 ** (10 / 12), "raised": 2 ** (11 / 12)},
}

# 12-TET Yaman ratios array (present pitches in rule-set key order:
# sa, re-raised, ga-raised, ma-raised, pa, dha-raised, ni-raised)
YAMAN_12TET_RATIOS = [
    1, 2 ** (2 / 12), 2 ** (4 / 12), 2 ** (6 / 12),
    2 ** (7 / 12), 2 ** (9 / 12), 2 ** (11 / 12),
]
# A Yaman with just-intonation ratios for its (raised) present pitches
YAMAN_JUST_RATIOS = [1, 9 / 8, 5 / 4, 45 / 32, 3 / 2, 27 / 16, 15 / 8]


def num_pitches(rule_set):
    n = 0
    for v in rule_set.values():
        if isinstance(v, bool):
            n += 1 if v else 0
        else:
            n += int(bool(v.get("lowered"))) + int(bool(v.get("raised")))
    return n


def build_tuning(rule_set, ratios):
    """Mirror the constructor: overwrite ET tuning with the ratios for present
    pitches (only when ratios count matches the rule set)."""
    import copy
    tuning = copy.deepcopy(ET_TUNING)
    if len(ratios) != num_pitches(rule_set):
        return tuning
    mapping = []
    for key, val in rule_set.items():
        if isinstance(val, dict):
            if val.get("lowered"):
                mapping.append((key, "lowered"))
            if val.get("raised"):
                mapping.append((key, "raised"))
        elif val:
            mapping.append((key, None))
    for idx, ratio in enumerate(ratios):
        swara, variant = mapping[idx]
        if swara in ("sa", "pa"):
            tuning[swara] = ratio
        else:
            tuning[swara][variant] = ratio
    return tuning


def stratified_ratios(rule_set, ratios, tuning):
    """Normal case (ratios count == num_pitches): interleave ratios (present
    pitches) with tuning (absent pitches). Matches raga.ts / raga.py."""
    out = []
    ct = 0
    for s in SARGAM:
        val = rule_set[s]
        base = tuning[s]
        if isinstance(val, bool):
            if val:
                out.append(ratios[ct]); ct += 1
            else:
                out.append(base)
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


def make(name, description, raga_name, fundamental, ratios):
    tuning = build_tuning(YAMAN_RULESET, ratios)
    strat = stratified_ratios(YAMAN_RULESET, ratios, tuning)
    return {
        "name": name,
        "description": description,
        "ruleSet": "yaman (default, not serialized)",
        "ragaJson": {
            "name": raga_name,
            "fundamental": fundamental,
            "ratios": ratios,
            "tuning": tuning,
        },
        "expected": {
            "fundamental": fundamental,
            "stratifiedRatios": strat,
        },
        "tolerance": {"rel": 1e-9},
    }


FIXTURES = [
    make("yaman-12tet-default-fundamental",
         "Yaman, 12-TET, default 261.63Hz fundamental. stratifiedRatios equals "
         "the Pitch default 12-TET stratified array.",
         "Yaman", 261.63, YAMAN_12TET_RATIOS),
    make("yaman-12tet-nondefault-fundamental",
         "Yaman, 12-TET, fundamental 246Hz. Same ratios, different fundamental "
         "(the value that must be threaded into every Pitch).",
         "Yaman", 246.0, YAMAN_12TET_RATIOS),
    make("yaman-just-intonation",
         "Yaman with JUST-INTONATION ratios for its raised pitches (re 9/8, "
         "ga 5/4, ma 45/32, dha 27/16, ni 15/8), fundamental 240Hz.",
         "Yaman", 240.0, YAMAN_JUST_RATIOS),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for fx in FIXTURES:
        with open(os.path.join(OUT, fx["name"] + ".json"), "w") as f:
            json.dump(fx, f, indent=2)
            f.write("\n")
        index.append({"name": fx["name"], "description": fx["description"]})
        print(f"wrote {fx['name']}.json  fund={fx['expected']['fundamental']}Hz")
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump({"entity": "raga", "fixtures": index}, f, indent=2)
        f.write("\n")
    print(f"\n{len(FIXTURES)} raga fixtures written")


if __name__ == "__main__":
    main()
