# Dataform adapter

Status: **implemented** (default engine). Declared in `adapter.yaml`.

| Semantic model | Dataform artefact |
|---|---|
| raw entity | `definitions/sources/raw_<entity>.sqlx` declaration |
| `role: staging` | `<m>__candidates` view (typed body, dedupe, reject reason), `<m>` view, `<m>_rejects` view, `<m>_history` view when a Type 2 dimension reads it |
| `role: business_view` / `nested_view` | view or table from the authored body |
| `role: materialised_view` | materialized view from the authored body |
| `role: dimension` (Type 2) | table rebuilt from staged history: validity windows, surrogate key, unknown member, policy tags |
| `role: fact` (transaction) | incremental table, partitioned and clustered, restated inside the correction window |
| `role: calendar` | generated date table |
| `grain_columns` | `assert_<model>_grain` (blocking) |
| quarantine rules | `assert_<model>_no_rejects`, listed as a dependency of every gold model |
| acceptance tests | assertions tagged `acceptance`, excluded from scheduled runs |

Notes:

- Assertions are generated from the declared grain, the quality policy, the pack rules and
  the acceptance mapping. They are never hand-written.
- Every generated file starts with a `dpf:` header naming the skill and requirements it
  realises, so `dpf trace` can follow a requirement to the artefact.
- Workflow configs (one per orchestration schedule) are rendered as Terraform in
  `generated/<product>/terraform/`.
