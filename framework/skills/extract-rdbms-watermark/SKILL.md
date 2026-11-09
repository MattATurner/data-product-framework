---
name: extract-rdbms-watermark
description: Pull changed rows from a relational source that Google Cloud cannot reach, using a watermark
  with lookback, and land them atomically in raw with a persisted landing manifest and schema-drift quarantine.
metadata:
  dpf:
    skill_id: extract-rdbms-watermark
    stage: extract
    scope: source
    implements: extract-incremental-capture
    consumes:
    - source-binding.v1
    produces:
    - landing-manifest.v1
    - raw-table.v1
    selects_when:
      source.engine:
      - oracle
      - postgres
      - mysql
      - sqlserver
      source.capture_mode: watermark
    tool_tier: 5
    tool: bespoke-code
    adr: ADR-015
    inspection_tool: mcp-toolbox-databases
    needs:
    - outbound_batch_extract
    gcp:
    - BigQuery
    - Cloud Logging
---

# Extract from a relational source by watermark

Bespoke code (tool tier 5), justified by **ADR-015**: the source sits behind NAT with no
inbound route, so no managed service can connect to it; an outbound-only job running next
to the database is the only option. Reference implementation:
`examples/sales_performance/extract/extract_oracle.py`.

## Behaviour

1. Read `watermark - lookback_minutes` to now (default lookback 15 minutes) so rows from
   late-committing transactions are not lost. Keep microsecond precision.
2. Derive the batch schema from the cursor; compare with the last accepted schema in the
   control dataset. Additive drift lands and is recorded; breaking drift goes to
   `raw_<entity>__quarantine`, the watermark does not move, and a structured log line
   `dpf_alert: schema_drift_breaking` is emitted.
3. Load into a temporary table, then in **one transaction** append to raw, advance the
   watermark and insert the `landing-manifest.v1` row. A retry never duplicates a batch and
   the watermark never moves without the data.
4. Any failure emits `dpf_alert: extract_failed` and exits non-zero.

## Delivery semantics

At least once into raw; exactly once after staging deduplication on natural key and
source change time.

## Must

- Carry the header marker `# dpf: skill=extract-rdbms-watermark tier=5 adr=ADR-015 requirements=R-..`.
- Never use schema autodetection.
