---
name: bind-upstream-foundation
description: Bind a decoupled consumption or semantic data product to an upstream DPF product or external BigQuery foundation, verifying schema, grain columns, surrogate keys and freshness SLAs before rendering downstream LookML or thin views.
metadata:
  dpf:
    skill_id: bind-upstream-foundation
    stage: integrate
    scope: upstream
    implements: model-consumption-layer
    consumes:
    - foundation-binding.v1
    produces:
    - semantic-model.v1
    tool_tier: 1
    tool: bigquery-mcp
    adr: ADR-018
    gcp:
    - BigQuery
    needs:
    - bigquery_metadata
---

# Bind upstream foundation

Use when a data product declares `upstream:` instead of ingesting raw sources from scratch — either
consuming output ports of an existing DPF data product (`upstream[].product`) or binding directly to
pre-existing external BigQuery tables (`upstream[].foundation` and `registry/foundations.yaml`).

## Modes

| Mode | Declaration | Resolution |
|---|---|---|
| Existing DPF product | `upstream: [{product: <id>, min_version: 1.0.0, models: [...]}]` | Imports grain, surrogate key, attributes, output columns and policy tags from the upstream `product.yaml` |
| External BigQuery foundation | `upstream: [{foundation: <id>, gcp_project: ..., dataset: ..., tables: [...]}]` | Validates grain columns, surrogate keys, measures and freshness against `foundation-binding.v1` and BigQuery `INFORMATION_SCHEMA.COLUMNS` via `bigquery-mcp` |

## Checks enforced at G1 and G4

1. Upstream `staging` models cannot be bound across product boundaries (`silver` and `gold` only).
2. Downstream freshness expectations cannot promise a tighter `max_staleness` than the upstream product or foundation provides.
3. Every external foundation table emits automated `grain:<name>` and `grain_not_null:<name>` SQL test cases in `test-spec.json` so `G4` proves the upstream grain holds on real data before Looker dashboards go live.
