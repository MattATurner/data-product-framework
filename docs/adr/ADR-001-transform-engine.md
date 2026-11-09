---
id: ADR-001
title: Transform engine
status: accepted
date: '2026-09-09'
scope: platform
decides: engine
---

# ADR-001: Transform engine

## Decision

Engines are pluggable and Dataform is the default. Methodology packs emit semantic models; engine adapters render them. dbt is supported for teams already invested in it; Dataflow (streaming) and Spark (non-SQL escape hatch) are planned. An adapter declares the roles it implements in engines/<engine>/adapter.yaml, and a pack may only list an engine for a role the adapter implements.

## Consequences

Unsupported pairings fail at compose time instead of generating code that compiles and misbehaves.
