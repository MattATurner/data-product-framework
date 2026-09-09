---
skill_id: direct/model-struct-shaping
implements: model-consumption-layer
methodology: direct
role: business_view
consumes: semantic-model.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Shape 1:N relationships as nested structures

The BigQuery-native alternative to splitting a parent and child into separate tables.

## When to nest

| Nest | Keep separate |
|---|---|
| Children are almost always read with the parent | Children are queried independently |
| Child cardinality is bounded and modest | Cardinality is large or unbounded |
| Consumers can handle `ARRAY<STRUCT>` | Consumers are BI tools that flatten poorly |

## Steps

1. Confirm the parent grain. Nesting must not change it — that is the whole point.
2. Aggregate children into `ARRAY<STRUCT<...>>` on the parent.
3. Name struct fields from the glossary.
4. Keep depth within the pack's nesting rule (default: two levels).
5. Record the decision and its rationale in the TDD.

## Must

- Preserve the parent grain and assert it after nesting.
- State in `semantics.md`, in business language, that children arrive with their parent.
