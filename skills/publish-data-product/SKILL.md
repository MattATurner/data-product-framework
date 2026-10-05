---
name: publish-data-product
description: 'Publish output ports with the right access mechanism: dataset grants or authorized views
  internally, a sharing listing for external consumers. Refuses to publish without signed semantics and
  G4 evidence.'
metadata:
  dpf:
    skill_id: publish-data-product
    stage: publish
    scope: product
    implements: model-consumption-layer
    consumes:
    - data-product.v1
    - test-evidence.v1
    produces: []
    tool_tier: 4
    tool: terraform
    needs:
    - sharing_listing_management
    - terraform_provisioning
    gate: G4
    gcp:
    - BigQuery
    - BigQuery sharing
---

# Publish the data product

1. `dpf check <product> --gate G4` must pass.
2. Apply the generated Terraform module: datasets, grants, policy tags, sharing listing.
3. Tag the product version.

## Version rules

- Semver. A breaking output-port change or a grain change needs a major bump and a
  published deprecation window.
- Refuse to publish when `semantics_signed` is false, when required catalog aspects are
  missing, or when live assumptions exist and status is not `provisional`.
