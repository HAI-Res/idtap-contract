# Proposals

Design decisions made during contract review.

**✅ STATUS (2026-07-13): PROP-1/2/3 IMPLEMENTED + MERGED in both clients** — TS via
`jon-myers/idtap#2`, Python via `jon-myers/Python-API#1`. Enforced by contract
conformance in both repos' CI. The text below is retained as the rationale/record.

---

## PROP-1 — Serialize `ruleSet` in the piece's raga (self-contained ragas)

**Decision (2026-07-10):** add `ruleSet` to the serialized Raga so every piece is
self-contained and can be interpreted without a live DB lookup. Resolves the whole
RAGA-1/2/3 cluster in `DIVERGENCES.md`.

### Why
- **Self-containment.** Today the ruleSet is fetched from the `ragas` DB collection
  by raga *name* at load time (`getRaagRule`) and injected before `Piece.fromJSON`.
  That makes a saved piece un-interpretable without a successful DB round-trip — the
  same "data needs external context" failure class as the Yaman pitch bug. A failed
  fetch silently falls back to Yaman → wrong pitches, no error.
- **Cheap.** Unlike the per-pitch `ratios`/`fundamental` that PR #887 stripped (dup'd
  on thousands of pitches), the ruleSet is **per-piece, stored once**, and tiny. So
  keeping it is fully consistent with #887's philosophy: strip per-pitch duplication,
  keep the per-piece raga definition complete.
- **Musically correct.** Raga interpretation genuinely varies (gharana, scholar,
  performer). Looking rules up by name imposes someone else's interpretation on the
  transcription. The transcriber's actual pitch set must travel *with* the piece.

### Two-tier model
| Tier | Location | Role |
|---|---|---|
| **Canonical rules** | DB `ragas` collection | Reference/defaults: seed new transcriptions, power corpus-wide search/analysis. |
| **Piece-specific ruleSet** | **In the piece's raga** | Source of truth for interpreting THIS piece. May match canonical or be personalized. |

The DB is consulted only when **creating/editing** a raga ("start me from canonical
Bhairav"). On **load**, the piece's own ruleSet is authoritative — no DB call.

### Load precedence (canonical)
1. `piece.raga.ruleSet` present → use it (self-contained; DB never consulted).
2. Legacy piece, no stored ruleSet → fetch DB rules by name to **heal**; persisted on
   next save (heals forward).
3. No DB entry → Yaman default (last resort).
**In all cases, stored transcription `ratios` win — never regenerate/discard them.**

### RAGA-2 resolution (fixes a current bug)
Today, on `ratios.length !== ruleSetNumPitches`, **TS discards the stored ratios and
regenerates from the ruleSet** (`setRatios`) — silently losing the transcription's
microtonal tuning. (Python's `preserve_ratios=True` keeps them.) **Canonical decision:
preserve stored ratios always; fix TS to stop regenerating.** With PROP-1 the mismatch
can't arise going forward anyway (ruleSet travels with ratios).

### Personalization
PROP-1 is only the data-model **enabler**. No editing UI/API is built by this change;
today the stored ruleSet just equals the canonical rules in effect at save time (no
user-visible change). A future "customize this raga's pitches" UI/API will have a place
to store its output (the piece) without polluting the canonical library.

### Implementation checklist
- [x] TS `Raga.toJSON()` — include `ruleSet`. *(PR jon-myers/idtap#2)*
- [x] TS `Raga.fromJSON`/constructor — use provided `ruleSet`; stop regenerating ratios
      on mismatch (preserve). *(PR #2; fixes RAGA-2)*
- [ ] TS app load path — keep DB fetch only as legacy fallback when `ruleSet` absent. *(app-level, not yet)*
- [x] Python `Raga.to_json()` — include `rule_set` (camelCase `ruleSet` on the wire).
- [x] Python `Raga.from_json` — use provided ruleSet; DB fetch only as fallback.
- [ ] Migration: on load, `ruleSet` present → use; absent → heal from DB; persist on save. *(app-level, not yet)*
- [ ] Consolidate the two endpoints (`getRaagRule` web / `/ragaRules` Python-API). *(app-level, not yet)*
- [x] `raga.schema.json` — add `ruleSet` (migrated-optional: emitted for new data,
      tolerated-absent for legacy).
- [x] Contract fixtures — added **non-Yaman** Raga fixtures (Bhairav [komal re/dha],
      Todi [komal re/ga, tivra ma, komal dha], a both-ni-variants raga). "Yaman-only"
      scope note lifted.

---

## PROP-2 — Piece metadata: `collections` and date format

**Decision (2026-07-10):** pin two `to_json` details for Piece. Neither affects
frequencies; both are about a clean, safe, language-neutral wire shape. Resolves
PIECE-2.

### `collections` — exclude from the piece serialization
- `collections` is **transcription-document metadata**, not part of the musical
  Piece. Membership is bidirectional (collection docs list transcriptions;
  transcription docs carry the reverse `collections:[colIds]`) and is maintained
  ONLY by dedicated endpoints (`/addTranscriptionToCollection`, `/remove...`).
- `updateTranscription` uses `$set` (not `replaceOne`), so a piece save that omits
  `collections` leaves the DB field untouched — **no data loss.** TS (which omits
  it) is correct.
- **Python including it is a liability:** read-then-write can clobber
  server-managed membership back to a stale value.
- **Canonical:** exclude `collections` from Piece serialization on both sides.
  - [x] Python `Piece.to_json()` — remove `collections`.
  - [x] Keep membership solely under the add/remove endpoints. *(unchanged; TS already excluded)*

### Dates — ISO 8601 UTC strings on the wire
- Today TS emits inconsistent values (JS `Date` → ISO via JSON.stringify, but Mongo
  `{$date}` stays `{$date}`); Python emits `.isoformat()` (naive, no offset) and
  strips `Z` on read. Both are sloppy about timezone.
- **Canonical:** `dateCreated`/`dateModified` are **ISO 8601 UTC strings** with an
  explicit `Z` (e.g. `2026-07-10T14:30:00.000Z`) on the wire. BSON `Date` is a
  **server-only storage detail** — the server parses ISO → Date on write (preserving
  date indexing/range queries) and emits ISO on read. Never leak `{$date}` into the API.
  - [x] TS — ensure dates serialize as ISO UTC, never `{$date}`. *(PR jon-myers/idtap#2)*
  - [x] Python — emit tz-aware UTC ISO; stop stripping `Z`; parse as UTC. *(`_iso_utc`/`_parse_utc`)*
  - [x] Server — parse incoming ISO → BSON Date on save. *(already done: `server.ts`
        `insertNewTranscription`/`updateTranscription` do `new Date(...)` before write)*
  - [x] `piece.schema.json` — pin `dateCreated`/`dateModified` as ISO-8601 date-time strings.

---

## PROP-3 — Chikari tuning: single source of truth = raga

**Decision (2026-07-10):** chikari drone tuning must derive from the piece's raga,
making the `Chikari` model's own pitch/fundamental data unnecessary. Corrects SEM-2.

### Finding
Chikari **playback is already correctly tuned**: both `Piece.chikariFreqs` (TS) and
`Piece.chikari_freqs` (Python) return `raga.chikariPitches` frequencies — derived from
the raga's `stratifiedRatios` + `fundamental`, so correct even for non-12-TET ragas.
The synth reads these, not the Chikari instances' pitches. **No audible bug.**

**But** the `Chikari` model carries vestigial 12-TET default `pitches` and its own
`fundamental`. Correctness depends on every consumer *knowing* to bypass
`chikari.pitches` and read `raga.chikariPitches`. Any consumer that reads
`chikari.pitches[i].frequency` directly (Python client, JSON export, analysis) silently
gets 12-TET — the exact "correct only if you know the secret handshake" fragility this
contract exists to remove. Identical structure in TS and Python.

### Decision — one source of truth
- Chikari drone pitches/frequencies **derive from `raga.chikariPitches`** wherever needed
  (as `piece.chikariFreqs` already does). The raga owns which strings sound (sa always,
  pa if present, ga if exactly one variant) and their tuning.
- The `Chikari` model's own `pitches` should not default to 12-TET; and its stored
  `fundamental` is redundant (== raga fundamental). Canonical serialized chikari shrinks
  toward just `{uniqueId}` (its time position is the `phrase.chikaris` dict key).
- **No audible change** — this hardens the data model and non-synth consumers and
  removes the footgun.

### Notes / dependency
- Deriving `chikariPitches` needs the full raga (ratios + fundamental + ruleSet, since
  "which strings" depends on the rule set). **PROP-1** (ruleSet in the piece) makes the
  raga fully reconstructable, so chikari pitches can be derived on load / on demand.

### TS finding (2026-07-10) — TS already correct; cleanup deferred
Confirmed on TS: `Chikari.fromJSON` with no `pitches` in the JSON (the canonical
`{fundamental, uniqueId}` form) passes `pitches:[]`, so **`chikari.pitches` ends up EMPTY**
after a canonical load — and the synth reads tuning from `raga.chikariPitches` (correct).
So there is **no audible/behavioral bug on TS**; `chikari.pitches` is simply vestigial. The
real cleanup (make `chikari.pitches` authoritative) needs the **full raga** threaded down
Piece→Phrase→Chikari — a deeper change with no bug driving it. **Deferred as a focused
design pass.** PROP-1/2 shipped on TS; PROP-3 remains the Python-side footgun (its
constructor populates 12-TET default pitches) + this optional TS cleanup.

### Implementation checklist
**Footgun removed (shipped):** the concrete divergence — canonical load left TS `chikari.pitches`
empty but Python synthesized 12-TET defaults — is closed. Both now leave `pitches` empty on
canonical load; readers already route through `raga.chikariPitches`. The deeper "derive
pitches from raga into the model" cleanup remains deferred (needs the full raga threaded
Piece→Phrase→Chikari; no bug drives it).
- [ ] TS `Chikari` — derive pitches from raga (or drop them); remove stored `fundamental`. *(deferred — TS already empty/harmless)*
- [x] Python `Chikari.from_json` — stop synthesizing 12-TET default pitches on canonical
      load (leave empty, matching TS). Full derive-from-raga still deferred.
- [x] Anywhere reading `chikari.pitches` for frequency → route through `raga.chikariPitches`.
      *(already the case on both sides; verified in Python — `Piece.chikari_freqs`)*
- [x] `chikari.schema.json` — canonical form is `{fundamental, uniqueId}`; description updated
      to say `pitches` stays empty on load. *(dropping stored `fundamental` deferred)*
- [ ] Contract fixtures — a non-12-TET raga chikari fixture: raga context → expected
      `chikariPitches` frequencies (proves both derive the same drone tuning). *(deferred)*

---

## PROP-4 — Meter offsets: serialize real proportional offsets (METER-1)

**Decision (2026-07-10):** Python's PulseStructure must serialize the real
proportional offsets, not zeros. **DONE (serialization)**; one deeper behavioral
follow-up noted.

### Finding
`PulseStructure.to_json` hardcoded `offsets: [0.0]*size`, while TS emits the real
`proportionalOffsets`. Web-app impact is nil (render + playback use `pulse.realTime`,
which IS preserved in both — like chikari SEM-2), but the `offsets` array is real
data a Python consumer would read, and it was being zeroed.

### Fix (applied to serialization)
Derive at `to_json` from the (preserved) pulse real_times:
`offset[i] = (realTime[i] - startTime - i*pulseDur) / pulseDur`. The pulses'
real_times round-trip correctly (constructor keeps input pulses; Pulse.to_json emits
realTime), so this makes the serialized offsets conformant. Fixture
`fixtures/meter/meter-offsets.json` (behavioral) pins it; was RED, now GREEN.

### Deeper behavioral follow-up (NOT serialization — separate)
Python's `set_tempo`/`set_start_time` recompute `real_time = start_time + i*pulse_dur`
(snap to grid), **discarding** offsets. TS's use `proportionalOffsets` to preserve
expressive timing across a tempo/start change. So Python can't faithfully *re-tempo*
an expressively-timed meter — it flattens it. Out of scope for the serialization
contract; worth a follow-up if Python ever needs to re-tempo.
  - [ ] (later) Python: maintain/apply proportional offsets in set_tempo/set_start_time.

---

## PROP-6 — Vibrato v2: rate in Hz, extent ramp, continuous phase (id 13 stays)

**Decision (Jon, 2026-09-12):** update the vibrato spec. Every stored vibrato is
translated; the web editor's vibrato panel is rebuilt. Evidence and reasoning are in
the lab journal (`autotranscribe-synth-loss` thread, ATS-17 → ATS-19) and in
`autotranscribe-synth-loss:feat/vibrato-articulation → VIBRATO.md`. Status: **APPROVED by
Jon 2026-09-13, implementation starting** (branches `vibrato-v2` in idtap-client,
idtap-contract, idtap-platform, then idtap-swift). This section is the spec and the plan. (Numbered PROP-5 until 2026-09-13; renumbered because PROP-5 already exists on branch `prop5/edit-and-ruleset-fixtures`.)

### Why
- **`periods` is the wrong parameter.** It is an integer count over the whole
  trajectory, so the achievable rate is quantised to multiples of `1/durTot` Hz: on a
  0.5 s ornament that is 2 Hz steps, a worst-case ±25 % rate error (ATS-17, 30 of 32
  measured runs). It also couples rate to duration: stretching a note slows its vibrato.
- **Real vibrato blooms.** On Begum Akhtar's Babul Mora (37.2–39.3 s) the extent grows
  from ~0 to ~40 c over two seconds; Jon's ear picked the drifting-extent render over
  the rigid one. A linear extent ramp captures nearly all of that gain.
- **The centre does not need to move.** Measured (ATS-19): median carrier drift under a
  vibrato is 10–17 c, 90th percentile under 45 c, on two pieces. So vibrato stays a
  fixed-centre type — id 13 keeps its meaning and no trajectory renumbering is needed.
- **Machine transcriptions need a target.** The autotranscriber's vibrato token is
  {centre, rate, start extent, end extent, phase}; v2 makes export exact instead of
  falling back to a cosine chain.

### The v2 `vibObj`
Wire keys, camelCase (Python: snake_case via humps, as today):

| key | type | units | meaning |
|---|---|---|---|
| `rate` | number > 0 | Hz | oscillation rate, independent of `durTot` |
| `extentStart` | number ≥ 0 | log2 (as `extent` today) | peak-to-peak excursion at x = 0 |
| `extentEnd` | number ≥ 0 | log2 | peak-to-peak excursion at x = 1; linear in x between |
| `vertOffset` | number | log2 | centre offset from `logFreqs[0]`, unchanged from v1 |
| `phase` | number | radians, [0, 2π) | phase at x = 0; v1 `initUp` becomes 0 or π |

`additionalProperties: false`. Units stay log2 on the wire because `vertOffset` and
`logFreqs` are log2; the UI displays cents (1 log2 = 1200 c; today's default 0.05 = 60 c).

### The curve (normative)
With `P = rate · durTot` (cycles over the trajectory, not necessarily an integer) and
`A(x) = (extentStart + (extentEnd − extentStart)·x) / 2`:

```
core(x) = logFreqs[0] + clamp(vertOffset, ±A(x)) + A(x) · cos(2π·P·x + phase)
```

**Ends: the curve always attaches at an extreme.** A trajectory must start and end on
its notated pitch, because that is how trajectories chain. v1 achieved this by
rescaling the first and last half-period, which silently relied on `phase ∈ {0, π}`
putting an extreme exactly at x = 0. With continuous phase the rule is stated on the
oscillation itself:

- `x₁` = the first extreme of the cosine (crest or trough) with `x₁ ≥ 1/(4P)`, i.e. at
  least a quarter period in. `x₂` = the last extreme with `x₂ ≤ 1 − 1/(4P)`.
- For `x ≤ x₁`: raised cosine from `logFreqs[0]` at x = 0 to `core(x₁)` at `x₁`:
  `y = logFreqs[0] + (core(x₁) − logFreqs[0]) · (1 − cos(π·x/x₁)) / 2`.
- For `x₁ ≤ x ≤ x₂`: `y = core(x)`.
- For `x ≥ x₂`: raised cosine from `core(x₂)` back to `logFreqs[0]` at x = 1.

Both joins are at points where the oscillation has zero slope, and the raised cosine
has zero slope at both of its ends, so the attach is smooth (C¹) for every phase: the
note sits on its pitch, swings out to the first extreme, oscillates, and comes home from
the last. The attack lasts between a quarter and three-quarters of a period depending on
phase. For `phase ∈ {0, π}` the first extreme after a quarter period is exactly at the
half-period, and the raised cosine over `[0, 1/(2P)]` is term-for-term the v1 rescaled
cosine — which is what keeps the heal lossless. If `P < 1` (fewer than one cycle),
compute with `P = 1` (not stored). If `x₂ ≤ x₁` (very short trajectory), the middle
section is empty and the two tapers meet at the single extreme. Return `2 ** y(x)` in Hz.

### Heal (v1 → v2), lossless
Detect v1 by the presence of `periods`. Then:
```
rate        = periods / durTot
extentStart = extentEnd = extent
vertOffset  = vertOffset
phase       = initUp ? π : 0
```
Real stored data carries the v1 fields as **strings** as often as numbers (the old slider
had no `.number` modifier; Babul Mora has `{periods: '3.5', extent: '0.055'}`), and
`periods` is frequently non-integer. The heal coerces all four fields with `Number()` and
uses the stored `periods` as-is. A migrated vibrato renders byte-identically (golden-test
this; the TS reference golden is `idtap-platform/src/ts/tests/fixtures/vibrato-v2-golden.json`). Python's `int(periods)`
truncation and Swift's `Double` already disagree on non-integer v1 periods; the heal
uses the stored number as-is, so whichever value was stored is what migrates.
Behavioural change to state plainly: after migration, **changing `durTot` keeps the
rate and changes the cycle count**, where v1 kept the count and changed the rate.

### Canonical form (PROP-6b, separable)
`vibObj` is emitted **only when `id === 13`**. Today all three implementations write a
default `{periods: 8, …}` on every trajectory of every type, so presence carries no
information and the DB carries thousands of meaningless copies. Loaders accept a
`vibObj` on any id and ignore it. This is the same stripping philosophy as PR #887.
Kept separable because it changes the wire shape of every trajectory and trips the
encode-stability tests; do it in the same release or not at all.

### Editor UI (web, then Swift)
- **Rate** slider, 1–12 Hz, step 0.1, default 5.5. Replaces Periods.
- **Extent** in cents, 0–200, step 1, default 60. A **Ramp** toggle exposes a second
  slider for the end extent; off means `extentEnd = extentStart`.
- **Offset** slider unchanged in behaviour; fix the existing bug where the fractional
  slider is written back with the absolute `vertOffset` (TS `TrajSelectPanel.vue:692`,
  `EditorComponent.vue:2009`), and the two read-only sliders bound to `periods`.
- **Starts upward** checkbox stays and writes `phase = π` / `0`. A continuous phase
  control is not exposed; the wire allows it for machine transcriptions.
- Help text and keyboard table (`EditorInstructions.vue`) updated; thumbnail unchanged.
- Web Audio envelopes sample at 50 Hz, adequate to 12 Hz.

### Rollout order (hard constraint first)
1. **Python client tolerant read, released first.** `idtap` ≤ 0.1.54 raises
   `ValueError` on any unknown `vib_obj` key, so a v2 document crashes every installed
   client. Ship a release that accepts v1 and v2 (heal v1 on load, write v2), then gate
   the rest on it being installed where it matters (cluster, Jon's machine).
2. **Contract:** this PROP; `schemas/trajectory.schema.json` `vibObj` sub-schema (v2
   strict, v1 accepted as LEGACY); fixtures under `fixtures/trajectory/`:
   `vib-v1-legacy-heals`, `vib-v2-equals-v1-golden` (the lossless proof: 21 sample
   points), `vib-v2-ramp`, `vib-v2-noninteger-cycles`; regenerate `index.json`; bump
   `contract.json` version to 0.2.0 and finally add the version assertion README:114
   promises. `tools/generate_trajectory_fixtures.py` gets the v2 formula.
3. **TypeScript (reference implementation):** `trajectory.ts` `id13` → v2 formula,
   constructor default, `fromJSON` heal, `toJSON`; `shared/types.ts` `VibObjType`;
   rewrite the mirror test at `trajectory.test.ts:113-146`; fixture
   `serialization_test.json` (one id 13, 34 default vibObjs); `Piece.fromJSON` needs no
   change (heal is per trajectory). Then the editor panel (above). Mirror in the
   duplicate model `src/js/classes.ts` and rebuild `server/extract.js`. Server: no
   validation exists, nothing to change; add `vibObj` handling to nothing.
4. **Swift:** regenerate `Tests/IDTAPCoreTests/Golden/TrajectoryGolden.swift` from the
   updated TS via `scripts/gen-trajectory-golden.ts` (Swift is downstream of TS);
   `VibratoObject` → v2 with v1 heal in `fromJSON`; `MixPanel.swift` vibrato controls;
   `DocumentSession.swift` defaults.
5. **Stored data:** house style is lazy heal-on-load + write-v2-on-save, which needs no
   DB script and heals every piece the first time anyone opens it. Optionally run a
   one-off `database_tools/*.js` `updateMany` (precedent: `updateTranscriptionFormat.js`)
   once steps 1–4 are deployed, so analysis queries over unopened pieces see v2 too.
   Size it first: there is no aggregation endpoint, so count id-13 trajectories by
   iterating `get_viewable_transcriptions()` → `get_piece()` from Jon's machine.
6. **autotranscribe-synth-loss:** `export_idtap.py` maps the vibrato token straight to
   v2 (`rate`, `extentStart/End`, `phase`); the cosine-chain fallback stays only for runs
   the collapse move rejected. `decompose_trajectory` in the Python client gains the v2
   branch: one cosine per half-period between consecutive extremes. This is exact
   only when `extentStart == extentEnd` (so for every healed v1 vibrato). With a ramp
   the chunk endpoints sit on the curve but the interior differs by at most the ramp
   increment over one half-period, because a half-cosine cannot carry a linearly
   varying amplitude.

### Things that must not be forgotten
- Three TS code paths rebuild a trajectory from a hand-written field list and already
  drop `vibObj` (`TranscriptionLayer.vue:5784, 7312, 7416`, and `insertFixedTraj*`).
  Switch them to `toJSON()`-based copies or the migrated field is lost on phrase splits.
- Saved analysis queries persist numeric trajectory ids; untouched because 13 stays.
- `durationsOfFixedPitches` and the drag-dot "fixed-like" rules already treat 13 as
  fixed; unchanged.
- Web picker's index-collapse hack around id 12/13 is untouched by this PROP; it is a
  separate cleanup.

### Resolved (Jon, 2026-09-13)
- **Extent units on the wire: log2.** UI displays cents.
- **PROP-6b ships in the same release.** `vibObj` is written only for id 13. In-memory
  objects keep the constructor default on every id, so retyping 0 ↔ 13 is unaffected;
  the one behavioural change is that a tuned vibrato no longer survives being retyped to
  fixed, saved, and retyped back.
- **Rate is bounded only in the UI, 1–12 Hz.** The wire requires `rate > 0` and nothing
  more, as `periods > 0` today. Musical bounds for the machine transcriber's token stay
  in autotranscribe-synth-loss. Rationale for 1–12: measured vibrato here is 3.3–7.3 Hz
  and the token uses 3–9; below ~1 Hz a sub-second note holds less than a cycle and reads
  as a bend; above ~12 Hz it is trill or buzz, and the 50 Hz Web Audio pitch envelope
  cannot render past 25 Hz anyway.

---

## PROP-7 — `system`: the transcription system travels with the piece

**Decision (Jon, 2026-11-12, plan decision 2):** one data model for every tradition,
with a `system` descriptor on `Piece`, not separate apps or forks. Status: **contract
drafted on `prop7-8/system-and-syllables` (0.3.0), awaiting review**; client PRs follow.
Source: the Claude Doc "IDTAP for Many Traditions: Plan", section "One model".

PROP-1 moved the raga's `ruleSet` into the piece so a transcription is interpretable
without the database. A tradition is the same move one level up.

- **Shape** (`schemas/system.schema.json`): optional object of extensible string ids,
  `{ pitch, phonology, rhythm, display }`. Unknown ids and unknown components are kept
  verbatim on load and re-emitted on save, never rejected.
- **Absent = Hindustani.** Every pre-0.3.0 document is unchanged. A missing component
  takes its Hindustani default: `pitch: 'raga'`, `phonology: 'hindi-urdu'`,
  `rhythm: 'tala'`, `display: ['sargam', 'Deva']`.
- **Only `phonology` has semantics in 0.3.0:** it names a pack (PROP-9). Pitch and rhythm
  generalizations (maqam, banshi, usul) are later proposals, written when a transcriber
  needs them.
- **Feature flag:** clients show syllable and tone UI only when `piece.system` is present.
- `Piece.lyricsText[track]` (optional, string or null per track): the source text as
  given, for reference only; never parsed.
- Fixtures: `fixtures/system/` (absent, hindustani explicit, cantonese, kurmanji).

---

## PROP-8 — The syllable tier replaces per-trajectory phonemes

**Decision (Jon, 2026-11-12, plan decisions 3, 4, 6):** `Phrase.syllables`, one list per
phrase (so per track); each syllable anchored to the trajectory it starts on; lyric and
sung vowels with provenance; the legacy fields are dual-written through 0.3.x. Status:
**contract drafted on `prop7-8/system-and-syllables` (0.3.0), awaiting review.**

### Design note (what the investigation found, before the schema)
- **The legacy fields are nine on the wire, twelve in memory, plus a fourth copy.**
  `Trajectory.toJSON` writes `vowel`, `startConsonant{,Hindi,Ipa,EngTrans}` and
  `endConsonant{,Hindi,Ipa,EngTrans}`. `vowelHindi/Ipa/EngTrans` exist only in memory
  (derived by `convertCIsoToHindiAndIpa`). The constructor also mirrors each consonant
  as an articulation `{name: 'consonant', stroke, hindi, ipa, engTrans}` at `'0.00'`
  (start) and `'1.00'` (end), and those are serialized. The projection writes all of it.
- **Stored values are ISO keys with the inherent a** (`ka`, `ā`). The display copies are
  `tables[indexOf(key)]`, first match, so today's `na` always gets index 14's copies
  (`न`, IPA `n`) and never index 19's (`n̪`). The Python synth already treats `na` as a
  dental n and puts the true retroflex at `ɳ`.
- **`firstTrajIdxs` already makes the heal lossless.** Its five triggers (first of the
  phrase, after a silence, a start consonant, after an end consonant, a vowel change)
  guarantee that within one group the vowel is constant, a start consonant can only be
  on the first trajectory and an end consonant only on the last. So legacy → syllables →
  legacy is the identity, which `heal-legacy-hindi-roundtrip` proves.
- **null vs absent differs between clients** (SYL-1): TS `fromJSON` spreads `...obj`, so
  a stored `null` consonant bypasses the constructor default and counts as present in
  `firstTrajIdxs`; Python treats `None` as absent. Normative: null == absent.
- **Syllables live on row 0 of trajectoryGrid (the melodic row; the only row on a vocal track)**, as `firstTrajIdxs` does. Syllables are per
  track via phrases: any number of tracks may carry them (a duet is two vocal tracks),
  and tracks are independent of one another; nothing in one track's tier refers to
  another's.

### Wire shape (`schemas/syllable.schema.json`, `Phrase.syllables`)
```
Syllable {
  anchor: { traj: <trajectory uniqueId>, t: 0 }   t in [0,1], default 0; must be 0 in 0.3.x
  orthography?   free text (詩, बा, her); no validation or lookup in 0.3.0
  romanization?  Jyutping with tone digit (si1); ISO for Hindi (bā); Kurmanji as spelled
  onset?         pack consonant key, or [keys] where the pack allows clusters (xw)
  nucleus?       pack vowel key; absent only for a syllabic final or where the pack allows
  coda?          pack coda key, or [keys]; no anchor of its own
  tone?          pack tone key (Jyutping '1'-'6'); a label only
  wordStart?     true when the syllable begins a word
  lyric: { vowel: <vowel key> | null, source: 'human' | 'model' | 'pack' }
  sung?: { vowel: <vowel key> | null, source }
}
```
Keys, not IPA: a syllable stores what the pack keys on (ISO for hindi-urdu, Jyutping
letters, Kurmanji letters); IPA and display forms are derived from the pack, never
stored (plan, pack-level call of 12 Nov). `Phrase.syllables` **absent** = not yet
healed; `[]` = healed, no syllables. Canonical output always emits it.

**Extent is implied:** a syllable runs from its anchor to the next anchor or to a
silence trajectory (id 12), whichever comes first, along the track's row-0
trajectories in phrase order, so it can cross a phrase boundary.

### Invariants (checked on load; codes in `fixtures/syllable/invariants.json`)
- `traj-uid-missing`: every row-0 trajectory has a uniqueId (heal, projection and
  re-homing refuse one without; loaders assign ids first).
- `anchor-missing`: every anchor names a trajectory of the same phrase's row 0.
- `anchor-silence`: never a silence. `anchor-order`: anchors in trajectory order, at most
  one per trajectory.
- `unanchored-start`: in a track that has any syllable, the track's first non-silent
  trajectory and every non-silent trajectory after a silence start a syllable.
- `anchor-t`: `t` is 0 (a later minor may let a system allow otherwise).
- `key-unknown`, `cluster-not-allowed`, `tone-not-allowed`, `nucleus-missing`,
  `final-unknown`, `syllabic-not-allowed`: keys against the pack (a coda cluster in a pack
  with `finals` is reported once, as `cluster-not-allowed`). Syllabic m/ng (no
  nucleus, coda m|ng) are valid only where the pack lists them as syllabic finals
  (Jyutping).
- `nucleus-lyric-mismatch` (error): `nucleus` and `lyric.vowel` must agree (absent
  nucleus == null lyric.vowel). Both stay on the wire (Jon, 2026-11-13): `nucleus` is the
  pack key IPA is derived from, `lyric.vowel` is the vowel the text says with its
  provenance, and the projection reads `lyric.vowel`. **Editors keep them in sync**: any
  edit of one writes the other, and a person's override sets `lyric.source: 'human'`.
  Disagreement is therefore corrupt data, not a reading.
- `track-not-vocal` (**warning**): a track whose `instrumentation[track]` is not a vocal
  label carries syllables (a sung bol on an instrumental track, or a mislabelled track).
  Vocal labels, pack-independent: `'Vocal (M)'`, `'Vocal (F)'` (`VOCAL_INSTRUMENTS`, the
  list idtap-platform and idtap-client already use).
Every code except `track-not-vocal` is an error. What a client does with an error
(refuse, repair, warn) is its choice in 0.3.0; a warning is shown, never refused.

### Heal: legacy → syllables (normative, `conformance/syllables.py` `heal_piece`)
1. Uniqueids are assigned before healing (loaders already do) and persisted; the
   reference heal raises on a row-0 trajectory without one.
2. A phrase with a `syllables` key keeps it, even `[]`; its legacy fields are ignored on
   load and rewritten by the projection (`mixed-healed-and-legacy-phrases`).
3. A phrase without the key: if no row-0 trajectory anywhere in its **track** has a
   vowel or consonant, `syllables = []` (instrumental tracks). Otherwise run
   `firstTrajIdxs` (null == absent); each start index opens a syllable that spans up to
   the next start or a silence. `onset` = first trajectory's `startConsonant`,
   `nucleus` = its `vowel`, `coda` = last trajectory's `endConsonant`,
   `lyric = { vowel: <vowel> or null, source: 'pack' }`, `anchor.t = 0`. A group with no
   vowel still becomes a syllable (lyric.vowel null), so no extent leaks over it.

### Projection: syllables → legacy fields (normative, `project_piece`)
For every syllable and the trajectories it spans: `vowel` on every spanned trajectory,
`startConsonant` + three copies + the `'0.00'` mirror on the first, `endConsonant` +
three copies + the `'1.00'` mirror on the last; every other row-0 trajectory has
all of them cleared (a stale `'0.00'`/`'1.00'` articulation is removed only when its name
is `consonant`). The values come from the pack entry's `legacy` block:
- **hindi-urdu:** exact, `{iso, hindi, ipa, engTrans}` = today's tables at
  `indexOf(key)`, bugs included (Jon, 2026-11-12: "legacy block"), so the round trip is
  byte-identical. A stored string that is not a pack key is written back as-is with no
  copies, as today's code does. The corrected forms live in `ipa`/`display` for new UI.
- **every other pack projects nothing** (Jon, 2026-11-12, reversing an earlier draft
  that mapped each Jyutping/Kurmanji entry to its nearest hindi-urdu key): all
  platforms move to the tier together, so a non-Hindi piece leaves every legacy field
  absent and every `'0.00'`/`'1.00'` consonant articulation removed. Those packs carry
  no `legacy` blocks, and the validator rejects one if it appears.
- Tones, orthography, romanization, word starts, clusters and sung vowels never project.
  `lyric.vowel` is projected; `sung` never is.

**Dual-write stays on through 0.3.x**; the legacy fields are dropped in a later minor.

### Tier disabled: preserve, never create (normative; readers before writers)
`/updateTranscription` does a `$set` of what the client sends, and `phraseGrid` goes up
as one key, so a client that drops `syllables` silently deletes a tier another client
(Swift, Python 0.1.57) wrote. A 0.3.0 client with the syllable tier disabled (the web
app with the flag off) therefore:
1. parses and keeps every existing `phrase.syllables` and re-emits it **byte-identical**
   on save;
2. **never persists healed syllables.** The heal may run in memory for reads, but the
   persist-on-save step is behind the flag; a phrase that arrived without the key leaves
   without it;
3. still writes the legacy fields as today. Where a phrase carries syllables, they are
   the source of truth and the legacy fields are their projection, as with the flag on.

Consequence: while the flag is off nothing new appears in the database. Existing Hindi
pieces stay readable by `idtap` 0.1.56; the only documents that trip 0.1.56 are the ones
Swift or Python 0.1.57 write explicitly with the tier. That keeps the order PyPI 0.1.57
→ server → web flag-off → Swift → flag on honest.

### Re-homing after phrase edits (normative, `rehome`)
After every phrase split, merge or moved division, pool every syllable the track had
before the edit and put each in the phrase that now holds its anchor trajectory, in
trajectory order; a syllable whose trajectory was deleted is dropped. Pooling from the
pre-edit state matters for a merge, which deletes a phrase and its list. Fixtures:
`rehome-split-at-syllable-boundary`, `rehome-split-mid-melisma`, `rehome-merge`. The
projection is unchanged by any of them.

### Write guard (document; the server implements)
A save from a client whose `X-IDTAP-Client` is below 0.3.0 is **refused** when the
stored piece is not legacy-safe. Legacy-safe (`legacy_safe`) means: the pack is
hindi-urdu, no syllable carries `orthography`, `romanization`, `tone`, `wordStart` or
`sung`, `t` is 0, no cluster, every onset, coda, nucleus and lyric vowel key has a
legacy form (not `ṇa`; reason `key`), and **healing the stored legacy fields gives back
the stored syllables** (anchor, onset, nucleus, coda, lyric.vowel; `lyric.source` is not
compared; reason `boundary`). The guard reads what is in the database, because that is
what a pre-0.3.0 save keeps (Jon, 2026-11-13; earlier drafts compared
heal(project(piece)), which passed a phrase with `syllables: []` beside stale legacy
fields). A 0.3.0 save always dual-writes, so on a well-formed document the stored legacy
fields are the projection and the two definitions agree; stale fields make a piece
unsafe until a 0.3.0 client saves it (`stale-legacy-beside-empty-syllables`,
`mixed-healed-and-legacy-phrases`). For every other piece the old client's
save drops the syllables and the next load rebuilds them losslessly. **For a non-Hindi piece the guard is the only protection:** its
legacy fields are empty, so a pre-0.3.0 save that got through would keep nothing of
its text, and the next load would have nothing to heal from. `system` and
`lyricsText` are top-level fields that a `$set` save leaves in place, so they do not
trip the guard. Reason codes: `fixtures/syllable/write-guard.json`.

### Rollout order (plan, "Release sequence")
1. **Contract 0.3.0** (this branch).
2. **All three client PRs ready and passing the same fixtures (the gate):** idtap-client
   (heal, project, rehome, invariants, packs bundled), idtap-platform (model + server
   guard), idtap-swift. Each bumps `CONTRACT_VERSION` to 0.3.0 in the commit that
   implements the semantics, never before.
3. **Dry run** over a DB dump: load every piece with the new model, heal, re-serialize,
   assert the legacy fields round-trip byte-for-byte. Zero diffs is the gate.
4. **PyPI 0.1.57, and installed where it matters** (cluster, Jon's machines) before
   anything writes the new keys. This is the hard constraint, as in PROP-6: `idtap`
   0.1.56 raises `ValueError: Invalid parameter: 'syllables'` in `Phrase._validate_parameters`
   on any phrase that has the tier, and `Piece._ALLOWED_JSON_KEYS` would refuse `system`
   and `lyricsText` the same way (verified 2026-11-12 against the Cantonese fixture).
5. **Server** (write guard, packs served by the API).
6. **Web with the flag off**: preserve, never create (above); no syllable UI.
7. **Swift.**
8. **Flag on** (syllable and tone UI where `piece.system` is set).
Rollback at any later step: dual-write keeps every document readable; only syllable
editing stops.

### Things that must not be forgotten
- **The `'0.00'`/`'1.00'` consonant articulations** are a fourth copy of each consonant
  and are serialized; the projection owns them. Code that edits consonants through
  `addConsonant`/`changeConsonant`/`removeConsonant` must go through the syllable tier.
- **Hand-written trajectory copies** (`TranscriptionLayer.vue` paths noted in PROP-6,
  `insertFixedTraj*`) must carry `uniqueId` and the phrase's syllables, or a split loses
  them; run `rehome` after each.
- **Stored display copies win today** (`if (!this.startConsonantHindi)`), so a document
  whose stored copy differs from the table changes on its first 0.3.0 save. The dry run
  measures this; expect it to be rare.
- **Empty strings:** null and missing are absent; `''` is a stored value. The dry run
  should count `''` in `vowel`/`startConsonant`/`endConsonant` before 0.3.0 ships.
- **Python 0.1.56 and earlier cannot read the new form at all** (step 4). So the
  "old client saves and drops the syllables" path in the write guard applies to stale web
  tabs and to scripts that write without loading, not to installed Python clients, which
  fail on load. The preserve-never-create rule keeps flag-off web from writing the tier,
  so 0.1.56 only meets it in documents a 0.3.0 client with the tier enabled wrote.
- **0.1.57 must accept and round-trip keys it does not know** on Phrase and Piece (at
  least `syllables`, `system`, `lyricsText`; ideally any key), rather than raise, so this
  blocker does not recur at 0.4.0. Swift and TS readers need the same property.
- **Uniqueids must be stable across save/load** in every client, since anchors depend on
  them. Check that no client regenerates trajectory `uniqueId` on load or copy-paste
  without re-pointing the syllable.
- **Analysis queries** that read `vowel`/`startConsonant` keep working through 0.3.x via
  dual-write; port them to the tier before the legacy fields are dropped.
- **The autotranscriber:** a consonant onset is a reason to start a new trajectory; the
  vowel search runs constrained to a syllable's sounds when a lyric is present.

---

## PROP-9 — Phoneme packs as data

**Decision (Jon, 2026-11-12, plan decision 5):** phoneme inventories stop being code;
Hindi/Urdu, Jyutping and Kurmanji packs are built together. Status: **drafted on
`prop7-8/system-and-syllables`; jyutping and kurmanji pending speaker review.**

- `packs/<id>.json`, schema `schemas/pack.schema.json`, generated by
  `tools/generate_packs.py`. Served by the API and bundled in each client.
- **Entries keyed by the pack's romanization key** (what a syllable stores), each with
  `ipa`, feature axes and `display` per ISO 15924 script. Consonants: `place`, `manner`,
  `voiced`, `aspirated` (the axes of the Python client's `ConsonantSpec`), plus
  `pharyngealized` (Kurmanji) and `labialized` (Jyutping gw, kw). Vowels: `height`,
  `backness`, `rounded`, `length`. `codas` is either `"consonants"` or its own map
  (Jyutping: unreleased -p -t -k, glides -i -u).
- `finals`: the vowel-realization table where the nucleus depends on the coda (Jyutping,
  enumerated, not nucleus × coda). `tones` with Chao contours. `flags`: syllabicNasals,
  onsetClusters, codaClusters, tones, nucleusOptional, legacyExact.
- `variants` hold context realizations (Kurmanji i → [ɨ] before m; e → [ə] in ew);
  they are not phonemes, and a syllable stores the letter.
- `unverified` lists what is not yet checked. Clients may show it, must not treat it as
  settled.

| pack | status | contents | open |
|---|---|---|---|
| `hindi-urdu` | complete | 33 consonants, 10 vowels + `_`; `legacy` blocks = today's tables exactly; `legacyTables` verbatim | Urdu (Arab) consonant forms unreviewed; three table bugs fixed in display (DIVERGENCES PACK-1) |
| `jyutping` | draft, Yingyao Yu to review | 19 onsets, 8 codas, 9 nuclei, 59 finals with IPA, 6 tones | Yingyao counts 60 finals, the sources give 59 (candidates: bare eo, en, um, up); tones 2 and 5 are 25/23 in her list and 35/13 on jyutping.org (both kept) |
| `kurmanji` | draft, Seba Kayan to review | 31 consonants incl. p̱ ṯ ḵ ç̱ (U+0331), ḥ, ʿ, flap r vs trill rr, x vs x̱; 8 vowels with context variants | [ɯ] glide after w; velar vs uvular x/x̱; [ɯɛ] after g, k; no Arabic-script forms |

Validator checks: every pack against the schema; every hindi-urdu legacy key heals to
a pack key and its `legacy` block equals `tables[indexOf(key)]`; no other pack carries
a `legacy` block or sets `legacyExact`; finals are consistent with nuclei and codas.
