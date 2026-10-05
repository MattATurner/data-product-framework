---
name: orchestrate-pipeline
description: 'Schedule the generated pipeline from the manifest''s orchestration schedules: release and
  workflow configurations per schedule, blocking on failed checks, honouring the restatement window. Use
  when deploying a product.'
metadata:
  dpf:
    skill_id: orchestrate-pipeline
    stage: orchestrate
    scope: product
    implements: compose-pipeline
    consumes:
    - product-manifest.v1
    produces: []
    tool_tier: 4
    tool: terraform
    needs:
    - terraform_provisioning
    - dataform_workflow_invocation
    gcp:
    - Dataform
---

# Orchestrate

| Use | When |
|---|---|
| Dataform release and workflow configs | Pure BigQuery SQL chains (generated in the Terraform module) |
| Cloud Composer | Non-BigQuery steps must be sequenced |

## Must

- Take cadence from the BRD's freshness answer via `orchestration.schedules`.
- Exclude acceptance tests (tag `acceptance`) from scheduled runs.
- Make every run idempotent and stop on a blocking check; never publish and warn.
