---
engine_id: dbt
status: supported
tool_tier: 4
tool: dbt_cli
---

# dbt adapter

For customers already invested in dbt. Interface parity with the Dataform adapter is the
requirement — the same `semantic-model.v1` must render to an equivalent dbt project.

| Semantic model | dbt artefact |
|---|---|
| typed_source / business_view | model (`view` or `table` materialisation) |
| dimension (SCD2) | snapshot, or incremental model with merge |
| fact | incremental model, partitioned and clustered |
| grain_columns | `unique_combination_of_columns` style test |
| quality rules | schema tests with matching severity |

**Not yet implemented.** Scaffold only — see the delivery plan.
