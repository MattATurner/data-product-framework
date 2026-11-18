---
id: ADR-SALES-002-01
title: Kimball dimensional model in silver
status: accepted
date: '2026-09-09'
scope: product
product: sales_performance
decides: methodology
---

# ADR-SALES-002-01: Kimball dimensional model in silver

## Context

R-5 and R-6 require figures that agree with Finance and Merchandising (AG-1, AG-2), which needs shared, owned definitions of customer and product. R-4 and R-6 require attributes to keep the value that applied at the time (HB-1 to HB-3), which a view over current-state source data cannot provide.

## Decision

The silver layer uses the kimball pack instead of the direct platform default.

## Consequences

Silver carries Type 2 dimensions registered in the bus matrix. Gold stays direct. Revisit if the reconciliation and history requirements are withdrawn.
