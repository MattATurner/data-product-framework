# Project context — Data Product Framework

## What this repository is

The behaviour contract for a data platform, plus the skills that generate the Google
Cloud artefacts satisfying it. Specs are the source of truth; generated code is
disposable output.

## Platform context

| Setting | Value |
|---|---|
| Cloud | Google Cloud |
| Warehouse | BigQuery |
| Default transform engine | Dataform (pluggable — see ADR-001) |
| Default storage | BigQuery native (option set — see ADR-002) |
| Default methodology | `direct` (optional and pluggable — see ADR-011) |
| Catalog | Knowledge Catalog |
| Orchestration | Dataform workflow configs; Cloud Composer for cross-service |
| Region | *(set per deployment — see `registry/platform-defaults.yaml`)* |

## Product naming

Use current Google Cloud names in prose. CLI and IAM identifiers keep their legacy
strings verbatim.

| Current | Formerly |
|---|---|
| Knowledge Catalog | Dataplex Universal Catalog / Data Catalog |
| Lakehouse; Lakehouse runtime catalog | BigLake; BigLake metastore |
| Apache Iceberg managed tables | BigLake tables for Apache Iceberg |
| BigQuery sharing | Analytics Hub |
| Managed Service for Apache Spark | Dataproc Serverless |
| Cross-cloud connections | BigQuery Omni |

`tools/dpf validate` lints for retired names. Re-verify against live docs before any
customer-facing use.

## Non-negotiables

1. The BRD is business-authored and contains no modelling vocabulary.
2. Every fact and view declares a grain, and the grain assertion is generated from it.
3. `semantics.md` is signed by the business before build.
4. Every design decision cites a BRD requirement ID.
5. Prefer MCP servers and existing agents over bespoke integration code.
