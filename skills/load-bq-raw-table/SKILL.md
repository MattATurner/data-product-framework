---
skill_id: load-bq-raw-table
implements: land-immutable-raw
consumes: landing-manifest.v1
produces: raw-table.v1
tool_tier: 1
tool: bigquery-mcp
gcp: [BigQuery]
---

# Load into a raw BigQuery table

Append-only, source-shaped, partitioned by ingest date.

## Lineage columns (all mandatory)

`_ingest_ts`, `_batch_id`, `_source_system`, `_op`, `_source_pk_hash`

## Steps

1. Read the manifest.
2. Create or evolve the raw table. Additive columns are allowed; breaking changes
   quarantine the batch.
3. Load with the storage format declared for the raw layer — BigQuery native, Iceberg
   managed table or an external table over GCS Parquet.
4. Partition on `_ingest_date`; cluster on `_source_pk_hash`.
5. Emit `raw-table.v1`.

## Must

- Append only. No updates, no deletes, no dedupe here — that is staging's job.
- Reconcile loaded row count against the manifest and fail on mismatch.
