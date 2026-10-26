---
id: ADR-016
title: Prototype fast-path, environment overrides, and stateful safeguards
status: accepted
date: '2026-10-26'
scope: platform
decides: lifecycle
---

# ADR-016: Prototype fast-path, environment overrides, and stateful safeguards

## Decision

1. **Prototype fast-path (`status: prototype`, `dpf proto init|promote`, `--gate proto`)**: Engineers may scaffold and iterate on a data product's SQL and pipeline logic without authoring a BRD, TDD, or sign-off upfront. Prototype products validate structure, design rules, and in-memory code generation at `--gate proto`, but are blocked from passing G0 or G1 until promoted via `dpf proto promote`.
2. **Default `prevent_destroy = true`**: Stateful Terraform resources (BigQuery datasets, control tables, policy tag taxonomies, policy tags, and sharing exchanges) emit `lifecycle { prevent_destroy = true }` by default, and `false` when `status: prototype` or overridden via `deployment.prevent_destroy`.
3. **Environment overrides (`deployment.environments`)**: A single `product.yaml` may declare per-environment overrides (`dev`, `test`, `prod`) for `gcp_project`, `dataset_prefix`, `prevent_destroy`, `enforce_policy_tags`, `schedules_enabled`, and IAM `principals`, selected via `dpf generate --env <env>` and `dpf test run --live --env <env>`.
4. **Configurable quarantine thresholds**: Quality policies support `max_reject_pct`, `warn_reject_pct`, and `max_reject_rows` alongside `gate_behaviour: warn | block` so teams can filter bad rows into `<stg>_rejects` while continuing downstream refreshes within a tolerated threshold.
5. **BQML and versioned BI semantic layer**: The `direct` pack supports `ml_model` (`bqml_model`) and `ml_prediction` roles across Dataform and dbt, and `semantic_layer` generates versioned `semantic-layer.v1` definitions for Cube, MetricFlow, AtScale, and OSI bound to `artefact_digest`.

## Consequences

Teams can prototype rapidly in dev sandboxes (`prevent_destroy = false`, `enforce_policy_tags = false`) while production builds enforce full G0–G4 governance, dynamic data masking, and destruction safeguards.
