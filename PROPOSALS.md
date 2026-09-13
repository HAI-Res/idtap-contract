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
