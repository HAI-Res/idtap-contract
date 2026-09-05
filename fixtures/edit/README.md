# Contract proposals (from the Swift port)

Golden fixtures proposed for `idtap-contract`, generated from `IDTAPCore` by
`Tests/IDTAPCoreTests/ContractProposalTests.swift` (`IDTAP_WRITE_PROPOSALS=1 swift test
--filter ContractProposalTests` rewrites them; the plain test checks they are current and
that every edit fixture replays).

## `edit/` — edit round-trip fixtures (new entity)

```
{
  "name", "description", "scenario": "edit",
  "pieceJson":  the piece before (canonical stripped form, deterministic ids),
  "operation":  { "op": <name>, ...arguments in the web's vocabulary },
  "expected":   observables after the edit,
  "tolerance":  { "rel": 1e-9 }
}
```

`operation.op` is one of `deleteTrajectories`, `insertSilentTrajectoryLeft`,
`insertFixedTrajectoryRight`, `insertPhraseDivision`, `deletePhraseDivision`,
`moveDragDot`; locations are `{track, phraseIdx, stringIdx, trajIdx}` (index into
`trajectoryGrid[stringIdx]`), times are absolute seconds, `logFreq` is log2 Hz.

`expected` pins what any implementation must agree on and nothing implementation-specific:
`durTot`, `phraseStarts`, per phrase `durTot`, `isSectionStart`, `chikariKeys` and per string
the trajectories' `id`, `durTot`, `durArray`, `pitchFrequencies`, `articulations` (key → name);
`survivingTrajectoryIds` lists the pre-existing ids still present, in order (ids of created
trajectories are minted by the implementation and are not pinned). An adapter: load
`pieceJson`, apply the operation, compare its own observables to `expected` at the tolerance.

## `raga/` — rule-set / ratios count mismatch (RAGA-2)

Same shape as `fixtures/raga/*`: `ragaJson` in, `expected.fundamental` and
`expected.stratifiedRatios` out, plus `expected.ratiosPreserved` (the stored ratios must
survive the load untouched) and `expected.ruleSetNumPitches`. Two cases: a rule set with more
pitches than stored ratios (komal re added to Yaman) and one with fewer (pa removed).
