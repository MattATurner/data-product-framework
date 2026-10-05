---
id: ADR-015
title: Outbound-only watermark extractor
status: accepted
date: '2026-10-02'
scope: platform
decides: capture
---

# ADR-015: Outbound-only watermark extractor

## Decision

Where a relational source has no inbound route from Google Cloud, capture runs as bespoke code next to the database (tool tier 5): watermark with lookback, explicit schemas, drift classification with quarantine, and one transaction that appends raw rows, advances the watermark and persists the landing manifest. No MCP server or managed service covers scheduled outbound bulk extraction (registry capability outbound_batch_extract).

## Consequences

The code carries a dpf header marker naming the skill, tier and this ADR; dpf lint fails tier-5 code without it. Revisit when private connectivity allows managed CDC.
