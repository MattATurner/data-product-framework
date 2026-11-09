---
id: ADR-004
title: CDC apply strategy
status: accepted
date: '2026-09-09'
scope: platform
decides: capture
---

# ADR-004: CDC apply strategy

## Decision

The apply strategy is decided per entity in the TDD, driven by the BRD's history requirement: native current-state replication where only current state is needed; land the full change stream and resolve in staging where history is required.

## Consequences

History requirements, not engineering habit, decide how changes are applied.
