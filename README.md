# idtap-contract

**The language-neutral source of truth for IDTAP's serialized data model.**

IDTAP's domain model (Pitch, Trajectory, Phrase, Piece, Raga, …) is implemented
**twice** — once in TypeScript (`idtap`: web app + server) and once in Python
(`idtap-api`: the PyPI client). You cannot share an *implementation* across two
languages, so the two copies inevitably **drift**. This repo shares the one thing
that *can* be common: a **contract** — JSON Schemas + golden fixtures — that both
implementations are provably tested against.

## Why this exists

A real bug this contract prevents: IDTAP recently stripped redundant fields from
its JSON (PR #887) — `Pitch` no longer serializes `ratios`/`fundamental`; those
are inherited from the piece's raga and **threaded in at load time**. The Python
client was never updated, so `Pitch.from_json()` silently fell back to defaults
(12-TET, 261.63 Hz). Result: a Yaman transcription with a 246 Hz fundamental
**loaded at 261.63 Hz** — wrong frequencies, no error. A conformance fixture that
pins `(pitch json + raga context) → expected frequency` turns that silent drift
into a failing test.

## The core idea

A serialized entity has two parts, and the contract pins **both**:

1. **Wire shape** — which fields exist and their types (`schemas/*.schema.json`,
   JSON Schema). Catches *structural* drift.
2. **Semantics** — what the bytes *mean*. For Pitch, `frequency` is derived from
   `(swara, raised, oct, logOffset)` **plus the raga context** `(ratios,
   fundamental)`, which is **not in the Pitch JSON** — it is threaded down from
   the enclosing Piece. Golden fixtures (`fixtures/*/`) pin input + context →
   expected derived values. Catches *behavioral* drift (the Yaman class of bug).

Codegen can enforce #1 for free; only executable fixtures enforce #2.

## Layout

```
schemas/                 JSON Schema per entity (the wire shape)
  pitch.schema.json
fixtures/<entity>/       golden fixtures: input json + context + expected values
  pitch/
    index.json
    stripped-*.json      canonical (stripped) form, context threaded separately
    legacy-embedded-*.json   legacy form, ratios/fundamental embedded in the json
conformance/             reference runner + how each repo wires up its own tests
  validate_fixtures.py   self-check that fixtures are internally consistent
tools/                   fixture generators (recompute expected values)
```

## The stripped format (what PR #887 removed)

| Entity | Field(s) removed from serialization | Recovered at load from |
|---|---|---|
| **Pitch** | `ratios`, `fundamental` | raga context (threaded) |
| **Trajectory** | `name`, `instrumentation`, `tags` | `name`/`instrumentation` derived; `tags` defaults `[]` |
| **Phrase** | `raga` | piece-level raga |
| **Piece** | `durArray`, `sectionCategorization` (+ legacy `phrases`, `sectionStarts`, `sectionStartsGrid`) | `durArrayGrid[0]`, `sectionCatGrid[0]`, `phraseGrid[0]` |

**Context threading** (the load-time recovery path):

```
Piece.fromJSON(obj)
  → extract raga.stratifiedRatios, raga.fundamental
  → Phrase.fromJSON(…, ratios, fundamental)
    → Trajectory.fromJSON(…, ratios, fundamental)
      → Pitch.fromJSON(…, ratios, fundamental)
```

Each level: **threaded context wins; embedded (legacy) values are fallback.**

## Three scenarios every implementation must handle

- **A — stripped** (new TS output): no `ratios`/`fundamental` on pitches, no
  `raga` on phrases, etc. Context must be threaded from the piece raga.
- **B — legacy full** (old DB data): everything embedded. Must still load
  correctly using embedded values.
- **C — mixed** (partially migrated): some pitches embed ratios, some don't.
  Threaded context takes precedence; embedded is fallback.

Fixtures are tagged with their scenario so both repos exercise all three.

## How each implementation consumes this

The contract is vendored into both repos (git submodule or a synced copy) and run
in CI. Each repo provides a thin adapter that maps a fixture to *its* model and
asserts against `expected`. See `conformance/README.md` for TS (vitest) and
Python (pytest) adapter templates. `conformance/validate_fixtures.py` is the
reference loop and this repo's own self-check.

## Versioning

The contract is versioned (`version` in `contract.json`, currently **0.2.0**;
`versionPolicy` there carries the changelog). Serialized documents carry no
version field, so the assertion lives in each client's **conformance suite**, not
in the loader:

1. Each implementation keeps one constant naming the contract version it was
   built against — `CONTRACT_VERSION` in `conformance/validate_fixtures.py` is
   the reference; the clients mirror it (`src/ts/tests/contract-conformance.test.ts`
   in idtap-platform, `idtap/tests/test_contract_conformance.py` in idtap-client,
   the Swift golden test in idtap-swift).
2. That suite reads the vendored `contract.json` and asserts
   `version == CONTRACT_VERSION` **exactly**. A minor bump (wire semantics
   changed) therefore fails CI in every client until the client is updated and
   its constant bumped; a patch bump is reserved for fixture/doc additions and
   should be applied to the constant in the same sync commit.
3. The constant is bumped **only** in the commit that implements the new
   semantics (for 0.2.0: the PROP-6 vibrato heal + `id == 13` canonical rule).

This is deliberately a CI-time check. A load-time check would need a
`contractVersion` field on the wire, which is a separate proposal.

## Status / roadmap

- [x] **Pitch** — schema + 8 fixtures (12-TET, non-default fundamental, just
      intonation, logOffset, legacy-embedded) + reference runner. *This is the
      reference slice; the others follow the same pattern.*
- [x] **Raga** — schema + 3 fixtures pinning `Raga JSON → stratifiedRatios +
      fundamental`. Surfaced RAGA-1..3 divergences (see `DIVERGENCES.md`).
- [x] **Trajectory** — schema + 27 fixtures (pitch-frequency preservation through
      context threading; stripped name/instrumentation/tags; every id 0-13).
      Surfaced TRAJ-1/2.
- [x] **Vibrato v2 (PROP-6, contract 0.2.0)** — `vibObj` sub-schema (v2 strict,
      v1 LEGACY) + 8 `vib-*`/`canonical-omits-vibobj-*` fixtures pinning the
      lossless v1→v2 heal, the normative curve at 21 sample points (equal-to-v1
      proof, extent ramp, non-integer cycles with both tapers, sub-cycle), and
      the `id == 13`-only canonical rule (PROP-6b). Values are bit-identical to
      the TS reference golden (`tools/crosscheck_vibrato_golden.py`).
- [x] **Phrase** — schema + 2 fixtures (grid context-threading + legacy
      raga-fallback). Surfaced PHRASE-1/2.
- [x] **Piece** — schema + 3 fixtures (full-piece frequency preservation through
      the whole threading chain; legacy full-embedded). Surfaced PIECE-1/2, SEM-1.
- [x] **Supporting sub-schemas** — Articulation, Automation, Chikari, Group, Meter
      (structural). All consistent except METER-1 (PulseStructure.offsets).
- [x] Wire conformance suites into `idtap` and `idtap-api` CI (2026-07-13)
- [x] Publish contract version + compatibility assertion — designed above
      (`CONTRACT_VERSION` constant vs `contract.json`); reference check in
      `validate_fixtures.py`. Clients add the one-line assertion with their
      0.2.0 sync.
