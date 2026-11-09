# dbt adapter

Status: **implemented**. Declared in `adapter.yaml`. For teams already invested in dbt.

The dbt adapter renders the same semantic models and SQL bodies as the Dataform adapter:

| Semantic model | dbt artefact |
|---|---|
| raw entity | `models/sources.yml` source table |
| `role: staging` | `<m>__candidates`, `<m>`, `<m>_rejects` (and `<m>_history`) models |
| `role: business_view` / `nested_view` | `view` or `table` model |
| `role: materialised_view` | `materialized_view` model |
| `role: dimension` (Type 2) | `table` model rebuilt from staged history |
| `role: fact` | `incremental` model (`insert_overwrite` on the partition column) |
| `role: calendar` | `table` model |
| grain, quality, reject gate, acceptance | singular tests in `tests/` |

The reject-gate test also references the clean staging model, so `dbt build` skips every
downstream model when a row is quarantined, the same blocking behaviour as Dataform.
