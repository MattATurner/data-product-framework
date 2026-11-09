---
name: extract-rdbms-cdc
description: Capture inserts, updates and deletes continuously from a reachable relational source with
  a managed change data capture stream into raw. Use when the source has an inbound route and change logging
  enabled.
metadata:
  dpf:
    skill_id: extract-rdbms-cdc
    stage: extract
    scope: source
    implements: extract-incremental-capture
    consumes:
    - source-binding.v1
    produces:
    - landing-manifest.v1
    selects_when:
      source.engine:
      - oracle
      - postgres
      - mysql
      - sqlserver
      source.capture_mode: cdc
    tool_tier: 4
    tool: datastream-api
    inspection_tool: mcp-toolbox-databases
    needs:
    - datastream_stream_management
    gcp:
    - Datastream
    - BigQuery
---

# Capture changes continuously (CDC)

## Preconditions (checked in the feasibility pass)

- An inbound network route from Google Cloud to the database.
- Change logging enabled (for Oracle: ARCHIVELOG, supplemental logging, LogMiner grants).
- The source registry lists `cdc` in `capture.supported_now`; otherwise G1 fails.

## Steps

1. Create the connection profiles and stream (tier 4 API; no MCP option exists yet).
2. Land change records append-only with `_op` set to insert, update or delete.
3. Emit a `landing-manifest.v1` per committed window so staging can reconcile counts.

## Must

- Never apply changes in place in raw; staging resolves the latest state.
