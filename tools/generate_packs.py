#!/usr/bin/env python3
"""Generate packs/<id>.json (PROP-9 phoneme packs as data).

Three packs: hindi-urdu (from the tables compiled into idtap-platform
src/ts/model/trajectory.ts, bugs fixed, legacy forms kept for the projection),
jyutping (LSHK scheme; Yingyao Yu's inventory, cross-checked against
jyutping.org and Wikipedia), kurmanji (Seba Kayan's overview for IDTAP, from
Thackston 2006 and Haig & Opengin 2015).

Run:  python3 tools/generate_packs.py      (writes packs/*.json)
The validator checks every pack against schemas/pack.schema.json and checks
that hindi-urdu's `legacy` blocks reproduce `legacyTables` exactly.
"""
import json, os, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "packs")

# --------------------------------------------------------------------------
# hindi-urdu
# --------------------------------------------------------------------------
# Verbatim from idtap-platform src/ts/model/trajectory.ts (constructor), as of
# platform commit 7b510d2e. Same arrays in idtap-client idtap/classes/trajectory.py.
C_IPAS = ['k', 'kʰ', 'g', 'gʱ', 'ŋ', 'c', 'cʰ', 'ɟ', 'ɟʱ', 'ɲ', 'ʈ',
          'ʈʰ', 'ɖ', 'ɖʱ', 'n', 't', 'tʰ', 'd', 'dʱ', 'n̪', 'p', 'pʰ', 'b', 'bʱ',
          'm', 'j', 'r', 'l', 'v', 'ʃ', 'ʂ', 's', 'h']
C_ISOS = ['ka', 'kha', 'ga', 'gha', 'ṅa', 'ca', 'cha', 'ja', 'jha',
          'ña', 'ṭa', 'ṭha', 'ḍa', 'ḍha', 'na', 'ta', 'tha', 'da', 'dha', 'na',
          'pa', 'pha', 'ba', 'bha', 'ma', 'ya', 'ra', 'la', 'va', 'śa', 'ṣa', 'sa',
          'ha']
C_HINDIS = ['क', 'ख', 'ग', 'घ', 'ङ', 'च', 'छ', 'ज', 'झ', 'ञ', 'ट',
            'ठ', 'ड', 'ढ', 'न', 'त', 'थ', 'द', 'ध', 'न', 'प', 'फ़', 'ब', 'भ', 'म', 'य',
            'र', 'ल', 'व', 'श', 'ष', 'स', 'ह']
C_ENGTRANS = ['k', 'kh', 'g', 'gh', 'ṅ', 'c', 'ch', 'j', 'jh', 'ñ', 'ṭ',
              'ṭh', 'ḍ', 'ḍh', 'n', 't', 'th', 'd', 'dh', 'n', 'p', 'ph', 'b', 'bh',
              'm', 'y', 'r', 'l', 'v', 'ś', 'ṣ', 's', 'h']
V_IPAS = ['ə', 'aː', 'ɪ', 'iː', 'ʊ', 'uː', 'eː', 'ɛː', 'oː', 'ɔː', '_']
V_ISOS = ['a', 'ā', 'i', 'ī', 'u', 'ū', 'ē', 'ai', 'ō', 'au', '_']
V_HINDIS = ['अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ए', 'ऐ', 'ओ', 'औ', '_']
V_ENGTRANS = ['a', 'ā', 'i', 'ī', 'u', 'ū', 'ē', 'ai', 'ō', 'au', '_']

# Feature axes per consonant, as in idtap-client ConsonantSpec (idtap/synthesis/
# consonants.py). `ipa` here is the CORRECTED phoneme; the legacy block keeps
# what today's tables print.
# key: (ipa, place, manner, voiced, aspirated, Deva, Latn, Arab)
HINDI_CONSONANTS = [
    ('ka',  'k',  'velar', 'stop', False, False, 'क', 'k', 'ک'),
    ('kha', 'kʰ', 'velar', 'stop', False, True,  'ख', 'kh', 'کھ'),
    ('ga',  'g',  'velar', 'stop', True,  False, 'ग', 'g', 'گ'),
    ('gha', 'gʱ', 'velar', 'stop', True,  True,  'घ', 'gh', 'گھ'),
    ('ṅa',  'ŋ',  'velar', 'nasal', True, False, 'ङ', 'ṅ', 'ن'),
    ('ca',  'c',  'palatal', 'affricate', False, False, 'च', 'c', 'چ'),
    ('cha', 'cʰ', 'palatal', 'affricate', False, True,  'छ', 'ch', 'چھ'),
    ('ja',  'ɟ',  'palatal', 'affricate', True,  False, 'ज', 'j', 'ج'),
    ('jha', 'ɟʱ', 'palatal', 'affricate', True,  True,  'झ', 'jh', 'جھ'),
    ('ña',  'ɲ',  'palatal', 'nasal', True, False, 'ञ', 'ñ', 'ن'),
    ('ṭa',  'ʈ',  'retroflex', 'stop', False, False, 'ट', 'ṭ', 'ٹ'),
    ('ṭha', 'ʈʰ', 'retroflex', 'stop', False, True,  'ठ', 'ṭh', 'ٹھ'),
    ('ḍa',  'ɖ',  'retroflex', 'stop', True,  False, 'ड', 'ḍ', 'ڈ'),
    ('ḍha', 'ɖʱ', 'retroflex', 'stop', True,  True,  'ढ', 'ḍh', 'ڈھ'),
    # NEW (bug 1): the retroflex nasal had no entry; slot 14 was labelled न/na.
    ('ṇa',  'ɳ',  'retroflex', 'nasal', True, False, 'ण', 'ṇ', 'ن'),
    ('ta',  't',  'dental', 'stop', False, False, 'त', 't', 'ت'),
    ('tha', 'tʰ', 'dental', 'stop', False, True,  'थ', 'th', 'تھ'),
    ('da',  'd',  'dental', 'stop', True,  False, 'द', 'd', 'د'),
    ('dha', 'dʱ', 'dental', 'stop', True,  True,  'ध', 'dh', 'دھ'),
    # bug 2: `na` appeared at legacy indices 14 and 19; one key now, dental.
    ('na',  'n̪',  'dental', 'nasal', True, False, 'न', 'n', 'ن'),
    ('pa',  'p',  'labial', 'stop', False, False, 'प', 'p', 'پ'),
    # bug 3: the table printed फ़ (fa, nukta) where फ (pha) belongs.
    ('pha', 'pʰ', 'labial', 'stop', False, True,  'फ', 'ph', 'پھ'),
    ('ba',  'b',  'labial', 'stop', True,  False, 'ब', 'b', 'ب'),
    ('bha', 'bʱ', 'labial', 'stop', True,  True,  'भ', 'bh', 'بھ'),
    ('ma',  'm',  'labial', 'nasal', True, False, 'म', 'm', 'م'),
    ('ya',  'j',  'palatal', 'approximant', True, False, 'य', 'y', 'ی'),
    ('ra',  'r',  'dental', 'trill', True, False, 'र', 'r', 'ر'),
    ('la',  'l',  'dental', 'lateral', True, False, 'ल', 'l', 'ل'),
    ('va',  'v',  'labiodental', 'approximant', True, False, 'व', 'v', 'و'),
    ('śa',  'ʃ',  'postalveolar', 'fricative', False, False, 'श', 'ś', 'ش'),
    ('ṣa',  'ʂ',  'retroflex', 'fricative', False, False, 'ष', 'ṣ', 'ش'),
    ('sa',  's',  'dental', 'fricative', False, False, 'स', 's', 'س'),
    ('ha',  'h',  'glottal', 'fricative', False, True, 'ह', 'h', 'ہ'),
]

# key: (ipa, height, backness, rounded, length, Deva)
HINDI_VOWELS = [
    ('a',  'ə',  'mid', 'central', False, 'short', 'अ'),
    ('ā',  'aː', 'open', 'central', False, 'long', 'आ'),
    ('i',  'ɪ',  'near-close', 'front', False, 'short', 'इ'),
    ('ī',  'iː', 'close', 'front', False, 'long', 'ई'),
    ('u',  'ʊ',  'near-close', 'back', True, 'short', 'उ'),
    ('ū',  'uː', 'close', 'back', True, 'long', 'ऊ'),
    ('ē',  'eː', 'close-mid', 'front', False, 'long', 'ए'),
    ('ai', 'ɛː', 'open-mid', 'front', False, 'long', 'ऐ'),
    ('ō',  'oː', 'close-mid', 'back', True, 'long', 'ओ'),
    ('au', 'ɔː', 'open-mid', 'back', True, 'long', 'औ'),
]


def legacy_consonant(key):
    """What today's code writes for a stored iso key: tables[indexOf(key)]."""
    if key not in C_ISOS:
        return None
    i = C_ISOS.index(key)
    return {"iso": key, "hindi": C_HINDIS[i], "ipa": C_IPAS[i], "engTrans": C_ENGTRANS[i]}


def legacy_vowel(key):
    if key not in V_ISOS:
        return None
    i = V_ISOS.index(key)
    return {"iso": key, "hindi": V_HINDIS[i], "ipa": V_IPAS[i], "engTrans": V_ENGTRANS[i]}


def hindi_urdu():
    cons = {}
    for key, ipa, place, manner, voiced, asp, deva, latn, arab in HINDI_CONSONANTS:
        e = {"ipa": ipa, "place": place, "manner": manner, "voiced": voiced,
             "aspirated": asp, "display": {"Deva": deva, "Latn": latn, "Arab": arab}}
        leg = legacy_consonant(key)
        if leg:
            e["legacy"] = leg
        cons[key] = e
    vows = {}
    for key, ipa, h, b, r, ln, deva in HINDI_VOWELS:
        vows[key] = {"ipa": ipa, "height": h, "backness": b, "rounded": r, "length": ln,
                     "display": {"Deva": deva, "Latn": key}, "legacy": legacy_vowel(key)}
    vows["_"] = {"placeholder": True, "display": {"Deva": "_", "Latn": "_"},
                 "legacy": legacy_vowel("_"),
                 "note": "Legacy placeholder in the vowel tables (no vowel sung). Kept so every stored value heals; the formant tables map it like 'a'."}
    return {
        "id": "hindi-urdu",
        "name": "Hindi / Urdu (Hindustani vocal)",
        "packVersion": "1.1.0",
        "status": "complete",
        "keyScheme": "ISO 15919, consonants with the inherent a (ka, kha, ...), as stored in Trajectory.startConsonant/endConsonant/vowel since 2022.",
        "scripts": ["Deva", "Latn", "Arab"],
        "sources": [
            "idtap-platform src/ts/model/trajectory.ts constructor tables (cIpas, cIsos, cHindis, cEngTrans, vIpas, vIsos, vHindis, vEngTrans), platform 7b510d2e",
            "idtap-client idtap/synthesis/consonants.py ConsonantSpec feature axes",
        ],
        "notes": [
            "Keys are the legacy iso strings, so the PROP-8 heal is a copy: onset = startConsonant, coda = endConsonant, nucleus = lyric.vowel = vowel.",
            "`legacy` on an entry is exactly what today's code writes for that key (tables[indexOf(key)], first match). The PROP-8 projection writes it, so a legacy round trip is byte-identical. `ipa` and `display` are the corrected forms for new UI.",
            "Three table bugs are fixed in ipa/display and listed in DIVERGENCES.md PACK-1: no retroflex ṇa (now its own key, no legacy form); `na` at indices 14 and 19 (one key, dental n̪; legacy form keeps index 14's ipa 'n'); फ़ printed for pha (display फ; legacy keeps फ़).",
            "Arab display forms are Urdu consonant letters and have not been reviewed by an Urdu reader. Urdu vowel forms depend on position in the word and are not given.",
        ],
        "unverified": ["consonants.*.display.Arab"],
        "flags": {"syllabicNasals": False, "onsetClusters": False, "codaClusters": False,
                  "tones": False, "nucleusOptional": True, "legacyExact": True},
        "consonants": cons,
        "codas": "consonants",
        "vowels": vows,
        "legacyTables": {"cIpas": C_IPAS, "cIsos": C_ISOS, "cHindis": C_HINDIS,
                         "cEngTrans": C_ENGTRANS, "vIpas": V_IPAS, "vIsos": V_ISOS,
                         "vHindis": V_HINDIS, "vEngTrans": V_ENGTRANS},
    }


# --------------------------------------------------------------------------
# jyutping
# --------------------------------------------------------------------------
# onset key: (ipa, place, manner, voiced, aspirated, labialized)
JYUT_ONSETS = [
    ('b',  'p',   'labial', 'stop', False, False, False),
    ('p',  'pʰ',  'labial', 'stop', False, True,  False),
    ('m',  'm',   'labial', 'nasal', True, False, False),
    ('f',  'f',   'labiodental', 'fricative', False, False, False),
    ('d',  't',   'alveolar', 'stop', False, False, False),
    ('t',  'tʰ',  'alveolar', 'stop', False, True,  False),
    ('n',  'n',   'alveolar', 'nasal', True, False, False),
    ('l',  'l',   'alveolar', 'lateral', True, False, False),
    ('g',  'k',   'velar', 'stop', False, False, False),
    ('k',  'kʰ',  'velar', 'stop', False, True,  False),
    ('ng', 'ŋ',   'velar', 'nasal', True, False, False),
    ('h',  'h',   'glottal', 'fricative', False, False, False),
    ('gw', 'kʷ',  'velar', 'stop', False, False, True),
    ('kw', 'kʷʰ', 'velar', 'stop', False, True,  True),
    ('w',  'w',   'labiovelar', 'approximant', True, False, False),
    ('z',  't͡s', 'alveolar', 'affricate', False, False, False),
    ('c',  't͡sʰ', 'alveolar', 'affricate', False, True, False),
    ('s',  's',   'alveolar', 'fricative', False, False, False),
    ('j',  'j',   'palatal', 'approximant', True, False, False),
]
# coda key: (ipa, place, manner, voiced)
JYUT_CODAS = [
    ('i',  'i̯', 'palatal', 'approximant', True),
    ('u',  'u̯', 'labiovelar', 'approximant', True),
    ('m',  'm',  'labial', 'nasal', True),
    ('n',  'n',  'alveolar', 'nasal', True),
    ('ng', 'ŋ',  'velar', 'nasal', True),
    ('p',  'p̚', 'labial', 'stop', False),
    ('t',  't̚', 'alveolar', 'stop', False),
    ('k',  'k̚', 'velar', 'stop', False),
]
# nucleus key: (base ipa, height, backness, rounded, length)
JYUT_NUCLEI = [
    ('aa', 'aː', 'open', 'central', False, 'long'),
    ('a',  'ɐ',  'near-open', 'central', False, 'short'),
    ('e',  'ɛː', 'open-mid', 'front', False, 'long'),
    ('i',  'iː', 'close', 'front', False, 'long'),
    ('o',  'ɔː', 'open-mid', 'back', True, 'long'),
    ('u',  'uː', 'close', 'back', True, 'long'),
    ('eo', 'ɵ',  'close-mid', 'central', True, 'short'),
    ('oe', 'œː', 'open-mid', 'front', True, 'long'),
    ('yu', 'yː', 'close', 'front', True, 'long'),
]
# final: (nucleus, coda, ipa). jyutping.org chart (57) + syllabic m, ng = 59.
JYUT_FINALS = [
    ('aa', None, 'aː'), ('aa', 'i', 'aːi̯'), ('aa', 'u', 'aːu̯'), ('aa', 'm', 'aːm'),
    ('aa', 'n', 'aːn'), ('aa', 'ng', 'aːŋ'), ('aa', 'p', 'aːp̚'), ('aa', 't', 'aːt̚'),
    ('aa', 'k', 'aːk̚'),
    ('a', None, 'ɐ'), ('a', 'i', 'ɐi̯'), ('a', 'u', 'ɐu̯'), ('a', 'm', 'ɐm'),
    ('a', 'n', 'ɐn'), ('a', 'ng', 'ɐŋ'), ('a', 'p', 'ɐp̚'), ('a', 't', 'ɐt̚'),
    ('a', 'k', 'ɐk̚'),
    ('e', None, 'ɛː'), ('e', 'i', 'ei̯'), ('e', 'u', 'ɛːu̯'), ('e', 'm', 'ɛːm'),
    ('e', 'ng', 'ɛːŋ'), ('e', 'p', 'ɛːp̚'), ('e', 't', 'ɛːt̚'), ('e', 'k', 'ɛːk̚'),
    ('i', None, 'iː'), ('i', 'u', 'iːu̯'), ('i', 'm', 'iːm'), ('i', 'n', 'iːn'),
    ('i', 'ng', 'eŋ'), ('i', 'p', 'iːp̚'), ('i', 't', 'iːt̚'), ('i', 'k', 'ek̚'),
    ('o', None, 'ɔː'), ('o', 'i', 'ɔːy̯'), ('o', 'u', 'ou̯'), ('o', 'n', 'ɔːn'),
    ('o', 'ng', 'ɔːŋ'), ('o', 't', 'ɔːt̚'), ('o', 'k', 'ɔːk̚'),
    ('u', None, 'uː'), ('u', 'i', 'uːy̯'), ('u', 'n', 'uːn'), ('u', 'ng', 'oŋ'),
    ('u', 't', 'uːt̚'), ('u', 'k', 'ok̚'),
    ('eo', 'i', 'ɵy̯'), ('eo', 'n', 'ɵn'), ('eo', 't', 'ɵt̚'),
    ('oe', None, 'œː'), ('oe', 'ng', 'œːŋ'), ('oe', 't', 'œːt̚'), ('oe', 'k', 'œːk̚'),
    ('yu', None, 'yː'), ('yu', 'n', 'yːn'), ('yu', 't', 'yːt̚'),
    (None, 'm', 'm̩'), (None, 'ng', 'ŋ̍'),
]
JYUT_RARE = {"a": "elided casual speech only (sei3 a6 sei3); added to Jyutping 2018",
             "eu": "colloquial (deu6 掉)", "em": "colloquial (lem2 舐)",
             "ep": "colloquial (gep6 夾)", "oet": "onomatopoeia only (oet6, goet4); added 2018"}


def jyutping():
    onsets = {}
    for key, ipa, place, manner, voiced, asp, lab in JYUT_ONSETS:
        e = {"ipa": ipa, "place": place, "manner": manner, "voiced": voiced,
             "aspirated": asp, "display": {"Latn": key}}
        if lab:
            e["labialized"] = True
        onsets[key] = e
    codas = {}
    for key, ipa, place, manner, voiced in JYUT_CODAS:
        codas[key] = {"ipa": ipa, "place": place, "manner": manner, "voiced": voiced,
                      "aspirated": False, "display": {"Latn": key}}
    nuclei = {}
    for key, ipa, h, b, r, ln in JYUT_NUCLEI:
        nuclei[key] = {"ipa": ipa, "height": h, "backness": b, "rounded": r, "length": ln,
                       "display": {"Latn": key}}
    finals = {}
    for nuc, coda, ipa in JYUT_FINALS:
        key = (nuc or "") + (coda or "")
        e = {"nucleus": nuc, "coda": coda, "ipa": ipa}
        if key in JYUT_RARE:
            e["note"] = JYUT_RARE[key]
        if nuc is None:
            e["syllabic"] = True
        finals[key] = e
    assert len(finals) == 59, len(finals)
    return {
        "id": "jyutping",
        "name": "Cantonese (Jyutping)",
        "packVersion": "0.2.0",
        "status": "draft: pending review by Yingyao Yu",
        "keyScheme": "LSHK Jyutping letters. A syllable stores onset, nucleus and coda as Jyutping letters and tone as its digit; IPA is derived from `finals`, never stored.",
        "scripts": ["Latn", "Hant"],
        "sources": [
            "Yingyao Yu's Jyutping inventory for IDTAP (19 onsets + null; nuclei aa a e eo i o oe u yu; codas -i -u -m -n -ng -p -t -k; 60 finals; 6 tones; syllabic m and ng)",
            "https://jyutping.org/en/jyutping/ (finals chart section 3.3, tone table), read 2026-11-12",
            "https://en.wikipedia.org/wiki/Jyutping (finals grid, colloquial footnotes), read 2026-11-12",
        ],
        "notes": [
            "Finals are enumerated, not nucleus x coda: the nucleus quality depends on the coda (i before ng/k is [e], u before ng/k is [o], o before u is [o], e before i is [e]).",
            "Finals IPA follows jyutping.org's chart. Wikipedia writes ing/ik as [ɪŋ ɪk] and ung/uk as [ʊŋ ʊk]; both are common transcriptions of the same sounds.",
            "Orthography (characters) is free text on the syllable: no validation or lookup in 0.3.0.",
            "No `legacy` blocks (Jon, 2026-11-12): every platform moves to the syllable tier together, so a non-Hindi piece projects nothing into the pre-0.3.0 per-trajectory fields. The write guard is the only protection against a pre-0.3.0 save.",
        ],
        "unverified": [
            "finals: Yingyao's inventory counts 60 finals; jyutping.org and Wikipedia give 57 + syllabic m, ng = 59. Candidates for the 60th: bare eo (jyutping.org section 3.1 lists 'eo [ɵ]'), en, um, up (chart labels with no example character).",
            "tones.*.chao: Yingyao gives 55 25 33 21 23 22; jyutping.org gives 55 35 33 21 13 22 (tones 2 and 5 differ in starting height). `chao` holds Yingyao's values, `chaoAlt` jyutping.org's.",
        ],
        "flags": {"syllabicNasals": True, "onsetClusters": False, "codaClusters": False,
                  "tones": True, "nucleusOptional": False, "legacyExact": False},
        "consonants": onsets,
        "codas": codas,
        "vowels": nuclei,
        "finals": finals,
        "tones": {
            "1": {"chao": "55", "chaoAlt": "55", "name": "high level", "checkedChao": "5"},
            "2": {"chao": "25", "chaoAlt": "35", "name": "mid rising"},
            "3": {"chao": "33", "chaoAlt": "33", "name": "mid level", "checkedChao": "3"},
            "4": {"chao": "21", "chaoAlt": "21", "name": "low falling"},
            "5": {"chao": "23", "chaoAlt": "13", "name": "low rising"},
            "6": {"chao": "22", "chaoAlt": "22", "name": "low level", "checkedChao": "2"},
        },
        "toneSystems": {
            "nine": {
                "description": "The traditional nine-tone count (ILE). Stored tone stays 1-6 (Jyutping); the nine-tone number is derived from (tone, coda): on a checked syllable (coda p, t or k) tones 1, 3, 6 are 7, 8, 9. Lossless both ways. A checked syllable with any other tone (a colloquial changed tone, e.g. 2) keeps its number.",
                "checkedCodas": ["p", "t", "k"],
                "checked": {"1": "7", "3": "8", "6": "9"},
            },
        },
        "toneNotes": "Checked (entering) syllables, finals in -p -t -k, take tones 1, 3, 6 in Jyutping (ILE 7, 8, 9); `checkedChao` is their short contour. Tone is a label on the syllable in 0.3.0; contours are reference shapes for later overlay and query work.",
    }


# --------------------------------------------------------------------------
# kurmanji
# --------------------------------------------------------------------------
U = "̱"  # combining macron below: Thackston's underline
# key: (ipa, place, manner, voiced, aspirated, pharyngealized, note)
KUR_CONSONANTS = [
    ('b', 'b', 'labial', 'stop', True, False, False, None),
    ('c', 'd͡ʒ', 'postalveolar', 'affricate', True, False, False, None),
    ('ç', 't͡ʃʰ', 'postalveolar', 'affricate', False, True, False, None),
    ('ç' + U, 't͡ʃˤ', 'postalveolar', 'affricate', False, False, True,
     "Thackston's underlined ç: unaspirated, pharyngealized; not maintained by all speakers (p. 4)."),
    ('d', 'd', 'alveolar', 'stop', True, False, False, None),
    ('f', 'f', 'labiodental', 'fricative', False, False, False, None),
    ('g', 'g', 'velar', 'stop', True, False, False, None),
    ('h', 'h', 'glottal', 'fricative', False, False, False, None),
    ('ḥ', 'ħ', 'pharyngeal', 'fricative', False, False, False,
     "Thackston's underlined h; elsewhere not distinguished from h."),
    ('j', 'ʒ', 'postalveolar', 'fricative', True, False, False, None),
    ('k', 'kʰ', 'velar', 'stop', False, True, False, None),
    ('k' + U, 'kˤ', 'velar', 'stop', False, False, True,
     "Thackston's underlined k: unaspirated, pharyngealized; not maintained by all speakers."),
    ('l', 'l', 'alveolar', 'lateral', True, False, False, None),
    ('m', 'm', 'labial', 'nasal', True, False, False, None),
    ('n', 'n', 'alveolar', 'nasal', True, False, False, None),
    ('p', 'pʰ', 'labial', 'stop', False, True, False, None),
    ('p' + U, 'pˤ', 'labial', 'stop', False, False, True,
     "Thackston's underlined p: unaspirated, pharyngealized; not maintained by all speakers."),
    ('q', 'q', 'uvular', 'stop', False, False, False, None),
    ('r', 'ɾ', 'alveolar', 'flap', True, False, False, "Flap; does not occur word-initially."),
    ('rr', 'r', 'alveolar', 'trill', True, False, False,
     "Trill; every initial r is trilled. Spelled rr only sporadically (pirr); a transcriber writes rr wherever a trill is heard."),
    ('s', 's', 'alveolar', 'fricative', False, False, False, None),
    ('ş', 'ʃ', 'postalveolar', 'fricative', False, False, False, None),
    ('t', 'tʰ', 'alveolar', 'stop', False, True, False, None),
    ('t' + U, 'tˤ', 'alveolar', 'stop', False, False, True,
     "Thackston's underlined t: unaspirated, pharyngealized; not maintained by all speakers."),
    ('v', 'v', 'labiodental', 'fricative', True, False, False, None),
    ('w', 'w', 'labiovelar', 'approximant', True, False, False, None),
    ('x', 'x', 'velar', 'fricative', False, False, False, None),
    ('x' + U, 'ɣ', 'velar', 'fricative', True, False, False,
     "Thackston's underlined x, the voiced counterpart of x (Arabic ghayn)."),
    ('y', 'j', 'palatal', 'approximant', True, False, False, None),
    ('z', 'z', 'alveolar', 'fricative', True, False, False, None),
    ('ʿ', 'ʕ', 'pharyngeal', 'fricative', True, False, False,
     "Not part of the orthography; marks Arabic 'ayn in Thackston's vocabulary."),
]
# key: (ipa, height, backness, rounded, length, example, variants)
KUR_VOWELS = [
    ('î', 'i', 'close', 'front', False, 'long', 'nîv [niv] half', []),
    ('i', 'ɪ', 'near-close', 'front', False, 'short', 'dil [dɪl] heart',
     [{"ipa": "ɨ", "context": "often in closed syllables ending in m", "example": "vedixwim [ˈvædɪxwɨm] I drink"}]),
    ('ê', 'e', 'close-mid', 'front', False, 'long', 'hêz [hez] power', []),
    ('e', 'æ', 'near-open', 'front', False, 'short', 'berhem [bæɾˈhæm] product',
     [{"ipa": "ə", "context": "in the sequence ew", "example": "ew [əw] that"},
      {"ipa": "ɛ", "context": "followed by y in another syllable", "example": "odeya [oˈdɛjɑ] room"},
      {"ipa": "ɛ", "context": "after the stress, particularly word-finally", "example": "miróvek [mɪˈrovɛk] a man"}]),
    ('û', 'u', 'close', 'back', True, 'long', 'bûn [bun] to be', []),
    ('u', 'ʊ', 'near-close', 'back', True, 'short', 'du [dʊ] two',
     [{"ipa": "ɯɛ", "context": "after g and k for some speakers, particularly in closed syllables", "example": "gur [gɯɛɾ] or [gʊɾ] wolf", "unverified": True}]),
    ('o', 'o', 'close-mid', 'back', True, 'long', 'nod [nod] ninety', []),
    ('a', 'ɑ', 'open', 'back', False, 'long', 'bav [bɑv] father', []),
]


def kurmanji():
    cons = {}
    for key, ipa, place, manner, voiced, asp, phar, note in KUR_CONSONANTS:
        e = {"ipa": ipa, "place": place, "manner": manner, "voiced": voiced,
             "aspirated": asp, "display": {"Latn": key}}
        if phar:
            e["pharyngealized"] = True
        if note:
            e["note"] = note
        cons[key] = e
    cons["w"]["variants"] = [{"ipa": "ɯ", "context": "before i, î, ê (Thackston)", "unverified": True,
                              "note": "[ɯ] is a vowel symbol; the glide would be [ɰ] or non-syllabic [ɯ]. Thackston's French comparison (cuire, huit) points to [ɥ], a rounded glide."}]
    cons["x"]["variants"] = [{"ipa": "χ", "context": "uvular realization", "unverified": True,
                              "note": "Thackston calls x uvular but writes the velar symbol; not yet verified for Gazîn's recording."}]
    cons["x" + U]["variants"] = [{"ipa": "ʁ", "context": "uvular realization", "unverified": True,
                                  "note": "As for x: velar or uvular not yet verified."}]
    vows = {}
    for key, ipa, h, b, r, ln, ex, var in KUR_VOWELS:
        e = {"ipa": ipa, "height": h, "backness": b, "rounded": r, "length": ln,
             "display": {"Latn": key}, "example": ex}
        if var:
            e["variants"] = var
        vows[key] = e
    vows["e"]["note"] = "Thackston takes [æ] as the reference pronunciation; many speakers are closer to [ɛ]."
    return {
        "id": "kurmanji",
        "name": "Kurmanji Kurdish",
        "packVersion": "0.2.0",
        "status": "draft: pending review by Seba Kayan",
        "keyScheme": "Kurmanji Latin (Hawar) letters. Thackston's underlined letters, which the spelling does not distinguish, are written with U+0331 COMBINING MACRON BELOW (p̱ ç̱ x̱), or the precomposed letter where Unicode has one (ṯ U+1E6F, ḵ U+1E35); keys are NFC; pharyngeal h is ḥ; the trill is rr; 'ayn is ʿ.",
        "scripts": ["Latn"],
        "sources": [
            "Seba Kayan, 'Kurmanji Kurdish: Vowels and Consonants' (overview for IDTAP, 2026-11-11)",
            "Thackston, W. M. (2006). Kurmanji Kurdish: A Reference Grammar with Selected Readings, pp. 1-6",
            "Haig, G. and Öpengin, E. (2015 draft). Kurmanji Kurdish in Turkey: Structure, Varieties, and Status, pp. 11-13",
        ],
        "notes": [
            "Syllable = onset (one or more consonants, e.g. xw) + vowel + optional coda. Clusters are arrays of keys on the syllable.",
            "Context variants are realizations, not separate phonemes: the syllable stores the letter; a variant is something `sung` may record.",
            "Test piece: Dengbêj Gazîn, 'Her wayê wayê wayê' (Çakır ed. 2026, song record 152).",
            "Arabic-script (Kurdish) display forms are not given yet.",
            "No `legacy` blocks (Jon, 2026-11-12): every platform moves to the syllable tier together, so a non-Hindi piece projects nothing into the pre-0.3.0 per-trajectory fields. The write guard is the only protection against a pre-0.3.0 save.",
        ],
        "unverified": [
            "consonants.w.variants: the [ɯ] glide before front vowels",
            "consonants.x / x̱: velar [x ɣ] versus uvular [χ ʁ]",
            "vowels.u.variants: [ɯɛ] after g, k",
        ],
        "flags": {"syllabicNasals": False, "onsetClusters": True, "codaClusters": True,
                  "tones": False, "nucleusOptional": False, "legacyExact": False},
        "consonants": cons,
        "codas": "consonants",
        "vowels": vows,
    }


def nfc_keys(pack):
    """Pack keys are NFC (2026-11-13): Kurmanji's underlined k and t have
    precomposed forms (U+1E35, U+1E6F); p, c-cedilla and x keep U+0331."""
    for table in ("consonants", "vowels", "codas", "finals", "tones"):
        if isinstance(pack.get(table), dict):
            pack[table] = {unicodedata.normalize("NFC", k): v for k, v in pack[table].items()}
    return pack


HINTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hints-draft.json")


def add_hints(pack):
    """Attach the drafted 'sounds like' hints (display only, status 'proposed')."""
    hints = json.load(open(HINTS, encoding="utf-8"))["packs"].get(pack["id"], {})
    for table in ("consonants", "codas", "vowels", "tones"):
        entries = hints.get(table) or {}
        target = pack["consonants"] if table == "codas" and pack.get("codas") == "consonants" else pack.get(table)
        for key, hint in entries.items():
            if not isinstance(target, dict) or key not in target:
                raise SystemExit(f"hint for unknown {pack['id']} {table} key {key!r}")
            target[key]["hint"] = hint
    return pack


def main():
    os.makedirs(OUT, exist_ok=True)
    for pack in (add_hints(nfc_keys(p())) for p in (hindi_urdu, jyutping, kurmanji)):
        path = os.path.join(OUT, pack["id"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
