# Known TS ↔ Python divergences

Divergences discovered while building the contract. **These are design questions
to resolve before "fixing" the Python client** — patching Python to match TS
would bake in TS behavior that may itself be wrong. Each needs an explicit
decision on the canonical behavior; the fixtures then encode that decision and
both implementations are held to it.

Status legend: 🔴 unresolved · 🟡 decided, not yet enforced · 🟢 enforced by fixtures

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

## PIECE-2 🟡 Minor field-set drift in `to_json`

- **Python** emits a `collections` field; **TS** does not.
- **Dates:** Python serializes `dateCreated`/`dateModified` as ISO strings;
  TS emits the raw stored value (often a Mongo `{$date}` or Date). Not
  frequency-affecting, but the canonical wire shape should be pinned.
- Piece-level *stripping* is otherwise already aligned — both omit `durArray`,
  `sectionCategorization`, `sectionStarts`, `sectionStartsGrid`, `phrases`.

## METER-1 🔴 PulseStructure `offsets` differs

- **TS** `PulseStructure.toJSON()` emits `offsets: this.proportionalOffsets` (the
  real per-pulse proportional offsets). **Python** emits `'offsets': [0.0]*size`
  (always zeros).
- **Effect:** micro-timing offsets are lost on the Python side.
- **Structural only** (no frequency impact); low severity but a real drift.
- **Fix (deferred):** Python should serialize the actual proportional offsets.

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
- **SEM-2** `Chikari` is self-contained: it serializes its OWN `fundamental` and
  applies it to its drone pitches on load; **neither** implementation threads raga
  ratios into chikari pitches (both use default/embedded ratios + the chikari
  fundamental). So chikari is NOT part of the Yaman context chain — consistent
  across TS/Python. (Chikari pitches in a non-12-TET raga therefore use 12-TET
  ratios in both; a separate design question, but not a TS↔Python divergence.)

---

## Resolution workflow

1. Finish modeling every entity in the contract (surface all divergences here).
2. For each 🔴, decide the canonical behavior with the project owner.
3. Encode the decision as golden fixtures (→ 🟡).
4. Apply fixes to both implementations; wire conformance suites into CI (→ 🟢).
