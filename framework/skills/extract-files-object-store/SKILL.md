---
name: extract-files-object-store
description: Pick up files dropped in object storage (CSV, JSON, Parquet, Avro, ORC) since the last watermark,
  validate their schema fingerprint and emit a landing manifest. Use for file-drop sources.
metadata:
  dpf:
    skill_id: extract-files-object-store
    stage: extract
    scope: source
    implements: extract-incremental-capture
    consumes:
    - source-binding.v1
    produces:
    - landing-manifest.v1
    selects_when:
      source.engine:
      - gcs_objects
      - s3_objects
      - azure_blob
    tool_tier: 4
    tool: gcloud-storage
    needs:
    - object_listing
    - object_copy
    gcp:
    - Cloud Storage
---

# Extract from object storage

## Steps

1. Discover new objects since the watermark. Prefer a manifest or event notification over
   listing a whole prefix.
2. Validate each file against the expected schema fingerprint.
3. Classify drift: additive passes, breaking quarantines and alerts.
4. Emit `landing-manifest.v1` with row and byte counts, checksum and watermark bounds.

## Must

- Never advance the watermark on partial failure.
- Treat files as immutable; reprocessing must be idempotent.
