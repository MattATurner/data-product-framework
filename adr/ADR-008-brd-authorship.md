---
id: ADR-008
title: BRD authorship and ownership
status: accepted
date: '2026-09-09'
scope: platform
decides: ownership
---

# ADR-008: BRD authorship and ownership

## Decision

BRDs are authored by a business SME or analyst, facilitated by a data engineer and drafted by an agent from a structured interview. BRDs contain no modelling vocabulary.

## Consequences

G0 fails a BRD that uses modelling or technology vocabulary (registry/brd-vocabulary.yaml).
