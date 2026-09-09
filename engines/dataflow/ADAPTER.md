---
engine_id: dataflow
status: supported for streaming-capable roles
tool_tier: 4
tool: dataflow_api
---

# Dataflow (Beam) adapter

For genuine streaming: sub-minute latency, windowed or stateful logic.

**Streaming is a different execution model, not a SQL dialect swap.** Roles requiring
durable history (Kimball SCD2, Data Vault satellites) are *not* declared supported
unless the pack ships an explicit streaming variant.

## Typical shape

Dataflow handles streaming ingest and enrichment, landing into a raw or current-state
table; Dataform builds the modelled layers on top. Mixing engines across layers within
one product is supported and normal.

**Not yet implemented.** Scaffold only.
