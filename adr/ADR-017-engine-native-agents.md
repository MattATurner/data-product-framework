---
id: ADR-017
title: Engine-native agents as bounded leaf workers
status: accepted
date: '2026-11-03'
scope: platform
decides: agent_integration
---

# ADR-017: Engine-native agents as bounded leaf workers

## Decision

1. **DPF retains design authority and deterministic rendering.** Engine-native AI agents—such as the BigQuery and Dataform Data Engineering Agent (`geminidataanalytics.googleapis.com` A2A API)—never own `product.yaml`, modelling choices, or `generated/` artefacts. Structural generation (`dpf generate`) remains 100% deterministic and offline so `MANIFEST.json` build digests, `tests/golden/` snapshots, and cross-plane coordination (SQLX, Terraform, policy tags, Knowledge Catalog quality scans, semantic layers, and G4 test specs) stay atomic.
2. **Tier-3 leaf worker scope (`data-engineering-agent-api`).** Dataform's Data Engineering Agent is registered at Tier 3 (`managed_agent`) with capabilities strictly disjoint from `artefact_generation` and `dataform_workflow_invocation`:
   - drafting or optimising engine-neutral SQL bodies saved back to `products/<id>/sql/*.sql` (`sql_wrangling`);
   - interactive sandbox prototyping imported via `dpf proto import-dataform` into `status: prototype` products;
   - diagnosing failed Dataform workflow invocations and proposing fixes via OpenSpec changes (`pipeline_troubleshooting`).
3. **Anti-drift repository and release guardrails.** The Dataform adapter emits a deterministic `dataform/GEMINI.md` agent instruction file naming the product's grain contracts and forbidding direct edits to `definitions/` or silent `WHERE` row drops in staging. Non-prototype Terraform release configurations disable scheduled auto-compilation of `main` (`dataform_release_schedule = ""`) so unreviewed console workspace commits cannot auto-release into production.

## Consequences

Teams gain live-schema SQL wrangling, BigQuery Studio prototype intake, and execution-log diagnosis from Dataform's native agent without sacrificing engine neutrality (`dataform` / `dbt`), quarantine integrity, or cryptographic build-to-evidence traceability.
