---
skill_id: load-gcs-raw-zone
implements: land-immutable-raw
consumes: landing-manifest.v1
produces: landing-manifest.v1
tool_tier: 4
tool: terraform
gcp: [Cloud Storage]
---

# Land into the immutable raw zone

## Layout

```
raw/<source_system>/<entity>/ingest_date=YYYY-MM-DD/batch_id=<id>/
```

## Must

- Write once. Never update or delete a landed object.
- Write a manifest alongside every batch; an unmanifested batch is not consumable.
- Apply lifecycle and retention from the BRD's retention answer.
