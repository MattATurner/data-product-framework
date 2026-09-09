---
skill_id: publish-data-product
implements: model-consumption-layer
consumes: data-product.v1
produces: data-product.v1
tool_tier: 1
tool: bigquery-mcp
gcp: [BigQuery, BigQuery sharing, IAM]
---

# Publish the data product

## Steps

1. Create the versioned product dataset and output ports.
2. Choose the access mechanism: authorized view or dataset for internal consumers,
   **BigQuery sharing** listing for consumers outside the organisation.
3. Apply IAM from the BRD's access answers.
4. Tag the version.

## Version rules

- Semver. A breaking output-port change **or a grain change** requires a major bump plus
  a published deprecation window.
- Refuse to publish when `semantics_signed` is false, or when required catalog aspects
  are missing, or when live assumptions exist and status is not `provisional`.
