---
name: model-scd
description: 'Model a Kimball dimension with Type 1 or Type 2 history from staged change history: validity
  windows, surrogate key, unknown member and current-valued attributes. Use for role dimension in a kimball
  layer.'
metadata:
  dpf:
    skill_id: kimball/model-scd
    stage: integrate
    scope: model
    implements: model-integration-layer
    methodology: kimball
    role: dimension
    consumes:
    - staging-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role: dimension
      layer.methodology: kimball
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Model a slowly changing dimension

## Type selection

Derived from the BRD history answer, never asked directly.

| Business answer | Type |
|---|---|
| "Past figures should show the value that applied at the time" | **2** |
| "Past figures should update to the current value" | **1** |

## Declare in the manifest

```yaml
- name: dim_customer
  role: dimension
  grain_columns: [customer_id, valid_from]
  natural_key: [customer_id]
  surrogate_key: sk_customer
  history_semantics: point_in_time
  conformed_as: dim_customer
  attributes:
    scd_type: 2
    source: stg_customers
    tracked: [customer_segment, region]          # Type 2: a change opens a new version
    current: [customer_name, customer_email]     # Type 1: always the latest value
```

## What dpf generates

A table rebuilt from `<source>_history`: a new version whenever a tracked attribute
changes, validity windows from the change times (first version from 1900-01-01), a
surrogate key that is not the natural key, current-valued attributes from the latest
staging row, an unknown member `-1`, and policy tags on protected columns. Tests: grain
uniqueness, no overlapping windows, exactly one current row per natural key.
