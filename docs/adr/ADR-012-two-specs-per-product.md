---
id: ADR-012
title: Two specs per product
status: accepted
date: '2026-09-09'
scope: platform
decides: specification
---

# ADR-012: Two specs per product

## Decision

The BRD and TDD are separate, independently versioned and approved specs, bound by Satisfies: BRD-...@<version>. A BRD version bump marks the TDD stale.

## Consequences

TDD-only changes ship without business re-approval unless they change the semantic digest.
