---
id: ADR-SALES-002-02
title: Watermark capture instead of CDC
status: accepted
date: '2026-09-09'
scope: product
product: sales_performance
decides: capture
---

# ADR-SALES-002-02: Watermark capture instead of CDC

## Context

The on-premises PostgreSQL database sits behind corporate NAT with no inbound route from Google Cloud, and `wal_level = logical` / logical replication slots are not enabled, so a managed CDC stream (Datastream) cannot reach it. The business accepted intraday freshness (BRD 1.1.0).

## Decision

`pg_local` is captured by outbound 15-minute watermark extraction (`*/15 * * * *`) with a 15-minute lookback window, not by change data capture.

## Consequences

Deletes at source are not captured; segment history starts at go-live. Review when network connectivity changes; CDC needs no model redesign.
