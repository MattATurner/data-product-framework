---
id: ADR-002
title: Storage format
status: accepted
date: '2026-09-09'
scope: platform
decides: storage
---

# ADR-002: Storage format

## Decision

Storage is an option set chosen per layer: BigQuery native (default), Apache Iceberg managed tables, Cloud Storage Parquet with external tables, object tables for unstructured data, and cross-cloud connections where data cannot move. The choice is driven by residency, multi-engine access and cost signals in the BRD.

## Consequences

Raw storage drives land-skill selection (load-bq-raw-table versus load-gcs-raw-zone).
