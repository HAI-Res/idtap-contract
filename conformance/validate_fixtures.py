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

import syllables as SYL  # PROP-7/8/9 reference rules (same folder)

try:  # schema validation of the PROP-7/8/9 fixtures and packs; CI installs it
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover
    jsonschema = None

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures")
CONTRACT = os.path.join(HERE, "..", "contract.json")
SCHEMAS = os.path.join(HERE, "..", "schemas")
PACKS = os.path.join(HERE, "..", "packs")

# The contract version this runner was written against. Each implementation
# repo keeps the same kind of constant (see README "Versioning") and asserts it
# against contract.json in its conformance suite, so a bump that changes wire
# semantics fails CI in every client until the client is updated.
CONTRACT_VERSION = "0.3.0"

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


# --------------------------------------------------------------------------- schemas
_VALIDATORS = {}


def schema_errors(instance, name):
    """Errors of `instance` against schemas/<name>.schema.json ([] when
    jsonschema is not installed; main() says so)."""
    if jsonschema is None:
        return []
    if name not in _VALIDATORS:
        reg, mine = Registry(), None
        for path in glob.glob(os.path.join(SCHEMAS, "*.schema.json")):
            sch = json.load(open(path, encoding="utf-8"))
            reg = reg.with_resource(sch["$id"], Resource.from_contents(sch))
            if os.path.basename(path) == name + ".schema.json":
                mine = sch
        _VALIDATORS[name] = jsonschema.Draft202012Validator(mine, registry=reg)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:120]}"
            for e in _VALIDATORS[name].iter_errors(instance)]


def piece_schema_ok(*pieces):
    errs = [e for pc in pieces for e in schema_errors(pc, "piece")]
    return not errs, errs


# --------------------------------------------------------------------------- syllable (PROP-8)
def _guard(pc, exp):
    return SYL.legacy_safe(pc) == (exp["legacySafe"], exp["legacySafeReasons"])


def _violations(pc, exp):
    return [c for c, _ in SYL.check_invariants(pc)] == exp["violations"]


def _grid(pc):
    return [[ph.get("syllables") for ph in tr] for tr in pc["phraseGrid"]]


def check_syllable(fx):
    kind, exp = fx["kind"], fx.get("expected")
    notes = []
    if kind in ("invariants", "guard"):
        ok = True
        for c in fx["cases"]:
            good, errs = piece_schema_ok(c["pieceJson"])
            if kind == "invariants":
                good = good and _violations(c["pieceJson"], c["expected"])
            else:
                good = good and _guard(c["pieceJson"], c["expected"])
            if not good:
                notes.append(f"case {c['name']} FAILED {errs[:2]}")
            ok = ok and good
        return ok, f"{len(fx['cases'])} cases" + ("; " + "; ".join(notes) if notes else "")
    pc = fx["pieceJson"]
    if kind == "heal":
        out = SYL.heal_piece(pc)
        ok = _grid(out) == exp["syllables"]
        proj = SYL.project_piece(out)
        if exp.get("legacyRoundTrip"):
            before = {t["uniqueId"]: SYL.legacy_of_traj(t)
                      for tr in pc["phraseGrid"] for _, _, t in SYL.track_flat(tr)}
            ok = ok and proj == before
            notes.append("heal->project identical")
        for uid, want in (exp.get("legacyAfterProjection") or {}).items():
            ok = ok and proj[uid] == want
    elif kind == "project":
        out = pc
        ok = SYL.project_piece(pc) == exp["legacy"]
        pack = SYL.pack_of(pc)
        ipa = [SYL.derive_ipa(s, pack) for tr in pc["phraseGrid"] for ph in tr for s in ph["syllables"]]
        ok = ok and ipa == exp["derivedIpa"]
        notes.append("ipa " + " ".join(ipa))
    elif kind == "rehome":
        out, dropped = SYL.rehome(pc, fx["pieceAfterEdit"])
        ok = _grid(out) == exp["syllables"] and dropped == exp["dropped"]
        if exp.get("legacyUnchanged"):
            ok = ok and SYL.project_piece(out) == SYL.project_piece(pc)
    else:
        return False, f"unknown kind {kind}"
    good, errs = piece_schema_ok(pc, out)
    ok = ok and good and _guard(out, exp) and _violations(out, exp)
    notes.append(f"legacySafe={exp['legacySafe']} {exp['legacySafeReasons']}")
    return ok, "; ".join(notes + errs[:3])


# --------------------------------------------------------------------------- system (PROP-7)
def check_system(fx):
    pc, exp = fx["pieceJson"], fx["expected"]
    res = SYL.resolve_system(pc)
    ok = res == exp["resolved"] and res["phonology"] == exp["pack"]
    ok = ok and os.path.exists(os.path.join(PACKS, exp["pack"] + ".json"))
    ok = ok and ("system" in pc) == exp["syllableUi"]
    healed = SYL.heal_piece(pc)
    ok = ok and [c for c, _ in SYL.check_invariants(healed)] == exp["violations"]
    if "derivedIpa" in exp:
        pack = SYL.pack_of(pc)
        ok = ok and [SYL.derive_ipa(s, pack) for s in healed["phraseGrid"][0][0]["syllables"]] == exp["derivedIpa"]
    good, errs = piece_schema_ok(pc, healed)
    return ok and good, f"phonology={res['phonology']}" + (f" ipa={' '.join(exp['derivedIpa'])}" if "derivedIpa" in exp else "") + (f" {errs[:2]}" if errs else "")


# --------------------------------------------------------------------------- packs (PROP-9)
def check_pack(pack):
    errs = schema_errors(pack, "pack")
    codas = SYL.codas_of(pack)
    if pack["id"] == SYL.LEGACY_PACK:
        lt = pack["legacyTables"]
        # every stored legacy key heals to a pack key, and each legacy block is
        # exactly what today's code writes for it: tables[indexOf(key)]
        for table, isos, cols in (("consonants", "cIsos", ("cHindis", "cIpas", "cEngTrans")),
                                  ("vowels", "vIsos", ("vHindis", "vIpas", "vEngTrans"))):
            for key in lt[isos]:
                e = pack[table].get(key)
                i = lt[isos].index(key)
                want = {"iso": key, "hindi": lt[cols[0]][i], "ipa": lt[cols[1]][i], "engTrans": lt[cols[2]][i]}
                if e is None or e.get("legacy") != want:
                    errs.append(f"{table}.{key}: legacy block != tables[indexOf]")
            for key, e in pack[table].items():
                if "legacy" in e and key not in lt[isos]:
                    errs.append(f"{table}.{key}: legacy block for a key the tables lack")
    else:
        # non-Hindi packs project nothing into the legacy fields (PROP-8)
        if pack["flags"]["legacyExact"]:
            errs.append("flags.legacyExact is true on a non-hindi-urdu pack")
        maps = [pack["consonants"], pack["vowels"]] + ([codas] if codas is not pack["consonants"] else [])
        for m in maps:
            for key, e in m.items():
                if "legacy" in e:
                    errs.append(f"{key}: legacy block on a non-hindi-urdu pack")
    for key, f in (pack.get("finals") or {}).items():
        if (f["nucleus"] or "") + (f["coda"] or "") != key:
            errs.append(f"finals.{key}: key != nucleus + coda")
        if f["nucleus"] is not None and f["nucleus"] not in pack["vowels"]:
            errs.append(f"finals.{key}: unknown nucleus")
        if f["coda"] is not None and f["coda"] not in codas:
            errs.append(f"finals.{key}: unknown coda")
        if f.get("syllabic") and not pack["flags"]["syllabicNasals"]:
            errs.append(f"finals.{key}: syllabic final without flags.syllabicNasals")
    if pack["flags"]["tones"] != bool(pack.get("tones")):
        errs.append("flags.tones disagrees with tones")
    n = {k: len(pack[k]) for k in ("consonants", "vowels")}
    if pack.get("finals"):
        n["finals"] = len(pack["finals"])
    if pack.get("tones"):
        n["tones"] = len(pack["tones"])
    return not errs, " ".join(f"{k}={v}" for k, v in n.items()) + (f" ERR {errs[:3]}" if errs else "")


CHECKERS = {"pitch": check_pitch, "raga": check_raga,
            "trajectory": check_trajectory, "phrase": check_phrase,
            "piece": check_piece,
            "articulation": check_structural, "automation": check_structural,
            "chikari": check_structural, "group": check_structural,
            "meter": check_meter,
            "syllable": check_syllable, "system": check_system}


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
    print("== packs ==")
    for path in sorted(glob.glob(os.path.join(PACKS, "*.json"))):
        pack = json.load(open(path, encoding="utf-8"))
        ok, info = check_pack(pack)
        total += 1
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {pack['id']}  {info}")
    if jsonschema is None:
        print("\n  NOTE: jsonschema not installed; schema validation of syllable/system "
              "fixtures and packs was skipped (pip install jsonschema)")
    print(f"\n{total - fails}/{total} fixtures consistent; contract version "
          f"{'OK' if version_ok else 'MISMATCH'}")
    sys.exit(1 if fails or not version_ok else 0)


if __name__ == "__main__":
    main()
