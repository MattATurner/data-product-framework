---
name: trace-coverage
description: Build the requirement-to-evidence traceability matrix (requirement, decision, manifest element,
  artefact, test, evidence) in both directions and fail on orphans. Use at G1, G3 and G4.
metadata:
  dpf:
    skill_id: trace-coverage
    stage: test
    scope: product
    implements: traceability
    consumes:
    - product-manifest.v1
    - test-spec.v1
    - test-evidence.v1
    produces:
    - trace-matrix.v1
    tool_tier: 4
    tool: dpf-local
    needs:
    - traceability
    gate: G3
---

# Build the traceability matrix

```
requirement -> decision -> manifest element -> generated artefact -> test -> evidence
```

```bash
dpf trace <product>        # writes generated/<product>/trace-matrix.json
```

## Blocking failures

| Failure | Meaning |
|---|---|
| Orphan requirement | A requirement with no decision, element, artefact or test |
| Orphan design | A decision or element citing no requirement or platform capability |
| Untested scenario | An AX scenario with no acceptance test |
| Stale TDD | The TDD satisfies a superseded BRD version |

Artefacts are found through the `dpf:` header each generated file carries. At G4 the
matrix, with evidence status per requirement, is the acceptance pack.
