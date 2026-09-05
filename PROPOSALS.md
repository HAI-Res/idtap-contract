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


## PROP-5 — Edit round-trip fixtures and the RAGA-2 mismatch cases (from the Swift port)

**Proposal (2026-09-05):** add two fixture families so the three implementations agree not
only on how a document loads but on what the editor's operations do to it.

### Why
- The Swift port (`idtap-swift`, `IDTAPCore`) reimplements the editor's model operations
  (insert/delete trajectories, phrase divisions, drag dots) from `TranscriptionLayer.vue`.
  Porting them exposed several places where the TypeScript's result depends on incidental
  details (ULP-level rescaling in the Phrase constructor, articulation keys not re-keyed after
  a duration change, `uniqueId`s minted on every load). Each was resolved with a documented
  divergence in `idtap-swift/Sources/IDTAPCore/HANDOFF.md`. Without fixtures, the next port
  (or the next refactor of the web) will resolve them differently.
- RAGA-2 recorded the ratios/rule-set count mismatch as an open edge case with no fixture.
  With PROP-1 the mismatch cannot arise from a save, but a hand-edited rule set or a stale
  document still hits it, and the canonical decision ("preserve stored ratios; the guard
  serves `tuning`") has never been pinned.

### The `edit` entity
A fixture is `pieceJson` (before, deterministic ids) + `operation` + `expected`
observables (see `Fixtures/contract-proposals/README.md` for the shape). The eight proposed
cases cover: delete → silence merge; silent/fixed insert carving; phrase division inside a
silence (split at the exact time on both strings, chikari stays) and snapping to a trajectory
end (second string split); division deletion merging both strings and re-basing chikari keys;
an inner drag dot reshaping `durArray` and re-keying the krintin's hammer; an end drag dot
moving the boundary with the next trajectory.

Observables deliberately exclude created `uniqueId`s and the `startTime`/`num` bookkeeping
(derived), so an implementation is free in how it mints ids and settles, and pinned in what
the music becomes.

### The RAGA-2 cases
These live under `fixtures/raga-ruleset-mismatch/` (their own entity) because the self-check's
canonical raga rule regenerates ratios positionally and would index past the stored list on
exactly the mismatch these fixtures pin; the validator needs a PROP-1-aware rule before they
can join `fixtures/raga/`.
`ruleset-mismatch-more-rules-than-ratios` (Yaman just ratios, komal re added) and
`ruleset-mismatch-fewer-rules-than-ratios` (pa removed). Expected: `ratiosPreserved` equals
the stored ratios byte for byte; `stratifiedRatios` comes from `tuning`, which carries the
stored just ratios for the degrees that had one and the tuning's own value for the new one.
This is the "preserve" behaviour PROP-1 chose; the TS regeneration path (`setRatios`) would
fail both.

### Implementation checklist
- [ ] Copy `edit/*.json`, `edit/index.json` to `fixtures/edit/`; `raga/*.json` into
      `fixtures/raga/` and extend `fixtures/raga/index.json`.
- [ ] `schemas/edit.schema.json` for the fixture shape (operation vocabulary above).
- [ ] TS adapter: `Piece.fromJSON(pieceJson)` → the matching `TranscriptionLayer` operation
      (they are component methods today; PROP-5 is also an argument for lifting them onto the
      model, where the Swift port has them).
- [ ] Python adapter: skip `edit` until the editor ops exist there; run the raga cases now.
- [ ] `validate_fixtures.py`: `expected.durTot == sum(phrase durTots)`, `phraseStarts`
      cumulative, every string spans its phrase.
