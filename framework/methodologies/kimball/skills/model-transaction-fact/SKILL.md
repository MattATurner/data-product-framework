---
name: model-transaction-fact
description: Model a Kimball transaction fact at the declared grain with dimension keys resolved as at
  the event date, additive measures, flags and an incremental restatement window. Use for role fact in
  a kimball layer.
metadata:
  dpf:
    skill_id: kimball/model-transaction-fact
    stage: integrate
    scope: model
    implements: model-integration-layer
    methodology: kimball
    role: fact
    consumes:
    - staging-model.v1
    - semantic-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role: fact
      layer.methodology: kimball
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Model a transaction fact

One row per business event, at the grain the TDD derived from the BRD.

## Declare in the manifest

```yaml
attributes:
  fact_type: transaction
  source: stg_order_lines
  event_date: order_date
  restatement_window_days: 90
  dim_refs:
    - {dimension: dim_customer, natural_key: customer_id, as_at: order_date}
    - {dimension: dim_date, from: order_date}
  measures:
    - {name: net_amount, additivity: additive}
  degenerate: [order_status]
  flags:
    - {name: is_cancelled, expression: "order_status = 'CANCELLED'"}
```

## What dpf generates

An incremental table partitioned on the event date that rebuilds only dates inside the
restatement window. Type 2 keys are resolved as at the event date; an unresolved member
maps to `-1` and raises a late-arrival warning, never a dropped row. Tests: grain
uniqueness and natural keys never null (rule `fact-fk-integrity`).
