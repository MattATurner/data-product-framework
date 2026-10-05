---
name: model-struct-shaping
description: Shape a one-to-many relationship as nested repeated records on the parent row, preserving
  the parent grain. Use for role nested_view in a direct layer when children are read with their parent.
metadata:
  dpf:
    skill_id: direct/model-struct-shaping
    stage: consume
    scope: model
    implements: model-consumption-layer
    methodology: direct
    role: nested_view
    consumes:
    - staging-model.v1
    - semantic-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role: nested_view
      layer.methodology: direct
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Shape 1:N relationships as nested records

| Nest | Keep separate |
|---|---|
| Children are almost always read with the parent | Children are queried independently |
| Child cardinality is bounded and modest | Cardinality is large or unbounded |
| Consumers handle repeated records | Consumers are BI tools that flatten poorly |

## Steps

1. Confirm the parent grain. Nesting must not change it.
2. Aggregate children into `ARRAY<STRUCT<...>>` in the authored body; declare
   `nesting: [{child, as, depth}]` in the manifest.
3. Keep depth within the pack rule (`nesting-depth-limit`, default 2).
4. State in `semantics.md`, in business language, that children arrive with their parent.
