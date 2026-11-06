---
name: transform-raw-to-staging
description: Conform raw rows into a typed, deduplicated staging model and quarantine unusable rows to
  a reject relation with a reason, blocking publication while any exist. Use for every staging model;
  no methodology applies here.
metadata:
  dpf:
    skill_id: transform-raw-to-staging
    stage: stage
    scope: model
    implements: conform-staging
    consumes:
    - raw-table.v1
    produces:
    - staging-model.v1
    selects_when:
      model.role: staging
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Conform raw into staging

Typed, deduplicated, house-standard rows. **No methodology applies here.**

## What you author

Only the typed projection, in `products/<product>/sql/<model>.sql`: explicit casts and
business names, reading raw with `{{ ref('raw_<entity>') }}`. Read the raw schema through
the BigQuery MCP server; do not guess it. For complex messy-data wrangling or BigQuery AI/ML
projections on Dataform projects, you may delegate draft SQL authoring to the tier-3
`data-engineering-agent-api` (ADR-017), saving the resulting query back to
`products/<product>/sql/<model>.sql` in engine-neutral `{{ ref('...') }}` syntax without
top-level `WHERE` or `QUALIFY` filters.

## What dpf generates from the manifest

| Relation | Purpose |
|---|---|
| `<model>__candidates` | typed body, latest row per `natural_key` by `dedupe_order`, plus `_reject_reason` |
| `<model>` | candidates with no reject reason |
| `<model>_rejects` | quarantined rows with the failing rule id as the reason |
| `<model>_history` | typed rows deduplicated on natural key and change time (only when a Type 2 dimension reads it) |
| `assert_<model>_no_rejects` | blocking check; every gold model depends on it |

Rules with `on_fail: quarantine` in `quality.rules` become reject reasons.

## Must

- Be deterministic: the same raw rows give the same staging rows.
- Never drop a row silently. Unusable rows are quarantined and block publication.
