---
name: test-data-product
description: Generate the product's test specification from grains, quality rules, pack integrity rules
  and the acceptance mapping, run it against a deployed build, and record evidence bound to the build
  digest for G4.
metadata:
  dpf:
    skill_id: test-data-product
    stage: test
    scope: product
    implements: test-data-product
    consumes:
    - semantic-model.v1
    - quality-policy.v1
    - acceptance.v1
    produces:
    - test-spec.v1
    - test-evidence.v1
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - test_planning
    gate: G4
    gcp:
    - BigQuery
---

# Test the data product

```bash
dpf test plan <product>                    # list every test and what it verifies
dpf test run <product> --live              # run automated and static tests, record evidence
dpf test attest <product> AT-5 --by "Finance controller" --role finance
```

## Test kinds

| Kind | From | Method |
|---|---|---|
| grain | every model's grain columns | automated |
| quality | quality rules | automated |
| reject_gate | quarantine rules | automated |
| scd_integrity | Type 2 dimensions | automated |
| integrity | fact dimension references | automated |
| acceptance | `acceptance.yaml` (AX scenarios) | automated, static or attestation |

Evidence (`test-evidence.v1`) is written to `evidence/<product>/` and carries the build
digest. Evidence from an older build is stale and does not count at G4.

## Must

- Never record evidence that was not observed. Attestations name the person and role.
