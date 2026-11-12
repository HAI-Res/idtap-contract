"""Reference rules for PROP-7 (system), PROP-8 (syllable tier) and PROP-9 (packs).

Plain functions over the serialized JSON, no model classes, so each client can
read them as the spec and port them. validate_fixtures.py uses them to re-derive
every fixture's `expected`; the generator (tools/generate_syllable_fixtures.py)
writes `expected` BY HAND and asserts these rules agree, so the fixtures are not
just this module's output played back.

Terms
  track       phraseGrid[k]: one phrase sequence (one singer).
  main(ph)    ph["trajectoryGrid"][0]: syllables live on the main string only.
  silence     a trajectory with id == 12.
  absent      a legacy field that is missing OR null (null == absent, PROP-8;
              see DIVERGENCES.md SYL-1 for the TS behaviour this overrides).
"""
import copy, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PACKS_DIR = os.path.join(HERE, "..", "packs")

HINDUSTANI = {"pitch": "raga", "phonology": "hindi-urdu", "rhythm": "tala",
              "display": ["sargam", "Deva"]}
LEGACY_PACK = "hindi-urdu"
WIRE_FIELDS = ["vowel",
               "startConsonant", "startConsonantHindi", "startConsonantIpa", "startConsonantEngTrans",
               "endConsonant", "endConsonantHindi", "endConsonantIpa", "endConsonantEngTrans"]
# Fields the legacy projection can carry; anything else on a syllable makes the
# piece unsafe for a pre-0.3.0 writer.
LEGACY_HOLDABLE = {"anchor", "onset", "nucleus", "coda", "lyric"}

_PACKS = {}


def load_pack(pid):
    if pid not in _PACKS:
        with open(os.path.join(PACKS_DIR, pid + ".json"), encoding="utf-8") as f:
            _PACKS[pid] = json.load(f)
    return _PACKS[pid]


# --------------------------------------------------------------------- PROP-7
def resolve_system(piece):
    """Absent system = Hindustani; each missing component takes its default;
    unknown components are kept verbatim."""
    out = dict(HINDUSTANI)
    out.update(piece.get("system") or {})
    return out


def pack_of(piece):
    return load_pack(resolve_system(piece)["phonology"])


def codas_of(pack):
    return pack["consonants"] if pack["codas"] == "consonants" else pack["codas"]


# --------------------------------------------------------------------- helpers
def main(ph):
    grid = ph.get("trajectoryGrid") or [[]]
    return grid[0] if grid else []


def silent(t):
    return t.get("id") == 12


def val(t, k):
    v = t.get(k)
    return None if v is None else v


def has_phonetics(t):
    return any(val(t, k) is not None for k in ("vowel", "startConsonant", "endConsonant"))


def track_flat(track):
    """[(phrase_idx, traj_idx, traj)] over the main string, in order."""
    return [(pi, ti, t) for pi, ph in enumerate(track) for ti, t in enumerate(main(ph))]


# --------------------------------------------------------------------- heal
def first_traj_idxs(trajs):
    """Phrase.firstTrajIdxs (TS) / first_traj_idxs (Python), with null == absent."""
    idxs, ct, silent_trigger = [], 0, False
    last_vowel, end_trigger = None, False
    for i, t in enumerate(trajs):
        if not silent(t):
            c1 = ct == 0
            c3 = val(t, "startConsonant") is not None
            c5 = val(t, "vowel") != last_vowel
            if c1 or silent_trigger or c3 or end_trigger or c5:
                idxs.append(i)
            ct += 1
            end_trigger = val(t, "endConsonant") is not None
            last_vowel = val(t, "vowel")
        silent_trigger = silent(t)
    return idxs


def heal_phrase(ph):
    trajs = main(ph)
    idxs = first_traj_idxs(trajs)
    out = []
    for n, i in enumerate(idxs):
        stop = idxs[n + 1] if n + 1 < len(idxs) else len(trajs)
        span = []
        for t in trajs[i:stop]:
            if silent(t):
                break
            span.append(t)
        first, last = span[0], span[-1]
        syl = {"anchor": {"traj": first["uniqueId"], "t": 0}}
        if val(first, "startConsonant") is not None:
            syl["onset"] = first["startConsonant"]
        vowel = val(first, "vowel")
        if vowel is not None:
            syl["nucleus"] = vowel
        if val(last, "endConsonant") is not None:
            syl["coda"] = last["endConsonant"]
        syl["lyric"] = {"vowel": vowel, "source": "pack"}
        out.append(syl)
    return out


def heal_piece(piece):
    """Normative heal. A phrase that already has `syllables` keeps them (even []).
    A phrase without the key is healed from its legacy fields; if its track has
    no phonetic data on any main-string trajectory, it gets []. Returns a copy."""
    pc = copy.deepcopy(piece)
    for track in pc["phraseGrid"]:
        phonetic = any(has_phonetics(t) for _, _, t in track_flat(track))
        for ph in track:
            if "syllables" not in ph:
                ph["syllables"] = heal_phrase(ph) if phonetic else []
    return pc


# --------------------------------------------------------------------- projection
def _legacy_entry(pack, table, key):
    """-> (iso, hindi, ipa, engTrans) written into the legacy fields for `key`,
    or None when the legacy fields cannot carry it."""
    if key is None or isinstance(key, list):
        return None  # clusters are reduced by the caller
    if pack["id"] == LEGACY_PACK:
        e = pack[table].get(key) if table != "codas" else codas_of(pack).get(key)
        leg = (e or {}).get("legacy")
        if e is None:
            # unknown stored string: today's code keeps it and its copies are undefined
            return (key, None, None, None)
        if leg is None:
            return None  # e.g. the new retroflex ṇa: no legacy form
        return (leg["iso"], leg.get("hindi"), leg.get("ipa"), leg.get("engTrans"))
    # Any other pack projects nothing (Jon, 2026-11-12): all platforms move to
    # the tier together; the write guard refuses pre-0.3.0 saves of such pieces.
    return None


def _cluster_head(key, onset):
    if isinstance(key, list):
        return key[0] if onset else key[-1]
    return key


def spans(track):
    """{anchor uid: [traj, ...]} and the list of uncovered non-silent trajs."""
    anchors = {}
    for ph in track:
        for s in ph.get("syllables") or []:
            anchors[s["anchor"]["traj"]] = s
    out, uncovered, cur = [], [], None
    for _, _, t in track_flat(track):
        if silent(t):
            cur = None
            continue
        uid = t.get("uniqueId")
        if uid in anchors:
            cur = (anchors[uid], [])
            out.append(cur)
        if cur is None:
            uncovered.append(t)
        else:
            cur[1].append(t)
    return out, uncovered


def project_piece(piece):
    """Normative projection syllables -> legacy fields. Returns
    {trajUniqueId: {wire field: value, ..., "art0": {...}|None, "art1": {...}|None}}
    for every main-string trajectory; absent fields are omitted, "art0"/"art1"
    are the 'consonant' articulations at '0.00' / '1.00' (None = none)."""
    pack = pack_of(piece)
    res = {}
    for track in piece["phraseGrid"]:
        sp, uncovered = spans(track)
        for _, _, t in track_flat(track):
            res[t["uniqueId"]] = {"art0": None, "art1": None}
        for syl, trajs in sp:
            v = _legacy_entry(pack, "vowels", (syl.get("lyric") or {}).get("vowel"))
            on = _legacy_entry(pack, "consonants", _cluster_head(syl.get("onset"), True))
            co = _legacy_entry(pack, "codas", _cluster_head(syl.get("coda"), False))
            for t in trajs:
                if v:
                    res[t["uniqueId"]]["vowel"] = v[0]
            for c, where, pre, art in ((on, trajs[0], "startConsonant", "art0"),
                                       (co, trajs[-1], "endConsonant", "art1")):
                if not c:
                    continue
                r = res[where["uniqueId"]]
                for suffix, x in zip(("", "Hindi", "Ipa", "EngTrans"), c):
                    if x is not None:
                        r[pre + suffix] = x
                a = {"name": "consonant", "stroke": c[0]}
                for k, x in zip(("hindi", "ipa", "engTrans"), c[1:]):
                    if x is not None:
                        a[k] = x
                r[art] = a
    return res


def legacy_of_traj(t):
    """The legacy fields as stored on a trajectory, in project_piece's shape."""
    r = {k: t[k] for k in WIRE_FIELDS if t.get(k) is not None}
    arts = t.get("articulations") or {}
    for key, name in (("0.00", "art0"), ("1.00", "art1")):
        a = arts.get(key)
        r[name] = dict(a) if a and a.get("name") == "consonant" else None
    return r


def apply_projection(piece):
    """Write the projection onto a copy of the piece (dual-write)."""
    pc = copy.deepcopy(piece)
    proj = project_piece(pc)
    for track in pc["phraseGrid"]:
        for _, _, t in track_flat(track):
            p = proj[t["uniqueId"]]
            for k in WIRE_FIELDS:
                t.pop(k, None)
                if k in p:
                    t[k] = p[k]
            arts = t.setdefault("articulations", {})
            for key, name in (("0.00", "art0"), ("1.00", "art1")):
                if arts.get(key, {}).get("name") == "consonant":
                    del arts[key]
                if p[name]:
                    arts[key] = p[name]
    return pc


# --------------------------------------------------------------------- derived
def derive_ipa(syl, pack):
    """Jyutping: onset IPA + the final's realization (IPA is derived, never stored)."""
    parts = []
    on = syl.get("onset")
    for k in (on if isinstance(on, list) else [on] if on else []):
        parts.append(pack["consonants"][k]["ipa"])
    if pack.get("finals") is not None:
        fk = (syl.get("nucleus") or "") + (syl.get("coda") or "")
        parts.append(pack["finals"][fk]["ipa"])
    else:
        if syl.get("nucleus"):
            parts.append(pack["vowels"][syl["nucleus"]].get("ipa", ""))
        co = syl.get("coda")
        for k in (co if isinstance(co, list) else [co] if co else []):
            parts.append(codas_of(pack)[k]["ipa"])
    return "".join(parts)


# --------------------------------------------------------------------- invariants
def check_invariants(piece):
    """-> sorted list of violation codes (with location). Empty = valid."""
    pack = pack_of(piece)
    codas = codas_of(pack)
    v = []
    for k, track in enumerate(piece["phraseGrid"]):
        any_syl = any(ph.get("syllables") for ph in track)
        anchored = set()
        for pi, ph in enumerate(track):
            idx = {t.get("uniqueId"): (i, t) for i, t in enumerate(main(ph))}
            last = -1
            for si, s in enumerate(ph.get("syllables") or []):
                where = f"track {k} phrase {pi} syllable {si}"
                a = s["anchor"]
                if a["traj"] not in idx:
                    v.append(("anchor-missing", where))
                    continue
                i, t = idx[a["traj"]]
                if silent(t):
                    v.append(("anchor-silence", where))
                if i <= last:
                    v.append(("anchor-order", where))
                last = i
                anchored.add(a["traj"])
                if a.get("t", 0) != 0:
                    v.append(("anchor-t", where))
                for f, table, flag in (("onset", pack["consonants"], "onsetClusters"),
                                       ("coda", codas, "codaClusters")):
                    x = s.get(f)
                    if isinstance(x, list) and not pack["flags"][flag]:
                        v.append(("cluster-not-allowed", where))
                    for key in (x if isinstance(x, list) else [x] if x is not None else []):
                        if key not in table:
                            v.append(("key-unknown", where))
                nuc = s.get("nucleus")
                if nuc is not None and nuc not in pack["vowels"]:
                    v.append(("key-unknown", where))
                for obs in ("lyric", "sung"):
                    ov = (s.get(obs) or {}).get("vowel")
                    if ov is not None and ov not in pack["vowels"]:
                        v.append(("key-unknown", where))
                if s.get("tone") is not None:
                    if not pack["flags"]["tones"]:
                        v.append(("tone-not-allowed", where))
                    elif s["tone"] not in pack["tones"]:
                        v.append(("key-unknown", where))
                if pack.get("finals") is not None:
                    fk = (nuc or "") + (s.get("coda") or "")
                    f = pack["finals"].get(fk)
                    if f is None:
                        v.append(("final-unknown", where))
                    elif f.get("syllabic") and not pack["flags"]["syllabicNasals"]:
                        v.append(("syllabic-not-allowed", where))
                elif nuc is None and not pack["flags"]["nucleusOptional"]:
                    v.append(("nucleus-missing", where))
        if any_syl:
            prev_silent = True  # the track start counts as a silence
            for pi, ti, t in track_flat(track):
                if not silent(t) and prev_silent and t.get("uniqueId") not in anchored:
                    v.append(("unanchored-start", f"track {k} phrase {pi} traj {ti}"))
                prev_silent = silent(t)
    return sorted(v)


# --------------------------------------------------------------------- write guard
def _comparable(syls):
    """Syllables as the legacy fields can express them (lyric.source dropped)."""
    out = []
    for s in syls:
        c = {"traj": s["anchor"]["traj"], "t": s["anchor"].get("t", 0)}
        for f in ("onset", "nucleus", "coda"):
            if s.get(f) is not None:
                c[f] = s[f]
        c["vowel"] = (s.get("lyric") or {}).get("vowel")
        out.append(c)
    return out


def legacy_safe(piece):
    """PROP-8 write guard. True when a pre-0.3.0 client may save this piece:
    dropping its syllables loses nothing, because heal(project(piece)) rebuilds
    them. -> (bool, sorted reason codes)."""
    reasons = set()
    pack = pack_of(piece)
    if pack["id"] != LEGACY_PACK:
        reasons.add("pack")
    for track in piece["phraseGrid"]:
        for ph in track:
            for s in ph.get("syllables") or []:
                for f in s:
                    if f not in LEGACY_HOLDABLE:
                        reasons.add(f)
                if s["anchor"].get("t", 0) != 0:
                    reasons.add("anchorT")
                for f in ("onset", "coda"):
                    if isinstance(s.get(f), list):
                        reasons.add("cluster")
                if pack["id"] == LEGACY_PACK:
                    for f, table in (("onset", "consonants"), ("coda", "codas")):
                        k = s.get(f)
                        if isinstance(k, str) and k in codas_of(pack) and \
                                "legacy" not in codas_of(pack)[k]:
                            reasons.add("key")
    if not reasons:
        rebuilt = heal_piece(strip_syllables(apply_projection(piece)))
        for ta, tb in zip(piece["phraseGrid"], rebuilt["phraseGrid"]):
            for pa, pb in zip(ta, tb):
                if _comparable(pa.get("syllables") or []) != _comparable(pb["syllables"]):
                    reasons.add("boundary")
    return (not reasons, sorted(reasons))


def strip_syllables(piece):
    """What a pre-0.3.0 client's save leaves: the syllable tier dropped."""
    pc = copy.deepcopy(piece)
    for track in pc["phraseGrid"]:
        for ph in track:
            ph.pop("syllables", None)
    return pc


# --------------------------------------------------------------------- re-homing
def rehome(before, after):
    """Run after every phrase split, merge or moved division. `before` is the
    piece as it was before the edit, `after` the piece the edit produced
    (whatever its phrases' syllable lists now hold is ignored). Every syllable
    of a track before the edit moves to the phrase of that track that now
    holds its anchor trajectory, in trajectory order. Pooling from `before`
    matters for a merge, which deletes a phrase and its list. Syllables whose
    trajectory no longer exists are dropped (deleting a trajectory deletes the
    syllable that starts on it). -> (piece copy, dropped anchor uids)."""
    pc = copy.deepcopy(after)
    dropped = []
    for k, track in enumerate(pc["phraseGrid"]):
        where = {t.get("uniqueId"): (pi, ti) for pi, ti, t in track_flat(track)}
        old = before["phraseGrid"][k] if k < len(before["phraseGrid"]) else []
        pool = [s for ph in old for s in ph.get("syllables") or []]
        buckets = [[] for _ in track]
        for s in pool:
            loc = where.get(s["anchor"]["traj"])
            if loc is None:
                dropped.append(s["anchor"]["traj"])
                continue
            buckets[loc[0]].append((loc[1], s))
        for ph, b in zip(track, buckets):
            ph["syllables"] = [s for _, s in sorted(b, key=lambda x: x[0])]
    return pc, dropped
