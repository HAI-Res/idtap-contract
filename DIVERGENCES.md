# Known TS ↔ Python divergences

Divergences discovered while building the contract. **These are design questions
to resolve before "fixing" the Python client** — patching Python to match TS
would bake in TS behavior that may itself be wrong. Each needs an explicit
decision on the canonical behavior; the fixtures then encode that decision and
both implementations are held to it.

Status legend: 🔧 decided (mechanical — Python matches TS, no judgment needed) ·
🟡 decided via proposal (see PROPOSALS.md) · 🟢 enforced by fixtures in both repos'
CI · ~~superseded~~

**✅ STATUS (2026-07-13): DRIFT CLOSED — both client PRs MERGED to main.**
- **TS** `jon-myers/idtap#2` merged (PROP-1/2 + conformance harness). **Python**
  `jon-myers/Python-API#1` merged (all 🔴 mechanical fixes PITCH/TRAJ/PHRASE/PIECE/METER
  + PROP-1/2/3 + STRING-SYNC). During the Python merge, a stale Feb sync (`#65`) was
  reconciled and a real serialization non-idempotence was fixed (`trajectory.py`
  `vert_offset` int→float). Contract conformance is now enforced in **both** repos' CI.
  So every 🔴 heading below is now **implemented + merged** (read as 🟢).
- **`chikari.fundamental` assessment (2026-07-13):** it is **vestigial for behavior** —
  in both langs it's only applied to the chikari's own `pitches`, which are (a) not
  serialized (PROP-3) and (b) not used for playback (`Piece.chikariFreqs` derives the
  drone from `raga.chikariPitches`, not the chikari). But it is still a *serialized,
  schema-canonical* field, so dropping it is a wire-format change → **harmless to keep;
  drop deferred to the restructure.** Added a legacy non-12-TET chikari fixture.
- **Remaining (restructure-bound, non-conformance):** endpoint consolidation
  (`getRaagRule`/`/ragaRules`) + "skip DB fetch when ruleSet present" optimization.

**STATUS (2026-07-10): all items decided — nothing awaits an owner decision.**
- Design decisions → **PROP-1** (RAGA-1/2/3), **PROP-2** (PIECE-2), **PROP-3** (Chikari/SEM-2).
- Everything else is 🔧 **mechanical**: PITCH-1/2, TRAJ-1/2, PHRASE-1/2, PIECE-1
  (thread raga context + stop emitting stripped fields — Python matches TS) and
  METER-1 (Python emit real offsets). No decisions required, only implementation.
- Caveat: this catalog is a static field-level read. Running the conformance
  fixtures against both real implementations (CI wiring) is what *proves*
  completeness and may surface deeper behavioral diffs (number precision,
  articulation dict-key formatting, humps edge cases).

The 🔴 markers on individual headings below mean "not yet implemented," NOT
"undecided" — read them as 🔧.

**IMPLEMENTED (2026-07-10):** the loop is closed on the client models.
- **Python** (`fix/serialization-sync-conformance`): mechanical fixes PITCH-1/2,
  TRAJ-1/2, PHRASE-1/2, PIECE-1, METER-1, plus **PROP-1** (serialize `ruleSet`),
  **PROP-2** (drop `collections`; ISO-UTC dates via `_iso_utc`/`_parse_utc`),
  **PROP-3** (chikari no longer synthesizes 12-TET defaults on canonical load), and
  **STRING-SYNC** (`ensure_string_synchronization` ported, idempotent).
  Verified by `test_contract_conformance.py` (67) + offline model tests (269 total).
- **Server (idtap):** `Piece.to_json` ISO-UTC dates are already parsed to BSON `Date`
  on save — `server.ts` `insertNewTranscription`/`updateTranscription` do `new Date(...)`.
  So the PROP-2 "server parse ISO→BSON" item needs no change.
- **TS** (`feat/contract-conformance-ts` → PR jon-myers/idtap#2): **PROP-1** (emit
  `ruleSet`, preserve stored ratios — fixes RAGA-2) + **PROP-2** (ISO dates). Verified
  by the TS conformance suite (55).
- **Contract**: `ruleSet` added to the raga schema + non-Yaman fixtures (Bhairav, Todi,
  both-ni); schemas for dates/collections/chikari updated. 61/61 fixtures consistent.
- **Still open (app-level / deferred, cosmetic — no bug driving):** legacy `ruleSet`
  heal-on-load is already handled on the web (EditorComponent fetches `getRaagRule` and
  injects before `Piece.fromJSON`; post-PR#2 `Raga.toJSON` emits `ruleSet` so a web
  load→save heals forward) — only the endpoint consolidation (`getRaagRule` /
  `/ragaRules`) + the "skip DB fetch when ruleSet already present" optimization remain,
  best bundled with the repo restructure. Dropping the redundant `chikari.fundamental`
  from the wire (nothing reads it) + a non-12-TET chikari fixture are cosmetic and also
  deferred to the restructure.

---

## PITCH-1 🔴 Python `from_json` doesn't thread raga context (the Yaman bug)

- **TS** `Pitch.fromJSON(obj, ratios?, fundamental?)` threads raga context in.
- **Python** `Pitch.from_json(obj)` takes no context params → stripped JSON falls
  back to constructor defaults (12-TET, 261.63 Hz).
- **Effect:** a Yaman pitch (fundamental 246 Hz) loads at 261.63 Hz in Python.
- **Canonical:** context must be threaded; embedded values are fallback.
- **Fix (deferred):** `SERIALIZATION_SYNC_SPEC.md` — add `ratios`/`fundamental`
  params to Python `from_json` at every level and thread from the piece raga.
- **Fixtures:** `fixtures/pitch/stripped-nondefault-fundamental-*`,
  `fixtures/pitch/stripped-just-intonation-*` (fail on Python until fixed).

## PITCH-2 🔴 Python `to_json` still emits `ratios` + `fundamental`

- **TS** strips them (canonical); **Python** still writes them.
- **Effect:** Python-produced JSON is bloated and non-canonical; a strict
  canonical-form validator would reject it.
- **Canonical:** stripped — `{swara, raised, oct, logOffset}` only.
- **Fix (deferred):** remove both from Python `Pitch.to_json()`.

## RAGA-1 🟡 `ruleSet` is not serialized — it's fetched from the DB by name (BY DESIGN)

- Neither `to_json()` includes `ruleSet`. It is **recovered from the DB by raga
  name at load time** and injected BEFORE deserialization. Confirmed in the web app
  (`EditorComponent.getPieceFromJson` + `analysis.instantiatePiece`):
  ```
  const rsRes = await getRaagRule(piece.raga.name);  // DB fetch by name
  piece.raga.ruleSet = rsRes.rules;                  // inject into raw JSON
  this.piece = Piece.fromJSON(piece);                // then deserialize
  ```
  `getRaagRule` -> server `getRaagRule?name=X` -> `ragas` collection -> `{rules}`.
- **So the open question is ANSWERED:** rule-set structure IS recoverable from
  `name` + the rules table. Non-Yaman ragas reconstruct fine — the ruleSet is
  fetched first. **Not a data-loss bug.**
- **Contract implication:** model `ruleSet` as **load-context for Raga** (exactly
  like ratios/fundamental are threaded into Pitch). Then non-Yaman Raga fixtures
  become possible: fixture carries {name, fundamental, ratios, tuning} + the
  fetched ruleSet as context -> expected stratifiedRatios.
- **Decision for owner:** keep the DB-fetch-by-name design (works), OR additionally
  serialize `ruleSet` for self-contained portability (belt-and-suspenders). Either
  way this is a choice, not a forced fix.

## RAGA-2 🟡 Mismatched ratios count: TS regenerates, Python preserves (EDGE CASE)

- On load, if `ratios.length !== ruleSetNumPitches`:
  - **TS** `Raga` constructor **discards** the serialized ratios and regenerates
    from the rule set (`setRatios`).
  - **Python** `Raga.from_json` passes `preserve_ratios=True` → **keeps** them.
- **BUT with the correct ruleSet injected (RAGA-1), counts MATCH** (the ratios were
  generated for that ruleSet) → both take the preserve path → no divergence in
  normal operation. This only bites in the **degenerate/error case**: ruleSet fetch
  skipped or failed, or the default Yaman ruleSet applied to a non-Yaman raga's
  ratios. Then TS regenerates (wrong raga) vs Python preserves.
- **Decision for owner:** pick the canonical mismatch behavior for the error path
  (preserve seems safer), and ideally make the ruleSet always available so the
  path is never hit. Low urgency given RAGA-1.

## RAGA-3 🟡 ruleSet is fetched at DIFFERENT LAYERS — not a data divergence

- Both sides recover the ruleSet from the DB by name; the layer differs:
  - **TS:** the **app layer** fetches (`getRaagRule(name)`) and injects into the raw
    JSON before `Piece.fromJSON`. The Raga constructor never fetches.
  - **Python:** the **Raga constructor** fetches (`client.get_raga_rules(name)`) when
    a client is passed.
- **Same outcome, different point.** Not a data-loss divergence.
- **Decision for owner:** align the pattern — e.g. Python client mirrors TS's
  fetch-then-inject-then-deserialize (or TS moves the fetch into a shared loader).
  Also: TWO endpoints do this job — web `getRaagRule` (server.ts) and
  Python-API `/ragaRules` (apiRoutes.ts). Consolidate during the endpoint merge.

## TRAJ-1 🔴 Python `to_json` still emits `name`, `instrumentation`, `tags`

- **TS** `Trajectory.toJSON()` strips all three (name derived from id,
  instrumentation inherited, tags default []). **Python** still writes them.
- **Canonical:** stripped. `name = names[id]`, `tags = []`, instrumentation from piece.
- **Fix (deferred):** remove the three keys from Python `Trajectory.to_json()`.

## TRAJ-2 🔴 Python `from_json` doesn't thread context to pitches

- **TS** `Trajectory.fromJSON(obj, ratios?, fundamental?)` passes context into
  `Pitch.fromJSON`. **Python** `from_json(obj)` has no context params and calls
  `Pitch.from_json(p)` bare — so **PITCH-1 propagates through every trajectory**.
- **Fix (deferred):** add `ratios`/`fundamental` params, thread to each pitch.
- **Fixtures:** `fixtures/trajectory/stripped-*` fail on Python until fixed.

## PHRASE-1 🔴 Python `to_json` still emits `raga`

- **TS** `Phrase.toJSON()` omits `raga` (inherited from piece). **Python** writes
  `'raga': self.raga.to_json()`.
- **Canonical:** stripped. **Fix (deferred):** remove `raga` from Python output.

## PHRASE-2 🔴 Python `from_json` threads no context and lacks legacy raga fallback

- **TS** `Phrase.fromJSON(obj, ratios?, fundamental?)`: `r = ratios ??
  phraseRaga.stratifiedRatios`, then threads `r,f` into every `Trajectory.fromJSON`.
- **Python** `from_json(obj)`: no context params, calls `Trajectory.from_json(t)`
  bare, and although it parses `obj['raga']`, it never uses it as context.
- **Effect:** (a) PITCH-1/TRAJ-2 propagate through phrases; (b) legacy phrases
  with an embedded raga but stripped pitches load at default frequencies.
- **Fix (deferred):** add params, derive `r,f` from param-or-embedded-raga, thread down.
- **Fixtures:** `fixtures/phrase/*` (both stripped and legacy-fallback) fail on
  Python until fixed.

## PIECE-1 🔴 Python `Piece.from_json` never extracts/threads the raga context

- **TS** `Piece.fromJSON`: `const ratios = raga.stratifiedRatios; const fundamental
  = raga.fundamental;` then `Phrase.fromJSON(p, ratios, fundamental)`. **This is
  where the context chain originates.**
- **Python** `Piece.from_json` parses `raga` but calls `Phrase.from_json(p)` with
  no context → **the entire threading chain is dead from the top.** Combined with
  PITCH/TRAJ/PHRASE `from_json` not accepting params, every pitch in every
  Python-loaded stripped piece uses default (12-TET / 261.63 Hz) context.
- **Fix (deferred):** extract `stratifiedRatios`/`fundamental` and thread down
  (the top of the chain; must be done together with the per-level param additions).
- **Fixtures:** `fixtures/piece/stripped-*` fail on Python until the whole chain is fixed.

## PIECE-2 🟡 Field-set drift in `to_json` — RESOLVED → PROP-2

Investigated 2026-07-10. Decisions captured in PROPOSALS.md (PROP-2).

- **`collections`** — **NO data loss** from TS omitting it. Membership is stored
  bidirectionally (collection docs hold `transcriptions:[ids]`; transcription docs
  hold the reverse `collections:[colIds]`), maintained ONLY by dedicated endpoints
  (`/addTranscriptionToCollection` etc.). Critically, `updateTranscription` uses
  `$set` (not `replaceOne`), so a piece save with no `collections` key leaves the
  DB field untouched. **`collections` is transcription-document metadata, not part
  of the musical Piece** → it should be OUT of the serialization (TS is correct).
  Python *including* it is the liability (risks clobbering server-managed membership
  back to a stale value on save). → **Python should drop it from `to_json`.**
- **Dates** — TS's "raw value" is inconsistent (JS `Date` → ISO via JSON.stringify,
  but Mongo `{$date}` → stays `{$date}`; Python even has defensive `$date` parsing).
  → **Canonical: ISO 8601 UTC strings on the wire** (`...Z`), BSON Date is a
  server-only storage detail. Fix timezone sloppiness on both sides (Python emits
  naive/no-offset and strips `Z`).
- Piece-level *stripping* is otherwise already aligned — both omit `durArray`,
  `sectionCategorization`, `sectionStarts`, `sectionStartsGrid`, `phrases` (server
  also `$unset`s these on every save).

## METER-1 🔴 PulseStructure `offsets` differs

- **TS** `PulseStructure.toJSON()` emits `offsets: this.proportionalOffsets` (the
  real per-pulse proportional offsets). **Python** emits `'offsets': [0.0]*size`
  (always zeros).
- **Effect:** micro-timing offsets are lost on the Python side.
- **Structural only** (no frequency impact); low severity but a real drift.
- **Fix (DEFERRED — deeper than mechanical):** Python's `PulseStructure` does NOT
  maintain a `proportional_offsets` array (TS does, updated as offsets apply). Python
  only has offset *methods* that mutate `pulse.real_time`. So the fix requires adding
  proportional-offset tracking/derivation to the Python meter logic (compute from
  pulse real_times vs the ideal grid, or maintain incrementally) — a focused change
  with its own tests, not a serialization one-liner. Not attempted with the mechanical
  frequency-chain fixes (2026-07-10).

## Supporting classes — CONSISTENT (no divergence found)

`Articulation`, `Automation`, `Chikari`, `Group` all serialize identically in TS
and Python (verified field-by-field). Chikari's `{fundamental, uniqueId}`-only
canonical form and self-containment are noted in SEM-2. Meter's nested
`Meter -> PulseStructure -> Pulse` shapes match except METER-1.

---

## Semantic notes (agreed behavior — preserve, don't "fix")

- **SEM-1** A komal (lowered) pitch of a swara whose raga rule set only defines
  the raised variant uses the **ET-tuned lowered slot** of `stratifiedRatios`
  (the absent variant falls back to `tuning`, not to any transcription ratio).
  Both implementations agree; fixtures encode it (`fixtures/piece/*-just-intonation`).
- **SEM-2** ~~Chikari is self-contained…~~ **SUPERSEDED → PROP-3.** Re-examined
  2026-07-10: playback is actually correct (both `Piece.chikariFreqs` /
  `chikari_freqs` derive drone frequencies from `raga.chikariPitches` — raga-tuned,
  non-12-TET-aware), so there is **no audible bug**. BUT the `Chikari` model's own
  `.pitches` (12-TET defaults) + stored `fundamental` are **vestigial for tuning** —
  a footgun: any consumer reading `chikari.pitches[i].frequency` directly (Python
  client, exports, analysis) silently gets 12-TET. Fix = single source of truth
  (chikari tuning derives from the raga). See PROP-3.

## STRING-SYNC 🟢 RESOLVED — Python now implements `ensure_string_synchronization`

**Resolution (2026-07-10):** the Python client now ports `ensure_string_synchronization`
(`Piece.from_json` calls it; `Python-API` PR #1). For Sitar/Sarangi tracks it synthesizes
a single silent id-12 second-string trajectory when that string has no non-silent content
— structurally identical to TS. Ported idempotently: an existing silent trajectory is
preserved (uniqueId kept), a fresh one is created only when the 2nd string is empty, so
`to_json → from_json → to_json` stays byte-stable (verified by the idempotence test).
Frequency conformance still compares MELODIC pitches only (excludes id-12) by design.
Original divergence below for history.

### (original) Python lacked `ensureStringSynchronization` (polyphonic 2nd string)

- **TS** `Piece.fromJSON` calls `ensureStringSynchronization()`, which synthesizes a
  **silent second string** (`trajectoryGrid[1]`, a single id-12 Silent trajectory) for
  polyphonic instruments (Sitar jor, Sarangi 2nd) when that string has no content.
- **Python** `Piece.from_json` has silent trajectories only for **duration-filling** on
  the main string — **no second-string synthesis** (no `ensure_string_synchronization`).
- **Effect:** after loading the same single-string Sitar piece, TS has 2 strings, Python
  has 1. Structural, not a frequency bug — the synthesized string is silent (no melody).
  Surfaced by the TS conformance suite (single-string pieces loaded 8 pitches vs 6).
- **Round-trip nuance:** once TS saves, the silent 2nd string is in the JSON, so Python
  then sees it too. The gap only shows for data never saved by TS-with-sync.
- **Decision for owner:** should the Python client implement `ensure_string_synchronization`
  to match TS structure? (It's a data client, not a synth — may not need it.)
- **Contract handling:** frequency conformance compares MELODIC pitches only (excludes
  id-12 Silent trajectories) so it's robust to this on both sides.

## VIB-1 🟡 v1 `vibObj.periods`: Python truncated, Swift kept a Double — RESOLVED → PROP-6

- **Python** (`idtap` ≤ 0.1.54) `VibObj.from_json` did `int(periods)`; **Swift**
  `VibratoObject` kept a `Double`; **TS** used the raw value (often a *string*, e.g.
  Babul Mora `{periods: '3.5', extent: '0.055'}`, coerced by arithmetic). So a stored
  non-integer `periods` rendered three different vibratos.
- **Canonical (PROP-6):** the v1 → v2 heal uses the **stored value as-is** —
  `rate = Number(periods) / durTot`, no truncation, no rounding — so whichever number
  was stored is what migrates. Fixture `vib-v1-legacy-string-fields-heals`
  (`periods: '3.5'`, `durTot: 0.474` → `rate = 7.3839…`) pins it; a client that
  truncates gets `rate = 6.329…` and fails.
- **Effect on old Python renders:** anything Python rendered from a non-integer
  v1 `periods` was already wrong relative to the web app; after the heal all three
  agree with what the web app played.

---

## Resolution workflow

1. Finish modeling every entity in the contract (surface all divergences here).
2. For each 🔴, decide the canonical behavior with the project owner.
3. Encode the decision as golden fixtures (→ 🟡).
4. Apply fixes to both implementations; wire conformance suites into CI (→ 🟢).
