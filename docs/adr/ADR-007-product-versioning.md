---
id: ADR-007
title: Product versioning
status: accepted
date: '2026-09-09'
scope: platform
decides: versioning
---

# ADR-007: Product versioning

## Decision

Semver on data-product.v1. A breaking output-port change or a grain change needs a major version and a deprecation window, enforced at publication.

## Consequences

Grain changes also invalidate the semantics signature (semantic digest).
