---
id: ADR-014
title: Materialisation strategy
status: accepted
date: '2026-09-09'
scope: platform
decides: materialisation
---

# ADR-014: Materialisation strategy

## Decision

View, materialized view, table or incremental table is an explicit TDD decision driven by freshness and expected query volume. Materialized view restrictions are re-verified at design time.

## Consequences

Gold models must declare materialisation; G1 fails otherwise.
