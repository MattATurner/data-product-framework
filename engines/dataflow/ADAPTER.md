# Dataflow (Beam) adapter

Status: **planned**. `adapter.yaml` declares no implemented roles.

For genuine streaming: sub-minute latency, windowed or stateful logic. Streaming is a
different execution model, not a SQL dialect swap. Roles requiring durable history (Type 2
dimensions) will not be declared without an explicit streaming variant.

Typical future shape: Dataflow handles streaming ingest and enrichment into raw or a
current-state table; Dataform builds the modelled layers on top.
