---
skill_id: kimball/design-bus-matrix
implements: model-integration-layer
methodology: kimball
role: dimension
consumes: staging-model.v1
produces: semantic-model.v1
tool_tier: 4
tool: local
---

# Design and maintain the bus matrix

Conformance is a cross-product concern, so it lives in `registry/conformance.yaml`,
never inside one product.

## Steps

1. List the business processes in scope and the dimensions each needs.
2. For each shared dimension, agree one grain, one natural key and one owning domain.
3. Record it in the registry.
4. On any new product, validate its dimension requests against the matrix.

## Must

- Fail G0 when a BRD implies a conformed dimension at a different grain or key, naming
  the owning domain in the conflict report.
- Treat a change to a conformed dimension as a change proposal with cross-product impact
  analysis, never a local edit.
