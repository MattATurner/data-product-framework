---
skill_id: kimball/model-scd
implements: model-integration-layer
methodology: kimball
role: dimension
consumes: staging-model.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Model a slowly changing dimension

## SCD type selection

Derived from the BRD history answer — never asked directly.

| Business answer | Type |
|---|---|
| "Past figures should show the value that applied at the time" | **2** |
| "Past figures should update to the current value" | **1** |
| "We need the previous value alongside the current one" | **3** |
| "Both current and as-at views are needed" | **6** |

## Steps

1. Read the staging model and the TDD's declared SCD type.
2. Generate a surrogate key. It must not be the natural key renamed.
3. For type 2: `valid_from`, `valid_to`, `is_current`; close the prior row on change.
4. Add an explicit unknown member so fact references never go null.
5. Handle late-arriving members: create the member, backfill the reference.
6. If `conformed_as` is set, validate against `registry/conformance.yaml` and fail on
   grain or key conflict, naming the owning domain.
7. Emit `semantic-model.v1`.

## Must

- Assert one row per natural key per validity window.
- Never allow a null foreign key reference.
