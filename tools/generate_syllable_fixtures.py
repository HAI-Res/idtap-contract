#!/usr/bin/env python3
"""Generate fixtures/syllable/* (PROP-8) and fixtures/system/* (PROP-7).

`expected` values are written BY HAND below (syllable lists, legacy fields,
reason codes, derived IPA); the generator then asserts that the reference rules
in conformance/syllables.py reproduce them before writing anything. A fixture
is therefore a statement about the rules, not a recording of their output.

Run:  python3 tools/generate_syllable_fixtures.py
"""
import copy, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "conformance"))
sys.path.insert(0, HERE)
import syllables as S  # noqa: E402
from generate_packs import legacy_consonant  # noqa: E402

RAGA = {
    "name": "Yaman", "fundamental": 246.0,
    "ratios": [1, 1.122462048309373, 1.2599210498948732, 1.4142135623730951,
               1.4983070768766815, 1.681792830507429, 1.8877486253633868],
    "tuning": {"sa": 1, "re": {"lowered": 1.0594630943592953, "raised": 1.122462048309373},
               "ga": {"lowered": 1.189207115002721, "raised": 1.2599210498948732},
               "ma": {"lowered": 1.3348398541700344, "raised": 1.4142135623730951},
               "pa": 1.4983070768766815,
               "dha": {"lowered": 1.5874010519681994, "raised": 1.681792830507429},
               "ni": {"lowered": 1.7817974362806785, "raised": 1.8877486253633868}},
}


# ------------------------------------------------------------------ builders
def legacy_copies(iso):
    """What a pre-0.3.0 client stores beside an iso consonant: tables[indexOf]."""
    leg = legacy_consonant(iso)
    return leg["hindi"], leg["ipa"], leg["engTrans"]


def traj(uid, vowel=None, start=None, end=None, tid=0, dur=0.5, swara=0):
    """A row-0 trajectory as a pre-0.3.0 client writes it: the nine wire
    fields plus the 'consonant' articulation mirrors at 0.00 / 1.00."""
    t = {"id": tid, "pitches": [{"swara": swara, "raised": True, "oct": 0, "logOffset": 0.0}],
         "durTot": dur, "durArray": [1.0], "slope": 2.0, "articulations": {},
         "num": 0, "uniqueId": uid}
    if tid == 12:
        del t["articulations"]  # stored silences often have no articulations key
        return t
    if vowel is not None:
        t["vowel"] = vowel
    for iso, pre, key in ((start, "startConsonant", "0.00"), (end, "endConsonant", "1.00")):
        if iso is None:
            continue
        h, ipa, eng = legacy_copies(iso)
        t[pre], t[pre + "Hindi"], t[pre + "Ipa"], t[pre + "EngTrans"] = iso, h, ipa, eng
        t["articulations"][key] = {"name": "consonant", "stroke": iso, "hindi": h, "ipa": ipa, "engTrans": eng}
    return t


def bare(uid, tid=0, dur=0.5):
    """A trajectory with no phonetic fields (0.3.0 canonical before projection)."""
    return traj(uid, tid=tid, dur=dur)


def phrase(uid, trajs, syllables=None, start=0.0):
    ph = {"durTot": sum(t["durTot"] for t in trajs), "durArray": None, "chikaris": {},
          "startTime": start, "trajectoryGrid": [trajs], "instrumentation": ["Vocal (F)"],
          "groupsGrid": [[]], "categorizationGrid": [], "uniqueId": uid,
          "adHocCategorizationGrid": [], "isSectionStart": False}
    tot = ph["durTot"]
    ph["durArray"] = [t["durTot"] / tot for t in trajs]
    if syllables is not None:
        ph["syllables"] = syllables
    return ph


def piece(tracks, system=None, lyrics=None, title="Contract Fixture (syllables)"):
    instr = ["Vocal (F)"] * len(tracks)
    t0 = 0.0
    for track in tracks:
        t = 0.0
        for ph in track:
            ph["startTime"] = t
            t += ph["durTot"]
        t0 = max(t0, t)
    pc = {"raga": copy.deepcopy(RAGA), "phraseGrid": tracks, "instrumentation": instr,
          "durTot": t0, "durArrayGrid": [[ph["durTot"] / t0 for ph in tr] for tr in tracks],
          "sectionCatGrid": [[] for _ in tracks], "meters": [], "title": title,
          "_id": "fixture000000000000000000"}
    if system is not None:
        pc["system"] = system
    if lyrics is not None:
        pc["lyricsText"] = lyrics
    return pc


def syl(traj_uid, nucleus=None, onset=None, coda=None, lyric=..., source="pack", **extra):
    s = {"anchor": {"traj": traj_uid, "t": 0}}
    if onset is not None:
        s["onset"] = onset
    if nucleus is not None:
        s["nucleus"] = nucleus
    if coda is not None:
        s["coda"] = coda
    s.update({k: v for k, v in extra.items() if k not in ("sung",)})
    s["lyric"] = {"vowel": nucleus if lyric is ... else lyric, "source": source}
    if "sung" in extra:
        s["sung"] = extra["sung"]
    return s


legacy_map = S.stored_legacy
grid = S.syllable_grid


def errors(pc):
    return S.split_violations(S.check_invariants(pc))[0]


FIXTURES = {"syllable": [], "system": []}


def emit(entity, fx):
    FIXTURES[entity].append(fx)


def same(a, b, what):
    if a != b:
        raise SystemExit(f"hand-written expectation disagrees with the rules: {what}\n"
                         f"  expected {json.dumps(a, ensure_ascii=False)}\n"
                         f"  rules    {json.dumps(b, ensure_ascii=False)}")


# ------------------------------------------------------------------ 1. heal + round trip
def fx_heal_roundtrip():
    p0 = phrase("ph-a", [traj("a1", "ā", start="ba"), traj("a2", "ā"),
                         traj("a3", "u", start="ba", end="la"), traj("a4", tid=12)])
    p1 = phrase("ph-b", [traj("b1", "ō", start="ma"), traj("b2", "ā", start="ra"), traj("b3", "ā"),
                         traj("b4", "a", start="pha"), traj("b5", "a", end="na"),
                         traj("b6", "ī"), traj("b7")])
    p2 = phrase("ph-c", [traj("c1", "ī"), traj("c2", "ī", start="na")])
    inst = phrase("ph-i", [traj("i1"), traj("i2", swara=4)])
    pc = piece([[p0, p1, p2], [inst]], title="Babul mora (fixture)")
    want = [[
        [syl("a1", "ā", onset="ba"), syl("a3", "u", onset="ba", coda="la")],
        [syl("b1", "ō", onset="ma"), syl("b2", "ā", onset="ra"),
         syl("b4", "a", onset="pha", coda="na"), syl("b6", "ī"), syl("b7", lyric=None)],
        [syl("c1", "ī"), syl("c2", "ī", onset="na")],
    ], [[]]]
    healed = S.heal_piece(pc)
    same(want, grid(healed), "heal")
    same(legacy_map(pc), S.project_piece(healed), "projection round trip")
    same(pc, S.strip_syllables(S.apply_projection(healed)), "dual-write leaves the legacy document byte-identical")
    same((True, []), S.legacy_safe(healed), "legacy_safe")
    same([], errors(healed), "invariants")
    emit("syllable", {
        "name": "heal-legacy-hindi-roundtrip",
        "scenario": "legacy",
        "kind": "heal",
        "description": "Legacy-only Hindustani piece (no syllables key anywhere). Heal by the firstTrajIdxs rule, then project: every legacy field and 'consonant' articulation mirror comes back identical. Covers: melisma (a1-a2, b2-b3, b4-b5), a coda that ends a syllable (a3 la, b5 na), a silence (a4), a vowel change with no consonant (b6), a group with no vowel (b7 -> lyric.vowel null), a phrase start not preceded by silence (c1), the legacy 'na' whose stored IPA copy is 'n' and 'pha' whose stored Hindi copy is फ़ (kept by the legacy block, PACK-1), and a vocal track with no phonetic data (-> syllables []).",
        "pieceJson": pc,
        "expected": {"syllables": want, "legacyRoundTrip": True, "legacySafe": True,
                     "legacySafeReasons": [], "violations": []},
    })


# ------------------------------------------------------------------ 2. cantonese projection
def fx_cantonese():
    t = {k: bare(k) for k in ("y1", "y2", "y3", "y4", "y5", "y7")}
    sil = traj("y6", tid=12)
    p0 = phrase("ph-y0", [t["y1"], t["y2"]], [
        syl("y1", "i", onset="s", tone="1", orthography="詩", romanization="si1", wordStart=True)])
    p1 = phrase("ph-y1", [t["y3"], t["y4"], t["y5"], sil, t["y7"]], [
        syl("y4", None, coda="m", lyric=None, tone="4", orthography="唔", romanization="m4", wordStart=True),
        syl("y5", "o", onset="h", coda="u", tone="2", orthography="好", romanization="hou2"),
        syl("y7", "i", onset="s", coda="k", tone="6", orthography="食", romanization="sik6", wordStart=True)])
    pc = piece([[p0, p1]], system={"phonology": "jyutping", "display": ["jyutping", "Hant"]},
               lyrics=["詩唔好 食"], title="Cantonese projection (fixture)")
    # Non-Hindi packs project nothing (Jon, 2026-11-12): every row-0
    # trajectory ends with no vowel, no consonants, no consonant articulations.
    legacy = {uid: {"art0": None, "art1": None} for uid in ("y1", "y2", "y3", "y4", "y5", "y6", "y7")}
    ipa = ["siː", "m̩", "hou̯", "sek̚"]
    pack = S.load_pack("jyutping")
    same(legacy, S.project_piece(pc), "cantonese projection")
    same(ipa, [S.derive_ipa(s, pack) for ph in pc["phraseGrid"][0] for s in ph["syllables"]], "ipa")
    nine = ["1", "4", "2", "9"]  # sik6 is checked (-k): tone 6 -> 9
    same(nine, [S.derived_tone(s, pack) for ph in pc["phraseGrid"][0] for s in ph["syllables"]], "nine-tone")
    reasons = ["orthography", "pack", "romanization", "tone", "wordStart"]
    same((False, reasons), S.legacy_safe(pc), "legacy_safe")
    same([], errors(pc), "invariants")
    emit("syllable", {
        "name": "project-cantonese-tone-orthography",
        "scenario": "stripped",
        "kind": "project",
        "description": "Cantonese piece (system.phonology jyutping) with tone, orthography, romanization and word starts. si1 is a melisma over y1-y3 that crosses the phrase boundary (y3 is the first trajectory of ph-y1 and is not an anchor); m4 is a syllabic nasal (no nucleus, coda m); hou2 has a glide coda the legacy fields cannot hold; sik6 is a checked syllable after a silence. Projection writes nothing into the legacy fields: no vowel, no consonants, no consonant articulations (non-Hindi packs carry no legacy mapping; every platform moves to the tier together). The write guard, which refuses a pre-0.3.0 save, is the only protection for such a piece. IPA is derived from the finals table and the nine-tone number from (tone, coda); neither is stored.",
        "pieceJson": pc,
        "expected": {"legacy": legacy, "derivedIpa": ipa, "nineTone": nine, "legacySafe": False,
                     "legacySafeReasons": reasons, "violations": []},
    })


# ------------------------------------------------------------------ 3. mixed
def fx_mixed():
    # ph-m0 was saved by a 0.3.0 client: syllables + dual-written legacy fields,
    # except that m1's stored vowel disagrees (ā) with its syllable (ī).
    p0 = phrase("ph-m0", [traj("m1", "ā", start="ga"), traj("m2", "ī")],
                [syl("m1", "ī", onset="ga")])
    # ph-m1 was last saved by a pre-0.3.0 client: no syllables key.
    p1 = phrase("ph-m1", [traj("n1", "ē", start="da"), traj("n2", tid=12), traj("n3", "ō", end="ma")])
    pc = piece([[p0, p1]], title="Mixed heal (fixture)")
    want = [[[syl("m1", "ī", onset="ga")],
             [syl("n1", "ē", onset="da"), syl("n3", "ō", coda="ma")]]]
    healed = S.heal_piece(pc)
    same(want, grid(healed), "mixed heal")
    proj = S.project_piece(healed)
    same("ī", proj["m1"]["vowel"], "syllables win over a disagreeing legacy field")
    same((False, ["boundary"]), S.legacy_safe(healed), "legacy_safe on the stored (stale) fields")
    same((True, []), S.legacy_safe(S.apply_projection(healed)), "legacy_safe after a 0.3.0 save")
    emit("syllable", {
        "name": "mixed-healed-and-legacy-phrases",
        "scenario": "mixed",
        "kind": "heal",
        "description": "One phrase carries syllables (written by a 0.3.0 client), the next has none (last saved by a pre-0.3.0 client). The loader keeps the first phrase's syllables and heals the second from its legacy fields. Where a phrase has syllables they win: m1's stale stored vowel 'ā' is ignored and the projection rewrites it to 'ī'. The write guard reads the STORED legacy fields, so as loaded the piece is not legacy-safe (healing the stale 'ā' disagrees with the stored syllable: boundary); once a 0.3.0 client saves it (dual-write) it is.",
        "pieceJson": pc,
        "expected": {"syllables": want, "legacyRoundTrip": False,
                     "legacyAfterProjection": {"m1": proj["m1"], "m2": proj["m2"]},
                     "legacySafe": False, "legacySafeReasons": ["boundary"], "violations": []},
    })


def fx_instrumental():
    voc = phrase("ph-v", [traj("v1", "ā", start="ba"), traj("v2", "ā")])
    sitar = phrase("ph-s", [traj("s1", "a"), traj("s2", "a"), traj("s3", "ē")])
    unlabelled = phrase("ph-u", [traj("u1", "a"), traj("u2", "a")])
    pc = piece([[voc], [sitar], [unlabelled]], title="Instrumental tracks (fixture)")
    pc["instrumentation"] = ["Vocal (M)", "Sitar"]  # track 2 has no label
    want = [[[syl("v1", "ā", onset="ba")]], [None], [None]]
    healed = S.heal_piece(pc)
    same(want, grid(healed), "only the vocal track is healed")
    same(legacy_map(pc), S.project_piece(healed), "non-vocal legacy fields stand")
    same(pc, S.strip_syllables(S.apply_projection(healed)), "dual-write leaves every track byte-identical")
    same((True, []), S.legacy_safe(pc), "legacy_safe")
    same([], errors(healed), "invariants")
    emit("syllable", {
        "name": "heal-instrumental-tracks-untouched",
        "scenario": "legacy",
        "kind": "heal",
        "description": "Syllables live on vocal tracks only (Jon, 2026-11-13). Track 0 is 'Vocal (M)' and is healed. Track 1 is a Sitar whose trajectories carry the editor's default vowel 'a' (and one 'e-macron'); track 2 has no instrumentation label. Neither gets a syllables key, and the projection leaves their stored legacy fields exactly as they are: not rewritten, not cleared. A tier stored on a non-vocal track is kept, not projected, and warned about (track-not-vocal).",
        "pieceJson": pc,
        "expected": {"syllables": want, "legacyRoundTrip": True,
                     "legacySafe": True, "legacySafeReasons": [], "violations": []},
    })


# ------------------------------------------------------------------ 4-6. re-homing
def _rehome_base():
    return [traj("r1", "ā", start="ba"), traj("r2", "ā"), traj("r3", "ī", start="ga"), traj("r4", "ī")]


def fx_rehome(name, split_at, want, safe, reasons, desc, merge=False):
    trajs = _rehome_base()
    if merge:
        before = piece([[phrase("ph-r0", trajs[:2], [syl("r1", "ā", onset="ba")]),
                         phrase("ph-r1", trajs[2:], [syl("r3", "ī", onset="ga")])]])
        after = piece([[phrase("ph-r0", copy.deepcopy(trajs))]])
    else:
        before = piece([[phrase("ph-r0", trajs, [syl("r1", "ā", onset="ba"), syl("r3", "ī", onset="ga")])]])
        after = piece([[phrase("ph-r0", copy.deepcopy(trajs[:split_at])),
                        phrase("ph-r1", copy.deepcopy(trajs[split_at:]))]])
    # the edit itself leaves the syllable lists where they were (or loses them)
    for ph in after["phraseGrid"][0]:
        ph.pop("syllables", None)
    got, dropped = S.rehome(before, after)
    same(want, grid(got)[0], name + " rehome")
    same([], dropped, name + " dropped")
    same(S.project_piece(before), S.project_piece(got), name + " projection unchanged by the edit")
    same((safe, reasons), S.legacy_safe(got), name + " legacy_safe")
    same([], errors(got), name + " invariants")
    emit("syllable", {"name": name, "scenario": "edit", "kind": "rehome", "description": desc,
                      "pieceJson": before, "pieceAfterEdit": after,
                      "expected": {"syllables": [want], "dropped": [], "legacyUnchanged": True,
                                   "legacySafe": safe, "legacySafeReasons": reasons, "violations": []}})


# ------------------------------------------------------------------ 7. invariants
def fx_invariants():
    cases = []

    def case(name, pc, codes, desc, warnings=()):
        errs, warns = S.split_violations(S.check_invariants(pc))
        same((sorted(codes), sorted(warnings)), (errs, warns), "invariants " + name)
        cases.append({"name": name, "description": desc, "pieceJson": pc,
                      "expected": {"violations": sorted(codes), "warnings": sorted(warnings)}})

    case("anchor-missing", piece([[phrase("p", [traj("v1", "ā")], [syl("nope", "ā")])]]),
         ["anchor-missing", "unanchored-start"],
         "The anchor names no trajectory of this phrase; v1 then starts the track without a syllable.")
    case("anchor-silence", piece([[phrase("p", [traj("v1", "ā"), traj("v2", tid=12)],
                                          [syl("v1", "ā"), syl("v2", "ā")])]]),
         ["anchor-silence"], "A syllable starts on a silence trajectory (id 12).")
    case("anchor-order", piece([[phrase("p", [traj("v1", "ā"), traj("v2", "ī")],
                                        [syl("v2", "ī"), syl("v1", "ā")])]]),
         ["anchor-order"], "Syllables out of trajectory order.")
    case("unanchored-after-silence", piece([[phrase("p", [traj("v1", "ā"), traj("v2", tid=12), traj("v3", "ā")],
                                                    [syl("v1", "ā")])]]),
         ["unanchored-start"], "v3 follows a silence but starts no syllable.")
    s = syl("v1", "ā")
    s["anchor"]["t"] = 0.5
    case("anchor-t-nonzero", piece([[phrase("p", [traj("v1", "ā")], [s])]]), ["anchor-t"],
         "anchor.t must be 0 in 0.3.x: no system allows a mid-trajectory onset yet.")
    case("tone-in-hindi", piece([[phrase("p", [traj("v1", "ā")], [syl("v1", "ā", tone="1")])]]),
         ["tone-not-allowed"], "hindi-urdu defines no tones.")
    case("cluster-in-hindi", piece([[phrase("p", [traj("v1", "ā")], [syl("v1", "ā", onset=["ka", "ra"])])]]),
         ["cluster-not-allowed"], "hindi-urdu does not allow onset clusters.")
    case("unknown-key", piece([[phrase("p", [traj("v1", "ā")], [syl("v1", "ā", onset="qa")])]]),
         ["key-unknown"], "onset 'qa' is not a hindi-urdu key.")
    kur = {"phonology": "kurmanji"}
    case("syllabic-nasal-in-kurmanji", piece([[phrase("p", [bare("v1")], [syl("v1", None, coda="m", lyric=None)])]], system=kur),
         ["nucleus-missing"], "Syllabic nasals (no nucleus, coda m|ng) are allowed only by a pack with syllabicNasals (jyutping).")
    case("kurmanji-cluster-ok", piece([[phrase("p", [bare("v1")], [syl("v1", "e", onset=["x", "w"])])]], system=kur),
         [], "xwe: Kurmanji allows the onset cluster x+w.")
    jy = {"phonology": "jyutping"}
    case("jyutping-bare-eo", piece([[phrase("p", [bare("v1")], [syl("v1", "eo", onset="s", tone="1")])]], system=jy),
         ["final-unknown"], "Bare eo is not among the 59 listed finals. It is a candidate for Yingyao's 60th final (unverified in packs/jyutping.json); if it is confirmed, this case becomes valid.")
    case("jyutping-coda-cluster", piece([[phrase("p", [bare("v1")], [syl("v1", "aa", onset="s", coda=["n", "t"], tone="1")])]], system=jy),
         ["cluster-not-allowed"], "A coda cluster in a pack with a finals table: reported once, not a crash and not also final-unknown.")
    nouid = traj("v1", "ā")
    nouid["uniqueId"] = None
    case("traj-without-uniqueId", piece([[phrase("p", [nouid, traj("v2", "ī")], [syl("v2", "ī")])]]),
         ["traj-uid-missing", "unanchored-start"],
         "A row-0 trajectory with no uniqueId cannot be anchored; loaders assign ids before healing, and heal/project/rehome refuse such a trajectory.")
    mis = syl("v1", "ā")
    mis["lyric"]["vowel"] = "ī"
    case("nucleus-lyric-mismatch", piece([[phrase("p", [traj("v1", "ā")], [mis])]]),
         ["nucleus-lyric-mismatch"],
         "nucleus 'ā' with lyric.vowel 'ī'. Editors keep the two in sync (absent nucleus == null lyric.vowel); the projection reads lyric.vowel and IPA reads nucleus, so a mismatch is an error.")
    sitar = piece([[phrase("p", [traj("v1", "ā")], [syl("v1", "ā")])], [phrase("q", [traj("s1")], [])]])
    sitar["instrumentation"] = ["Sitar", "Vocal (M)"]
    case("track-not-vocal", sitar, [], "Track 0 is a Sitar but carries syllables: a warning, not an error (a sung bol or a mislabelled track). Vocal labels: 'Vocal (M)', 'Vocal (F)'. Track 1 is vocal with no syllables: nothing to report; tracks are independent.",
         warnings=["track-not-vocal"])
    case("jyutping-syllabic-ng-ok", piece([[phrase("p", [bare("v1")], [syl("v1", None, coda="ng", lyric=None, tone="5")])]], system=jy),
         [], "ng5 (五): a syllabic nasal, allowed by jyutping.")
    emit("syllable", {
        "name": "invariants",
        "scenario": "validation",
        "kind": "invariants",
        "description": "Load-time invariants, one case each. Errors (`violations`): traj-uid-missing, nucleus-lyric-mismatch, anchor-missing, anchor-silence, anchor-order, unanchored-start, anchor-t, key-unknown, cluster-not-allowed, tone-not-allowed, nucleus-missing, final-unknown, syllabic-not-allowed. Warnings (`warnings`): track-not-vocal. A client reports them; what it does next (refuse, repair, warn) is its own choice in 0.3.0.",
        "cases": cases,
    })


# ------------------------------------------------------------------ 8. write guard
def fx_guard():
    cases = []

    def base(extra=None, onset="ba", system=None, second=None):
        s1 = syl("w1", "ā", onset=onset, **(extra or {}))
        trajs = [traj("w1", "ā", start="ba"), traj("w2", "ā")]
        syls = [s1] + ([second] if second else [])
        return piece([[phrase("p", trajs, syls)]], system=system)

    def case(name, pc, reasons, desc):
        same((not reasons, reasons), S.legacy_safe(pc), "guard " + name)
        cases.append({"name": name, "description": desc, "pieceJson": pc,
                      "expected": {"legacySafe": not reasons, "legacySafeReasons": reasons}})

    case("plain-hindi", base(), [], "Heal reproduces it: a pre-0.3.0 save is allowed (it drops the syllables; the next load rebuilds them).")
    case("explicit-hindustani-system", base(system={"phonology": "hindi-urdu"}), [],
         "An explicit hindi-urdu system is still legacy-safe; `system` is a top-level field that a $set save leaves in place.")
    case("word-start", base({"wordStart": True}), ["wordStart"], "Word starts have no legacy field.")
    case("orthography", base({"orthography": "बा"}), ["orthography"], "Written forms have no legacy field.")
    case("sung-vowel", base({"sung": {"vowel": "a", "source": "model"}}), ["sung"], "Sung vowels are not projected.")
    case("retroflex-na", base(onset="ṇa"), ["key"], "ṇa is new in the fixed pack and has no legacy form.")
    case("kurmanji-pack", piece([[phrase("p", [bare("w1")], [syl("w1", "a", onset="w")])]], system={"phonology": "kurmanji"}),
         ["pack"], "Any pack other than hindi-urdu.")
    stale = piece([[phrase("p", [traj("w1", "ā", start="ba"), traj("w2", "ā")], [])]])
    case("stale-legacy-beside-empty-syllables", stale, ["boundary"],
         "syllables: [] but the trajectories still carry 'ba' + 'ā' (a stale write). A pre-0.3.0 save would keep those fields and the next load would heal a syllable the tier says does not exist, so the guard, which reads the stored legacy fields, refuses.")
    untiered = piece([[phrase("p", [traj("w1", "ā", start="ba"), traj("w2", "ā")])]])
    untiered["phraseGrid"][0][0].pop("syllables", None)
    case("untiered-legacy", untiered, [],
         "No phrase has a syllables key: a plain legacy piece, as almost every stored piece is while the web flag is off. A pre-0.3.0 save drops nothing, so it is allowed. Only phrases with a stored tier are compared.")
    tiered_sitar = piece([[phrase("p", [traj("w1", "ā", start="ba"), traj("w2", "ā")], [syl("w1", "ā", onset="ba")])]])
    tiered_sitar["instrumentation"] = ["Sitar"]
    case("tier-on-instrumental-track", tiered_sitar, ["boundary"],
         "A tier stored on a Sitar track. The heal never builds syllables on a non-vocal track, so an old client's save would lose it: unsafe.")
    case("regrouped-by-heal", base(second=syl("w2", "ā")), ["boundary"],
         "Two adjacent syllables with the same vowel and no consonant between them: the heal would merge them into one, so the legacy fields cannot hold the boundary.")
    emit("syllable", {
        "name": "write-guard",
        "scenario": "validation",
        "kind": "guard",
        "description": "PROP-8 write guard: the server refuses a save from a client below 0.3.0 when the stored piece is not legacy-safe. Legacy-safe means healing the STORED legacy fields gives back the stored syllables (anchor, onset, nucleus, coda, lyric.vowel; lyric.source is not compared) and no syllable carries a field the legacy fields cannot hold. Reason codes: pack, orthography, romanization, tone, wordStart, sung, anchorT, cluster, key, boundary.",
        "cases": cases,
    })


# ------------------------------------------------------------------ PROP-7 system
def fx_systems():
    def her_waye():
        trajs = [bare("k1"), bare("k2"), bare("k3"), bare("k4")]
        return [[phrase("ph-k", trajs, [
            syl("k1", "e", onset="h", coda="r", orthography="her", romanization="her", wordStart=True),
            syl("k3", "a", onset="w", orthography="wa", romanization="wa", wordStart=True),
            syl("k4", "ê", onset="y", orthography="yê", romanization="yê")])]]

    def legacy_track():
        return [[phrase("ph-h", [traj("h1", "ā", start="ba"), traj("h2", "u", start="ba", end="la")])]]

    rows = [
        ("system-absent", None, legacy_track(), "Absent system: every pre-0.3.0 piece. Resolves to Hindustani.", None),
        ("system-hindustani-explicit", {"pitch": "raga", "phonology": "hindi-urdu", "rhythm": "tala", "display": ["sargam", "Deva"]},
         legacy_track(), "The Hindustani defaults written out; identical meaning to absent.", None),
        ("system-cantonese", {"phonology": "jyutping", "display": ["jyutping", "Hant"], "pitch": "mode-12tet"},
         [[phrase("ph-c", [bare("c1")], [syl("c1", "i", onset="s", tone="1", orthography="詩", romanization="si1")])]],
         "Cantonese: only phonology has semantics in 0.3.0; 'mode-12tet' is an extensible id kept verbatim. Missing rhythm defaults to tala.", ["siː"]),
        ("system-kurmanji", {"phonology": "kurmanji", "pitch": "maqam", "rhythm": "usul", "display": ["kurmanji-latin"], "x-notes": "Dengbêj"},
         her_waye(), "Kurmanji, Dengbêj Gazîn 'Her wayê wayê wayê' (first three syllables: her wa yê, with a melisma on her). An unknown component ('x-notes') is kept verbatim.", ["hæɾ", "wɑ", "je"]),
    ]
    for name, system, tracks, desc, ipa in rows:
        pc = piece(tracks, system=system, title=name)
        resolved = {"pitch": "raga", "phonology": "hindi-urdu", "rhythm": "tala", "display": ["sargam", "Deva"]}
        resolved.update(system or {})
        same(resolved, S.resolve_system(pc), name)
        healed = S.heal_piece(pc)
        same([], errors(healed), name + " invariants")
        exp = {"resolved": resolved, "pack": resolved["phonology"], "syllableUi": system is not None, "violations": []}
        if ipa:
            pack = S.load_pack(resolved["phonology"])
            same(ipa, [S.derive_ipa(s, pack) for s in healed["phraseGrid"][0][0]["syllables"]], name + " ipa")
            exp["derivedIpa"] = ipa
        emit("system", {"name": name, "scenario": "stripped" if system else "legacy", "description": desc,
                        "pieceJson": pc, "expected": exp})


def main():
    fx_heal_roundtrip()
    fx_cantonese()
    fx_mixed()
    fx_instrumental()
    fx_rehome("rehome-split-at-syllable-boundary", 2,
              [[syl("r1", "ā", onset="ba")], [syl("r3", "ī", onset="ga")]], True, [],
              "Split ph-r0 between r2 and r3, at a syllable boundary. The ga syllable follows r3 into the new phrase ph-r1; the legacy fields are unchanged and the piece stays legacy-safe.")
    fx_rehome("rehome-split-mid-melisma", 1,
              [[syl("r1", "ā", onset="ba")], [syl("r3", "ī", onset="ga")]], False, ["boundary"],
              "Split between r1 and r2, inside the melisma ba-ā (r1-r2). The syllable stays in ph-r0 and its extent continues into ph-r1 (r2 is not an anchor), so the legacy fields are unchanged. The heal would start a new syllable at r2 (first of a phrase), so the piece is no longer legacy-safe: a mid-melisma split locks out pre-0.3.0 writers.")
    fx_rehome("rehome-merge", None, [[syl("r1", "ā", onset="ba"), syl("r3", "ī", onset="ga")]], True, [],
              "Merge ph-r0 and ph-r1 into one phrase. The edit deletes ph-r1 and its syllable list; re-homing pools every syllable of the track from before the edit, so ga survives in the merged phrase.",
              merge=True)
    fx_invariants()
    fx_guard()
    fx_systems()
    for entity, fxs in FIXTURES.items():
        d = os.path.join(ROOT, "fixtures", entity)
        os.makedirs(d, exist_ok=True)
        index = {"entity": entity, "fixtures": []}
        for fx in fxs:
            with open(os.path.join(d, fx["name"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(fx, f, ensure_ascii=False, indent=2)
                f.write("\n")
            index["fixtures"].append({k: fx[k] for k in ("name", "scenario", "description")})
        with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {len(fxs)} fixtures to fixtures/{entity}/")


if __name__ == "__main__":
    main()
