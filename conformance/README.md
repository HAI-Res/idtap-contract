# Conformance

Each implementation repo runs the golden fixtures against **its own** model and
asserts the results match `expected`. The adapter is ~20 lines; the fixtures do
the work.

`validate_fixtures.py` in this folder is the **reference loop + self-check**: it
recomputes `expected` from the canonical rule (no real model) to prove the
fixtures are internally consistent. CI here runs it. The two templates below are
what the *implementation* repos add.

## Python (`idtap-api`) — pytest

```python
import json, glob, os, pytest
from idtap.classes.pitch import Pitch  # the real model under test

FIX = glob.glob("path/to/idtap-contract/fixtures/pitch/*.json")
FIX = [f for f in FIX if not f.endswith("index.json")]

@pytest.mark.parametrize("path", FIX, ids=lambda p: os.path.basename(p))
def test_pitch_conformance(path):
    fx = json.load(open(path))
    ctx = fx.get("context") or {}
    # Threaded context wins; embedded values are the fallback (see contract).
    p = Pitch.from_json(
        fx["pitchJson"],
        ratios=ctx.get("ratios"),
        fundamental=ctx.get("fundamental"),
    )
    exp = fx["expected"]
    rel = fx.get("tolerance", {}).get("rel", 1e-9)
    assert p.frequency == pytest.approx(exp["frequency"], rel=rel)
    assert p.numbered_pitch == exp["numberedPitch"]
    assert p.chroma == exp["chroma"]
    assert p.sargam_letter == exp["sargamLetter"]
```

Until `Pitch.from_json` accepts and threads `ratios`/`fundamental` (per
`SERIALIZATION_SYNC_SPEC.md`), the `stripped-*` non-default-fundamental and
just-intonation cases **fail** — which is the point: they surface the Yaman bug.

## TypeScript (`idtap`) — vitest

```ts
import { readFileSync, readdirSync } from "fs";
import { Pitch } from "@/ts/model/pitch";
import { describe, it, expect } from "vitest";

const dir = "path/to/idtap-contract/fixtures/pitch";
const files = readdirSync(dir).filter(f => f.endsWith(".json") && f !== "index.json");

describe("pitch conformance", () => {
  for (const file of files) {
    const fx = JSON.parse(readFileSync(`${dir}/${file}`, "utf8"));
    it(fx.name, () => {
      const ctx = fx.context ?? {};
      const p = Pitch.fromJSON(fx.pitchJson, ctx.ratios, ctx.fundamental);
      const rel = fx.tolerance?.rel ?? 1e-9;
      expect(p.frequency).toBeCloseTo(fx.expected.frequency, -Math.log10(rel * fx.expected.frequency));
      expect(p.numberedPitch).toBe(fx.expected.numberedPitch);
      expect(p.chroma).toBe(fx.expected.chroma);
      expect(p.sargamLetter).toBe(fx.expected.sargamLetter);
    });
  }
});
```

## Contract rule the adapters must honor

`ratios`/`fundamental` come from **context first, embedded fallback**:

```
ratios      = context.ratios      ?? pitchJson.ratios       (legacy)
fundamental = context.fundamental ?? pitchJson.fundamental  (legacy)
```

- **stripped** fixtures: context is populated, json has no ratios/fundamental.
- **legacy** fixtures: context is null, json embeds ratios/fundamental.
- **mixed** (future): context populated AND json embeds — context must win.

## Trajectory vibrato fixtures (PROP-6, contract 0.2.0)

The `fixtures/trajectory/vib-*` and `canonical-omits-vibobj-for-non-13` fixtures
add three optional `expected` blocks; adapters should assert each when present:

| `expected` key | assert |
|---|---|
| `vibObj` | after `fromJSON`, the trajectory's vibObj equals this v2 object (all five keys, rel tolerance). For v1 input this checks the heal. |
| `curveX` / `curveFrequencies` | `traj.compute(x)` (TS `id13`, Python `id13`, Swift `compute`) at each `curveX` equals `curveFrequencies[i]` within `tolerance.rel`. |
| `vibObjInCanonical` | `"vibObj" in traj.toJSON()` equals this boolean (true only for id 13 — PROP-6b). |

`expected.attach` (`P`, `x1`, `x2`) and `expected.v1Equivalent` are informational
for debugging a curve mismatch; clients need not expose them.

## Syllable tier, system, packs (PROP-7/8/9, contract 0.3.0)

`conformance/syllables.py` is the reference: read it as the spec and port its
functions. Each `fixtures/syllable/*.json` has a `kind`; the adapter does:

| `kind` | run | assert |
|---|---|---|
| `heal` | load `pieceJson` (phrases without `syllables` heal) | each phrase's syllables equal `expected.syllables[track][phrase]`; when `legacyRoundTrip`, re-serializing gives back every legacy field and the `'0.00'`/`'1.00'` consonant articulations of the input exactly; `legacyAfterProjection[uid]` where given |
| `project` | load, serialize | the legacy fields of each trajectory equal `expected.legacy[uid]` (`art0`/`art1` = the consonant articulations, `null` = none); `derivedIpa` from the pack in syllable order |
| `rehome` | load `pieceJson`, apply the structural edit in `pieceAfterEdit`, run your re-homing | syllables per phrase equal `expected.syllables`; `dropped`; the legacy fields equal those before the edit |
| `invariants` | each case: load, validate | error codes equal `expected.violations` and warning codes (`track-not-vocal`) equal `expected.warnings` (each sorted; `[]` = none) |
| `guard` | each case | your legacy-safe check gives `expected.legacySafe` with `legacySafeReasons` |

Every kind except `invariants`/`guard` also carries `legacySafe`, `legacySafeReasons`
and `violations` for the loaded piece. `fixtures/system/*` assert `expected.resolved`
(the system after defaults), `pack`, `syllableUi` (`"system" in pieceJson`), and
`derivedIpa` where present. Bundle `packs/*.json` as data; do not copy their tables
into code.

The write guard reads the stored legacy fields, not the projection (PROP-8).

Legacy-field shape used by `expected.legacy`: the nine wire fields (`vowel`,
`startConsonant{,Hindi,Ipa,EngTrans}`, `endConsonant{,Hindi,Ipa,EngTrans}`), absent
when undefined, plus `art0`/`art1`. In-memory `vowelHindi/Ipa/EngTrans` are not on the
wire and not asserted.

Version assertion (README "Versioning"): add to the suite

```python
assert json.load(open("path/to/idtap-contract/contract.json"))["version"] == CONTRACT_VERSION  # "0.3.0"
```
