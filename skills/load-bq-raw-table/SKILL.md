---
name: load-bq-raw-table
description: Declare and evolve append-only raw tables in BigQuery with mandatory lineage columns, and
  reconcile loaded rows against the landing manifest. Use when the raw layer's storage is BigQuery native.
metadata:
  dpf:
    skill_id: load-bq-raw-table
    stage: land
    scope: source
    implements: land-immutable-raw
    consumes:
    - landing-manifest.v1
    produces:
    - raw-table.v1
    selects_when:
      product.layers.raw.storage: bigquery_native
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Land into raw BigQuery tables

Append-only, source-shaped. One table per entity: `raw_<entity>` in the raw dataset.

## Lineage columns (all mandatory)

`_ingest_ts`, `_batch_id`, `_source_system`, `_op`, `_source_pk_hash`

## Steps

1. `dpf generate` emits a raw declaration per entity and the control tables
   (`landing_manifest`, `extract_watermark`, `schema_registry`) in the Terraform module.
2. Additive columns are allowed; breaking changes quarantine the batch.
3. Reconcile the loaded row count against the manifest and fail on mismatch.

## Must

- Append only. No updates, deletes or dedupe here; that is staging's job.
