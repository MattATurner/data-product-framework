---
skill_id: direct/model-materialisation
implements: model-consumption-layer
methodology: direct
role: materialised_view
consumes: semantic-model.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Decide and apply materialisation

Make view vs materialized view vs table an explicit, recorded decision.

## Decision table

| Option | Choose when | Trade-off |
|---|---|---|
| **View** | Low query volume; freshness matters more than latency; cheap upstream | Full compute on every read; cost scales with consumers |
| **Materialized view** | Repeated aggregation over a stable base; automatic incremental refresh acceptable | SQL restrictions apply — **verify current BigQuery limits at design time** |
| **Table** (scheduled build) | Complex logic, heavy joins, predictable refresh windows | Staleness between runs; storage cost; needs orchestration |
| **Incremental table** | Large volumes with a reliable change signal | Requires a durable watermark and restatement handling |

## Inputs

Driven by BRD answers, not preference:
- freshness need and its justification
- expected query volume and concurrency
- restatement window

## Must

- Record the choice and the citing BRD requirement ids in the TDD.
- Re-verify materialized view restrictions against current documentation before use.
- Where a materialized view cannot express the logic, fall back to a scheduled table and
  say so in the TDD rather than silently degrading freshness.
