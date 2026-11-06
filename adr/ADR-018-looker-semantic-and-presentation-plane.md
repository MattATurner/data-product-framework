---
id: ADR-018
title: Looker semantic and presentation plane, and decoupled foundation products
status: accepted
date: 2026-11-05
scope: platform
decides: semantic_layer
---

# ADR-018: Looker semantic and presentation plane, and decoupled foundation products

## Context

Data products frequently deliver executive and operational analytics through Looker
(LookML Views, Explores, and YAML Dashboards), and in practice Looker requests arrive
in two distinct organisational patterns:

1. **Coupled (full-stack data product):** one product team owns source extraction,
   staging/silver/gold transformations, and the Looker Explores and Dashboards that
   present them.
2. **Decoupled (consumer-aligned Looker product over an established foundation):** an
   upstream platform or domain team already operates a BigQuery data foundation (either
   as an upstream DPF product or as pre-existing enterprise warehouse tables), and a
   downstream team needs a governed Looker semantic model and dashboard suite with its
   own BRD, business sign-off, and release cycle—without duplicating raw or staging
   pipelines.

At the same time, hand-maintained LookML projects suffer from three recurring failure
modes:

- **Shadow transformations via Persistent Derived Tables (PDTs):** SQL or native
  `derived_table` blocks with `datagroup_trigger` or `sql_trigger_value` materialize
  tables in Looker scratch datasets outside DPF quarantine gates, lineage, and freshness
  SLOs.
- **Silent symmetric-aggregate fanout:** multi-column grain tables lacking a single
  `primary_key: yes` dimension cause Looker joins to miscount additive measures or fail
  at query time.
- **Presentation drift:** UI-edited dashboards and ad-hoc LookML metric edits diverge
  silently from signed business semantics (`playback.md` / `semantics.md`).

## Decision

1. **Looker is strictly a semantic and presentation plane (no PDTs by default).**
   Generated and imported LookML views bind read-only to BigQuery relations via
   `sql_table_name`. `derived_table`, `sql_trigger_value`, and PDT persistence blocks
   are rejected at G1 and G3 unless the product explicitly sets `looker.allow_pdt: true`
   and cites an ADR with `decides: semantic_layer`. BI query acceleration uses governed
   `gold` rollup models or LookML `aggregate_table` awareness.
2. **Symmetric-aggregate safety is compiled from declared grain.**
   Single-column non-time grains emit `primary_key: yes` directly; compound grains and
   time-keyed grains synthesize a deterministic hidden `_dpf_pk` dimension so Looker
   symmetric aggregates are exact across every Explore join.
3. **Decoupled products bind via `upstream:` without requiring `raw` or `staging`.**
   `product.yaml` may declare `upstream` entries referencing either an existing DPF
   product (`upstream[].product`) or external BigQuery foundation tables
   (`upstream[].foundation`, inline or from `registry/foundations.yaml`). When `upstream`
   is present, `sources`, `layers`, `quality`, and `orchestration` become optional:
   `dpf generate` emits the self-contained LookML repository (or Hub-and-Spoke `+view`
   refinements when `looker.import_views_from` is set), read-only foundation grain
   assertions in `test-spec.json`, and consumption-only IAM in Terraform.
4. **Dashboards are versioned YAML code (`.dashboard.lookml`) with Stephen Few defaults.**
   Dashboards compile from concise declarative `semantic_layer.dashboards` specs (or
   validated `.dashboard.lookml` passthrough files imported via `dpf proto import-looker`)
   enforcing zero-baseline bar/column axes, explicit requirement traceability, and static
   `<view>.<field>` symbol resolution at G3.
5. **Looker MCP (`looker-mcp`) is a bounded Tier-2 leaf worker.**
   `looker-mcp` (MCP Toolbox for Looker) is used for semantic inspection, live G4 query
   verification, operational health checks, and sandbox prototyping imported via
   `dpf proto import-looker`—never inside deterministic `dpf generate`.

## Consequences

- Both full-stack and foundation-decoupled Looker data products pass the same G0–G4
  gates, bind metric semantics into `semantic_digest` for business sign-off, and register
  `looker_explore` and `looker_dashboard` output ports in BigQuery Knowledge Catalog.
- Core `dpf` runtime dependencies remain unchanged (`pyyaml`, `jsonschema`, `referencing`)
  using a built-in deterministic LookML emitter and syntax/symbol verifier.
