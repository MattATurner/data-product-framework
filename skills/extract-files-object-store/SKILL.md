---
skill_id: extract-files-object-store
implements: extract-incremental-capture
consumes: source-binding.v1
produces: landing-manifest.v1
tool_tier: 4
tool: gcloud_storage
gcp: [Cloud Storage, Storage Transfer Service, BigQuery Data Transfer Service]
---

# Extract from object storage

CSV, JSON, Parquet, Avro or ORC arriving in a bucket.

## Steps

1. Discover new objects since the watermark. Prefer a manifest or event notification
   over listing a whole prefix.
2. Validate the file against the expected schema fingerprint.
3. Classify drift: additive passes, breaking quarantines and alerts.
4. Emit `landing-manifest.v1` with row and byte counts, checksum and watermark bounds.

## Must

- Never advance the watermark on partial failure.
- Treat the file as immutable; re-processing must be idempotent.
