---
engine_id: dataform
status: default
tool_tier: 4
tool: dataform_api
---

# Dataform adapter

## Renders

| Semantic model | Dataform artefact |
|---|---|
| `role: typed_source` | `.sqlx` view or incremental table |
| `role: business_view` | `.sqlx` view |
| `role: materialised_view` | `.sqlx` with `type: "table"` or a BigQuery materialized view |
| `role: dimension` (SCD2) | incremental `.sqlx` with merge logic |
| `role: fact` | incremental `.sqlx`, partitioned and clustered |
| `grain_columns` | `assert_<model>_grain` uniqueness assertion |
| `quality-policy.v1` rules | assertions with matching severity |

## Notes

- Assertions are generated, never hand-written — they derive from the declared grain and
  the BRD's fitness answers.
- Dependency order comes from the composed skill DAG, not from `ref()` archaeology.
- Workflow configs carry the freshness cadence from the BRD.
