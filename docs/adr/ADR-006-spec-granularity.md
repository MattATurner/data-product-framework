---
id: ADR-006
title: Spec granularity
status: accepted
date: '2026-09-09'
scope: platform
decides: specification
---

# ADR-006: Spec granularity

## Decision

One platform capability per behaviour cluster, not per skill. Several skills may implement one capability (for example three extract skills implement extract-incremental-capture).

## Consequences

Skills are selected by selects_when; capabilities stay stable as skills are added.
