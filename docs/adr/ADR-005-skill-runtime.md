---
id: ADR-005
title: Skill runtime
status: accepted
date: '2026-09-09'
scope: platform
decides: runtime
---

# ADR-005: Skill runtime

## Decision

Skills are Agent Skills (markdown front-matter plus instructions); the deterministic generators are a plain Python package (dpf) so CI runs them headless.

## Consequences

No skill only works inside a chat loop. dpf is the tier-4 tool most skills name.
