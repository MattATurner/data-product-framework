---
name: model-materialisation
description: Persist a business view as a BigQuery materialized view when repeated aggregation over a
  stable base justifies it, recording the choice and its BRD basis. Use for role materialised_view in
  a direct layer.
metadata:
  dpf:
    skill_id: direct/model-materialisation
    stage: consume
    scope: model
    implements: model-consumption-layer
    methodology: direct
    role: materialised_view
    consumes:
    - semantic-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role: materialised_view
      layer.methodology: direct
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Decide and apply materialisation

| Option | Choose when | Trade-off |
|---|---|---|
| View | Low query volume; freshness matters more than latency | Full compute on every read |
| Materialized view | Repeated aggregation over a stable base | SQL restrictions apply: verify current limits at design time |
| Table | Complex logic, predictable refresh windows | Staleness between runs; needs orchestration |
| Incremental table | Large volumes with a reliable change signal | Needs a restatement window |

Driven by BRD answers (freshness, expected users, restatement), not preference. Where a
materialized view cannot express the logic, fall back to a table and say so in the TDD.
