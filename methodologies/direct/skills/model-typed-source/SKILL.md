---
skill_id: direct/model-typed-source
implements: model-integration-layer
methodology: direct
role: typed_source
consumes: raw-table.v1
produces: semantic-model.v1
tool_tier: 1
tool: bigquery-mcp
---

# Type and rename a raw table

Turn a source-shaped raw table into typed, business-named rows. No restructuring.

## Inputs

- A `raw-table.v1` contract.
- The TDD's type map, natural key and dedupe strategy.

## Steps

1. **Inspect the raw schema** using the BigQuery MCP server (tier 1). Do not hand-write
   a schema; read it.
2. Apply the TDD type map. Cast explicitly — never rely on implicit coercion.
3. Rename columns to business language, using `registry/glossary.yaml` where a term exists.
4. Deduplicate on the natural key using the declared strategy.
5. Route rows failing the BRD's fitness definition to the reject table with a reason.
6. Emit `semantic-model.v1` with grain statement, grain columns and history semantics.

## Must

- Generate a uniqueness assertion from `grain_columns`.
- Never drop a row silently; quarantine it.
- Keep lineage columns intact.

## Must not

- Restructure, aggregate or join. That is the business view's job.
