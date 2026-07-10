# Proposals (decided, not yet implemented)

Design decisions made during contract review, to be applied to the TS and Python
implementations later. No implementation has changed yet.

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

### Implementation checklist (deferred)
- [ ] TS `Raga.toJSON()` — include `ruleSet`.
- [ ] TS `Raga.fromJSON`/constructor — use provided `ruleSet`; stop regenerating ratios
      on mismatch (preserve).
- [ ] TS app load path — keep DB fetch only as legacy fallback when `ruleSet` absent.
- [ ] Python `Raga.to_json()` — include `rule_set` (camelCase `ruleSet` on the wire).
- [ ] Python `Raga.from_json` — use provided ruleSet; DB fetch only as fallback.
- [ ] Migration: on load, `ruleSet` present → use; absent → heal from DB; persist on save.
- [ ] Consolidate the two endpoints (`getRaagRule` web / `/ragaRules` Python-API).
- [ ] `raga.schema.json` — add `ruleSet` (migrated-optional: required for new data,
      tolerated-absent for legacy).
- [ ] Contract fixtures — add **non-Yaman** Raga fixtures (Bhairav [komal re/dha],
      Todi [komal re/ga, tivra ma, komal dha], a both-variants raga) now that ruleSet
      is part of the serialized form. Lift the "Yaman-only" scope note.

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
  - [ ] Python `Piece.to_json()` — remove `collections`.
  - [ ] Keep membership solely under the add/remove endpoints.

### Dates — ISO 8601 UTC strings on the wire
- Today TS emits inconsistent values (JS `Date` → ISO via JSON.stringify, but Mongo
  `{$date}` stays `{$date}`); Python emits `.isoformat()` (naive, no offset) and
  strips `Z` on read. Both are sloppy about timezone.
- **Canonical:** `dateCreated`/`dateModified` are **ISO 8601 UTC strings** with an
  explicit `Z` (e.g. `2026-07-10T14:30:00.000Z`) on the wire. BSON `Date` is a
  **server-only storage detail** — the server parses ISO → Date on write (preserving
  date indexing/range queries) and emits ISO on read. Never leak `{$date}` into the API.
  - [ ] TS — ensure dates serialize as ISO UTC, never `{$date}`.
  - [ ] Python — emit tz-aware UTC ISO; stop stripping `Z`; parse as UTC.
  - [ ] Server — parse incoming ISO → BSON Date on save.
  - [ ] `piece.schema.json` — pin `dateCreated`/`dateModified` as ISO-8601 date-time strings.
