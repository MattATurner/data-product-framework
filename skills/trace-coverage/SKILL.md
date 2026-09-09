---
skill_id: trace-coverage
implements: traceability
consumes: brd.yaml, tdd/spec.md
produces: trace.md
tool_tier: 4
tool: local
gate: G1
---

# Build the traceability matrix

```
BRD requirement -> semantics statement -> TDD decision -> skill -> artefact -> test -> last run
```

## Blocking failures

| Failure | Meaning |
|---|---|
| **Orphan requirement** | A BRD requirement with no derivation, decision or test — something asked for is not being built |
| **Orphan design** | A TDD decision citing no requirement id — something is being built nobody asked for |
| **Stale TDD** | `satisfies:` names a superseded BRD version |

## Must

- Report both directions. One-way coverage is the usual failure and it hides unjustified work.
- At G4, emit the matrix as the acceptance pack.
