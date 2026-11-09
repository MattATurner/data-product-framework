---
name: assemble-data-product
description: 'Assemble the versioned data product descriptor from the manifest, sign-off and observability
  policy: ports, grain, service levels, classification and live assumptions. Use before publishing or
  registering.'
metadata:
  dpf:
    skill_id: assemble-data-product
    stage: assemble
    scope: product
    implements: generate-artefacts
    consumes:
    - product-manifest.v1
    - signoff.v1
    produces:
    - data-product.v1
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
---

# Assemble the data product

`dpf generate` writes `generated/<product>/data-product.json` (contract `data-product.v1`).

- `semantics_signed` is true only when `signoff.yaml` matches the current semantic digest.
- Any open BRD question with a recorded assumption forces `status: provisional`.
- Ports carry their model's grain statement so consumers see the grain in the catalog.
