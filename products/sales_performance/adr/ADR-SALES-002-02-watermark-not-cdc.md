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

The database is behind corporate NAT with no inbound route, and ARCHIVELOG and supplemental logging are not enabled, so a managed CDC stream cannot reach it. The business accepted hourly freshness (BRD 1.1.0).

## Decision

ora_local is captured by hourly watermark extraction with a 15-minute lookback, not by change data capture.

## Consequences

Deletes at source are not captured; segment history starts at go-live. Review when network connectivity changes; CDC needs no model redesign.
