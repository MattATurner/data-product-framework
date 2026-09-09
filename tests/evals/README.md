# Agent evaluation harness

Each eval is a fixture plus the properties the output must have, scored mechanically.
Run on every skill change **and on every model version change** — this is the honest
answer to "did upgrading the model break anything".

| Eval | Asserts |
|---|---|
| `incomplete-brd` | A BRD missing level-of-detail or history answers fails G0, and the gap register names the question to ask |
| `grain-violation` | Duplicate rows at the declared grain **fail** the build; they must not warn |
| `history-semantics` | A BRD requiring "as at the time" resolves to point-in-time history, never current-only |
| `no-methodology-envy` | A simple single-source product resolves to `direct`, not Kimball |
| `orphan-design` | A TDD decision citing no requirement id fails G1 |
| `stale-tdd` | Bumping the BRD version marks the TDD stale and blocks build |
| `modelling-vocabulary` | A BRD containing "grain" or "SCD" fails validation |
| `tool-tier` | A skill at tier 5 without an ADR fails lint |
| `unsupported-engine` | Kimball SCD2 on Dataflow fails compose rather than generating code |
| `idempotency` | Re-running the chain yields byte-identical artefacts |
| `governance-gate` | A product missing a required catalog aspect cannot reach `published` |

## Structure

```
tests/evals/<eval-id>/
├── eval.yaml       fixture inputs and expected verdict
└── expected.md     the properties the output must satisfy
```
