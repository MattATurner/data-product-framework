---
id: ADR-013
title: Grain is derived, then confirmed
status: accepted
date: '2026-09-09'
scope: platform
decides: grain
---

# ADR-013: Grain is derived, then confirmed

## Decision

Grain, history type, conformance and additivity are derived in the TDD from business answers, played back in semantics.md, and signed before build. The signature is bound to a digest of semantics.md and every model's grain and history declaration.

## Consequences

Changing any of them invalidates signoff.yaml and fails G1 until re-signed.
