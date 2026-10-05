---
name: load-gcs-raw-zone
description: Land batches as immutable objects in a Cloud Storage raw zone with a manifest beside each
  batch, exposed to BigQuery as external or Iceberg tables. Use only when the raw layer's storage is object
  storage.
metadata:
  dpf:
    skill_id: load-gcs-raw-zone
    stage: land
    scope: source
    implements: land-immutable-raw
    consumes:
    - landing-manifest.v1
    produces:
    - raw-table.v1
    selects_when:
      product.layers.raw.storage:
      - gcs_parquet_external
      - iceberg_managed
    tool_tier: 4
    tool: terraform
    needs:
    - terraform_provisioning
    gcp:
    - Cloud Storage
    - BigQuery
---

# Land into the object-storage raw zone

## Layout

```
raw/<source_system>/<entity>/ingest_date=YYYY-MM-DD/batch_id=<id>/
```

## Must

- Write once. Never update or delete a landed object.
- Write a manifest beside every batch; an unmanifested batch is not consumable.
- Apply lifecycle and retention from the BRD's retention answer.
