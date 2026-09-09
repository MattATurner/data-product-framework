---
skill_id: kimball/model-transaction-fact
implements: model-integration-layer
methodology: kimball
role: fact
consumes: staging-model.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Model a transaction fact

One row per business event, at the grain the TDD derived from the BRD.

## Steps

1. Assert the declared grain. Duplicates fail the build — they do not warn.
2. Resolve dimension surrogate keys **as at the event date** where the dimension is SCD2.
3. Fall back to the unknown member for unresolvable references; never null, never drop.
4. Carry declared measures with their additivity.
5. Keep degenerate dimensions (order numbers and the like) on the fact.
6. Partition on the event date; cluster on the highest-selectivity dimension keys.
7. Emit `semantic-model.v1`.

## Must

- Generate the grain uniqueness assertion from `grain_columns`.
- Honour the restatement window from the BRD when rebuilding partitions.
