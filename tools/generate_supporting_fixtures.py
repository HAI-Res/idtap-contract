#!/usr/bin/env python3
"""Generate structural example fixtures for the supporting classes.

These entities carry NO frequency semantics, so their fixtures pin the WIRE
SHAPE, not a computation: each provides a canonical example instance plus the
set of required keys. The structural checker confirms the example has all
required keys and no unexpected top-level ones. (Full validation is via the
JSON Schemas in schemas/.)

Run: python3 tools/generate_supporting_fixtures.py
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures")

EXAMPLES = {
    "articulation": {
        "example": {"name": "pluck", "stroke": "d", "strokeNickname": "da"},
        "required": ["name"],
        "description": "A pluck articulation with stroke 'd' -> nickname 'da'.",
    },
    "automation": {
        "example": {"values": [{"normTime": 0.0, "value": 1.0},
                               {"normTime": 0.5, "value": 0.8},
                               {"normTime": 1.0, "value": 1.0}]},
        "required": ["values"],
        "description": "A three-point normalized automation curve.",
    },
    "chikari": {
        "example": {"fundamental": 246.0, "uniqueId": "chik-1"},
        "required": ["fundamental", "uniqueId"],
        "description": "Canonical chikari: fundamental + uniqueId only (pitches reconstructed).",
    },
    "group": {
        "example": {
            "trajectories": [
                {"id": 0, "pitches": [{"swara": 0, "raised": True, "oct": 0, "logOffset": 0}],
                 "durTot": 1.0, "num": 0, "uniqueId": "t0"},
                {"id": 1, "pitches": [{"swara": 2, "raised": True, "oct": 0, "logOffset": 0}],
                 "durTot": 1.0, "num": 1, "uniqueId": "t1"}],
            "id": "grp-1"},
        "required": ["trajectories", "id"],
        "description": "A group of two adjacent trajectories (reconnected by num on load).",
    },
    "meter": {
        "example": {
            "uniqueId": "meter-1",
            "hierarchy": [4],
            "startTime": 0.0,
            "tempo": 60.0,
            "repetitions": 1,
            "talaName": None,
            "vibhaga": None,
            "pulseStructures": [[
                {"pulses": [{"realTime": 0.0, "uniqueId": "p0", "affiliations": [],
                             "meterId": "meter-1", "corporeal": True}],
                 "tempo": 60.0, "pulseDur": 1.0, "size": 1, "startTime": 0.0,
                 "uniqueId": "ps0", "frontWeighted": True, "layer": 0,
                 "parentPulseID": None, "primary": True, "segmentedMeterIdx": 0,
                 "meterId": "meter-1", "offsets": [0.0]}]],
        },
        "required": ["uniqueId", "hierarchy", "tempo", "pulseStructures"],
        "description": "A minimal single-pulse meter (one layer, one PulseStructure).",
    },
}


def main():
    for entity, spec in EXAMPLES.items():
        d = os.path.join(FIX, entity)
        os.makedirs(d, exist_ok=True)
        fx = {
            "name": f"{entity}-example",
            "description": spec["description"],
            "scenario": "structural",
            "entity": entity,
            "instance": spec["example"],
            "expected": {"requiredKeys": spec["required"]},
        }
        with open(os.path.join(d, f"{entity}-example.json"), "w") as f:
            json.dump(fx, f, indent=2)
            f.write("\n")
        with open(os.path.join(d, "index.json"), "w") as f:
            json.dump({"entity": entity, "fixtures": [
                {"name": f"{entity}-example", "scenario": "structural",
                 "description": spec["description"]}]}, f, indent=2)
            f.write("\n")
        print(f"wrote fixtures/{entity}/{entity}-example.json")
    print(f"\n{len(EXAMPLES)} structural example fixtures written")


if __name__ == "__main__":
    main()
