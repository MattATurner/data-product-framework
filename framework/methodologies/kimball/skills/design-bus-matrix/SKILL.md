---
name: design-bus-matrix
description: Design and maintain the bus matrix of conformed dimensions in the registry, and check a product's
  dimensions against it. Use when a Kimball product introduces or reuses a shared dimension.
metadata:
  dpf:
    skill_id: kimball/design-bus-matrix
    stage: design
    scope: product
    implements: model-integration-layer
    methodology: kimball
    consumes:
    - product-manifest.v1
    produces: []
    selects_when:
      product.layers.silver.methodology: kimball
    tool_tier: 4
    tool: dpf-local
    inspection_tool: knowledge-catalog-mcp
    needs:
    - traceability
---

# Design and maintain the bus matrix

Conformance is a cross-product concern, so it lives in `registry/conformance.yaml`, never
inside one product.

## Steps

1. List the business processes in scope and the dimensions each needs.
2. For each shared dimension agree one grain, one natural key and one owning domain.
3. Record it in the registry; list consuming products in `used_by`.
4. Declare `conformed_as` on the product's dimension models. Rule `conformance-respected`
   fails G1 on a grain or key conflict and names the owning domain.

## Must

- Treat a change to a conformed dimension as an OpenSpec change with cross-product impact
  analysis, never a local edit.
