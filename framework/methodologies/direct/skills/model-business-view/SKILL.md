---
name: model-business-view
description: Build a business view from an authored SQL body over staging or integration models, enforcing
  the signed semantics centrally. Use for role business_view in a direct layer.
metadata:
  dpf:
    skill_id: direct/model-business-view
    stage: consume
    scope: model
    implements: model-consumption-layer
    methodology: direct
    role: business_view
    consumes:
    - staging-model.v1
    - semantic-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role: business_view
      layer.methodology: direct
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Build the business view

## Steps

1. Read the signed `semantics.md`. Every statement in it must be true of this view.
2. Write the body in `products/<product>/sql/<model>.sql` using `{{ ref('model') }}` for
   inputs and `{{ var('name') }}` for variables. Name columns from the glossary.
3. Enforce exclusion rules in the view, never in the consumer.
4. Declare grain, history semantics and materialisation in the manifest; dpf generates the
   grain test and makes the model depend on every reject gate.

## Must not

- Introduce a rule that is not in the TDD. If one is missing, raise a gap.
