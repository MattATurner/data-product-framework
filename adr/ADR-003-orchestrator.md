---
id: ADR-003
title: Orchestrator
status: accepted
date: '2026-09-09'
scope: platform
decides: orchestration
---

# ADR-003: Orchestrator

## Decision

Dataform release and workflow configurations orchestrate pure-SQL chains. Cloud Composer is used when non-BigQuery steps must be sequenced. Workflows only for trivial cases.

## Consequences

Workflow configurations are generated from orchestration.schedules in the manifest.
