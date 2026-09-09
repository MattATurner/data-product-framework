---
skill_id: transform-raw-to-staging
implements: conform-staging
consumes: raw-table.v1
produces: staging-model.v1
tool_tier: 1
tool: bigquery-mcp
gcp: [BigQuery]
---

# Conform raw into staging

Typed, deduplicated, house-standard rows. **No methodology applies here.**

## Steps

1. Read the raw schema via the BigQuery MCP server; do not hand-write it.
2. Cast explicitly using the TDD type map.
3. Deduplicate on the natural key with the declared strategy.
4. Quarantine rows failing the BRD fitness definition into the reject table with a reason.
5. Assert uniqueness on the natural key.
6. Emit `staging-model.v1`.

## Must

- Be deterministic: same raw partitions in, identical staging out.
- Never drop a row silently.
