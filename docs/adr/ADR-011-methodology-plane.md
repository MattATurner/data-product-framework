---
id: ADR-011
title: Methodology plane
status: accepted
date: '2026-09-09'
scope: platform
decides: methodology
---

# ADR-011: Methodology plane

## Decision

Modelling methodology is a pluggable pack selected per layer. Every methodology is optional: direct (business views over the platform staging layer) is the default, and a heavier methodology must be justified by a BRD signal and recorded in a product ADR.

## Consequences

dpf recommends a methodology from BRD signals; a departure from the default without an ADR fails G1.
