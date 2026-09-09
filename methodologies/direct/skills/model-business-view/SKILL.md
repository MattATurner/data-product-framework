---
skill_id: direct/model-business-view
implements: model-consumption-layer
methodology: direct
role: business_view
consumes: semantic-model.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Build the business view

Apply business logic and shape the output for consumers.

## Steps

1. Read the signed `semantics.md`. Every statement in it must be true of this view.
2. Apply derived fields, filters and business rules from the TDD.
3. Enforce exclusion rules centrally — never leave them to the consumer.
4. Name columns from the glossary.
5. Nest child entities where the TDD's nesting strategy calls for it
   (see `direct/model-struct-shaping`).
6. Emit `semantic-model.v1`.

## Must

- Enforce every rule stated in `semantics.md`.
- Declare and assert the grain.
- Cite the BRD requirement id for each business rule implemented.

## Must not

- Introduce a rule that is not in the TDD. If it is missing, raise a gap.
